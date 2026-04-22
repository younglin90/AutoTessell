"""Preprocessor 파이프라인.

포맷 변환(Step 0) → L1 수리 → L2 리메쉬 → L3 AI fix 순서로 점진적 처리.
각 단계 후 gate 검사(watertight + manifold)를 통과하면 다음 단계를 건너뛴다.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import trimesh

from core.preprocessor.converter import FormatConverter
from core.preprocessor.remesh import SurfaceRemesher
from core.preprocessor.repair import SurfaceRepairer, gate_check
from core.schemas import (
    FinalValidation,
    GeometryReport,
    PreprocessedReport,
    PreprocessingSummary,
    PreprocessStep,
)
from core.utils.logging import get_logger

log = get_logger(__name__)


class Preprocessor:
    """전처리 파이프라인 오케스트레이터.

    Analyzer 출력(GeometryReport)을 기반으로 포맷 변환·수리·리메쉬를
    L1 → L2 → L3 순서로 수행하고, preprocessed.stl + PreprocessedReport를 반환한다.
    """

    def __init__(self) -> None:
        self._converter = FormatConverter()
        self._repairer = SurfaceRepairer()
        self._remesher = SurfaceRemesher()

    def run(
        self,
        input_path: Path,
        geometry_report: GeometryReport,
        output_dir: Path,
        *,
        tier_hint: str | None = None,
        no_repair: bool = False,
        surface_remesh: bool = False,
        remesh_target_faces: int | None = None,
        remesh_engine: str = "auto",
        allow_ai_fallback: bool = False,
        prefer_native: bool = False,
    ) -> tuple[Path, PreprocessedReport]:
        """전처리 파이프라인 실행.

        L1 → L2 → L3 점진적 표면 품질 개선 파이프라인.

        Args:
            input_path: 원본 입력 파일 경로.
            geometry_report: Analyzer 출력 GeometryReport.
            output_dir: 출력 디렉터리.
            tier_hint: Tier 힌트 ("netgen"이면 STEP/IGES 패스스루).
            no_repair: True이면 warning 수리 건너뜀 (critical은 수행).
            surface_remesh: True이면 gate 성공 여부와 무관하게 강제 L2 리메쉬.
            remesh_target_faces: 리메쉬 목표 삼각형 수 (None이면 자동).
            remesh_engine: L2 리메쉬 엔진 선택 (auto/vorpalite/pyacvd/pymeshlab/quadwild/none).
            allow_ai_fallback: True이면 L3 AI fix 시도 허용.

        Returns:
            (preprocessed.stl 경로, PreprocessedReport) 튜플.
        """
        pipeline_start = time.perf_counter()
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        steps_performed: list[PreprocessStep] = []
        suffix = input_path.suffix.lower()
        is_cad = suffix in {".step", ".stp", ".iges", ".igs", ".brep"}

        # ------------------------------------------------------------------
        # Tier 0.5 (Netgen) 패스스루: STEP/IGES 원본 그대로 전달
        # ------------------------------------------------------------------
        if tier_hint == "netgen" and is_cad:
            log.info(
                "passthrough_cad",
                reason="tier_hint=netgen",
                path=str(input_path),
            )
            total_time = time.perf_counter() - pipeline_start
            report = self._build_report(
                input_path=input_path,
                input_format=suffix.lstrip(".").upper(),
                output_path=input_path,
                passthrough_cad=True,
                steps=steps_performed,
                total_time=total_time,
                mesh=None,
                surface_quality_level=None,
            )
            return input_path, report

        # ------------------------------------------------------------------
        # Step 0: 포맷 변환
        # ------------------------------------------------------------------
        current_path, conv_step = self._step_convert(
            input_path, output_dir, is_cad, tier_hint
        )
        if conv_step is not None:
            steps_performed.append(conv_step)

        # ------------------------------------------------------------------
        # 메쉬 로딩
        # ------------------------------------------------------------------
        from core.analyzer.file_reader import load_mesh

        mesh = load_mesh(current_path)
        is_open_boundary = not mesh.is_watertight and not is_cad
        log.info(
            "mesh_loaded",
            path=str(current_path),
            num_faces=len(mesh.faces),
            is_watertight=mesh.is_watertight,
            is_open_boundary=is_open_boundary,
        )

        # ------------------------------------------------------------------
        # L1: 표면 수리 (Repair)
        # ------------------------------------------------------------------
        surface_quality_level: str | None = None
        force_l2_for_open = is_open_boundary and not surface_remesh

        if not no_repair:
            mesh, l1_passed, l1_record = self._l1_repair(
                mesh, geometry_report, prefer_native=prefer_native,
            )
            steps_performed.append(PreprocessStep(**l1_record))

            if l1_passed and not surface_remesh and not force_l2_for_open:
                surface_quality_level = "l1_repair"
                log.info("l1_gate_passed", surface_quality_level=surface_quality_level)
            else:
                # ----------------------------------------------------------
                # L2: 표면 리메쉬 (Remesh)
                # ----------------------------------------------------------
                if not l1_passed:
                    log.info("l1_gate_failed", reason="proceeding to L2")
                elif force_l2_for_open:
                    log.info("l2_forced", reason="open_boundary_detected")
                else:
                    log.info("l2_forced", reason="surface_remesh=True")

                mesh, l2_passed, l2_record = self._l2_remesh(
                    mesh,
                    remesh_target_faces,
                    remesh_engine=remesh_engine,
                    prefer_native=prefer_native,
                )
                steps_performed.append(PreprocessStep(**l2_record))

                if l2_passed:
                    surface_quality_level = "l2_remesh"
                    log.info("l2_gate_passed", surface_quality_level=surface_quality_level)
                else:
                    # ----------------------------------------------------------
                    # L3: AI fix (최후 수단)
                    # ----------------------------------------------------------
                    log.info("l2_gate_failed", reason="proceeding to L3")
                    mesh, l3_passed, l3_record = self._l3_ai_fix(
                        mesh, allow_ai_fallback=allow_ai_fallback
                    )
                    if l3_record is not None:
                        steps_performed.append(PreprocessStep(**l3_record))

                    surface_quality_level = "l3_ai"
                    if not l3_passed:
                        log.warning(
                            "l3_gate_failed",
                            msg="모든 surface 수리 단계 실패 — Generator에서 TetWild 강제",
                        )
                    else:
                        log.info("l3_gate_passed", surface_quality_level=surface_quality_level)
        else:
            log.info("repair_skipped", reason="no_repair=True")
            # no_repair 모드: L2 강제 리메쉬만 처리
            if surface_remesh or self._remesher.should_remesh(geometry_report):
                mesh, l2_passed, l2_record = self._l2_remesh(
                    mesh,
                    remesh_target_faces,
                    remesh_engine=remesh_engine,
                    prefer_native=prefer_native,
                )
                steps_performed.append(PreprocessStep(**l2_record))
                surface_quality_level = "l2_remesh" if l2_passed else None
            else:
                surface_quality_level = None  # 수리/리메쉬 미수행

        # ------------------------------------------------------------------
        # 최종 검증 및 저장
        # ------------------------------------------------------------------
        mesh = self._final_validate(mesh)
        out_stl = output_dir / "preprocessed.stl"
        mesh.export(str(out_stl))
        log.info("preprocessed_saved", path=str(out_stl))

        total_time = time.perf_counter() - pipeline_start
        report = self._build_report(
            input_path=input_path,
            input_format=suffix.lstrip(".").upper() or "STL",
            output_path=out_stl,
            passthrough_cad=False,
            steps=steps_performed,
            total_time=total_time,
            mesh=mesh,
            surface_quality_level=surface_quality_level,
        )
        return out_stl, report

    # ------------------------------------------------------------------
    # L1 / L2 / L3 단계 메서드
    # ------------------------------------------------------------------

    def _l1_repair_native(
        self,
        mesh: "trimesh.Trimesh",
        issues: list,
    ) -> tuple["trimesh.Trimesh", bool, dict]:
        """v0.4: 자체 native_repair 기반 L1 (pymeshfix/trimesh 없이)."""
        import numpy as np  # noqa: PLC0415
        import trimesh as _tm  # noqa: PLC0415
        from core.preprocessor.native_repair import run_native_repair  # noqa: PLC0415

        t0 = time.perf_counter()
        V = np.asarray(mesh.vertices, dtype=np.float64)
        F = np.asarray(mesh.faces, dtype=np.int64)
        res = run_native_repair(V, F)
        elapsed = time.perf_counter() - t0
        new_mesh = _tm.Trimesh(vertices=res.vertices, faces=res.faces, process=False)
        passed = bool(res.watertight and res.manifold)
        step_record = {
            "step": "l1_repair",
            "method": "native_repair",
            "params": {"steps": [s["step"] for s in res.steps]},
            "input_faces": int(F.shape[0]),
            "output_faces": int(res.faces.shape[0]),
            "time_seconds": round(elapsed, 4),
            "gate_passed": passed,
        }
        log.info(
            "l1_native_repair_done",
            watertight=res.watertight, manifold=res.manifold,
            input_faces=F.shape[0], output_faces=res.faces.shape[0],
        )
        return new_mesh, passed, step_record

    def _l1_repair(
        self,
        mesh: trimesh.Trimesh,
        geometry_report: GeometryReport,
        *,
        prefer_native: bool = False,
    ) -> tuple[trimesh.Trimesh, bool, dict[str, Any]]:
        """L1 표면 수리 수행.

        geometry_report의 issues를 참조하여 pymeshfix + trimesh 수리를 수행한다.
        수리 후 gate 검사를 실행한다.

        Returns:
            (수리된 메쉬, gate_passed, step_record) 튜플.
            수리 불필요 시 gate 검사만 수행하고 빈 step_record 반환.
        """
        from core.schemas import Severity

        issues = geometry_report.issues
        needs = any(
            i.severity in (Severity.CRITICAL, Severity.WARNING) for i in issues
        )

        if not needs:
            # 수리 불필요 → gate 검사만
            passed = gate_check(mesh)
            log.info("l1_repair_skipped", reason="no issues", gate_passed=passed)
            step_record = {
                "step": "l1_repair",
                "method": "skipped",
                "params": {"reason": "no critical/warning issues"},
                "input_faces": len(mesh.faces),
                "output_faces": len(mesh.faces),
                "time_seconds": 0.0,
                "gate_passed": passed,
            }
            return mesh, passed, step_record

        if prefer_native:
            return self._l1_repair_native(mesh, issues)
        return self._repairer.repair_l1(mesh, issues)

    def _l2_remesh(
        self,
        mesh: trimesh.Trimesh,
        target_faces: int | None,
        *,
        remesh_engine: str = "auto",
        prefer_native: bool = False,
    ) -> tuple[trimesh.Trimesh, bool, dict[str, Any]]:
        """L2 표면 리메쉬 수행.

        기본: pyACVD + 선택적 pymeshlab isotropic remeshing (SurfaceRemesher).
        prefer_native=True: 자체 native_remesh.isotropic_remesh (pyACVD 없이).

        리메쉬 후 gate 검사를 실행한다.

        Returns:
            (리메쉬된 메쉬, gate_passed, step_record) 튜플.
        """
        if prefer_native:
            return self._l2_remesh_native(mesh, target_faces)
        return self._remesher.remesh_l2(
            mesh,
            target_faces=target_faces,
            remesh_engine=remesh_engine,
        )

    def _l2_remesh_native(
        self,
        mesh: trimesh.Trimesh,
        target_faces: int | None,
    ) -> tuple[trimesh.Trimesh, bool, dict[str, Any]]:
        """v0.4: 자체 isotropic_remesh 로 L2 수행 (pyACVD/pymeshlab 없이)."""
        import time as _time  # noqa: PLC0415

        import numpy as np  # noqa: PLC0415
        import trimesh as _tm  # noqa: PLC0415
        from core.preprocessor.native_remesh import isotropic_remesh  # noqa: PLC0415
        from core.preprocessor.repair import gate_check as _gate  # noqa: PLC0415

        t0 = _time.perf_counter()
        V = np.asarray(mesh.vertices, dtype=np.float64)
        F = np.asarray(mesh.faces, dtype=np.int64)
        # target edge length — bbox / sqrt(target_faces) 근사
        bmin = V.min(axis=0); bmax = V.max(axis=0)
        diag = float(np.linalg.norm(bmax - bmin))
        if target_faces and target_faces > 0:
            target_edge = diag / (float(target_faces) ** 0.5) * 1.5
        else:
            # 기존 edge 평균 유지
            e01 = np.linalg.norm(V[F[:, 1]] - V[F[:, 0]], axis=1)
            target_edge = float(e01.mean()) if e01.size else diag / 50
        V2, F2 = isotropic_remesh(
            V, F, target_edge_length=float(target_edge), n_iter=3,
        )
        elapsed = _time.perf_counter() - t0
        new_mesh = _tm.Trimesh(vertices=V2, faces=F2, process=False)
        passed = bool(_gate(new_mesh))
        step_record = {
            "step": "l2_remesh",
            "method": "native_isotropic",
            "params": {
                "target_edge": float(target_edge),
                "n_iter": 3,
            },
            "input_faces": int(F.shape[0]),
            "output_faces": int(F2.shape[0]),
            "time_seconds": round(elapsed, 4),
            "gate_passed": passed,
        }
        log.info(
            "l2_native_remesh_done",
            input_faces=F.shape[0], output_faces=F2.shape[0],
            gate_passed=passed,
        )
        return new_mesh, passed, step_record

    def _l3_ai_fix(
        self,
        mesh: trimesh.Trimesh,
        *,
        allow_ai_fallback: bool = False,
    ) -> tuple[trimesh.Trimesh, bool, dict[str, Any] | None]:
        """L3 AI 표면 재생성 (최후 수단).

        meshgpt-pytorch → MeshAnythingV2 순서로 시도한다.
        GPU 없거나 allow_ai_fallback=False이면 즉시 반환한다.

        Returns:
            (메쉬, gate_passed, step_record 또는 None) 튜플.
            step_record가 None이면 스킵된 것이므로 steps에 추가하지 않는다.
        """
        import time as _time

        step_start = _time.perf_counter()

        if not allow_ai_fallback:
            log.info("l3_ai_skipped", reason="allow_ai_fallback=False")
            passed = gate_check(mesh)
            return mesh, passed, None

        try:
            import torch
            if not torch.cuda.is_available():
                log.warning("l3_ai_skipped", reason="no GPU available (CUDA not found)")
                passed = gate_check(mesh)
                return mesh, passed, None
        except ImportError:
            log.warning("l3_ai_skipped", reason="torch not installed")
            passed = gate_check(mesh)
            return mesh, passed, None

        # L3-A: meshgpt-pytorch (MIT, 우선)
        result_mesh = self._try_meshgpt(mesh)
        if result_mesh is not None and gate_check(result_mesh):
            elapsed = _time.perf_counter() - step_start
            step_record = {
                "step": "l3_ai",
                "method": "meshgpt-pytorch",
                "params": {},
                "input_faces": len(mesh.faces),
                "output_faces": len(result_mesh.faces),
                "time_seconds": round(elapsed, 4),
                "gate_passed": True,
            }
            return result_mesh, True, step_record

        # L3-B: MeshAnythingV2 (비상업, fallback)
        result_mesh2 = self._try_meshanything(mesh)
        if result_mesh2 is not None and gate_check(result_mesh2):
            elapsed = _time.perf_counter() - step_start
            step_record = {
                "step": "l3_ai",
                "method": "MeshAnythingV2",
                "params": {},
                "input_faces": len(mesh.faces),
                "output_faces": len(result_mesh2.faces),
                "time_seconds": round(elapsed, 4),
                "gate_passed": True,
            }
            return result_mesh2, True, step_record

        # L3 모두 실패
        elapsed = _time.perf_counter() - step_start
        best_mesh = result_mesh2 or result_mesh or mesh
        passed = gate_check(best_mesh)
        step_record = {
            "step": "l3_ai",
            "method": "failed",
            "params": {"engines_tried": ["meshgpt-pytorch", "MeshAnythingV2"]},
            "input_faces": len(mesh.faces),
            "output_faces": len(best_mesh.faces),
            "time_seconds": round(elapsed, 4),
            "gate_passed": passed,
        }
        return best_mesh, passed, step_record

    def _try_meshgpt(self, mesh: trimesh.Trimesh) -> trimesh.Trimesh | None:
        """meshgpt-pytorch 추론 시도. 실패 시 None 반환."""
        try:
            import numpy as np
            import torch
            from meshgpt_pytorch import MeshTransformer

            transformer = MeshTransformer.from_pretrained("MarcusLoren/MeshGPT-preview")
            transformer.eval().cuda()

            vertices = torch.tensor(mesh.vertices, dtype=torch.float32).unsqueeze(0).cuda()
            faces = torch.tensor(mesh.faces, dtype=torch.long).unsqueeze(0).cuda()

            with torch.no_grad():
                output = transformer.generate(vertices=vertices, faces=faces)

            # output은 (vertices, faces) 또는 mesh-like 객체 가정
            if hasattr(output, "vertices") and hasattr(output, "faces"):
                result = trimesh.Trimesh(
                    vertices=np.array(output.vertices.cpu()),
                    faces=np.array(output.faces.cpu()),
                    process=False,
                )
            else:
                log.warning("meshgpt_unexpected_output", type=str(type(output)))
                return None

            log.info("meshgpt_done", output_faces=len(result.faces))
            return result

        except ImportError:
            log.warning("l3_meshgpt_skipped", reason="meshgpt-pytorch not installed")
            return None
        except Exception as exc:
            log.warning("l3_meshgpt_failed", error=str(exc))
            return None

    def _try_meshanything(self, mesh: trimesh.Trimesh) -> trimesh.Trimesh | None:
        """MeshAnythingV2 추론 시도. 실패 시 None 반환."""
        import os
        import sys

        try:
            ma_dir = os.environ.get("MESHANYTHING_V2_DIR")
            if not ma_dir:
                log.warning("l3_meshanything_skipped", reason="MESHANYTHING_V2_DIR not set")
                return None

            if ma_dir not in sys.path:
                sys.path.insert(0, ma_dir)

            import numpy as np
            from main import load_model

            model = load_model()

            # 포인트 클라우드 생성 (N×6: xyz + normals)
            samples, face_idx = trimesh.sample.sample_surface(mesh, count=4096)
            normals = mesh.face_normals[face_idx]
            point_cloud = np.hstack([samples, normals]).astype(np.float32)

            output_mesh = model.inference(point_cloud)
            result = trimesh.Trimesh(
                vertices=output_mesh.vertices,
                faces=output_mesh.faces,
                process=False,
            )
            log.info("meshanything_done", output_faces=len(result.faces))
            return result

        except ImportError:
            log.warning("l3_meshanything_skipped", reason="MeshAnythingV2 not installed")
            return None
        except Exception as exc:
            log.warning("l3_meshanything_failed", error=str(exc))
            return None

    # ------------------------------------------------------------------
    # 기존 단계별 내부 메서드 (Step 0: 포맷 변환, 최종 검증, 리포트 생성)
    # ------------------------------------------------------------------

    def _step_convert(
        self,
        input_path: Path,
        output_dir: Path,
        is_cad: bool,
        tier_hint: str | None,
    ) -> tuple[Path, PreprocessStep | None]:
        """Step 0: 포맷 변환 단계."""
        if not self._converter.needs_conversion(input_path):
            return input_path, None

        step_start = time.perf_counter()
        log.info("step_convert_start", path=str(input_path))

        converted_path = self._converter.convert_to_stl(input_path, output_dir)
        elapsed = time.perf_counter() - step_start

        step = PreprocessStep(
            step="format_conversion",
            method=self._detect_conversion_method(input_path),
            params={"input_format": input_path.suffix.lower()},
            input_faces=None,
            output_faces=None,
            time_seconds=round(elapsed, 4),
        )
        return converted_path, step

    def _final_validate(self, mesh: trimesh.Trimesh) -> trimesh.Trimesh:
        """최종 검증 및 최소 정리.

        trimesh 4.x 기준:
        - is_manifold 속성 없음 → is_watertight + is_winding_consistent 사용
        - remove_degenerate_faces() 없음 → nondegenerate_faces() mask 사용
        - remove_duplicate_faces() 없음 → unique_faces() index 사용
        """
        # watertight이 아닌 경우 재수리 시도 (최대 2회)
        for attempt in range(2):
            if mesh.is_watertight:
                break
            log.info(
                "final_validate_repair",
                attempt=attempt + 1,
                is_watertight=mesh.is_watertight,
                is_winding_consistent=mesh.is_winding_consistent,
            )
            mesh.merge_vertices()
            try:
                nd_mask = mesh.nondegenerate_faces()
                if not nd_mask.all():
                    mesh.update_faces(nd_mask)
            except Exception:
                pass
            try:
                unique_idx = mesh.unique_faces()
                if len(unique_idx) < len(mesh.faces):
                    mesh.update_faces(unique_idx)
            except Exception:
                pass
            mesh.fix_normals()

        # 연결 컴포넌트가 여럿이면 최대 컴포넌트만 보존
        try:
            components = mesh.split(only_watertight=False)
            if len(components) > 1:
                log.info(
                    "keep_largest_component",
                    num_components=len(components),
                )
                mesh = max(components, key=lambda m: len(m.faces))
        except Exception:
            pass

        log.info(
            "final_validation",
            num_faces=len(mesh.faces),
            is_watertight=mesh.is_watertight,
            is_winding_consistent=mesh.is_winding_consistent,
        )
        return mesh

    def _build_report(
        self,
        input_path: Path,
        input_format: str,
        output_path: Path,
        passthrough_cad: bool,
        steps: list[PreprocessStep],
        total_time: float,
        mesh: trimesh.Trimesh | None,
        surface_quality_level: str | None,
    ) -> PreprocessedReport:
        """PreprocessedReport 생성."""
        if mesh is not None:
            import numpy as np

            face_areas = mesh.area_faces
            min_face_area = float(np.min(face_areas)) if len(face_areas) > 0 else 0.0

            edge_lengths = mesh.edges_unique_length
            if len(edge_lengths) > 1:
                max_edge_ratio = float(np.max(edge_lengths) / max(np.min(edge_lengths), 1e-12))
            else:
                max_edge_ratio = 1.0

            # trimesh 4.x: is_manifold 없음 → is_winding_consistent 사용
            is_manifold = getattr(mesh, "is_manifold", None)
            if is_manifold is None:
                is_manifold = mesh.is_winding_consistent

            final_validation = FinalValidation(
                is_watertight=mesh.is_watertight,
                is_manifold=bool(is_manifold),
                num_faces=len(mesh.faces),
                min_face_area=min_face_area,
                max_edge_length_ratio=max_edge_ratio,
            )
        else:
            # 패스스루의 경우 검증 미수행
            final_validation = FinalValidation(
                is_watertight=True,
                is_manifold=True,
                num_faces=0,
                min_face_area=0.0,
                max_edge_length_ratio=1.0,
            )

        summary = PreprocessingSummary(
            input_file=str(input_path),
            input_format=input_format,
            output_file=str(output_path),
            passthrough_cad=passthrough_cad,
            total_time_seconds=round(total_time, 4),
            steps_performed=steps,
            final_validation=final_validation,
            surface_quality_level=surface_quality_level,
        )
        return PreprocessedReport(
            preprocessing_summary=summary,
            surface_quality_level=surface_quality_level,
        )

    def _detect_conversion_method(self, path: Path) -> str:
        """변환 방법 문자열 반환."""
        suffix = path.suffix.lower()
        if suffix in {".step", ".stp", ".iges", ".igs"}:
            return "cadquery.exportStl"
        if suffix in {".obj", ".ply", ".off", ".3mf"}:
            return "trimesh.export"
        if suffix in {".msh", ".vtu", ".vtk"}:
            return "meshio.read"
        return "trimesh.export"
