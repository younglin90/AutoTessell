"""Y2 / beta2731 — surface mean curvature vector (Laplace-Beltrami).

H_v = (1/2A_v) * Σ (cot α + cot β) * (p_j - p_v)
    A_v = 1/3 sum incident face areas (barycentric).
    α, β = opposite angles to edge (v, j).

Reference: Meyer 2003, "Discrete Differential Geometry Operators".

|H_v| 이 큰 영역 = 곡률 큰 영역 = remesh density 늘릴 후보.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass
class MeanCurvatureResult:
    n_vertices: int = 0
    h_norm_min: float = 0.0
    h_norm_max: float = 0.0
    h_norm_mean: float = 0.0
    h_norm_p99: float = 0.0
    elapsed_s: float = 0.0


def vertex_mean_curvature(
    V: NDArray[np.float64],
    F: NDArray[np.int64],
) -> tuple[NDArray[np.float64], MeanCurvatureResult]:
    """vertex 별 mean curvature vector H (N, 3).

    Returns:
        (H (N, 3), MeanCurvatureResult).
    """
    import time
    t0 = time.perf_counter()

    V = np.asarray(V, dtype=np.float64)
    F = np.asarray(F, dtype=np.int64)
    n_v = int(V.shape[0])
    n_f = int(F.shape[0])

    if n_v == 0 or n_f == 0:
        return np.zeros((n_v, 3), dtype=np.float64), MeanCurvatureResult(
            n_vertices=n_v,
            elapsed_s=time.perf_counter() - t0,
        )

    H = np.zeros((n_v, 3), dtype=np.float64)
    A = np.zeros(n_v, dtype=np.float64)

    for fi in range(n_f):
        a, b, c = int(F[fi, 0]), int(F[fi, 1]), int(F[fi, 2])
        pa, pb, pc = V[a], V[b], V[c]

        face_n = np.cross(pb - pa, pc - pa)
        face_area = 0.5 * float(np.linalg.norm(face_n))
        if face_area < 1e-30:
            continue

        # cot α (opposite a) — angle at a.
        # cot of angle between (pb-pa) and (pc-pa).
        e_ab = pb - pa
        e_ac = pc - pa
        e_bc = pc - pb
        e_ba = -e_ab
        e_cb = -e_bc
        e_ca = -e_ac

        def _cot(u, v):
            num = float(np.dot(u, v))
            den = float(np.linalg.norm(np.cross(u, v)))
            return num / max(den, 1e-30)

        cot_a = _cot(e_ab, e_ac)
        cot_b = _cot(e_ba, e_bc)
        cot_c = _cot(e_ca, e_cb)

        # 각 edge 에 cot of opposite angle * (p_j - p_v).
        # edge (a,b): opposite c → cot_c * (pb-pa) at a, *(pa-pb) at b.
        H[a] += cot_c * (pb - pa) + cot_b * (pc - pa)
        H[b] += cot_c * (pa - pb) + cot_a * (pc - pb)
        H[c] += cot_b * (pa - pc) + cot_a * (pb - pc)

        A[a] += face_area / 3.0
        A[b] += face_area / 3.0
        A[c] += face_area / 3.0

    safe = A > 1e-30
    H[safe] = H[safe] / (2.0 * A[safe, None])
    H[~safe] = 0.0

    h_norm = np.linalg.norm(H, axis=1)
    return H, MeanCurvatureResult(
        n_vertices=n_v,
        h_norm_min=float(h_norm.min()),
        h_norm_max=float(h_norm.max()),
        h_norm_mean=float(h_norm.mean()),
        h_norm_p99=float(np.percentile(h_norm, 99)),
        elapsed_s=time.perf_counter() - t0,
    )
