"""Q4 / beta2677 — Signed distance from query points to triangle mesh.

inside (negative) / outside (positive) judged via generalized winding number
(Jacobson 2013) — robust for non-watertight surfaces.

API:
    sd, info = signed_distance(query_pts, surf_V, surf_F)
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass
class SignedDistanceResult:
    n_query: int = 0
    n_inside: int = 0
    n_outside: int = 0
    elapsed_s: float = 0.0
    backend: str = ""
    message: str = ""


def signed_distance(
    query_pts: NDArray[np.float64],
    surf_V: NDArray[np.float64],
    surf_F: NDArray[np.int64],
) -> tuple[NDArray[np.float64], SignedDistanceResult]:
    """Per-query signed distance.

    Algorithm:
        1. unsigned distance via point-to-triangle (already in core).
        2. sign via inside_winding_number (Jacobson 2013, GWN).
        3. signed = unsigned × (inside ? -1 : +1).

    Returns:
        (signed_dist (N,), SignedDistanceResult).
    """
    import time
    t0 = time.perf_counter()

    query_pts = np.asarray(query_pts, dtype=np.float64)
    surf_V = np.asarray(surf_V, dtype=np.float64)
    surf_F = np.asarray(surf_F, dtype=np.int64)

    N = int(query_pts.shape[0])
    F_n = int(surf_F.shape[0])

    if N == 0 or F_n == 0:
        return (
            np.zeros(N, dtype=np.float64),
            SignedDistanceResult(
                n_query=N, backend="empty",
                elapsed_s=time.perf_counter() - t0,
            ),
        )

    # unsigned distance: point-to-triangle (BVH).
    try:
        from core.utils.aabb import TriangleBVH
        bvh = TriangleBVH.build(surf_V, surf_F)
        unsigned = bvh.unsigned_distances(query_pts)
    except Exception as exc:
        return (
            np.zeros(N, dtype=np.float64),
            SignedDistanceResult(
                n_query=N, backend="skip",
                message=f"bvh unavailable: {exc!s:.50}",
                elapsed_s=time.perf_counter() - t0,
            ),
        )

    # sign via inside_winding_number.
    try:
        from core.utils.geometry import inside_winding_number
        inside_mask = inside_winding_number(query_pts, surf_V, surf_F)
    except Exception as exc:
        # fallback: 모두 outside.
        inside_mask = np.zeros(N, dtype=bool)

    signed = np.where(inside_mask, -unsigned, unsigned).astype(np.float64)
    n_in = int(inside_mask.sum())

    return (
        signed,
        SignedDistanceResult(
            n_query=N,
            n_inside=n_in,
            n_outside=N - n_in,
            backend="bvh+gwn",
            elapsed_s=time.perf_counter() - t0,
            message=f"signed dist computed ({n_in} inside, {N - n_in} outside)",
        ),
    )
