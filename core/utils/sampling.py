"""R3 / beta2683 — Triangle mesh uniform surface sampling.

각 face area-weighted 샘플링 → uniform 분포의 surface point cloud 생성.
Hausdorff 측정 / point-cloud 변환 등에 사용.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass
class SamplingResult:
    n_samples: int = 0
    elapsed_s: float = 0.0


def sample_surface_uniform(
    V: NDArray[np.float64],
    F: NDArray[np.int64],
    n_samples: int,
    *,
    seed: int = 42,
) -> tuple[NDArray[np.float64], SamplingResult]:
    """Triangle mesh surface 의 area-weighted uniform sampling.

    Args:
        V: (N, 3) coords.
        F: (M, 3) tri indices.
        n_samples: 출력 sample 수.
        seed: RNG seed.

    Returns:
        (samples (n_samples, 3), SamplingResult).
    """
    import time
    t0 = time.perf_counter()

    V = np.asarray(V, dtype=np.float64)
    F = np.asarray(F, dtype=np.int64)
    n_f = int(F.shape[0])

    if n_f == 0 or n_samples <= 0:
        return np.zeros((0, 3), dtype=np.float64), SamplingResult(elapsed_s=time.perf_counter() - t0)

    rng = np.random.default_rng(seed)

    # face areas.
    e1 = V[F[:, 1]] - V[F[:, 0]]
    e2 = V[F[:, 2]] - V[F[:, 0]]
    fa = 0.5 * np.linalg.norm(np.cross(e1, e2), axis=1)
    fa_total = float(fa.sum())
    if fa_total < 1e-30:
        return np.zeros((0, 3), dtype=np.float64), SamplingResult(elapsed_s=time.perf_counter() - t0)

    # face index choice — probability proportional to area.
    probs = fa / fa_total
    face_choice = rng.choice(n_f, size=int(n_samples), p=probs)

    # barycentric (u, v) in [0, 1] with u+v ≤ 1.
    u = rng.random(int(n_samples))
    v = rng.random(int(n_samples))
    over = u + v > 1
    u[over] = 1 - u[over]
    v[over] = 1 - v[over]
    w = 1 - u - v

    # samples = w*v0 + u*v1 + v*v2.
    v0 = V[F[face_choice, 0]]
    v1 = V[F[face_choice, 1]]
    v2 = V[F[face_choice, 2]]
    samples = (
        w[:, None] * v0
        + u[:, None] * v1
        + v[:, None] * v2
    )

    return samples, SamplingResult(
        n_samples=int(n_samples),
        elapsed_s=time.perf_counter() - t0,
    )
