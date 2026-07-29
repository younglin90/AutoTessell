"""P1 / beta2667 — Geometry KPI report.

Surface mesh 의 종합 KPI: bbox / 부피 (signed) / surface area / Euler 특성 / 종속 통계.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

try:
    from core.generator.native_tet._native import (
        surface_area_volume_stats_batch as _c_surface_area_volume_stats_batch,
        surface_edge_stats_batch as _c_surface_edge_stats_batch,
    )
except Exception:  # pragma: no cover - optional native extension
    _c_surface_area_volume_stats_batch = None
    _c_surface_edge_stats_batch = None


@dataclass
class GeometryKPIResult:
    n_vertices: int = 0
    n_faces: int = 0
    n_edges: int = 0
    bbox_min: tuple[float, float, float] = (0.0, 0.0, 0.0)
    bbox_max: tuple[float, float, float] = (0.0, 0.0, 0.0)
    bbox_diag: float = 0.0
    bbox_volume: float = 0.0
    surface_area: float = 0.0
    enclosed_volume: float = 0.0   # signed (closed mesh).
    euler_characteristic: int = 0   # V - E + F (closed sphere=2).
    genus_estimate: int = 0          # (2 - chi) / 2 (orientable).
    elapsed_s: float = 0.0


def compute_geometry_kpi(
    V: NDArray[np.float64],
    F: NDArray[np.int64],
) -> GeometryKPIResult:
    """Surface mesh KPI 종합."""
    import time
    t0 = time.perf_counter()

    V = np.asarray(V, dtype=np.float64)
    F = np.asarray(F, dtype=np.int64)
    n_v = int(V.shape[0])
    n_f = int(F.shape[0])

    if n_v == 0 or n_f == 0:
        return GeometryKPIResult(
            n_vertices=n_v, n_faces=n_f,
            elapsed_s=time.perf_counter() - t0,
        )

    bmin = V.min(axis=0)
    bmax = V.max(axis=0)
    extents = bmax - bmin
    bbox_diag = float(np.linalg.norm(extents))
    bbox_vol = float(extents[0] * extents[1] * extents[2])

    native_area_volume = None
    if _c_surface_area_volume_stats_batch is not None:
        native_area_volume = _c_surface_area_volume_stats_batch(V, F)
    if native_area_volume is not None:
        surf_area, enclosed_vol, _native_bbox_vol = native_area_volume
        surf_area = float(surf_area)
        enclosed_vol = float(enclosed_vol)
    else:
        # surface area.
        e1 = V[F[:, 1]] - V[F[:, 0]]
        e2 = V[F[:, 2]] - V[F[:, 0]]
        cross = np.cross(e1, e2)
        face_areas = 0.5 * np.linalg.norm(cross, axis=1)
        surf_area = float(face_areas.sum())

        # signed volume (divergence theorem).
        # V = (1/6) Σ ((p0 × p1) · p2).
        p0 = V[F[:, 0]]; p1 = V[F[:, 1]]; p2 = V[F[:, 2]]
        enclosed_vol = float(((np.cross(p0, p1) * p2).sum(axis=1)).sum()) / 6.0

    native_edge_stats = None
    if _c_surface_edge_stats_batch is not None:
        native_edge_stats = _c_surface_edge_stats_batch(F)
    if native_edge_stats is not None:
        n_e = int(native_edge_stats[0])
    else:
        # edge count (unique).
        edges_per_face = np.stack([
            F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]],
        ], axis=1).reshape(-1, 2)
        edges_canon = np.sort(edges_per_face, axis=1)
        # unique edges.
        keys = edges_canon[:, 0].astype(np.int64) * (n_v + 1) + edges_canon[:, 1].astype(np.int64)
        n_e = int(np.unique(keys).size)

    # Euler χ = V - E + F.
    chi = n_v - n_e + n_f
    # closed orientable: χ = 2 - 2g.
    genus = max(0, (2 - chi) // 2)

    return GeometryKPIResult(
        n_vertices=n_v, n_faces=n_f, n_edges=n_e,
        bbox_min=tuple(map(float, bmin)),
        bbox_max=tuple(map(float, bmax)),
        bbox_diag=bbox_diag,
        bbox_volume=bbox_vol,
        surface_area=surf_area,
        enclosed_volume=enclosed_vol,
        euler_characteristic=chi,
        genus_estimate=genus,
        elapsed_s=time.perf_counter() - t0,
    )
