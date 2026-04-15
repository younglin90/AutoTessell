"""Tier WildMesh: wildmeshing (fTetWild Python 바인딩) 기반 Tet 메쉬 생성기.

Wild 계열 알고리즘 개요
======================
WildMesh는 fTetWild 알고리즘의 Python 바인딩이다.
"envelope" 방식으로 작동하며, 입력 표면에서
``epsilon × bbox_diagonal`` 이내 편차를 허용하면서 고품질 사면체를 생성한다.

형상 보존을 위한 파라미터 지침
-------------------------------
- epsilon을 0.02 이상으로 올리면 cube 같은 날카로운 형상의 모서리가
  tet 경계에서 1~2cm 이상 이탈해 시각적으로 모양이 달라 보인다.
- 기본값(draft=0.002, standard=0.001, fine=0.0003)은 cube 꼭짓점 전부를
  tet 경계면에 0.0001m 이내로 보존한다.
- 생성 후 경계 정점 snap 후처리로 잔류 편차를 추가 제거한다.

파라미터 요약
-------------
- ``wildmesh_epsilon``      : envelope 크기 (bbox 대각선 비율).
  draft=0.002, standard=0.001, fine=0.0003
- ``wildmesh_edge_length_r``: bbox 대각선 대비 엣지 비율.
  draft=0.06, standard=0.04, fine=0.02
- ``wildmesh_stop_quality`` : 목표 품질. draft=20, standard=10, fine=5.
- ``wildmesh_max_its``      : 최대 최적화 반복 횟수.
- ``wildmesh_snap_boundary``: 경계 snap 후처리 사용 여부 (기본 true).
"""

from __future__ import annotations

import concurrent.futures as _cf
import time
from pathlib import Path
from typing import Any

import numpy as np

from core.generator.polymesh_writer import PolyMeshWriter
from core.schemas import MeshStrategy, TierAttempt
from core.utils.logging import get_logger

logger = get_logger(__name__)

TIER_NAME = "tier_wildmesh"

try:
    import wildmeshing  # noqa: F401
    _HAS_WILDMESHING = True
except ImportError:
    _HAS_WILDMESHING = False


def _get_quality_params(quality_level: str, params: dict[str, Any]) -> dict[str, Any]:
    """quality_level에 따른 기본 파라미터를 반환하고 tier_specific_params로 오버라이드한다."""
    # epsilon 0.002 이하 → cube 꼭짓점 완벽 보존
    # epsilon 0.02 이상 → 모서리에서 1~2cm 이탈 (형상 변화 심함)
    _defaults: dict[str, dict[str, Any]] = {
        "draft":    {"stop_quality": 20.0, "max_its": 40,  "epsilon": 0.002,  "edge_length_r": 0.06},
        "standard": {"stop_quality": 10.0, "max_its": 80,  "epsilon": 0.001,  "edge_length_r": 0.04},
        "fine":     {"stop_quality": 5.0,  "max_its": 200, "epsilon": 0.0003, "edge_length_r": 0.02},
    }
    d = _defaults.get(quality_level, _defaults["standard"])
    return {
        "stop_quality":  float(params.get("wildmesh_stop_quality",  d["stop_quality"])),
        "max_its":       int(params.get("wildmesh_max_its",          d["max_its"])),
        "epsilon":       float(params.get("wildmesh_epsilon",        d["epsilon"])),
        "edge_length_r": float(params.get("wildmesh_edge_length_r",
                                          params.get("wildmesh_edge_length",
                                                     d["edge_length_r"]))),
    }


def _boundary_vertices(tet_f: np.ndarray) -> np.ndarray:
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
    tet_v: np.ndarray,
    tet_f: np.ndarray,
    orig_surf: Any,
    epsilon: float,
) -> np.ndarray:
    """tet mesh 경계 정점을 원본 표면에 snap해 잔류 형상 편차를 제거한다."""
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

        logger.info(
            "wildmesh_boundary_snap",
            n_snapped=int(np.sum(snap_mask)),
            max_moved=f"{float(np.max(dists[snap_mask])):.6f}m",
        )
        return new_tet_v
    except Exception as e:
        logger.debug("wildmesh_boundary_snap_skipped", error=str(e))
        return tet_v


def _hausdorff_log(orig_surf: Any, tet_v: np.ndarray, tet_f: np.ndarray) -> None:
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
            "wildmesh_hausdorff",
            max_dist=f"{float(np.max(dists)):.6f}m",
            mean_dist=f"{float(np.mean(dists)):.6f}m",
            hausdorff_ratio=f"{h_ratio:.4%}",
        )
    except Exception as e:
        logger.debug("wildmesh_hausdorff_skipped", error=str(e))


