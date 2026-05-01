"""Z6 / beta2742 — Hex edge stretch metric.

Hex 의 12 edge length → max/min ratio = stretch.
- regular cube → stretch = 1.
- thin slab → stretch = h_thin / h_long.

Knupp 2003 stretch metric (Eq. 13).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass
class HexStretchResult:
    n_hexes: int = 0
    stretch_min: float = 0.0  # min over hexes (worst).
    stretch_max: float = 1.0  # max over hexes (best).
    stretch_mean: float = 0.0
    n_below_0p1: int = 0      # very stretched (< 0.1).
    elapsed_s: float = 0.0


# Hex 12 edges (CCW bottom 0-3, CCW top 4-7, vertical 0-4 etc).
_HEX_EDGES = (
    (0, 1), (1, 2), (2, 3), (3, 0),  # bottom
    (4, 5), (5, 6), (6, 7), (7, 4),  # top
    (0, 4), (1, 5), (2, 6), (3, 7),  # vertical
)


def hex_stretch_stats(
    pts: NDArray[np.float64],
    hexes: NDArray[np.int64],
) -> HexStretchResult:
    """hex 별 stretch = min_edge / max_edge ∈ (0, 1].

    Args:
        pts: (N, 3).
        hexes: (H, 8).

    Returns:
        HexStretchResult.
    """
    import time
    t0 = time.perf_counter()

    pts = np.asarray(pts, dtype=np.float64)
    hexes = np.asarray(hexes, dtype=np.int64)
    n_h = int(hexes.shape[0])

    if n_h == 0:
        return HexStretchResult(elapsed_s=time.perf_counter() - t0)

    corners = pts[hexes]  # (H, 8, 3).

    edge_lens = np.zeros((n_h, 12), dtype=np.float64)
    for i, (a, b) in enumerate(_HEX_EDGES):
        edge_lens[:, i] = np.linalg.norm(
            corners[:, b, :] - corners[:, a, :], axis=-1,
        )

    e_min = edge_lens.min(axis=1)
    e_max = edge_lens.max(axis=1)
    safe = e_max > 1e-30
    stretch = np.zeros(n_h, dtype=np.float64)
    stretch[safe] = e_min[safe] / e_max[safe]

    return HexStretchResult(
        n_hexes=n_h,
        stretch_min=float(stretch.min()),
        stretch_max=float(stretch.max()),
        stretch_mean=float(stretch.mean()),
        n_below_0p1=int((stretch < 0.1).sum()),
        elapsed_s=time.perf_counter() - t0,
    )
