"""Z5 / beta2741 — bbox octant split.

mesh 의 bbox 를 8 octant 로 분할 → 각 vertex 의 octant 인덱스 (0-7).
- divide-and-conquer 알고리즘 입력 (parallel mesh build).
- KDTree / Octree 의 단순 1-level 버전.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass
class OctantSplitResult:
    n_points: int = 0
    bbox_min: tuple[float, float, float] = (0.0, 0.0, 0.0)
    bbox_max: tuple[float, float, float] = (0.0, 0.0, 0.0)
    bbox_center: tuple[float, float, float] = (0.0, 0.0, 0.0)
    counts: tuple = ()  # 8 octant counts.
    elapsed_s: float = 0.0


def octant_assign(
    pts: NDArray[np.float64],
    *,
    center: NDArray[np.float64] | None = None,
) -> tuple[NDArray[np.int64], OctantSplitResult]:
    """각 vertex → 0~7 octant idx (xyz bit packing).

    octant idx = 4*x_bit + 2*y_bit + z_bit, bit = (coord >= center).

    Args:
        pts: (N, 3).
        center: (3,) optional. None → bbox center.

    Returns:
        (octant (N,) int64 in [0..7], OctantSplitResult).
    """
    import time
    t0 = time.perf_counter()

    pts = np.asarray(pts, dtype=np.float64)
    n = int(pts.shape[0])

    if n == 0:
        return np.zeros(0, dtype=np.int64), OctantSplitResult(
            elapsed_s=time.perf_counter() - t0,
        )

    bb_min = pts.min(axis=0)
    bb_max = pts.max(axis=0)
    if center is None:
        center = (bb_min + bb_max) / 2.0
    center = np.asarray(center, dtype=np.float64)

    bits = (pts >= center).astype(np.int64)  # (N, 3).
    octant = bits[:, 0] * 4 + bits[:, 1] * 2 + bits[:, 2]

    counts = tuple(int((octant == k).sum()) for k in range(8))

    return octant, OctantSplitResult(
        n_points=n,
        bbox_min=tuple(float(x) for x in bb_min),
        bbox_max=tuple(float(x) for x in bb_max),
        bbox_center=tuple(float(x) for x in center),
        counts=counts,
        elapsed_s=time.perf_counter() - t0,
    )
