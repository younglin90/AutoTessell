"""Round 45 — Staged-precision geometric predicates.

3 단계 파이프라인 (Shewchuk 1997 adaptive idea 의 간단한 Python 재해석):

    Stage 1 (fast): 순수 double. error bound (Jonathan Shewchuk 의 epsilon
                    × sum_of_abs) 안에 들면 확정.
    Stage 2 (medium): |det| 이 error bound 근처면 numpy float128 로 재계산.
    Stage 3 (exact): 여전히 불확실하면 Python fractions.Fraction 경유.

평균 속도는 Stage 1 (double) 수준이고, 문제 케이스만 Stage 2/3 로 drop.

본 모듈은 독립 Python 재구현. Shewchuk 의 expansion 배열 연산 대신 numpy
float128 과 fractions 를 활용 — 교육적/실용적 속도 조합.
"""
from __future__ import annotations

import numpy as np


# Shewchuk ε ≈ 2^-53 ≈ 1.1e-16; orient3d error bound 상수는 경험적 2**-49.
_ORIENT3D_ERROR_BOUND_COEF = 7.0 * (2.0 ** -53)


def orient3d_staged(a, b, c, d) -> int:
    """3 단계 staged orient3d.

    a/b/c/d: (3,) coords (tuple / list / ndarray).
    반환: -1 / 0 / +1.
    """
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    c = np.asarray(c, dtype=np.float64)
    d = np.asarray(d, dtype=np.float64)

    # Stage 1: double.
    ab = b - a; ac = c - a; ad = d - a
    det = float(np.dot(ab, np.cross(ac, ad)))
    # 대략적 error bound — |coord| 의 합.
    scale = (
        float(np.abs(ab).sum())
        * float(np.abs(ac).sum())
        * float(np.abs(ad).sum())
    )
    bound = _ORIENT3D_ERROR_BOUND_COEF * max(scale, 1.0)
    if det > bound:
        return 1
    if det < -bound:
        return -1

    # Stage 2: float128.
    try:
        a_ld = np.asarray(a, dtype=np.float128)
        b_ld = np.asarray(b, dtype=np.float128)
        c_ld = np.asarray(c, dtype=np.float128)
        d_ld = np.asarray(d, dtype=np.float128)
        ab_l = b_ld - a_ld; ac_l = c_ld - a_ld; ad_l = d_ld - a_ld
        det_l = np.dot(ab_l, np.cross(ac_l, ad_l))
        # float128 는 80/128-bit depending on platform. ε 훨씬 작음.
        bound_l = float(bound) * 1e-4
        if det_l > bound_l:
            return 1
        if det_l < -bound_l:
            return -1
    except Exception:
        # 플랫폼에 float128 없으면 stage 2 건너뜀.
        pass

    # Stage 3: exact fraction.
    from core.utils.predicates_exact import orient3d as exact_orient3d
    return exact_orient3d(
        tuple(a.tolist()), tuple(b.tolist()),
        tuple(c.tolist()), tuple(d.tolist()),
    )


_INSPHERE_ERROR_BOUND_COEF = 1.5e-14


def insphere_staged(a, b, c, d, e) -> int:
    """beta1190 (R124) — staged insphere.

    4 vertex tet (a,b,c,d) (positive orient) + query e. 반환:
        +1: e 가 circumsphere 내부
        -1: 외부
         0: boundary
    """
    A = np.asarray(a, dtype=np.float64)
    B = np.asarray(b, dtype=np.float64)
    C = np.asarray(c, dtype=np.float64)
    D = np.asarray(d, dtype=np.float64)
    E = np.asarray(e, dtype=np.float64)

    # Stage 1: double.
    def _det5(A_, B_, C_, D_, E_, dtype):
        M = np.empty((4, 4), dtype=dtype)
        for i, P in enumerate([A_, B_, C_, D_]):
            d = np.asarray(P, dtype=dtype) - np.asarray(E_, dtype=dtype)
            M[i, 0] = d[0]; M[i, 1] = d[1]; M[i, 2] = d[2]
            M[i, 3] = d[0] * d[0] + d[1] * d[1] + d[2] * d[2]
        return np.linalg.det(M)

    det = float(_det5(A, B, C, D, E, np.float64))
    scale_pts = (
        float(np.abs(A - E).sum())
        + float(np.abs(B - E).sum())
        + float(np.abs(C - E).sum())
        + float(np.abs(D - E).sum())
    ) ** 4
    bound = _INSPHERE_ERROR_BOUND_COEF * max(scale_pts, 1.0)
    if det > bound:
        return 1
    if det < -bound:
        return -1

    # Stage 2: float128.
    try:
        det_l = float(_det5(A, B, C, D, E, np.float128))
        if det_l > bound * 1e-4:
            return 1
        if det_l < -bound * 1e-4:
            return -1
    except Exception:
        pass

    # Stage 3: exact via fractions (시간 여유 시 고정밀 expansion 권장).
    from fractions import Fraction  # noqa: PLC0415

    def _frac(v):
        return Fraction(float(v)).limit_denominator(10 ** 18)

    def _det4_frac(rows):
        # 4x4 determinant by expansion.
        def _minor(M, r, c):
            return [row[:c] + row[c + 1:] for i, row in enumerate(M) if i != r]

        def _det3(M3):
            return (
                M3[0][0] * (M3[1][1] * M3[2][2] - M3[1][2] * M3[2][1])
                - M3[0][1] * (M3[1][0] * M3[2][2] - M3[1][2] * M3[2][0])
                + M3[0][2] * (M3[1][0] * M3[2][1] - M3[1][1] * M3[2][0])
            )

        total = Fraction(0)
        for c in range(4):
            sign = 1 if c % 2 == 0 else -1
            total += sign * rows[0][c] * _det3(_minor(rows, 0, c))
        return total

    rows = []
    for P in (A, B, C, D):
        dx = _frac(P[0]) - _frac(E[0])
        dy = _frac(P[1]) - _frac(E[1])
        dz = _frac(P[2]) - _frac(E[2])
        rows.append([dx, dy, dz, dx * dx + dy * dy + dz * dz])
    det_f = _det4_frac(rows)
    if det_f > 0:
        return 1
    if det_f < 0:
        return -1
    return 0


def orient3d_staged_batch(
    A: np.ndarray, B: np.ndarray, C: np.ndarray, D: np.ndarray,
) -> np.ndarray:
    """Stage 1 만 batch, 불확실한 행은 Stage 3 로 drop.

    결과: int8 array ∈ {-1, 0, +1}.
    """
    A = np.asarray(A, dtype=np.float64)
    B = np.asarray(B, dtype=np.float64)
    C = np.asarray(C, dtype=np.float64)
    D = np.asarray(D, dtype=np.float64)

    ab = B - A; ac = C - A; ad = D - A
    det = np.einsum("ij,ij->i", ab, np.cross(ac, ad))
    scale = (
        np.abs(ab).sum(axis=1)
        * np.abs(ac).sum(axis=1)
        * np.abs(ad).sum(axis=1)
    )
    bound = _ORIENT3D_ERROR_BOUND_COEF * np.maximum(scale, 1.0)

    out = np.zeros(det.shape[0], dtype=np.int8)
    out[det > bound] = 1
    out[det < -bound] = -1

    uncertain = (det <= bound) & (det >= -bound)
    if uncertain.any():
        for i in np.where(uncertain)[0].tolist():
            out[i] = orient3d_staged(A[i], B[i], C[i], D[i])
    return out
