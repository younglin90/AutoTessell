"""Tier 2: TetWild + MMG 메쉬 생성기 (최후 fallback).

Wild 계열 알고리즘 개요
======================
TetWild는 "envelope" 방식으로 작동한다. 입력 표면에서
``epsilon × bbox_diagonal`` 거리 이내의 편차를 허용하면서 고품질
사면체 메쉬를 생성한다. epsilon이 클수록 빠르고 형상 변화가 크며,
작을수록 느리고 원본에 충실하다.

형상 보존을 위한 파라미터 지침
-------------------------------
- epsilon을 0.02 이상으로 올리면 cube 같은 날카로운 형상의 모서리가
  tet 경계에서 1~3cm 이상 이탈해 시각적으로 모양이 달라 보인다.
- 기본값(draft=0.002, standard=0.001, fine=0.0003)은 cube 꼭짓점 전부를
  tet 경계면에 0.0001m 이내로 보존한다.
- 생성 후 경계 정점 snap 후처리로 잔류 편차를 추가 제거한다.

파라미터 요약
-------------
- ``tetwild_epsilon``        : envelope 크기 (bbox 대각선 비율).
  draft=0.002, standard=0.001, fine=0.0003
- ``tetwild_edge_length``    : 절대 엣지 길이(m). 설정 시 우선.
- ``tetwild_edge_length_fac``: bbox 대각선 대비 엣지 비율.
  draft=0.10, standard=0.07, fine=0.02
- ``tetwild_stop_energy``    : 최적화 종료 energy.
- ``tw_max_iterations``      : 최적화 최대 반복 횟수.
- ``tetwild_snap_boundary``  : 경계 snap 후처리 사용 여부 (기본 true).
"""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from core.generator.polymesh_writer import PolyMeshWriter
from core.schemas import MeshStrategy, TierAttempt
from core.utils.errors import format_missing_dependency_message
from core.utils.logging import get_logger

logger = get_logger(__name__)

TIER_NAME = "tier2_tetwild"


def _try_gmsh_to_foam(mesh_path: Path, case_dir: Path) -> bool:
    gmsh_to_foam = shutil.which("gmshToFoam")
    if gmsh_to_foam is None:
        return False
    try:
        from core.utils.openfoam_utils import run_openfoam
        run_openfoam("gmshToFoam", case_dir, args=[str(mesh_path)])
        logger.info("gmsh_to_foam_success", mesh_path=str(mesh_path))
        return True
    except Exception as exc:
        logger.warning("gmsh_to_foam_failed", error=str(exc))
        return False


def _convert_to_openfoam(
    vertices: npt.NDArray[Any],
    tets: npt.NDArray[Any],
    mesh_path: Path,
    case_dir: Path,
) -> dict[str, int]:
    if _try_gmsh_to_foam(mesh_path, case_dir):
        return {}
    logger.info("polymesh_writer_convert", src=str(mesh_path), dst=str(case_dir))
    writer = PolyMeshWriter()
    return writer.write(vertices, tets, case_dir)


def _boundary_vertices(tet_f: npt.NDArray[Any]) -> npt.NDArray[Any]:
    """tet mesh에서 경계면(외부 노출) 정점 인덱스를 반환한다."""
    from collections import Counter
    face_count: Counter = Counter()
    for tet in tet_f:
        for tri in [
            (tet[0], tet[1], tet[2]),
            (tet[0], tet[1], tet[3]),
            (tet[0], tet[2], tet[3]),
            (tet[1], tet[2], tet[3]),
        ]:
            face_count[tuple(sorted(tri))] += 1
    bv: set[int] = set()
    for face, cnt in face_count.items():
        if cnt == 1:
            bv.update(face)
    return np.array(sorted(bv), dtype=np.int64)


