"""DD2 / beta2786 — surface sharp corner vertex detector.

각 vertex 의 incident face normals 의 평균 각도 분산 → 큰 분산 = sharp corner.
- corner = 3+ feature edge incident vertex (multi-edge sharp meeting point).
- snap target / preserve 후보 입력.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass
class SharpCornerResult:
    n_vertices: int = 0
    n_sharp_corners: int = 0
    n_smooth_vertices: int = 0
    elapsed_s: float = 0.0


def detect_sharp_corners(
    V: NDArray[np.float64],
    F: NDArray[np.int64],
    *,
    angle_threshold_deg: float = 60.0,
) -> tuple[NDArray[np.bool_], SharpCornerResult]:
    """vertex 별 normal divergence 가 임계 이상이면 sharp corner.

    Args:
        V: (N, 3).
        F: (M, 3).
        angle_threshold_deg: incident face normal 간 max angle 이 이값 초과면 sharp.

    Returns:
        (is_corner (N,) bool, SharpCornerResult).
    """
    import time
    t0 = time.perf_counter()

    V = np.asarray(V, dtype=np.float64)
    F = np.asarray(F, dtype=np.int64)
    n_v = int(V.shape[0])
    n_f = int(F.shape[0])

    if n_v == 0 or n_f == 0:
        return np.zeros(n_v, dtype=bool), SharpCornerResult(
            n_vertices=n_v,
            elapsed_s=time.perf_counter() - t0,
        )

    # face normals.
    e1 = V[F[:, 1]] - V[F[:, 0]]
    e2 = V[F[:, 2]] - V[F[:, 0]]
    fn = np.cross(e1, e2)
    fn_norm = np.linalg.norm(fn, axis=1)
    safe = fn_norm > 1e-30
    fn[safe] = fn[safe] / fn_norm[safe, None]

    # vertex → list of face normals.
    vert_to_faces: list[list[int]] = [[] for _ in range(n_v)]
    for fi in range(n_f):
        for k in range(3):
            vert_to_faces[int(F[fi, k])].append(fi)

    is_corner = np.zeros(n_v, dtype=bool)
    cos_thr = float(np.cos(np.radians(angle_threshold_deg)))

    for vi in range(n_v):
        fids = vert_to_faces[vi]
        if len(fids) < 2:
            continue
        ns = fn[fids]
        # max angle = min cos.
        # naive: pair-wise dot, find min.
        min_cos = 1.0
        for a in range(len(fids)):
            for b in range(a + 1, len(fids)):
                c = float(np.dot(ns[a], ns[b]))
                if c < min_cos:
                    min_cos = c
        if min_cos < cos_thr:
            is_corner[vi] = True

    n_corner = int(is_corner.sum())
    return is_corner, SharpCornerResult(
        n_vertices=n_v,
        n_sharp_corners=n_corner,
        n_smooth_vertices=n_v - n_corner,
        elapsed_s=time.perf_counter() - t0,
    )
