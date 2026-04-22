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


def _inside_winding_number(
    query: np.ndarray, V: np.ndarray, F: np.ndarray,
) -> np.ndarray:
    """ray casting 기반 inside 판정 (+x 방향 ray, face 교차 수 홀수면 inside).

    Robustness 는 간이적 — MVP 수준. 빠른 벡터화 구현.
    """
    Q = np.asarray(query, dtype=np.float64)
    N = Q.shape[0]
    inside = np.zeros(N, dtype=bool)
    # 각 face 에 대해 ray-triangle 교차 누적 (Möller–Trumbore)
    v0 = V[F[:, 0]]; v1 = V[F[:, 1]]; v2 = V[F[:, 2]]
    edge1 = v1 - v0; edge2 = v2 - v0
    d = np.array([1.0, 0.0, 0.0])
    # 각 query 당 count (vectorized per-query)
    # F 가 크면 batch 로 (query 를 batch 로 순회)
    batch = 128
    for qi in range(0, N, batch):
        qs = Q[qi:qi + batch]   # (B, 3)
        # for each face, for each query: compute t, u, v
        pvec = np.cross(d, edge2)                       # (F, 3)
        det = (edge1 * pvec).sum(axis=1)                # (F,)
        safe = np.abs(det) > 1e-12
        inv_det = np.zeros_like(det)
        np.divide(1.0, det, where=safe, out=inv_det)
        tvec = qs[:, None, :] - v0[None, :, :]          # (B, F, 3)
        u = (tvec * pvec[None, :, :]).sum(axis=2) * inv_det[None, :]
        qvec = np.cross(tvec, edge1[None, :, :])        # (B, F, 3)
        v = (qvec * d).sum(axis=2) * inv_det[None, :]
        t = (edge2[None, :, :] * qvec).sum(axis=2) * inv_det[None, :]
        hit = (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 1e-9)
        count = hit.sum(axis=1)
        inside[qi:qi + batch] = (count % 2) == 1
    return inside


def generate_native_tet(
    vertices: np.ndarray,
    faces: np.ndarray,
    case_dir: Path,
    *,
    target_edge_length: float | None = None,
    seed_density: int = 12,
) -> NativeTetResult:
    """입력 표면 메쉬 → tet polyMesh (MVP).

    Args:
        vertices: (V, 3) 표면 점.
        faces: (F, 3) 표면 triangles (watertight 가정).
        case_dir: OpenFOAM case 디렉터리 (constant/polyMesh 생성됨).
        target_edge_length: 내부 grid spacing. None 이면 bbox_diag / seed_density.
        seed_density: target_edge_length 가 None 일 때 bbox_diag 분할 수.

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
    kept = tets[inside_tet]
    if kept.shape[0] == 0:
        return NativeTetResult(
            False, time.perf_counter() - t0,
            message="inside tet 0 — target_edge_length 조정 필요",
        )

    # 4) 사용된 vertex 만 추출 + 인덱스 압축
    used = np.unique(kept.ravel())
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
    )