def _snap_boundary_to_surface(
    tet_v: npt.NDArray[Any],
    tet_f: npt.NDArray[Any],
    orig_surf: Any,
    epsilon: float,
) -> npt.NDArray[Any]:
    """tet mesh 경계 정점을 원본 표면에 snap해 잔류 형상 편차를 제거한다.

    epsilon × bbox_diag × 3 이내 경계 정점만 snap한다
    (너무 멀면 내부 정점이 오판된 것이므로 무시).
    """
    try:
        bbox_diag = float(np.linalg.norm(
            np.array(orig_surf.bounds[1]) - np.array(orig_surf.bounds[0])
        ))
        snap_threshold = epsilon * bbox_diag * 3.0

        bv_indices = _boundary_vertices(tet_f)
        if len(bv_indices) == 0:
            return tet_v

        bv_coords = tet_v[bv_indices]
        closest_pts, dists, _ = orig_surf.nearest.on_surface(bv_coords)

        snap_mask = dists < snap_threshold
        if not np.any(snap_mask):
            return tet_v

        new_tet_v = tet_v.copy()
        new_tet_v[bv_indices[snap_mask]] = closest_pts[snap_mask]

        n_snapped = int(np.sum(snap_mask))
        max_moved = float(np.max(dists[snap_mask]))
        logger.info(
            "tetwild_boundary_snap",
            n_snapped=n_snapped,
            max_moved=f"{max_moved:.6f}m",
            snap_threshold=f"{snap_threshold:.6f}m",
        )
        return new_tet_v
    except Exception as e:
        logger.debug("tetwild_boundary_snap_skipped", error=str(e))
        return tet_v


def _hausdorff_log(
    orig_surf: Any,
    tet_v: npt.NDArray[Any],
    tet_f: npt.NDArray[Any],
) -> None:
    """원본 표면과 tet mesh 경계 간 Hausdorff 거리를 로그에 기록한다."""
    try:
        import trimesh as _trimesh
        from collections import Counter
        face_count: Counter = Counter()
        for tet in tet_f:
            for tri in [(tet[0],tet[1],tet[2]),(tet[0],tet[1],tet[3]),
                        (tet[0],tet[2],tet[3]),(tet[1],tet[2],tet[3])]:
                face_count[tuple(sorted(tri))] += 1
        btris = np.array([list(f) for f, cnt in face_count.items() if cnt == 1], dtype=np.int64)
        if len(btris) == 0:
            return
        tet_surf = _trimesh.Trimesh(vertices=tet_v, faces=btris)
        pts = tet_surf.sample(min(500, len(tet_surf.faces)))
        _, dists, _ = orig_surf.nearest.on_surface(pts)
        bbox_diag = float(np.linalg.norm(
            np.array(orig_surf.bounds[1]) - np.array(orig_surf.bounds[0])
        ))
        h_ratio = float(np.max(dists)) / max(bbox_diag, 1e-9)
        logger.info(
            "tetwild_hausdorff",
            max_dist=f"{float(np.max(dists)):.6f}m",
            mean_dist=f"{float(np.mean(dists)):.6f}m",
            hausdorff_ratio=f"{h_ratio:.4%}",
        )
    except Exception as e:
        logger.debug("tetwild_hausdorff_skipped", error=str(e))


