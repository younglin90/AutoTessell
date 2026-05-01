"""CC5 / beta2762 — tet centroid + bbox + spatial distribution stats.

각 tet 의 centroid (4 vertex 평균) → 전체 mesh 의 spatial distribution.
- centroid bbox (mesh interior 추정).
- centroid std (uniform vs clustered distribution).

CVT3D Lloyd / sampling density / parallel partition 입력.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass
class TetCentroidResult:
    n_tets: int = 0
    centroid_bbox_min: tuple[float, float, float] = (0.0, 0.0, 0.0)
    centroid_bbox_max: tuple[float, float, float] = (0.0, 0.0, 0.0)
    centroid_std: tuple[float, float, float] = (0.0, 0.0, 0.0)
    centroid_mean: tuple[float, float, float] = (0.0, 0.0, 0.0)
    elapsed_s: float = 0.0


def tet_centroids(
    pts: NDArray[np.float64],
    tets: NDArray[np.int64],
) -> tuple[NDArray[np.float64], TetCentroidResult]:
    """tet 별 centroid (T, 3) + 전체 분포 통계.

    Returns:
        (centroids (T, 3), TetCentroidResult).
    """
    import time
    t0 = time.perf_counter()

    pts = np.asarray(pts, dtype=np.float64)
    tets = np.asarray(tets, dtype=np.int64)
    n_t = int(tets.shape[0])

    if n_t == 0:
        return np.zeros((0, 3), dtype=np.float64), TetCentroidResult(
            elapsed_s=time.perf_counter() - t0,
        )

    centroids = pts[tets].mean(axis=1)  # (T, 3).

    bb_min = centroids.min(axis=0)
    bb_max = centroids.max(axis=0)
    c_std = centroids.std(axis=0)
    c_mean = centroids.mean(axis=0)

    return centroids, TetCentroidResult(
        n_tets=n_t,
        centroid_bbox_min=tuple(float(x) for x in bb_min),
        centroid_bbox_max=tuple(float(x) for x in bb_max),
        centroid_std=tuple(float(x) for x in c_std),
        centroid_mean=tuple(float(x) for x in c_mean),
        elapsed_s=time.perf_counter() - t0,
    )
