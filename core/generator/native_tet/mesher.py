"""native_tet MVP 메쉬 생성기."""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from core.utils.logging import get_logger

log = get_logger(__name__)


@dataclass
class NativeTetResult:
    success: bool
    elapsed: float
    n_cells: int = 0
    n_points: int = 0
    message: str = ""
    # v0.4: dual 변환 등 downstream 사용을 위해 tet array 와 points 를 함께 반환.
    tet_points: np.ndarray | None = None
    tets: np.ndarray | None = None


def _seed_points_uniform(
    bbox_min: np.ndarray, bbox_max: np.ndarray, spacing: float,
) -> np.ndarray:
    """bbox 내부 uniform grid 시드. spacing 이 bbox 보다 크면 빈 array."""
    diag = float(np.linalg.norm(bbox_max - bbox_min))
    if spacing <= 0 or diag == 0:
        return np.zeros((0, 3))
    # safety: 한 축 당 최대 60 개 (grid size 제한)
    nxyz = np.maximum(
        np.ceil((bbox_max - bbox_min) / spacing).astype(int),
        1,
    )
    nxyz = np.minimum(nxyz, 60)
    xs = np.linspace(bbox_min[0], bbox_max[0], nxyz[0])
    ys = np.linspace(bbox_min[1], bbox_max[1], nxyz[1])
    zs = np.linspace(bbox_min[2], bbox_max[2], nxyz[2])
    X, Y, Z = np.meshgrid(xs, ys, zs, indexing="ij")
    return np.stack([X.ravel(), Y.ravel(), Z.ravel()], axis=1)


from core.utils.geometry import inside_winding_number as _inside_winding_number


