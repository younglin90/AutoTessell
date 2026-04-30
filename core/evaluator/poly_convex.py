"""W1 / beta2716 — Polyhedral cell convexity check.

각 poly cell 의 vertex 들이 face plane 의 같은 쪽에 있는지 (convex test).
non-convex 셀 비율 → mesh quality 진단 + Strategist 재시도 신호.

Note: 정확한 cell-by-face 검증을 위해서는 OpenFOAM polyMesh 의 face/cell 인접성이
필요. 여기서는 간단화: cell 별 vertex 집합 + face plane 들이 주어진다고 가정.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass
class PolyConvexResult:
    n_cells: int = 0
    n_convex: int = 0
    n_non_convex: int = 0
    convex_ratio: float = 1.0
    max_violation: float = 0.0  # max signed distance of vertex outside face plane.
    elapsed_s: float = 0.0


def poly_cell_convex(
    pts: NDArray[np.float64],
    cell_vertices: list[NDArray[np.int64]],
    cell_face_planes: list[NDArray[np.float64]],
    *,
    tol: float = 1e-9,
) -> PolyConvexResult:
    """cell 별 convex 검증.

    Args:
        pts: (N, 3).
        cell_vertices: [cell0_v_indices, cell1_v_indices, ...] each (k_i,).
        cell_face_planes: [cell0_planes, cell1_planes, ...] each (n_face_i, 4)
            여기서 plane = (a, b, c, d) → a*x + b*y + c*z + d = 0,
            inward normal 가정 (cell 내부 점 → a*x+b*y+c*z+d <= 0).
        tol: violation tolerance.

    Returns:
        PolyConvexResult.
    """
    import time
    t0 = time.perf_counter()

    pts = np.asarray(pts, dtype=np.float64)
    n_cells = len(cell_vertices)

    if n_cells == 0:
        return PolyConvexResult(elapsed_s=time.perf_counter() - t0)

    n_convex = 0
    max_viol = 0.0

    for ci in range(n_cells):
        v_idx = np.asarray(cell_vertices[ci], dtype=np.int64)
        planes = np.asarray(cell_face_planes[ci], dtype=np.float64)
        if v_idx.size == 0 or planes.size == 0:
            n_convex += 1
            continue

        v_pts = pts[v_idx]  # (k, 3).
        # signed distance: a*x + b*y + c*z + d.
        # broadcast: (n_face, 1, 4) vs (1, k, 3+1) → use planes[:, :3] @ v_pts.T + planes[:, 3].
        n = planes[:, :3]   # (n_face, 3).
        d = planes[:, 3]    # (n_face,).
        signed = (v_pts @ n.T) + d  # (k, n_face).

        # convex: 모든 vertex 가 inward (≤ tol).
        viol = np.maximum(signed.max(), 0.0)
        if viol > tol:
            max_viol = max(max_viol, float(viol))
        else:
            n_convex += 1

    n_non = n_cells - n_convex
    return PolyConvexResult(
        n_cells=n_cells,
        n_convex=n_convex,
        n_non_convex=n_non,
        convex_ratio=float(n_convex) / max(n_cells, 1),
        max_violation=max_viol,
        elapsed_s=time.perf_counter() - t0,
    )
