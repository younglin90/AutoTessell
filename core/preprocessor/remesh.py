"""표면 리메쉬 모듈 (L2 단계).

vorpalite(geogram) → pyACVD → pymeshlab 순서로 시도한다.
vorpalite가 PATH에 있으면 최우선으로 사용 (특징 보존 고품질 리메쉬).
없을 경우 pyACVD Voronoi 기반 균일 리메쉬를 수행한다.
추가로 pymeshlab isotropic remeshing을 선택적으로 적용한다.
어떤 도구도 없으면 trimesh 패스스루.
L2 리메쉬 완료 후 gate 검사(watertight + manifold)를 수행한다.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

import trimesh

from core.schemas import GeometryReport
from core.utils.logging import get_logger

log = get_logger(__name__)

try:
    import pyacvd
    import pyvista as pv
    _PYACVD_AVAILABLE = True
except ImportError:
    _PYACVD_AVAILABLE = False
    log.info("pyacvd_unavailable", msg="pyacvd/pyvista 미설치 — 리메쉬 패스스루")

try:
    import pymeshlab
    _PYMESHLAB_AVAILABLE = True
except ImportError:
    _PYMESHLAB_AVAILABLE = False
    log.info("pymeshlab_unavailable", msg="pymeshlab 미설치 — isotropic remesh 건너뜀")

try:
    import fast_simplification
    _FAST_SIMPLIFICATION_AVAILABLE = True
except ImportError:
    _FAST_SIMPLIFICATION_AVAILABLE = False
    msg = "fast-simplification 미설치 — L2 사전 데시메이션 비활성화"
    log.debug("fast_simplification_unavailable", msg=msg)

try:
    import igl  # noqa: F401
    _IGL_AVAILABLE = True
except ImportError:
    _IGL_AVAILABLE = False
    log.debug("igl_unavailable", msg="igl 미설치 — Laplacian smoothing 비활성화")

try:
    import xatlas
    _XATLAS_AVAILABLE = True
except ImportError:
    _XATLAS_AVAILABLE = False
    log.debug("xatlas_unavailable", msg="xatlas 미설치 — UV unwrap 비활성화")


def _run_vorpalite_remesh(
    input_stl: Path, output_stl: Path, target_edge_length: float
) -> bool:
    """geogram vorpalite로 고품질 특징 보존 표면 리메쉬를 수행한다.

    vorpalite가 PATH에 없으면 즉시 False를 반환한다.

    Args:
        input_stl: 입력 STL 파일 경로.
        output_stl: 출력 STL 파일 경로.
        target_edge_length: 목표 엣지 길이.

    Returns:
        성공 여부.
    """
    if not shutil.which("vorpalite"):
        log.debug("vorpalite_not_found")
        return False

    # 목표 점 수 추정: 메쉬 면적 / (target_edge_length^2) * 0.5
    # vorpalite는 점 수(nb_pts)로 제어
    try:
        surf = trimesh.load(str(input_stl), force="mesh")
        if isinstance(surf, trimesh.Scene):
            meshes = list(surf.geometry.values())
            surf = trimesh.util.concatenate(meshes)
        surface_area = float(surf.area)  # type: ignore[attr-defined]
        target_pts = max(1000, int(surface_area / (target_edge_length ** 2) * 0.5))
    except Exception:
        target_pts = 50_000

    cmd = [
        "vorpalite",
        str(input_stl),
        str(output_stl),
        "profile=repair",
        f"remesh:nb_pts={target_pts}",
    ]

    log.info("running_vorpalite", cmd=" ".join(cmd), target_pts=target_pts)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0 and output_stl.exists():
            log.info("vorpalite_success", output=str(output_stl))
            return True
        log.warning(
            "vorpalite_failed",
            returncode=result.returncode,
            stderr=result.stderr[:300],
        )
        return False
    except subprocess.TimeoutExpired:
        log.warning("vorpalite_timeout")
        return False
    except Exception as exc:
        log.warning("vorpalite_exception", error=str(exc))
        return False


def _obj_face_stats(obj_path: Path) -> tuple[int, int, int]:
    """OBJ 파일의 face 통계를 계산한다.

    Returns:
        (총 face 수, quad face 수, tri face 수)
    """
    total = 0
    quads = 0
    tris = 0
    for line in obj_path.read_text(errors="ignore").splitlines():
        if not line.startswith("f "):
            continue
        total += 1
        n = len(line.split()) - 1
        if n == 4:
            quads += 1
        elif n == 3:
            tris += 1
    return total, quads, tris


def _run_quadwild_remesh(input_mesh: Path, setup_txt: Path, work_dir: Path) -> Path | None:
    """quadwild를 실행하고, 유효한 quad 결과 OBJ 경로를 반환한다.

    - `quadwild` 명령이 없으면 None.
    - 종료코드 비정상 / 결과 파일 없음 / quad face 없음이면 None.
    """
    quadwild_bin = shutil.which("quadwild")
    if not quadwild_bin:
        log.debug("quadwild_not_found")
        return None

    cmd = [quadwild_bin, str(input_mesh), str(setup_txt)]
    log.info("running_quadwild", cmd=" ".join(cmd), cwd=str(work_dir))
    env = os.environ.copy()
    env.setdefault("OMP_NUM_THREADS", "1")

    try:
        result = subprocess.run(
            cmd,
            cwd=str(work_dir),
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        log.warning("quadwild_timeout")
        return None
    except Exception as exc:
        log.warning("quadwild_exception", error=str(exc))
        return None

    stem = input_mesh.stem
    out_obj = work_dir / f"{stem}_p0.obj"
    if result.returncode != 0:
        log.warning(
            "quadwild_failed",
            returncode=result.returncode,
            stderr=(result.stderr or "")[:400],
            stdout_tail=(result.stdout or "")[-400:],
        )
        return None
    if not out_obj.exists():
        log.warning("quadwild_no_output_obj", expected=str(out_obj))
        return None

    total, quads, tris = _obj_face_stats(out_obj)
    if total == 0 or quads == 0:
        # 프로젝트 목적(quad 기반 자동 생성)에 맞지 않는 결과는 실패로 간주.
        log.warning(
            "quadwild_invalid_output",
            total_faces=total,
            quad_faces=quads,
            tri_faces=tris,
        )
        return None
    log.info("quadwild_success", output=str(out_obj), total_faces=total, quad_faces=quads)
    return out_obj


class SurfaceRemesher:
    """표면 리메쉬기 (L2).

    vorpalite(geogram) → pyACVD → pymeshlab 순서로 시도한다.
    remesh_l2()는 (mesh, gate_passed, step_record) 튜플을 반환한다.
    """

    def remesh_l2(
        self,
        mesh: trimesh.Trimesh,
        target_faces: int | None = None,
        element_size: float | None = None,
        remesh_engine: str = "auto",
    ) -> tuple[trimesh.Trimesh, bool, dict[str, Any]]:
        """L2 리메쉬 수행 후 gate 검사.

        0. fast-simplification 사전 데시메이션 (200k+ 면일 때)
        1. quadwild (옵션) / vorpalite(geogram) — 고품질 표면 리메쉬
        2. pyACVD Voronoi 균일 리메쉬
        3. pymeshlab isotropic remesh (선택적 추가 개선)

        Args:
            mesh: 입력 trimesh.Trimesh 객체.
            target_faces: 목표 삼각형 수 (None이면 자동 계산).
            element_size: pymeshlab isotropic remesh용 목표 엣지 길이 (None이면 건너뜀).

        Returns:
            (리메쉬된 메쉬, gate_passed, step_record) 튜플.
        """
        from core.preprocessor.repair import gate_check

        step_start = time.perf_counter()
        input_faces = len(mesh.faces)
        methods_used: list[str] = []

        remeshed = mesh
        computed_target = target_faces or self._compute_target_faces(mesh)
        engine = remesh_engine.lower()
        if engine not in {"auto", "quadwild", "vorpalite", "pyacvd", "pymeshlab", "none"}:
            log.warning("invalid_remesh_engine", remesh_engine=remesh_engine, fallback="auto")
            engine = "auto"

        # 0) fast-simplification 사전 데시메이션 (200k+ 면일 때)
        if len(remeshed.faces) > 200_000 and _FAST_SIMPLIFICATION_AVAILABLE:
            remeshed, simplify_applied = self._run_fast_simplification(
                remeshed, target_reduction=0.5
            )
            if simplify_applied:
                methods_used.append("fast_simplification")
                log.info(
                    "l2_fast_simplification_done",
                    input_faces=len(mesh.faces),
                    output_faces=len(remeshed.faces),
                )

        # 1) quadwild/vorpalite
        target_edge = element_size or self._estimate_element_size(mesh)
        remesh_primary_succeeded = False

        if engine == "none":
            methods_used.append("passthrough")
            remesh_primary_succeeded = True

        if not remesh_primary_succeeded and engine in {"auto", "quadwild"}:
            with tempfile.TemporaryDirectory() as tmp:
                in_obj = Path(tmp) / "in.obj"
                setup_txt = Path(tmp) / "basic_setup.txt"
                try:
                    mesh.export(str(in_obj))
                    setup_txt.write_text("do_remesh 1\nsharp_feature_thr 35\nalpha 0.01\nscaleFact 1\n")
                    out_obj = _run_quadwild_remesh(in_obj, setup_txt, Path(tmp))
                    if out_obj is not None:
                        loaded = trimesh.load(str(out_obj), force="mesh")
                        if isinstance(loaded, trimesh.Scene):
                            loaded = trimesh.util.concatenate(list(loaded.geometry.values()))
                        remeshed = loaded  # type: ignore[assignment]
                        methods_used.append("quadwild")
                        remesh_primary_succeeded = True
                except Exception as exc:
                    log.warning("l2_quadwild_failed", error=str(exc))

        if not remesh_primary_succeeded and engine in {"auto", "vorpalite", "quadwild"}:
            with tempfile.TemporaryDirectory() as tmp:
                in_stl = Path(tmp) / "in.stl"
                out_stl = Path(tmp) / "vorpalite_out.stl"
                try:
                    mesh.export(str(in_stl))
                    if _run_vorpalite_remesh(in_stl, out_stl, target_edge):
                        loaded = trimesh.load(str(out_stl), force="mesh")
                        if isinstance(loaded, trimesh.Scene):
                            meshes = list(loaded.geometry.values())
                            loaded = trimesh.util.concatenate(meshes)
                        remeshed = loaded  # type: ignore[assignment]
                        methods_used.append("vorpalite")
                        remesh_primary_succeeded = True
                except Exception as exc:
                    log.warning("l2_vorpalite_failed", error=str(exc))

        # 2) pyACVD (상위 엔진 실패 시 혹은 pyacvd 강제)
        if not remesh_primary_succeeded and engine in {"auto", "pyacvd", "quadwild", "vorpalite"}:
            if _PYACVD_AVAILABLE:
                try:
                    remeshed = self._run_pyacvd(remeshed, computed_target)
                    methods_used.append("pyacvd")
                    remesh_primary_succeeded = True
                except Exception as exc:
                    log.warning("l2_pyacvd_failed", error=str(exc))
            else:
                log.info("l2_pyacvd_skipped", reason="pyacvd unavailable")

        # 3) pymeshlab (마지막 fallback 혹은 pymeshlab 강제)
        if not remesh_primary_succeeded and engine in {"auto", "pymeshlab", "quadwild", "vorpalite", "pyacvd"}:
            if _PYMESHLAB_AVAILABLE:
                try:
                    auto_size = element_size or self._estimate_element_size(remeshed)
                    remeshed = self._run_pymeshlab_isotropic(remeshed, auto_size)
                    methods_used.append("pymeshlab")
                    remesh_primary_succeeded = True
                except Exception as exc:
                    log.warning("l2_pymeshlab_fallback_failed", error=str(exc))
            else:
                log.info("l2_pymeshlab_skipped", reason="pymeshlab unavailable")

        # 요청 엔진이 실패해도 전체 파이프라인을 깨지 않도록 passthrough 유지
        if not remesh_primary_succeeded:
            methods_used.append("passthrough")

        # 3-b) element_size가 주어진 경우 pymeshlab 추가 후처리
        if _PYMESHLAB_AVAILABLE and element_size is not None and engine != "none":
            try:
                remeshed = self._run_pymeshlab_isotropic(remeshed, element_size)
                methods_used.append("pymeshlab")
            except Exception as exc:
                log.warning("l2_pymeshlab_failed", error=str(exc))

        # 4) igl Laplacian smoothing (마무리 품질 개선)
        if _IGL_AVAILABLE and engine != "none":
            try:
                remeshed = self.apply_laplacian_smoothing(remeshed, iterations=5, lambda_=0.5)
                methods_used.append("igl_laplacian")
            except Exception as exc:
                log.warning("l2_laplacian_smoothing_failed", error=str(exc))

        elapsed = time.perf_counter() - step_start
        passed = gate_check(remeshed)
        method_str = "+".join(methods_used) if methods_used else "passthrough"

        log.info(
            "l2_remesh_gate",
            gate_passed=passed,
            is_watertight=remeshed.is_watertight,
            methods=methods_used,
            input_faces=input_faces,
            output_faces=len(remeshed.faces),
        )

        step_record = {
            "step": "l2_remesh",
            "method": method_str,
            "params": {
                "target_faces": computed_target,
                "subdivide": 3,
            },
            "input_faces": input_faces,
            "output_faces": len(remeshed.faces),
            "time_seconds": round(elapsed, 4),
            "gate_passed": passed,
        }
        return remeshed, passed, step_record

    def _estimate_element_size(self, mesh: trimesh.Trimesh) -> float:
        """BBox 대각선 기반 목표 엣지 길이 추정."""
        bbox_extents = mesh.bounding_box.extents
        diagonal = float((bbox_extents ** 2).sum() ** 0.5)
        return max(diagonal / 50.0, 1e-9)

    def _run_pymeshlab_isotropic(
        self,
        mesh: trimesh.Trimesh,
        element_size: float,
    ) -> trimesh.Trimesh:
        """pymeshlab isotropic explicit remeshing 수행."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            in_stl = Path(tmp) / "in.stl"
            out_stl = Path(tmp) / "out.stl"
            mesh.export(str(in_stl))

            ms = pymeshlab.MeshSet()
            ms.load_new_mesh(str(in_stl))
            ms.meshing_isotropic_explicit_remeshing(
                targetlen=pymeshlab.AbsoluteValue(element_size)
            )
            ms.save_current_mesh(str(out_stl))

            loaded = trimesh.load(str(out_stl), force="mesh")
            if isinstance(loaded, trimesh.Scene):
                meshes = list(loaded.geometry.values())
                loaded = trimesh.util.concatenate(meshes)
            result: trimesh.Trimesh = loaded  # type: ignore[assignment]

        log.info(
            "pymeshlab_isotropic_done",
            element_size=element_size,
            output_faces=len(result.faces),
        )
        return result

    def should_remesh(self, report: GeometryReport) -> bool:
        """리메쉬 필요 여부 판단.

        조건:
        - edge_length_ratio > 100 (삼각형 크기 편차 과다)
        - num_faces > 200000 (과다 삼각형)
        - has_degenerate_faces == True

        Args:
            report: Analyzer가 생성한 GeometryReport.

        Returns:
            True이면 리메쉬 권장.
        """
        surface = report.geometry.surface

        # 극소 메쉬(< 100면)는 edge_length_ratio가 아무리 높아도 리메쉬 불필요.
        # 6면 등 toy 형상에 pyACVD/quadwild를 돌리면 수백 초 낭비 발생.
        if surface.num_faces < 100:
            log.info("remesh_skipped_tiny_mesh", num_faces=surface.num_faces)
            return False

        if surface.edge_length_ratio > 100:
            log.info(
                "remesh_recommended",
                reason="edge_length_ratio > 100",
                value=surface.edge_length_ratio,
            )
            return True
        if surface.num_faces > 200_000:
            log.info(
                "remesh_recommended",
                reason="num_faces > 200000",
                value=surface.num_faces,
            )
            return True
        if surface.has_degenerate_faces:
            log.info("remesh_recommended", reason="has_degenerate_faces")
            return True
        return False

    def remesh(
        self,
        mesh: trimesh.Trimesh,
        target_faces: int | None = None,
    ) -> trimesh.Trimesh:
        """표면 균일 리메쉬 수행.

        Args:
            mesh: 입력 trimesh.Trimesh.
            target_faces: 목표 삼각형 수. None이면 자동 계산.

        Returns:
            리메쉬된 trimesh.Trimesh (pyacvd 미설치 시 원본 반환).
        """
        if not _PYACVD_AVAILABLE:
            log.info("remesh_passthrough", reason="pyacvd unavailable")
            return mesh

        computed_target = target_faces or self._compute_target_faces(mesh)
        log.info("remesh_start", target_faces=computed_target, input_faces=len(mesh.faces))

        try:
            return self._run_pyacvd(mesh, computed_target)
        except Exception as exc:
            log.warning("remesh_failed", error=str(exc), fallback="passthrough")
            return mesh

    def apply_laplacian_smoothing(
        self,
        mesh: trimesh.Trimesh,
        iterations: int = 5,
        lambda_: float = 0.5,
    ) -> trimesh.Trimesh:
        """Laplacian 스무딩을 적용하여 메쉬 품질을 개선한다.

        igl의 cotmatrix()와 massmatrix()를 사용하여 기하학적 스무딩을 수행.

        Args:
            mesh: 입력 trimesh.Trimesh.
            iterations: 스무딩 반복 횟수 (기본: 5).
            lambda_: 스무딩 강도 (0.0~1.0, 기본: 0.5).

        Returns:
            스무딩된 trimesh.Trimesh (igl 미설치 시 원본 반환).
        """
        if not _IGL_AVAILABLE:
            log.debug("laplacian_smoothing_skipped", reason="igl unavailable")
            return mesh

        import numpy as np
        from scipy.sparse import linalg

        try:
            import igl

            V = np.asarray(mesh.vertices, dtype=np.float64)
            F = np.asarray(mesh.faces, dtype=np.int64)

            # Cotangent Laplacian과 Mass matrix 계산
            L = igl.cotmatrix(V, F)
            M = igl.massmatrix(V, F, igl.MASSMATRIX_TYPE_VORONOI)

            # Laplacian smoothing: V_new = V - lambda * M^(-1) * L * V
            # 더 안정적인 구현: iterate (M - lambda * L) * V_new = M * V
            # which gives V_new = (M - lambda * L)^(-1) * M * V
            A = M - lambda_ * L

            V_smoothed = V.copy()
            for _ in range(iterations):
                # Solve A @ V_smoothed = M @ V for each coordinate separately
                for coord_idx in range(3):
                    rhs = M.dot(V_smoothed[:, coord_idx])
                    V_smoothed[:, coord_idx] = linalg.spsolve(A, rhs)

            result = trimesh.Trimesh(
                vertices=V_smoothed,
                faces=F,
                process=False,
            )

            log.info(
                "laplacian_smoothing_done",
                iterations=iterations,
                lambda_=lambda_,
                num_vertices=len(V),
            )
            return result

        except Exception as exc:
            log.warning("laplacian_smoothing_failed", error=str(exc), fallback="passthrough")
            return mesh

    # ------------------------------------------------------------------
    # 내부 메서드
    # ------------------------------------------------------------------

    def _compute_target_faces(self, mesh: trimesh.Trimesh) -> int:
        """BBox 기반 목표 삼각형 수 자동 계산."""
        surface_area = float(mesh.area)
        # characteristic element size: bbox 대각선 / 50
        bbox_extents = mesh.bounding_box.extents
        diagonal = float((bbox_extents ** 2).sum() ** 0.5)
        element_size = max(diagonal / 50.0, 1e-9)

        target = int(surface_area / (element_size ** 2) * 2)
        target = max(10_000, min(100_000, target))
        log.info(
            "remesh_target_computed",
            surface_area=surface_area,
            element_size=element_size,
            target_faces=target,
        )
        return target

    def _run_fast_simplification(
        self,
        mesh: trimesh.Trimesh,
        target_reduction: float = 0.5,
    ) -> tuple[trimesh.Trimesh, bool]:
        """fast-simplification으로 메쉬 데시메이션.

        Args:
            mesh: 입력 trimesh.Trimesh.
            target_reduction: 목표 감소율 (0.0~1.0). 0.5 = 50% 감소.

        Returns:
            (단순화된 메쉬, 적용 여부) 튜플.
        """
        try:
            import numpy as np

            simplified_verts, simplified_faces = fast_simplification.simplify(
                mesh.vertices.astype(np.float64),
                mesh.faces.astype(np.uint32),
                target_reduction=target_reduction,
            )

            if len(simplified_faces) == 0:
                log.warning("fast_simplification_no_output")
                return mesh, False

            result = trimesh.Trimesh(
                vertices=simplified_verts,
                faces=simplified_faces,
                process=False,
            )
            log.info(
                "fast_simplification_success",
                input_faces=len(mesh.faces),
                output_faces=len(result.faces),
                target_reduction=target_reduction,
            )
            return result, True
        except Exception as exc:
            log.warning("fast_simplification_failed", error=str(exc))
            return mesh, False

    def _run_pyacvd(self, mesh: trimesh.Trimesh, target_faces: int) -> trimesh.Trimesh:
        """pyacvd 리메쉬 실행."""
        import numpy as np

        # trimesh → pyvista PolyData 변환
        vertices = mesh.vertices
        faces = mesh.faces
        # pyvista face format: [3, v0, v1, v2, ...]
        n_faces = len(faces)
        pv_faces = np.hstack([
            np.full((n_faces, 1), 3, dtype=np.int64),
            faces.astype(np.int64),
        ]).ravel()

        poly = pv.PolyData(vertices, pv_faces)

        clus = pyacvd.Clustering(poly)
        clus.subdivide(3)
        clus.cluster(target_faces)
        remeshed_poly = clus.create_mesh()

        # pyvista → trimesh 변환
        pts = np.asarray(remeshed_poly.points)
        raw_faces = np.asarray(remeshed_poly.faces).reshape(-1, 4)
        tri_faces = raw_faces[:, 1:4]

        result = trimesh.Trimesh(vertices=pts, faces=tri_faces, process=False)
        log.info(
            "remesh_done",
            input_faces=len(mesh.faces),
            output_faces=len(result.faces),
        )
        return result

    def apply_uv_unwrap(self, mesh: trimesh.Trimesh) -> trimesh.Trimesh:
        """xatlas를 사용한 UV 언랩 적용.

        AI 모델 입력 전처리 등에서 UV 좌표가 필요할 때 사용.
        xatlas가 미설치되거나 실패 시 UV 없는 원본 메쉬를 반환한다.

        Args:
            mesh: 입력 trimesh.Trimesh 객체.

        Returns:
            UV 좌표가 추가된 trimesh.Trimesh (또는 원본).
        """
        if not _XATLAS_AVAILABLE:
            log.debug("apply_uv_unwrap_skipped", reason="xatlas unavailable")
            return mesh

        import numpy as np

        try:
            vertices = np.asarray(mesh.vertices, dtype=np.float32)
            faces = np.asarray(mesh.faces, dtype=np.uint32)

            # xatlas.parametrize(positions, indices) → (atlas, chart_indices, uvs)
            # positions: (N, 3) float32 vertices
            # indices: (F, 3) uint32 faces
            # Returns: (atlas_uint32, chart_indices_uint32, uvs_float32)
            # uvs는 (V, 2) float32 배열
            atlas, chart_indices, uvs = xatlas.parametrize(vertices, faces)

            if uvs is None or len(uvs) == 0:
                log.warning("xatlas_parametrize_no_uvs")
                return mesh

            # trimesh visual에 UV 저장
            # trimesh.visual.TextureVisuals는 uv 좌표를 가질 수 있음
            try:
                mesh.visual.uv = uvs  # type: ignore[union-attr]
            except (AttributeError, TypeError):
                log.warning("xatlas_uv_assignment_failed")

            log.info(
                "uv_unwrap_done",
                num_vertices=len(vertices),
                num_faces=len(faces),
                uv_shape=uvs.shape,
            )
            return mesh

        except Exception as exc:
            log.warning("apply_uv_unwrap_failed", error=str(exc), fallback="passthrough")
            return mesh