def generate_native_tet(
    vertices: np.ndarray,
    faces: np.ndarray,
    case_dir: Path,
    *,
    target_edge_length: float | None = None,
    seed_density: int = 12,
    sliver_quality_threshold: float = 0.05,
) -> NativeTetResult:
    """입력 표면 메쉬 → tet polyMesh (MVP).

    Args:
        vertices: (V, 3) 표면 점.
        faces: (F, 3) 표면 triangles (watertight 가정).
        case_dir: OpenFOAM case 디렉터리 (constant/polyMesh 생성됨).
        target_edge_length: 내부 grid spacing. None 이면 bbox_diag / seed_density.
        seed_density: target_edge_length 가 None 일 때 bbox_diag 분할 수.
        sliver_quality_threshold: shape quality (정사면체≈1, sliver≈0) 하한. 이
            값 미만 tet 은 제거. beta62: 0.05 기본이었으나 복잡 형상에서 모든 tet
            이 탈락해 harness 수렴 실패 → 기본값을 quality 별로 조정 가능하게 노출.

    Returns:
        NativeTetResult.
    """
    t0 = time.perf_counter()
    try:
        from scipy.spatial import Delaunay
    except Exception as exc:
        return NativeTetResult(False, 0.0, message=f"scipy 필요: {exc}")

    try:
        from core.generator.polymesh_writer import PolyMeshWriter
    except Exception as exc:
        return NativeTetResult(False, 0.0, message=f"polymesh_writer import 실패: {exc}")

    V = np.asarray(vertices, dtype=np.float64)
    F = np.asarray(faces, dtype=np.int64)
    if V.size == 0 or F.size == 0:
        return NativeTetResult(False, 0.0, message="빈 입력 mesh")

    bmin = V.min(axis=0); bmax = V.max(axis=0)
    diag = float(np.linalg.norm(bmax - bmin))
    if target_edge_length is None or target_edge_length <= 0:
        target_edge_length = diag / max(1, int(seed_density))

    log.info(
        "native_tet_start",
        n_surf_verts=V.shape[0], n_surf_faces=F.shape[0],
        bbox_diag=diag, target_edge_length=float(target_edge_length),
    )

    # 1) 시드 = 표면 vertex + 내부 uniform grid
    grid = _seed_points_uniform(bmin, bmax, float(target_edge_length))
    # grid 중 outside 제거 (아니면 bbox 밖으로 tet 이 많이 생김)
    if grid.shape[0] > 0:
        inside_mask = _inside_winding_number(grid, V, F)
        grid = grid[inside_mask]

    all_pts = np.vstack([V, grid]) if grid.shape[0] else V.copy()
    log.info("native_tet_seed", n_points=all_pts.shape[0], n_grid_inside=grid.shape[0])

    # 2) Delaunay
    try:
        dl = Delaunay(all_pts)
    except Exception as exc:
        return NativeTetResult(
            False, time.perf_counter() - t0,
            message=f"Delaunay 실패: {exc}",
        )
    tets = np.asarray(dl.simplices, dtype=np.int64)
    if tets.shape[0] == 0:
        return NativeTetResult(
            False, time.perf_counter() - t0,
            message="Delaunay 가 0 tet 반환",
        )

    # 3) tet centroid 로 inside 판정
    centroids = all_pts[tets].mean(axis=1)
    inside_tet = _inside_winding_number(centroids, V, F)

    # 3b) sliver tet 제거 — shape quality:
    #     q = 8.48 * volume / (sum of edge_len^3 / 6) ≈ aspect ratio 의 역수.
    #     정사면체 q ≈ 1, sliver 는 0 근처. 임계값 ε 아래이면 탈락.
    v = all_pts[tets]   # (T, 4, 3)
    e01 = np.linalg.norm(v[:, 1] - v[:, 0], axis=1)
    e02 = np.linalg.norm(v[:, 2] - v[:, 0], axis=1)
    e03 = np.linalg.norm(v[:, 3] - v[:, 0], axis=1)
    e12 = np.linalg.norm(v[:, 2] - v[:, 1], axis=1)
    e13 = np.linalg.norm(v[:, 3] - v[:, 1], axis=1)
    e23 = np.linalg.norm(v[:, 3] - v[:, 2], axis=1)
    edge_max = np.maximum.reduce([e01, e02, e03, e12, e13, e23])
    # tet signed volume (abs 이므로 winding 무관)
    vol6 = np.abs(
        np.einsum(
            "ij,ij->i",
            v[:, 1] - v[:, 0],
            np.cross(v[:, 2] - v[:, 0], v[:, 3] - v[:, 0]),
        )
    )
    # shape quality: 8.48 * V / edge_max^3 ∈ [0, 1]
    safe = edge_max > 1e-30
    q = np.zeros_like(edge_max)
    q[safe] = (8.48 * (vol6[safe] / 6.0)) / (edge_max[safe] ** 3)
    # beta5: sliver threshold 상향 (0.02 → 0.05). beta62: 파라미터화.
    q_thresh = max(0.0, float(sliver_quality_threshold))
    keep_mask = inside_tet & (q >= q_thresh)
    n_dropped_sliver = int(inside_tet.sum() - keep_mask.sum())
    log.info(
        "native_tet_sliver_filter",
        kept=int(keep_mask.sum()),
        dropped_sliver=n_dropped_sliver,
        q_threshold=q_thresh,
    )
    kept = tets[keep_mask]
    if kept.shape[0] == 0:
        return NativeTetResult(
            False, time.perf_counter() - t0,
            message="inside tet 0 — target_edge_length 조정 필요",
        )

    # 4) 사용된 vertex 만 추출 + 인덱스 압축.
    #    v0.4.0-beta5: Hausdorff 보존을 위해 모든 surface vertex (V) 는 사용
    #    여부와 무관하게 최종 mesh 에 강제 포함.
    used_set = set(np.unique(kept.ravel()).tolist())
    surface_vert_ids = set(range(V.shape[0]))
    used_set |= surface_vert_ids
    used = np.array(sorted(used_set), dtype=np.int64)
    remap = -np.ones(all_pts.shape[0], dtype=np.int64)
    remap[used] = np.arange(used.shape[0])
    final_tets = remap[kept].astype(np.int64)
    final_pts = all_pts[used]

    # 5) polyMesh 쓰기
    try:
        stats = PolyMeshWriter().write(final_pts, final_tets, case_dir)
    except Exception as exc:
        return NativeTetResult(
            False, time.perf_counter() - t0,
            message=f"polyMesh 쓰기 실패: {exc}",
        )

    elapsed = time.perf_counter() - t0
    n_cells = int(stats.get("num_cells", final_tets.shape[0]))
    n_points = int(stats.get("num_points", final_pts.shape[0]))
    return NativeTetResult(
        success=True, elapsed=elapsed,
        n_cells=n_cells, n_points=n_points,
        message=(
            f"native_tet OK — cells={n_cells}, points={n_points}, "
            f"seed_grid={grid.shape[0]}, target_edge={target_edge_length:.4g}"
        ),
        tet_points=final_pts, tets=final_tets,
    )
