"""U6 / beta2707 — Degenerate volume cell detector.

tet 의 degenerate / sliver / inverted 셀 탐지:
- inverted: signed_volume <= 0 (winding error or self-overlap).
- zero-vol : |volume| < tol.
- sliver  : volume / (max_edge^3) < cube_ratio (regular tet ≈ 0.118).

Quality predictor 의 가벼운 alternative + Evaluator early reject 입력.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

try:
    from core.generator.native_tet._native import (
        detect_degenerate_tets_stats as _c_detect_degenerate_tets_stats,
    )
except Exception:  # pragma: no cover - optional native extension
    _c_detect_degenerate_tets_stats = None


@dataclass
class DegenerateResult:
    n_tets: int = 0
    n_inverted: int = 0
    n_zero_vol: int = 0
    n_sliver: int = 0
    n_ok: int = 0
    worst_volume: float = 0.0       # most negative.
    smallest_abs_volume: float = 0.0
    elapsed_s: float = 0.0


_TET_EDGES = np.array(
    [[0, 1], [0, 2], [0, 3], [1, 2], [1, 3], [2, 3]],
    dtype=np.int64,
)


def detect_degenerate_tets(
    pts: NDArray[np.float64],
    tets: NDArray[np.int64],
    *,
    zero_tol: float = 1e-12,
    sliver_cube_ratio: float = 0.01,
) -> DegenerateResult:
    """tet 들의 inverted / zero / sliver 카운트.

    signed volume = (1/6) det([b-a, c-a, d-a]).

    Args:
        zero_tol: |vol| < tol → zero.
        sliver_cube_ratio: |vol| / max_edge^3 < ratio → sliver
                           (regular tet ≈ 0.118; 0.01 = 8% of regular).
    """
    import time
    t0 = time.perf_counter()

    pts = np.asarray(pts, dtype=np.float64)
    tets = np.asarray(tets, dtype=np.int64)
    n_t = int(tets.shape[0])

    if n_t == 0:
        return DegenerateResult(elapsed_s=time.perf_counter() - t0)

    if _c_detect_degenerate_tets_stats is not None:
        native = _c_detect_degenerate_tets_stats(
            pts, tets, zero_tol, sliver_cube_ratio,
        )
        if native is not None:
            n_inv, n_zero, n_sliv, n_ok, worst, smallest_abs = native
            return DegenerateResult(
                n_tets=n_t,
                n_inverted=n_inv,
                n_zero_vol=n_zero,
                n_sliver=n_sliv,
                n_ok=n_ok,
                worst_volume=worst,
                smallest_abs_volume=smallest_abs,
                elapsed_s=time.perf_counter() - t0,
            )

    a = pts[tets[:, 0]]
    b = pts[tets[:, 1]]
    c = pts[tets[:, 2]]
    d = pts[tets[:, 3]]
    vol = np.einsum("ij,ij->i", np.cross(b - a, c - a), d - a) / 6.0

    inverted = vol < -zero_tol
    zero = np.abs(vol) <= zero_tol

    # max edge length per tet for sliver test.
    e_idx = tets[:, _TET_EDGES]  # (T, 6, 2).
    p0 = pts[e_idx[..., 0]]
    p1 = pts[e_idx[..., 1]]
    e_max = np.linalg.norm(p1 - p0, axis=-1).max(axis=1)
    e_max_safe = np.maximum(e_max, 1e-30)
    cube_ratio = np.abs(vol) / (e_max_safe ** 3)
    sliver = (~zero) & (~inverted) & (cube_ratio < sliver_cube_ratio)

    n_inv = int(inverted.sum())
    n_zero = int(zero.sum())
    n_sliv = int(sliver.sum())
    n_ok = n_t - n_inv - n_zero - n_sliv

    return DegenerateResult(
        n_tets=n_t,
        n_inverted=n_inv,
        n_zero_vol=n_zero,
        n_sliver=n_sliv,
        n_ok=n_ok,
        worst_volume=float(vol.min()) if n_t > 0 else 0.0,
        smallest_abs_volume=float(np.abs(vol).min()),
        elapsed_s=time.perf_counter() - t0,
    )
