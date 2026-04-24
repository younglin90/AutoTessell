"""Phase D2 — BVH-anchored surface snapping.

Smoothing 이나 local ops 로 drift 된 surface vertex 를 입력 표면 위로 projection.
fTetWild 가 매 iteration 말에 수행하는 "snap to boundary" 의 기본 아이디어.

레퍼런스
    - Hu et al. 2020 (fTetWild, MPL-2.0) §3.3 snap-to-boundary.
    - Botsch et al. 2010 §5.5.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from core.utils.aabb import TriangleBVH


@dataclass
class SnapResult:
    n_snapped: int
    max_displacement: float


def snap_surface_vertices(
    pts: np.ndarray,
    bvh: TriangleBVH,
    surface_vertex_ids: np.ndarray,
    *,
    max_distance: float | None = None,
    locked_vertex_ids: np.ndarray | None = None,
) -> SnapResult:
    """pts in-place 업데이트. surface_vertex_ids 각각을 BVH 상 가장 가까운 점
    으로 projection.

    Args:
        pts: (N, 3), in-place.
        bvh: 입력 표면 BVH.
        surface_vertex_ids: projection 대상 vertex index.
        max_distance: 이 거리보다 멀면 skip (신뢰할 수 없는 이동 방지).
            None 이면 무제한.
        locked_vertex_ids: 이 집합에 속하면 projection 하지 않음.

    Returns:
        SnapResult.
    """
    pts = np.asarray(pts, dtype=np.float64)
    ids = np.asarray(surface_vertex_ids, dtype=np.int64).ravel()
    locked = set()
    if locked_vertex_ids is not None:
        locked = set(int(x) for x in np.asarray(locked_vertex_ids).ravel())

    max_disp = 0.0
    n_snap = 0
    for vid in ids:
        vi = int(vid)
        if vi in locked:
            continue
        p = pts[vi]
        cp, d, _ti = bvh.closest_point(p)
        if max_distance is not None and d > float(max_distance):
            continue
        disp = float(np.linalg.norm(cp - p))
        if disp > 0:
            pts[vi] = cp
            n_snap += 1
            if disp > max_disp:
                max_disp = disp
    return SnapResult(n_snapped=int(n_snap), max_displacement=float(max_disp))
