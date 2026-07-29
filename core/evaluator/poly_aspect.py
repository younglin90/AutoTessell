"""DD6 / beta2790 — Poly cell aspect ratio (bbox-based).

각 cell vertex 들의 bbox → max_extent / min_extent.
isotropic cell ≈ 1, stretched > 5.

Strategist 의 cell 적합도 판단 + 진단.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

try:
    from core.generator.native_tet._native import (
        poly_aspect_stats_batch as _c_poly_aspect_stats_batch,
    )
except Exception:  # pragma: no cover - native extension optional
    _c_poly_aspect_stats_batch = None


@dataclass
class PolyAspectResult:
    n_cells: int = 0
    aspect_min: float = 0.0
    aspect_max: float = 0.0
    aspect_mean: float = 0.0
    n_above_5: int = 0


def poly_cell_aspect(
    pts: NDArray[np.float64],
    cell_vertices: list,
) -> PolyAspectResult:
    """cell 별 bbox aspect.

    Args:
        pts: (N, 3).
        cell_vertices: list of vertex_idx arrays per cell.

    Returns:
        PolyAspectResult.
    """
    pts = np.asarray(pts, dtype=np.float64)
    n_cells = len(cell_vertices)
    if n_cells == 0:
        return PolyAspectResult()

    if _c_poly_aspect_stats_batch is not None:
        native = _c_poly_aspect_stats_batch(pts, cell_vertices)
        if native is not None:
            stats, n_above_5, n_valid = native
            if n_valid == 0:
                return PolyAspectResult(n_cells=n_cells)
            return PolyAspectResult(
                n_cells=n_cells,
                aspect_min=stats[0],
                aspect_max=stats[1],
                aspect_mean=stats[2],
                n_above_5=n_above_5,
            )

    aspects = []
    for cv in cell_vertices:
        v_idx = np.asarray(cv, dtype=np.int64)
        if v_idx.size < 4:
            continue
        verts = pts[v_idx]
        ext = verts.max(axis=0) - verts.min(axis=0)
        ext_min = float(ext.min())
        if ext_min < 1e-30:
            aspects.append(1e6)
        else:
            aspects.append(float(ext.max() / ext_min))

    if not aspects:
        return PolyAspectResult(n_cells=n_cells)

    arr = np.array(aspects, dtype=np.float64)
    return PolyAspectResult(
        n_cells=n_cells,
        aspect_min=float(arr.min()),
        aspect_max=float(arr.max()),
        aspect_mean=float(arr.mean()),
        n_above_5=int((arr > 5.0).sum()),
    )
