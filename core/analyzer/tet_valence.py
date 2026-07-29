"""Y1 / beta2730 — Tet vertex valence (degree) stats.

각 vertex 가 몇 개의 tet 에 incident 한지 (= cell valence).
- 이상값 (very high valence) = potential mesh quality issue.
- 평균 valence ≈ 24 (3D Delaunay near-uniform regular).

ML feature 보강 + sliver localization 입력.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

try:
    from core.generator.native_tet._native import (
        tet_vertex_valence_batch as _c_tet_vertex_valence_batch,
    )
except Exception:  # pragma: no cover - native extension optional
    _c_tet_vertex_valence_batch = None


@dataclass
class TetValenceResult:
    n_vertices: int = 0
    n_used: int = 0           # tet 에 등장하는 vertex 수.
    valence_min: int = 0
    valence_max: int = 0
    valence_mean: float = 0.0
    valence_p99: float = 0.0
    n_above_50: int = 0       # very high valence count.
    n_isolated: int = 0       # valence == 0.
    elapsed_s: float = 0.0


def tet_vertex_valence(
    n_vertices: int,
    tets: NDArray[np.int64],
) -> tuple[NDArray[np.int64], TetValenceResult]:
    """vertex 별 incident tet count.

    Args:
        n_vertices: 전체 vertex 수.
        tets: (T, 4).

    Returns:
        (valence (n_vertices,) int64, TetValenceResult).
    """
    import time
    t0 = time.perf_counter()

    tets = np.asarray(tets, dtype=np.int64)
    n_v = int(n_vertices)

    if n_v == 0 or tets.shape[0] == 0:
        return np.zeros(n_v, dtype=np.int64), TetValenceResult(
            n_vertices=n_v,
            elapsed_s=time.perf_counter() - t0,
        )

    if _c_tet_vertex_valence_batch is not None:
        native = _c_tet_vertex_valence_batch(tets, n_v)
        if native is not None:
            valence, stats, floats = native
            return valence, TetValenceResult(
                n_vertices=n_v,
                n_used=stats[0],
                valence_min=stats[1],
                valence_max=stats[2],
                valence_mean=floats[0],
                valence_p99=floats[1],
                n_above_50=stats[3],
                n_isolated=stats[4],
                elapsed_s=time.perf_counter() - t0,
            )

    valence = np.bincount(tets.reshape(-1), minlength=n_v).astype(np.int64)
    used = valence > 0
    n_used = int(used.sum())
    n_isolated = n_v - n_used

    if n_used == 0:
        return valence, TetValenceResult(
            n_vertices=n_v,
            n_used=0,
            n_isolated=n_isolated,
            elapsed_s=time.perf_counter() - t0,
        )

    used_v = valence[used]
    return valence, TetValenceResult(
        n_vertices=n_v,
        n_used=n_used,
        valence_min=int(used_v.min()),
        valence_max=int(used_v.max()),
        valence_mean=float(used_v.mean()),
        valence_p99=float(np.percentile(used_v, 99)),
        n_above_50=int((used_v > 50).sum()),
        n_isolated=n_isolated,
        elapsed_s=time.perf_counter() - t0,
    )
