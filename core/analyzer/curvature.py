"""R4 / beta2684 — Vertex Gaussian curvature (angle deficit method).

Discrete Gaussian curvature K_v = (2π - Σ θ_i) / A_v
    θ_i = corner angle at vertex v in incident triangle.
    A_v = 1/3 sum of incident face areas (barycentric).

Reference: Meyer 2003, "Discrete Differential-Geometry Operators for
Triangulated 2-Manifolds".
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass
class CurvatureResult:
    n_vertices: int = 0
    curvature_min: float = 0.0
    curvature_max: float = 0.0
    curvature_mean: float = 0.0
    curvature_total: float = 0.0  # ∫K dA = 2π χ for closed.
    elapsed_s: float = 0.0


def vertex_gaussian_curvature(
    V: NDArray[np.float64],
    F: NDArray[np.int64],
) -> tuple[NDArray[np.float64], CurvatureResult]:
    """Vertex 별 discrete Gaussian curvature.

    Returns:
        (K (N,), CurvatureResult).
    """
    import time
    t0 = time.perf_counter()

    V = np.asarray(V, dtype=np.float64)
    F = np.asarray(F, dtype=np.int64)
    n_v = int(V.shape[0])
    n_f = int(F.shape[0])

    if n_v == 0 or n_f == 0:
        return np.zeros(0, dtype=np.float64), CurvatureResult(
            elapsed_s=time.perf_counter() - t0,
        )

    # angle sum per vertex (corner angles).
    angle_sum = np.zeros(n_v, dtype=np.float64)
    area_sum = np.zeros(n_v, dtype=np.float64)

    for fi in range(n_f):
        a, b, c = int(F[fi, 0]), int(F[fi, 1]), int(F[fi, 2])
        pa, pb, pc = V[a], V[b], V[c]
        # face area (barycentric 1/3).
        face_n = np.cross(pb - pa, pc - pa)
        face_area = 0.5 * float(np.linalg.norm(face_n))
        area_sum[a] += face_area / 3.0
        area_sum[b] += face_area / 3.0
        area_sum[c] += face_area / 3.0

        # corner angles.
        for v_idx, p_v, p_l, p_r in (
            (a, pa, pb, pc),
            (b, pb, pa, pc),
            (c, pc, pa, pb),
        ):
            e1 = p_l - p_v
            e2 = p_r - p_v
            n1 = float(np.linalg.norm(e1))
            n2 = float(np.linalg.norm(e2))
            if n1 < 1e-30 or n2 < 1e-30:
                continue
            cos_t = float(np.dot(e1, e2)) / (n1 * n2)
            cos_t = max(-1.0, min(1.0, cos_t))
            angle_sum[v_idx] += float(np.arccos(cos_t))

    K = np.zeros(n_v, dtype=np.float64)
    safe = area_sum > 1e-30
    K[safe] = (2.0 * np.pi - angle_sum[safe]) / area_sum[safe]

    # boundary vertex 의 expected sum is π (not 2π) — but for closed surface
    # we keep the 2π convention. caller가 boundary detect 후 후처리 권장.

    return K, CurvatureResult(
        n_vertices=n_v,
        curvature_min=float(K.min()) if n_v > 0 else 0.0,
        curvature_max=float(K.max()) if n_v > 0 else 0.0,
        curvature_mean=float(K.mean()) if n_v > 0 else 0.0,
        curvature_total=float((K * area_sum).sum()),
        elapsed_s=time.perf_counter() - t0,
    )
