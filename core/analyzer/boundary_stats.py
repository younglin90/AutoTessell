"""T6 / beta2700 — Native tet/poly mesh 의 boundary vertex statistics.

surface vertex 비율 / interior vertex 분포 / boundary edge length 분석.
mesh quality 진단 + ML feature 보강 입력.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

try:
    from core.generator.native_tet._native import (
        tet_boundary_vertex_stats_batch as _c_tet_boundary_vertex_stats_batch,
    )
except Exception:  # pragma: no cover - native extension optional
    _c_tet_boundary_vertex_stats_batch = None


@dataclass
class BoundaryStatsResult:
    n_total_vertices: int = 0
    n_surface_vertices: int = 0   # 입력 surface 와 일치 (idx < n_input).
    n_interior_vertices: int = 0  # idx >= n_input.
    n_boundary_tets: int = 0       # 1+ surface vertex.
    n_interior_tets: int = 0
    surface_ratio: float = 0.0
    elapsed_s: float = 0.0


def boundary_vertex_stats(
    pts: NDArray[np.float64],
    tets: NDArray[np.int64],
    n_input_surface_verts: int,
) -> BoundaryStatsResult:
    """surface (input) vs interior (added) vertex 분류.

    Native tet pipeline 에서 surface vertex 는 [0, n_input) 인덱스,
    interior 는 [n_input, ∞).

    Args:
        pts: (N, 3).
        tets: (T, 4).
        n_input_surface_verts: 입력 surface 의 vertex 수.

    Returns:
        BoundaryStatsResult.
    """
    import time
    t0 = time.perf_counter()

    pts = np.asarray(pts, dtype=np.float64)
    tets = np.asarray(tets, dtype=np.int64)
    n_v = int(pts.shape[0])
    n_t = int(tets.shape[0])

    if n_v == 0:
        return BoundaryStatsResult(elapsed_s=time.perf_counter() - t0)

    n_surf = min(int(n_input_surface_verts), n_v)
    n_int = n_v - n_surf

    # surface vertex 인 tets 카운트 (≥1 surface idx).
    native_counts = (
        _c_tet_boundary_vertex_stats_batch(tets, n_surf)
        if _c_tet_boundary_vertex_stats_batch is not None and n_t > 0
        else None
    )
    if native_counts is not None:
        n_bnd_tets, n_int_tets = native_counts
    elif n_t > 0:
        is_surface_v = tets < n_surf  # (T, 4) bool.
        n_bnd_tets = int(is_surface_v.any(axis=1).sum())
        n_int_tets = n_t - n_bnd_tets
    else:
        n_bnd_tets = 0
        n_int_tets = 0

    return BoundaryStatsResult(
        n_total_vertices=n_v,
        n_surface_vertices=n_surf,
        n_interior_vertices=n_int,
        n_boundary_tets=n_bnd_tets,
        n_interior_tets=n_int_tets,
        surface_ratio=float(n_surf) / max(n_v, 1),
        elapsed_s=time.perf_counter() - t0,
    )