class TierWildMeshGenerator:
    """wildmeshing (fTetWild) 기반 테트라헤드럴 메쉬 생성기.

    형상 충실도 보장
    ----------------
    epsilon 기본값을 draft=0.002로 설정하여 cube 같은 날카로운 형상의
    모서리/꼭짓점을 정확히 보존한다.
    생성 후 경계 정점 snap 후처리로 잔류 편차를 추가 제거한다.
    """

    def run(
        self,
        strategy: MeshStrategy,
        preprocessed_path: Path,
        case_dir: Path,
    ) -> TierAttempt:
        t_start = time.monotonic()
        logger.info("tier_wildmesh_start", preprocessed_path=str(preprocessed_path))

        if not _HAS_WILDMESHING:
            elapsed = time.monotonic() - t_start
            msg = (
                "wildmeshing 미설치. "
                "설치: pip install wildmeshing"
            )
            logger.warning("tier_wildmesh_import_failed", hint=msg)
            return TierAttempt(tier=TIER_NAME, status="failed", time_seconds=elapsed, error_message=msg)

        if not preprocessed_path.exists():
            elapsed = time.monotonic() - t_start
            return TierAttempt(
                tier=TIER_NAME, status="failed", time_seconds=elapsed,
                error_message=f"전처리 파일을 찾을 수 없습니다: {preprocessed_path}",
            )

        try:
            return self._run_pipeline(strategy, preprocessed_path, case_dir, t_start)
        except Exception as exc:
            elapsed = time.monotonic() - t_start
            logger.exception("tier_wildmesh_failed", error=str(exc))
            return TierAttempt(
                tier=TIER_NAME, status="failed", time_seconds=elapsed,
                error_message=f"tier_wildmesh 실행 실패: {exc}",
            )

    def _run_pipeline(
        self,
        strategy: MeshStrategy,
        preprocessed_path: Path,
        case_dir: Path,
        t_start: float,
    ) -> TierAttempt:
        import trimesh as _trimesh
        import wildmeshing as wm

        params = strategy.tier_specific_params
        quality_level = getattr(strategy, "quality_level", "standard")
        if hasattr(quality_level, "value"):
            quality_level = quality_level.value

        p = _get_quality_params(quality_level, params)
        snap_boundary = str(params.get("wildmesh_snap_boundary", "true")).lower() != "false"

        logger.info("tier_wildmesh_params", quality_level=quality_level, snap_boundary=snap_boundary, **p)

        # 표면 로드 및 닫기
        surf: _trimesh.Trimesh = _trimesh.load(str(preprocessed_path), force="mesh")  # type: ignore[assignment]
        if not surf.is_watertight:
            logger.info("wildmesh_pre_close_open_surface")
            surf.fill_holes()
            if not surf.is_watertight:
                try:
                    import pymeshfix
                    mf = pymeshfix.MeshFix(surf.vertices, surf.faces)
                    mf.repair()
                    surf = _trimesh.Trimesh(vertices=mf.points, faces=mf.faces)
                    logger.info("wildmesh_pre_close_pymeshfix_success")
                except Exception as e:  # noqa: BLE001
                    logger.warning("wildmesh_pre_close_pymeshfix_failed", error=str(e))
            if not surf.is_watertight:
                logger.warning("wildmesh_surface_still_open_proceeding")

        orig_surf = surf

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
                "wildmesh_external_flow_compound",
                body_faces=len(surf.faces),
                domain_faces=len(domain_box.faces),
            )
        else:
            vertices = np.asarray(surf.vertices, dtype=np.float64)
            faces = np.asarray(surf.faces, dtype=np.int32)

        # ── Tetrahedralizer ────────────────────────────────────────────
        tetra = wm.Tetrahedralizer(
            stop_quality=p["stop_quality"],
            max_its=p["max_its"],
            epsilon=p["epsilon"],
            edge_length_r=p["edge_length_r"],
            max_threads=0,
            skip_simplify=False,
        )
        tetra.set_log_level(6)

        _TIMEOUT_SEC = {"draft": 60, "standard": 150, "fine": 400}
        timeout_sec = int(params.get("wildmesh_timeout", _TIMEOUT_SEC.get(quality_level, 150)))

        def _tetrahedralize() -> tuple[Any, Any, Any]:
            tetra.set_mesh(vertices, faces)
            tetra.tetrahedralize()
            result = tetra.get_tet_mesh(correct_surface_orientation=True)
            return result[0], result[1], result[2] if len(result) > 2 else None

        logger.info("wildmesh_tetrahedralize_start", timeout=timeout_sec)
        try:
            with _cf.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_tetrahedralize)
                tet_v, tet_f, _tags = future.result(timeout=timeout_sec)
        except _cf.TimeoutError as e:
            raise RuntimeError(
                f"wildmeshing timeout after {timeout_sec}s — "
                "epsilon을 키우거나 edge_length_r을 올리면 빨라집니다."
            ) from e

        logger.info(
            "wildmesh_tetrahedralize_done",
            num_vertices=len(tet_v),
            num_tets=len(tet_f),
        )

        if len(tet_v) == 0 or len(tet_f) == 0:
            raise RuntimeError("wildmeshing이 빈 메쉬를 반환했습니다.")

        # ── 경계 정점 snap 후처리 (internal flow만) ──────────────────────
        if snap_boundary and flow_type != "external":
            tet_v = _snap_boundary_to_surface(tet_v, tet_f, orig_surf, p["epsilon"])

        # Hausdorff 로그 (internal flow만)
        if flow_type != "external":
            _hausdorff_log(orig_surf, tet_v, tet_f)

        # PolyMeshWriter로 polyMesh 변환
        logger.info("wildmesh_polymesh_write_start", case_dir=str(case_dir))
        writer = PolyMeshWriter()
        mesh_stats = writer.write(tet_v, tet_f, case_dir)

        elapsed = time.monotonic() - t_start
        logger.info("tier_wildmesh_success", elapsed=elapsed, mesh_stats=mesh_stats)
        return TierAttempt(tier=TIER_NAME, status="success", time_seconds=elapsed)
