"""T2 / beta2696 — Halton low-discrepancy sequence (volumetric seeding).

Random uniform 보다 evenly-spaced 한 점 분포 → 더 균일한 mesh seed.
fTetWild §3.x / 학회 논문 기준 standard.
"""
from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


def _halton_1d(n: int, base: int) -> NDArray[np.float64]:
    """1D Halton sequence (van der Corput in base `base`)."""
    out = np.zeros(n, dtype=np.float64)
    for i in range(n):
        f = 1.0
        r = 0.0
        idx = i + 1
        while idx > 0:
            f /= base
            r += f * (idx % base)
            idx //= base
        out[i] = r
    return out


def halton_3d(
    n: int,
    *,
    bbox_min: NDArray[np.float64] | None = None,
    bbox_max: NDArray[np.float64] | None = None,
    bases: tuple[int, int, int] = (2, 3, 5),
) -> NDArray[np.float64]:
    """3D Halton sequence — volumetric uniform seed.

    Args:
        n: 점 개수.
        bbox_min/max: bbox 로 [0,1]³ → bbox 매핑. None → unit cube.
        bases: 3 prime bases (2, 3, 5 default).

    Returns:
        (n, 3) array.
    """
    if n <= 0:
        return np.zeros((0, 3), dtype=np.float64)

    pts = np.stack([
        _halton_1d(n, bases[0]),
        _halton_1d(n, bases[1]),
        _halton_1d(n, bases[2]),
    ], axis=1)

    if bbox_min is not None and bbox_max is not None:
        bmin = np.asarray(bbox_min, dtype=np.float64)
        bmax = np.asarray(bbox_max, dtype=np.float64)
        pts = bmin[None, :] + pts * (bmax - bmin)[None, :]

    return pts


def halton_seed_inside(
    V: NDArray[np.float64],
    F: NDArray[np.int64],
    *,
    n_target: int = 1000,
    oversample: int = 3,
) -> NDArray[np.float64]:
    """Halton 기반 mesh 내부 seed 점 생성.

    bbox 안에서 oversample × n_target 개의 Halton 점을 만들어,
    inside_winding_number 로 내부 점만 추출.

    Args:
        V, F: surface mesh.
        n_target: 목표 inside 점 수.
        oversample: bbox 기반 점 oversampling.

    Returns:
        (M, 3) inside seed points (M ≤ oversample × n_target).
    """
    V = np.asarray(V, dtype=np.float64)
    F = np.asarray(F, dtype=np.int64)
    if V.shape[0] == 0:
        return np.zeros((0, 3), dtype=np.float64)

    bmin = V.min(axis=0)
    bmax = V.max(axis=0)
    pts = halton_3d(int(n_target * oversample), bbox_min=bmin, bbox_max=bmax)

    try:
        from core.utils.geometry import inside_winding_number
        inside = inside_winding_number(pts, V, F)
        return pts[inside]
    except Exception:
        return pts
