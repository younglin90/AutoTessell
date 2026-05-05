"""Round 36 — exact-sign geometric predicates.

`predicates.py` 는 tolerance 기반이라 얇은 tet 의 sign 을 놓칠 수 있다. 본 모듈
은 Python `fractions.Fraction` 기반 exact-rational 산술로 orient3d / insphere
부호를 **항상 정확히** 반환한다 (느리지만 fallback 용).

사용 패턴:
    s = predicates.orient3d(...)                  # fast tol 버전
    if s == 0:
        s = predicates_exact.orient3d(...)        # 정확 재계산

레퍼런스
    - Shewchuk 1997, "Adaptive Precision Floating-Point Arithmetic and Fast
      Robust Geometric Predicates". Shewchuk 의 expansion 배열 기법 대신 본
      모듈은 더 간단한 Python fractions 사용 (성능 < 10× 느림).
"""
from __future__ import annotations

from fractions import Fraction

import numpy as np


def _to_frac(v) -> tuple[Fraction, Fraction, Fraction]:
    return (Fraction(float(v[0])), Fraction(float(v[1])), Fraction(float(v[2])))


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b) -> Fraction:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def orient3d(a, b, c, d) -> int:
    """정확 signed-volume 부호 (-1, 0, +1)."""
    af = _to_frac(a); bf = _to_frac(b); cf = _to_frac(c); df = _to_frac(d)
    ab = _sub(bf, af)
    ac = _sub(cf, af)
    ad = _sub(df, af)
    v6 = _dot(ab, _cross(ac, ad))
    if v6 > 0:
        return 1
    if v6 < 0:
        return -1
    return 0


def insphere(a, b, c, d, e) -> int:
    """정확 insphere 부호.

    반환: +1 (e 가 positive-oriented tet abcd 의 circumsphere 내부),
         -1 (외부), 0 (sphere 위).
    """
    af = _to_frac(a); bf = _to_frac(b); cf = _to_frac(c); df = _to_frac(d)
    ef = _to_frac(e)

    ax, ay, az = af[0] - ef[0], af[1] - ef[1], af[2] - ef[2]
    bx, by, bz = bf[0] - ef[0], bf[1] - ef[1], bf[2] - ef[2]
    cx, cy, cz = cf[0] - ef[0], cf[1] - ef[1], cf[2] - ef[2]
    dx, dy, dz = df[0] - ef[0], df[1] - ef[1], df[2] - ef[2]

    alift = ax * ax + ay * ay + az * az
    blift = bx * bx + by * by + bz * bz
    clift = cx * cx + cy * cy + cz * cz
    dlift = dx * dx + dy * dy + dz * dz

    def det3(r, s, t):
        return (
            r[0] * (s[1] * t[2] - s[2] * t[1])
            - r[1] * (s[0] * t[2] - s[2] * t[0])
            + r[2] * (s[0] * t[1] - s[1] * t[0])
        )

    det = (
        alift * det3((bx, by, bz), (cx, cy, cz), (dx, dy, dz))
        - blift * det3((ax, ay, az), (cx, cy, cz), (dx, dy, dz))
        + clift * det3((ax, ay, az), (bx, by, bz), (dx, dy, dz))
        - dlift * det3((ax, ay, az), (bx, by, bz), (cx, cy, cz))
    )
    if det > 0:
        return 1
    if det < 0:
        return -1
    return 0


def robust_orient3d(a, b, c, d, *, tol: float = 1e-14) -> int:
    """tolerance 먼저, uncertain 면 exact fallback."""
    from core.utils.predicates import orient3d as fast_orient3d

    s = fast_orient3d(np.asarray(a), np.asarray(b), np.asarray(c), np.asarray(d), tol=tol)
    if s != 0:
        return s
    return orient3d(a, b, c, d)


def robust_insphere(a, b, c, d, e, *, tol: float = 1e-14) -> int:
    from core.utils.predicates import insphere as fast_insphere

    s = fast_insphere(
        np.asarray(a), np.asarray(b), np.asarray(c),
        np.asarray(d), np.asarray(e), tol=tol,
    )
    if s != 0:
        return s
    return insphere(a, b, c, d, e)
