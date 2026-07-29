"""Y6 / beta2735 — Hex 6 face area stats.

Hex (8-vertex) 의 6 quad face area + face area ratio (max/min).
- ratio 클수록 hex 가 stretched.
- regular cube → ratio = 1.

Knupp 2003, "Algebraic Mesh Quality" 의 hex face metric.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

try:
    from core.generator.native_tet._native import (
        hex_face_area_stats_batch as _c_hex_face_area_stats_batch,
    )
except Exception:  # pragma: no cover - native extension optional
    _c_hex_face_area_stats_batch = None


@dataclass
class HexFaceAreaResult:
    n_hexes: int = 0
    area_min: float = 0.0
    area_max: float = 0.0
    area_mean: float = 0.0
    ratio_max: float = 0.0  # max(face_max / face_min) over hexes.
    ratio_mean: float = 0.0
    n_stretched: int = 0    # ratio > 5 count.
    elapsed_s: float = 0.0


# Hex 6 face (CCW outward, OpenFOAM order).
_HEX_FACES = (
    (0, 3, 2, 1),  # bottom (-z)
    (4, 5, 6, 7),  # top (+z)
    (0, 1, 5, 4),  # -y
    (2, 3, 7, 6),  # +y
    (0, 4, 7, 3),  # -x
    (1, 2, 6, 5),  # +x
)


def _quad_area(p0, p1, p2, p3):
    """quad area = sum of two triangle areas."""
    a1 = 0.5 * np.linalg.norm(np.cross(p1 - p0, p2 - p0), axis=-1)
    a2 = 0.5 * np.linalg.norm(np.cross(p2 - p0, p3 - p0), axis=-1)
    return a1 + a2


def hex_face_area_stats(
    pts: NDArray[np.float64],
    hexes: NDArray[np.int64],
) -> HexFaceAreaResult:
    """hex 별 6 face area 통계.

    Returns:
        HexFaceAreaResult.
    """
    import time
    t0 = time.perf_counter()

    pts = np.asarray(pts, dtype=np.float64)
    hexes = np.asarray(hexes, dtype=np.int64)
    n_h = int(hexes.shape[0])

    if n_h == 0:
        return HexFaceAreaResult(elapsed_s=time.perf_counter() - t0)

    if _c_hex_face_area_stats_batch is not None:
        native = _c_hex_face_area_stats_batch(pts, hexes)
        if native is not None:
            stats, n_stretched = native
            return HexFaceAreaResult(
                n_hexes=n_h,
                area_min=stats[0],
                area_max=stats[1],
                area_mean=stats[2],
                ratio_max=stats[3],
                ratio_mean=stats[4],
                n_stretched=n_stretched,
                elapsed_s=time.perf_counter() - t0,
            )

    corners = pts[hexes]  # (H, 8, 3).

    face_areas = np.zeros((n_h, 6), dtype=np.float64)
    for fi, (a, b, c, d) in enumerate(_HEX_FACES):
        face_areas[:, fi] = _quad_area(
            corners[:, a, :], corners[:, b, :],
            corners[:, c, :], corners[:, d, :],
        )

    a_min = face_areas.min(axis=1)
    a_max = face_areas.max(axis=1)
    safe = a_min > 1e-30
    ratio = np.zeros(n_h, dtype=np.float64)
    ratio[safe] = a_max[safe] / a_min[safe]

    return HexFaceAreaResult(
        n_hexes=n_h,
        area_min=float(face_areas.min()),
        area_max=float(face_areas.max()),
        area_mean=float(face_areas.mean()),
        ratio_max=float(ratio.max()),
        ratio_mean=float(ratio.mean()),
        n_stretched=int((ratio > 5.0).sum()),
        elapsed_s=time.perf_counter() - t0,
    )
