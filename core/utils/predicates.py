"""Robust geometric predicates (간이 버전).

Shewchuk 1997 "Adaptive Precision Floating-Point Arithmetic and Fast Robust
Geometric Predicates" 의 완전한 exact arithmetic 은 복잡하므로 본 모듈은
**실용적 tolerance 기반 predicate** 만 제공:

    orient3d(a, b, c, d) → + / 0 / − (양의 부피 / 공면 / 음의 부피)
    insphere(a, b, c, d, e) → + (e 가 abcd circumsphere 내부) / 0 / −

수치적으로 얇은 tet 에서 sign 이 불안정할 때, robust_sign 이 double-double
배정밀 대신 작은 tolerance 로 완화. 정확한 exact predicate 가 필요하면
`shewchuk-predicates` 같은 외부 라이브러리로 교체 권장.
"""
from __future__ import annotations

import numpy as np


def orient3d(
    a: np.ndarray, b: np.ndarray, c: np.ndarray, d: np.ndarray,
    *, tol: float = 1e-14,
) -> int:
    """3D orientation: 4 점의 signed volume 부호."""
    v6 = float(np.dot(b - a, np.cross(c - a, d - a)))
    if v6 > tol:
        return 1
    if v6 < -tol:
        return -1
    return 0


def orient3d_batch(
    A: np.ndarray, B: np.ndarray, C: np.ndarray, D: np.ndarray,
    *, tol: float = 1e-14,
) -> np.ndarray:
    """N 개 tet 의 orient3d. returns int8 array ∈ {-1, 0, +1}."""
    v6 = np.einsum("ij,ij->i", B - A, np.cross(C - A, D - A))
    out = np.zeros(v6.shape[0], dtype=np.int8)
    out[v6 > tol] = 1
    out[v6 < -tol] = -1
    return out


def insphere(
    a: np.ndarray, b: np.ndarray, c: np.ndarray, d: np.ndarray, e: np.ndarray,
    *, tol: float = 1e-14,
) -> int:
    """e 가 tet abcd 의 circumsphere 내부인지.

    Shewchuk §4.3 의 5×5 determinant 전개. positive orient 가정.
    """
    ax, ay, az = a - e
    bx, by, bz = b - e
    cx, cy, cz = c - e
    dx, dy, dz = d - e

    alift = ax * ax + ay * ay + az * az
    blift = bx * bx + by * by + bz * bz
    clift = cx * cx + cy * cy + cz * cz
    dlift = dx * dx + dy * dy + dz * dz

    ab = ax * by - bx * ay
    bc = bx * cy - cx * by
    cd = cx * dy - dx * cy
    da = dx * ay - ax * dy
    ac = ax * cy - cx * ay
    bd = bx * dy - dx * by

    abc = az * bc - bz * ac + cz * ab
    bcd = bz * cd - cz * bd + dz * bc
    cda = cz * da + dz * ac + az * cd
    dab = dz * ab + az * bd + bz * da

    det = alift * bcd - blift * cda + clift * dab - dlift * abc
    if det > tol:
        return 1
    if det < -tol:
        return -1
    return 0
