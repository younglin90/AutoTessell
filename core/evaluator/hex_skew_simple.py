"""DD5 / beta2789 — Hex 단순 skewness metric (cell center → face center 거리).

OpenFOAM checkMesh 의 skewness 와 다른 가벼운 단순 metric:
    skew_i = ||face_center - cell_center|| / sqrt(face_area)
    높으면 cell 이 한 face 쪽으로 치우침.

빠른 진단 / 단위 테스트 / Strategist 입력.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass
class HexSkewSimpleResult:
    n_hexes: int = 0
    skew_min: float = 0.0
    skew_max: float = 0.0
    skew_mean: float = 0.0
    n_above_1: int = 0


_HEX_FACES = (
    (0, 3, 2, 1),
    (4, 5, 6, 7),
    (0, 1, 5, 4),
    (2, 3, 7, 6),
    (0, 4, 7, 3),
    (1, 2, 6, 5),
)


def hex_skew_simple(
    pts: NDArray[np.float64],
    hexes: NDArray[np.int64],
) -> HexSkewSimpleResult:
    """skew = ||face_c - cell_c|| / sqrt(face_area).

    regular cube → 0.5 (모든 face), uniform.
    skewed → 큰 값.
    """
    pts = np.asarray(pts, dtype=np.float64)
    hexes = np.asarray(hexes, dtype=np.int64)
    n_h = int(hexes.shape[0])
    if n_h == 0:
        return HexSkewSimpleResult()

    corners = pts[hexes]  # (H, 8, 3).
    cell_c = corners.mean(axis=1)  # (H, 3).

    skews = np.zeros((n_h, 6), dtype=np.float64)
    for fi, (a, b, c, d) in enumerate(_HEX_FACES):
        p_a = corners[:, a, :]; p_b = corners[:, b, :]
        p_c = corners[:, c, :]; p_d = corners[:, d, :]
        face_c = (p_a + p_b + p_c + p_d) / 4.0
        # face area (sum of 2 tri).
        tri1 = 0.5 * np.linalg.norm(np.cross(p_b - p_a, p_c - p_a), axis=-1)
        tri2 = 0.5 * np.linalg.norm(np.cross(p_c - p_a, p_d - p_a), axis=-1)
        area = tri1 + tri2
        dist = np.linalg.norm(face_c - cell_c, axis=-1)
        skews[:, fi] = dist / np.maximum(np.sqrt(area), 1e-30)

    sk_max = skews.max(axis=1)
    return HexSkewSimpleResult(
        n_hexes=n_h,
        skew_min=float(skews.min()),
        skew_max=float(sk_max.max()),
        skew_mean=float(skews.mean()),
        n_above_1=int((sk_max > 1.0).sum()),
    )
