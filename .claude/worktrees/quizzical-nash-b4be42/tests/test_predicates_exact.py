"""Round 36 — exact predicates tests."""
from __future__ import annotations

import numpy as np
import pytest


def test_exact_orient3d_positive() -> None:
    from core.utils.predicates_exact import orient3d

    a = (0, 0, 0); b = (1, 0, 0); c = (0, 1, 0); d = (0, 0, 1)
    assert orient3d(a, b, c, d) == 1


def test_exact_orient3d_negative() -> None:
    from core.utils.predicates_exact import orient3d

    a = (0, 0, 0); b = (1, 0, 0); c = (0, 0, 1); d = (0, 1, 0)
    assert orient3d(a, b, c, d) == -1


def test_exact_orient3d_coplanar() -> None:
    from core.utils.predicates_exact import orient3d

    a = (0, 0, 0); b = (1, 0, 0); c = (0, 1, 0); d = (1, 1, 0)
    assert orient3d(a, b, c, d) == 0


def test_exact_handles_near_coplanar_where_tol_fails() -> None:
    """tolerance 로는 0 이 나오지만 exact 로는 nonzero 인 경우."""
    from core.utils.predicates import orient3d as tol_orient
    from core.utils.predicates_exact import orient3d as exact_orient

    # 매우 얇은 tet. tol_orient 는 tol=1e-14 에서 0 반환할 수 있음.
    a = (0, 0, 0); b = (1, 0, 0); c = (0, 1, 0)
    d = (0.5, 0.5, 1e-18)
    tol_res = tol_orient(
        np.array(a, dtype=np.float64),
        np.array(b, dtype=np.float64),
        np.array(c, dtype=np.float64),
        np.array(d, dtype=np.float64),
    )
    exact_res = exact_orient(a, b, c, d)
    # tol 은 0, exact 는 +1.
    assert tol_res == 0
    assert exact_res == 1


def test_robust_orient3d_uses_exact_when_tol_is_zero() -> None:
    from core.utils.predicates_exact import robust_orient3d

    a = (0, 0, 0); b = (1, 0, 0); c = (0, 1, 0)
    d = (0.5, 0.5, 1e-18)
    # robust wrapper 가 exact 경로로 강하해야 +1 반환.
    assert robust_orient3d(a, b, c, d) == 1


def test_exact_insphere_inside_outside() -> None:
    from core.utils.predicates_exact import insphere

    a = (1, 1, 1); b = (1, -1, -1); c = (-1, 1, -1); d = (-1, -1, 1)
    # origin 이 circumcenter → 내부.
    assert insphere(a, b, c, d, (0, 0, 0)) != 0
    # 멀리.
    assert insphere(a, b, c, d, (10, 10, 10)) != 0
