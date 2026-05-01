"""BB1 / beta2751 — tet circumsphere + Delaunay-ness check.

각 tet 의 circumcenter + radius 계산.
- 다른 vertex 가 그 sphere 안에 있는지 → non-Delaunay (locally).
- Delaunay tet 일수록 mesh quality 좋음.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass
class CircumsphereResult:
    n_tets: int = 0
    radius_min: float = 0.0
    radius_max: float = 0.0
    radius_mean: float = 0.0
    n_degenerate: int = 0   # circumcenter 못 구함.
    elapsed_s: float = 0.0


def tet_circumspheres(
    pts: NDArray[np.float64],
    tets: NDArray[np.int64],
) -> tuple[NDArray[np.float64], NDArray[np.float64], CircumsphereResult]:
    """tet 별 circumcenter + radius.

    System: |p_i - C|^2 = R^2 → 3 equations (linear in C, R^2).

    Returns:
        (centers (T, 3), radii (T,), result).
    """
    import time
    t0 = time.perf_counter()

    pts = np.asarray(pts, dtype=np.float64)
    tets = np.asarray(tets, dtype=np.int64)
    n_t = int(tets.shape[0])

    if n_t == 0:
        return (
            np.zeros((0, 3), dtype=np.float64),
            np.zeros(0, dtype=np.float64),
            CircumsphereResult(elapsed_s=time.perf_counter() - t0),
        )

    a = pts[tets[:, 0]]; b = pts[tets[:, 1]]
    c = pts[tets[:, 2]]; d = pts[tets[:, 3]]

    # Solve A * C = rhs where:
    # A_i = 2 * (p_i - p_0), rhs_i = |p_i|^2 - |p_0|^2  (i = 1, 2, 3).
    A = np.stack([
        2 * (b - a), 2 * (c - a), 2 * (d - a),
    ], axis=1)  # (T, 3, 3).

    rhs = np.stack([
        (b * b).sum(axis=1) - (a * a).sum(axis=1),
        (c * c).sum(axis=1) - (a * a).sum(axis=1),
        (d * d).sum(axis=1) - (a * a).sum(axis=1),
    ], axis=1)  # (T, 3).

    centers = np.zeros((n_t, 3), dtype=np.float64)
    radii = np.zeros(n_t, dtype=np.float64)
    n_deg = 0

    for i in range(n_t):
        try:
            C = np.linalg.solve(A[i], rhs[i])
            centers[i] = C
            radii[i] = float(np.linalg.norm(a[i] - C))
        except np.linalg.LinAlgError:
            n_deg += 1
            centers[i] = a[i]
            radii[i] = 0.0

    safe_r = radii[radii > 0]
    return centers, radii, CircumsphereResult(
        n_tets=n_t,
        radius_min=float(safe_r.min()) if safe_r.size > 0 else 0.0,
        radius_max=float(safe_r.max()) if safe_r.size > 0 else 0.0,
        radius_mean=float(safe_r.mean()) if safe_r.size > 0 else 0.0,
        n_degenerate=n_deg,
        elapsed_s=time.perf_counter() - t0,
    )
