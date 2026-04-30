"""V3 / beta2711 — Hex Jacobian min/max stats.

Hex (8-vertex hexahedron) 의 8 corner Jacobian determinant 계산.
J_min < 0  → inverted corner (illegal).
J_min/J_max → scaled jacobian, 1.0 = perfect cube.

Knupp 2003, "Algebraic Mesh Quality Metrics" 의 hex 정의.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass
class HexJacobianResult:
    n_hexes: int = 0
    j_min: float = 0.0
    j_max: float = 0.0
    j_mean: float = 0.0
    n_inverted: int = 0          # at least one corner J < 0.
    scaled_j_min: float = 0.0    # min(J_min/J_max).
    scaled_j_mean: float = 0.0
    elapsed_s: float = 0.0


# CCW hex node order (OpenFOAM): bottom 0-3, top 4-7.
# 8 corners: each corner uses 3 incident edges.
# corner i 의 J = det([e_a, e_b, e_c]) where e_a,b,c are incident edges.
_HEX_CORNER_EDGES = (
    # corner_idx: (neighbor_a, neighbor_b, neighbor_c)
    (0, 1, 3, 4),
    (1, 2, 0, 5),
    (2, 3, 1, 6),
    (3, 0, 2, 7),
    (4, 7, 5, 0),
    (5, 4, 6, 1),
    (6, 5, 7, 2),
    (7, 6, 4, 3),
)


def hex_jacobian_stats(
    pts: NDArray[np.float64],
    hexes: NDArray[np.int64],
) -> HexJacobianResult:
    """hex 8 corner J_det 통계.

    Args:
        pts: (N, 3).
        hexes: (H, 8) 정수 인덱스.

    Returns:
        HexJacobianResult.
    """
    import time
    t0 = time.perf_counter()

    pts = np.asarray(pts, dtype=np.float64)
    hexes = np.asarray(hexes, dtype=np.int64)
    n_h = int(hexes.shape[0])

    if n_h == 0:
        return HexJacobianResult(elapsed_s=time.perf_counter() - t0)

    # gather corner coords: hexes (H, 8) → (H, 8, 3).
    corners = pts[hexes]  # (H, 8, 3).

    # 8 corner J_det.
    j_per_corner = np.zeros((n_h, 8), dtype=np.float64)
    for ci, (c, na, nb, nc) in enumerate(_HEX_CORNER_EDGES):
        e1 = corners[:, na, :] - corners[:, c, :]
        e2 = corners[:, nb, :] - corners[:, c, :]
        e3 = corners[:, nc, :] - corners[:, c, :]
        # det([e1, e2, e3]).
        j_per_corner[:, ci] = np.einsum(
            "ij,ij->i", np.cross(e1, e2), e3,
        )

    j_min = j_per_corner.min(axis=1)
    j_max = j_per_corner.max(axis=1)
    n_inv = int((j_min < 0).sum())
    safe = np.abs(j_max) > 1e-30
    scaled = np.zeros(n_h, dtype=np.float64)
    scaled[safe] = j_min[safe] / np.abs(j_max[safe])

    return HexJacobianResult(
        n_hexes=n_h,
        j_min=float(j_min.min()),
        j_max=float(j_max.max()),
        j_mean=float(j_per_corner.mean()),
        n_inverted=n_inv,
        scaled_j_min=float(scaled.min()),
        scaled_j_mean=float(scaled.mean()),
        elapsed_s=time.perf_counter() - t0,
    )
