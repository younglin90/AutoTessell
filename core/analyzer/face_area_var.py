"""BB2 / beta2752 — surface face area variance / uniformity.

triangle face area distribution: mean / std / cv (coefficient of variation).
- 균일한 mesh → cv 작음 (< 0.3).
- adaptive (curvature-driven) mesh → cv 큼.

Strategist 의 mesh density 결정 입력.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass
class FaceAreaVarResult:
    n_triangles: int = 0
    area_min: float = 0.0
    area_max: float = 0.0
    area_mean: float = 0.0
    area_std: float = 0.0
    cv: float = 0.0       # coeff of variation (std / mean).
    p99_to_p01: float = 0.0  # area ratio (extreme spread).
    elapsed_s: float = 0.0


def face_area_variance(
    V: NDArray[np.float64],
    F: NDArray[np.int64],
) -> FaceAreaVarResult:
    """tri area 분포 통계.

    Returns:
        FaceAreaVarResult.
    """
    import time
    t0 = time.perf_counter()

    V = np.asarray(V, dtype=np.float64)
    F = np.asarray(F, dtype=np.int64)
    n_f = int(F.shape[0])

    if n_f == 0 or V.shape[0] == 0:
        return FaceAreaVarResult(elapsed_s=time.perf_counter() - t0)

    a = V[F[:, 0]]; b = V[F[:, 1]]; c = V[F[:, 2]]
    cross = np.cross(b - a, c - a)
    areas = 0.5 * np.linalg.norm(cross, axis=1)

    a_mean = float(areas.mean())
    a_std = float(areas.std())
    cv = a_std / max(a_mean, 1e-30)

    p01, p99 = np.percentile(areas, [1, 99])
    ratio = float(p99) / max(float(p01), 1e-30)

    return FaceAreaVarResult(
        n_triangles=n_f,
        area_min=float(areas.min()),
        area_max=float(areas.max()),
        area_mean=a_mean,
        area_std=a_std,
        cv=float(cv),
        p99_to_p01=ratio,
        elapsed_s=time.perf_counter() - t0,
    )
