"""X2 / beta2724 — surface area + enclosed volume integral.

Watertight surface 의 면적 / 부피 계산.
- area = sum(0.5 * |e1 × e2|)
- volume = (1/6) * sum( v0 · (v1 × v2) )  (divergence theorem, signed)

mesh sanity check + L2/L3 remesh 효과 측정 + Hausdorff 기반 비교.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

try:
    from core.generator.native_tet._native import (
        surface_area_volume_stats_batch as _c_surface_area_volume_stats_batch,
    )
except Exception:  # pragma: no cover - optional native extension
    _c_surface_area_volume_stats_batch = None


@dataclass
class SurfaceVolumeResult:
    n_triangles: int = 0
    surface_area: float = 0.0
    enclosed_volume: float = 0.0  # signed (depends on orientation).
    bbox_volume: float = 0.0
    fill_ratio: float = 0.0       # |volume| / bbox_volume.
    elapsed_s: float = 0.0


def surface_volume_integral(
    V: NDArray[np.float64],
    F: NDArray[np.int64],
) -> SurfaceVolumeResult:
    """area + signed volume.

    면적: triangle area 합.
    부피: divergence theorem — closed surface 가정, sign 은 winding 에 따라.
    """
    import time
    t0 = time.perf_counter()

    V = np.asarray(V, dtype=np.float64)
    F = np.asarray(F, dtype=np.int64)
    n_f = int(F.shape[0])

    if n_f == 0 or V.shape[0] == 0:
        return SurfaceVolumeResult(elapsed_s=time.perf_counter() - t0)

    if _c_surface_area_volume_stats_batch is not None:
        native = _c_surface_area_volume_stats_batch(V, F)
        if native is not None:
            area, vol, bbox_vol = native
            fill = abs(vol) / max(bbox_vol, 1e-30)
            return SurfaceVolumeResult(
                n_triangles=n_f,
                surface_area=float(area),
                enclosed_volume=float(vol),
                bbox_volume=float(bbox_vol),
                fill_ratio=float(fill),
                elapsed_s=time.perf_counter() - t0,
            )

    a = V[F[:, 0]]
    b = V[F[:, 1]]
    c = V[F[:, 2]]

    cross_ab = np.cross(b - a, c - a)
    area_each = 0.5 * np.linalg.norm(cross_ab, axis=1)
    area = float(area_each.sum())

    # signed volume = sum(a · (b × c)) / 6.
    vol_each = np.einsum("ij,ij->i", a, np.cross(b, c)) / 6.0
    vol = float(vol_each.sum())

    bbox = (V.max(axis=0) - V.min(axis=0))
    bbox_vol = float(np.prod(np.maximum(bbox, 0.0)))
    fill = abs(vol) / max(bbox_vol, 1e-30)

    return SurfaceVolumeResult(
        n_triangles=n_f,
        surface_area=area,
        enclosed_volume=vol,
        bbox_volume=bbox_vol,
        fill_ratio=float(fill),
        elapsed_s=time.perf_counter() - t0,
    )
