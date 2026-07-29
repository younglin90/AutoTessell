"""CC1 / beta2758 — tet inradius (inscribed sphere radius).

r = 3V / S  where V = tet volume, S = sum of 4 face areas.
- Quality metric: r / R (in/circum) ratio = mean ratio (Klingner Eq. 3).
- Regular tet → r/R = 1/3.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

try:
    from core.generator.native_tet._native import (
        tet_inradius_batch as _c_tet_inradius_batch,
    )
except Exception:  # pragma: no cover - native extension optional
    _c_tet_inradius_batch = None


@dataclass
class TetInradiusResult:
    n_tets: int = 0
    r_min: float = 0.0
    r_max: float = 0.0
    r_mean: float = 0.0
    n_zero_radius: int = 0   # 거의 degenerate.
    elapsed_s: float = 0.0


def tet_inradii(
    pts: NDArray[np.float64],
    tets: NDArray[np.int64],
) -> tuple[NDArray[np.float64], TetInradiusResult]:
    """tet 별 inradius.

    Returns:
        (r (T,), TetInradiusResult).
    """
    import time
    t0 = time.perf_counter()

    pts = np.asarray(pts, dtype=np.float64)
    tets = np.asarray(tets, dtype=np.int64)
    n_t = int(tets.shape[0])

    if n_t == 0:
        return np.zeros(0, dtype=np.float64), TetInradiusResult(
            elapsed_s=time.perf_counter() - t0,
        )

    if _c_tet_inradius_batch is not None:
        native = _c_tet_inradius_batch(pts, tets)
        if native is not None:
            r, stats, n_zero = native
            return r, TetInradiusResult(
                n_tets=n_t,
                r_min=stats[0],
                r_max=stats[1],
                r_mean=stats[2],
                n_zero_radius=n_zero,
                elapsed_s=time.perf_counter() - t0,
            )

    a = pts[tets[:, 0]]; b = pts[tets[:, 1]]
    c = pts[tets[:, 2]]; d = pts[tets[:, 3]]

    vol = np.abs(np.einsum("ij,ij->i", np.cross(b - a, c - a), d - a)) / 6.0

    # 4 face areas.
    def tri_area(p, q, r):
        return 0.5 * np.linalg.norm(np.cross(q - p, r - p), axis=-1)

    s = (
        tri_area(a, b, c) + tri_area(a, b, d)
        + tri_area(a, c, d) + tri_area(b, c, d)
    )

    safe = s > 1e-30
    r = np.zeros(n_t, dtype=np.float64)
    r[safe] = 3.0 * vol[safe] / s[safe]

    n_zero = int((r < 1e-12).sum())

    return r, TetInradiusResult(
        n_tets=n_t,
        r_min=float(r.min()),
        r_max=float(r.max()),
        r_mean=float(r.mean()),
        n_zero_radius=n_zero,
        elapsed_s=time.perf_counter() - t0,
    )
