"""Phase J1 — Inverted tet detection + swap repair.

Local operation (flip/collapse/smooth) 이후 signed volume 이 음수로 뒤집힌
tet 은 invalid mesh 를 만든다. 본 모듈은:
    1. 각 tet 의 signed volume 계산.
    2. 음수인 tet 의 last 2 vertex swap 으로 양수 복구.
    3. 복구 불가능한 degenerate (|vol| < eps) 는 리포트.

정상 Delaunay 직후에는 문제없지만 split/collapse/flip 반복 후 numerical
edge case 에서 발생 가능. 대규모 안전판.

레퍼런스
    - Shewchuk 1997, "Adaptive Precision Floating-Point Arithmetic and Fast
      Robust Geometric Predicates" — signed volume robustness.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class ValidateResult:
    n_tets: int
    n_inverted_before: int
    n_fixed_by_swap: int
    n_degenerate: int


def signed_volume6(pts: np.ndarray, tets: np.ndarray) -> np.ndarray:
    """per-tet signed (6 × volume). 양수 = 양의 방향."""
    tets = np.asarray(tets, dtype=np.int64)
    if tets.size == 0:
        return np.zeros(0)
    v = pts[tets]
    return np.einsum(
        "ij,ij->i",
        v[:, 1] - v[:, 0],
        np.cross(v[:, 2] - v[:, 0], v[:, 3] - v[:, 0]),
    )


def fix_inverted_tets(
    pts: np.ndarray,
    tets: np.ndarray,
    *,
    degenerate_eps: float = 1e-20,
) -> tuple[np.ndarray, ValidateResult]:
    """음수 signed vol tet 은 마지막 두 vertex swap 으로 양수화.

    Returns:
        (fixed_tets, ValidateResult).
    """
    tets = np.asarray(tets, dtype=np.int64).copy()
    pts = np.asarray(pts, dtype=np.float64)
    if tets.size == 0:
        return tets, ValidateResult(0, 0, 0, 0)

    vol6 = signed_volume6(pts, tets)
    inverted = vol6 < -float(degenerate_eps)
    degenerate = np.abs(vol6) < float(degenerate_eps)
    n_before = int(inverted.sum())
    n_degen = int(degenerate.sum())

    # swap (v2, v3) — signed volume sign 뒤집힘.
    if n_before > 0:
        idx = np.where(inverted)[0]
        tmp = tets[idx, 2].copy()
        tets[idx, 2] = tets[idx, 3]
        tets[idx, 3] = tmp

    vol6_after = signed_volume6(pts, tets)
    still = int((vol6_after < -float(degenerate_eps)).sum())
    fixed = n_before - still

    return tets, ValidateResult(
        n_tets=int(tets.shape[0]),
        n_inverted_before=n_before,
        n_fixed_by_swap=int(fixed),
        n_degenerate=n_degen,
    )