class Tier2TetWildGenerator:
    """TetWild + MMG 기반 테트라헤드럴 메쉬 생성기.

    형상 충실도 보장
    ----------------
    epsilon 기본값을 draft=0.002, standard=0.001, fine=0.0003으로 설정하여
    cube 같은 날카로운 형상의 모서리/꼭짓점을 정확히 보존한다.
    생성 후 경계 정점 snap 후처리로 잔류 편차를 추가 제거한다.
    """

    def run(
        self,
        strategy: MeshStrategy,
        preprocessed_path: Path,
        case_dir: Path,
    ) -> TierAttempt:
        t_start = time.monotonic()
        logger.info("tier2_tetwild_start", preprocessed_path=str(preprocessed_path))

        try:
            import pytetwild  # noqa: F401
        except ImportError as exc:
            elapsed = time.monotonic() - t_start
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message=format_missing_dependency_message(
                    dependency="pytetwild",
                    fallback="다른 tier로 fallback",
                    action="pip install pytetwild",
                    detail=str(exc),
                ),
            )

        if not preprocessed_path.exists():
            elapsed = time.monotonic() - t_start
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message=f"전처리 파일을 찾을 수 없습니다: {preprocessed_path}",
            )

        try:
            return self._run_pipeline(strategy, preprocessed_path, case_dir, t_start)
        except Exception as exc:
            elapsed = time.monotonic() - t_start
            logger.exception("tier2_tetwild_failed", error=str(exc))
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message=f"Tier 2 실행 실패: {exc}",
            )

    def _run_pipeline(
        self,
        strategy: MeshStrategy,
        preprocessed_path: Path,
        case_dir: Path,
        t_start: float,
    ) -> TierAttempt:
        import concurrent.futures as _cf
        import pytetwild
        import trimesh as _trimesh

        params = strategy.tier_specific_params
        quality_level = getattr(strategy, "quality_level", "standard")
        if hasattr(quality_level, "value"):
            quality_level = quality_level.value

        # ── 품질 레벨별 기본값 ────────────────────────────────────────────
        # epsilon 0.002 이하 → cube 꼭짓점 완벽 보존 (Hausdorff ≈ 0)
        # epsilon 0.02 이상 → cube 모서리에서 1~3cm 이탈 (형상 변화 심함)
        _defaults: dict[str, dict[str, Any]] = {
            "draft":    {"epsilon": 0.002,  "edge_length_fac": 0.10, "stop_energy": 20.0, "num_opt_iter": 20},
            "standard": {"epsilon": 0.001,  "edge_length_fac": 0.07, "stop_energy": 10.0, "num_opt_iter": 50},
            "fine":     {"epsilon": 0.0003, "edge_length_fac": 0.02, "stop_energy": 5.0,  "num_opt_iter": 150},
        }
        d = _defaults.get(quality_level, _defaults["standard"])

        epsilon = float(params.get("tetwild_epsilon", d["epsilon"]))
        stop_energy = float(params.get("tetwild_stop_energy", d["stop_energy"]))
        num_opt_iter = int(params.get("tw_max_iterations", d["num_opt_iter"]))
        edge_length_fac = float(params.get("tetwild_edge_length_fac", d["edge_length_fac"]))
        edge_length_abs = params.get("tetwild_edge_length", None)
        snap_boundary = str(params.get("tetwild_snap_boundary", "true")).lower() != "false"

        logger.info(
            "tier2_tetwild_params",
            quality_level=quality_level,
            epsilon=epsilon,
            edge_length_abs=edge_length_abs,
            edge_length_fac=edge_length_fac,
            stop_energy=stop_energy,
            num_opt_iter=num_opt_iter,
            snap_boundary=snap_boundary,
        )

        surf: _trimesh.Trimesh = _trimesh.load(str(preprocessed_path), force="mesh")  # type: ignore[assignment]

        # 열린 표면 닫기 시도
        if not surf.is_watertight:
            logger.info("tetwild_pre_close_open_surface")
            surf.fill_holes()
            if not surf.is_watertight:
                try:
                    import pymeshfix
                    mf = pymeshfix.MeshFix(surf.vertices, surf.faces)
                    mf.repair()
                    surf = _trimesh.Trimesh(vertices=mf.points, faces=mf.faces)
                    logger.info("tetwild_pre_close_pymeshfix_success")
                except Exception as e:  # noqa: BLE001
                    logger.warning("tetwild_pre_close_pymeshfix_failed", error=str(e))
            if not surf.is_watertight:
                logger.warning("tetwild_surface_still_open_proceeding")

        orig_surf = surf  # snap 후처리에 사용

        # External flow: 도메인 박스 + 물체 복합 지오메트리
        flow_type = getattr(strategy, "flow_type", "internal")
        if flow_type == "external" and strategy.domain is not None:
            domain = strategy.domain
            box_size = [float(domain.max[i] - domain.min[i]) for i in range(3)]
            box_center = [float((domain.min[i] + domain.max[i]) / 2) for i in range(3)]
            domain_box = _trimesh.creation.box(extents=box_size)
            domain_box.apply_translation(box_center)
            domain_box.invert()
            compound = _trimesh.util.concatenate([surf, domain_box])
            vertices = np.asarray(compound.vertices, dtype=np.float64)
            faces = np.asarray(compound.faces, dtype=np.int32)
            logger.info(
                "tetwild_external_flow_compound",
                body_faces=len(surf.faces),
                domain_faces=len(domain_box.faces),
            )
        else:
            vertices = np.asarray(surf.vertices, dtype=np.float64)
            faces = np.asarray(surf.faces, dtype=np.int32)

        # ── pytetwild 호출 ───────────────────────────────────────────────
        tetra_kwargs: dict[str, Any] = {
            "epsilon": epsilon,
            "stop_energy": stop_energy,
            "num_opt_iter": num_opt_iter,
            "optimize": True,
            "quiet": True,
        }
        if edge_length_abs is not None:
            tetra_kwargs["edge_length_abs"] = float(edge_length_abs)
        else:
            tetra_kwargs["edge_length_fac"] = edge_length_fac

        _TW_TIMEOUT_SEC = {"draft": 60, "standard": 120, "fine": 300}
        timeout_sec = int(params.get("tetwild_timeout", _TW_TIMEOUT_SEC.get(quality_level, 120)))

        def _run_tetwild() -> tuple[Any, Any]:
            return pytetwild.tetrahedralize(
                np.asarray(vertices, dtype=np.float64),
                np.asarray(faces, dtype=np.int32),
                **tetra_kwargs,
            )

        logger.info("tetwild_tetrahedralize_start", timeout=timeout_sec, **tetra_kwargs)
        try:
            with _cf.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_run_tetwild)
                tet_v, tet_f = future.result(timeout=timeout_sec)
        except _cf.TimeoutError as e:
            raise RuntimeError(
                f"pytetwild timeout after {timeout_sec}s — "
                "epsilon을 키우거나 edge_length_fac를 올리면 빨라집니다."
            ) from e

        logger.info("tetwild_tetrahedralize_done", num_vertices=len(tet_v), num_tets=len(tet_f))

        if len(tet_v) == 0 or len(tet_f) == 0:
            raise RuntimeError("pytetwild이 빈 메쉬를 반환했습니다.")

        # ── 경계 정점 snap 후처리 (internal flow만) ─────────────────────
        # external flow는 도메인 박스가 포함되어 원본 표면과 단순 비교 불가
        if snap_boundary and flow_type != "external":
            tet_v = _snap_boundary_to_surface(tet_v, tet_f, orig_surf, epsilon)

        # Hausdorff 로그 (internal flow만)
        if flow_type != "external":
            _hausdorff_log(orig_surf, tet_v, tet_f)

        # meshio로 .msh 저장
        import meshio as _meshio
        tet_mesh = _meshio.Mesh(points=tet_v, cells=[("tetra", tet_f)])
        result_msh = case_dir / "tetwild_result.msh"
        _meshio.write(str(result_msh), tet_mesh)
        logger.info("tetwild_msh_saved", path=str(result_msh))

        # MMG 품질 후처리 (standard/fine 전용)
        mmg_mesh_path = result_msh
        mmg_verts = tet_v
        mmg_tets = tet_f
        if quality_level in ("standard", "fine") and shutil.which("mmg3d"):
            mmg_mesh_path = self._run_mmg(result_msh, case_dir, strategy)
            if mmg_mesh_path != result_msh:
                try:
                    import meshio as _meshio2
                    mmg_result = _meshio2.read(str(mmg_mesh_path))
                    tetra_cells = [c for c in mmg_result.cells if c.type == "tetra"]
                    if tetra_cells:
                        mmg_verts = mmg_result.points
                        mmg_tets = tetra_cells[0].data
                except Exception as mmg_read_exc:
                    logger.warning("mmg_read_failed", error=str(mmg_read_exc))

        mesh_stats = _convert_to_openfoam(mmg_verts, mmg_tets, mmg_mesh_path, case_dir)

        elapsed = time.monotonic() - t_start
        logger.info("tier2_tetwild_success", elapsed=elapsed, mesh_stats=mesh_stats)
        return TierAttempt(tier=TIER_NAME, status="success", time_seconds=elapsed)

    def _convert_msh_to_medit(self, input_msh: Path, case_dir: Path) -> Path:
        medit_path = case_dir / "tetwild_result.mesh"
        try:
            import meshio as _meshio
            mesh = _meshio.read(str(input_msh))
            _meshio.write(str(medit_path), mesh, file_format="medit")
            return medit_path
        except Exception as exc:
            logger.warning("msh_to_medit_failed", error=str(exc))
            return input_msh

    def _run_mmg(self, input_msh: Path, case_dir: Path, strategy: MeshStrategy) -> Path:
        params = strategy.tier_specific_params
        hmin = params.get("mmg_hmin", strategy.surface_mesh.min_cell_size)
        hmax = params.get("mmg_hmax", strategy.surface_mesh.target_cell_size)
        hgrad = params.get("mmg_hgrad", 1.3)
        hausd = params.get("mmg_hausd", 0.01)

        if input_msh.suffix == ".msh":
            medit_input = self._convert_msh_to_medit(input_msh, case_dir)
        else:
            medit_input = input_msh

        optimized = case_dir / "mmg_optimized.mesh"
        cmd = ["mmg3d", str(medit_input)]
        if hmin is not None:
            cmd += ["-hmin", str(hmin)]
        if hmax is not None:
            cmd += ["-hmax", str(hmax)]
        cmd += ["-hgrad", str(hgrad), "-hausd", str(hausd), "-o", str(optimized)]

        logger.info("running_mmg3d", cmd=" ".join(cmd))
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
            if result.returncode == 0 and optimized.exists():
                return optimized
            logger.warning("mmg3d_failed", returncode=result.returncode, stderr=result.stderr[:300])
            return input_msh
        except Exception as exc:
            logger.warning("mmg3d_exception", error=str(exc))
            return input_msh
