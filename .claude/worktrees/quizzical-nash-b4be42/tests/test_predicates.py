"""Round 24/25 — geometric predicates unit tests."""
from __future__ import annotations

import numpy as np
import pytest


def test_orient3d_positive() -> None:
    from core.utils.predicates import orient3d

    a = np.array([0, 0, 0], dtype=np.float64)
    b = np.array([1, 0, 0], dtype=np.float64)
    c = np.array([0, 1, 0], dtype=np.float64)
    d = np.array([0, 0, 1], dtype=np.float64)
    assert orient3d(a, b, c, d) == 1


def test_orient3d_negative() -> None:
    from core.utils.predicates import orient3d

    a = np.array([0, 0, 0], dtype=np.float64)
    b = np.array([1, 0, 0], dtype=np.float64)
    c = np.array([0, 0, 1], dtype=np.float64)
    d = np.array([0, 1, 0], dtype=np.float64)  # 순서 바뀜 → 음수.
    assert orient3d(a, b, c, d) == -1


def test_orient3d_coplanar() -> None:
    from core.utils.predicates import orient3d

    a = np.array([0, 0, 0], dtype=np.float64)
    b = np.array([1, 0, 0], dtype=np.float64)
    c = np.array([0, 1, 0], dtype=np.float64)
    d = np.array([1, 1, 0], dtype=np.float64)  # xy 평면.
    assert orient3d(a, b, c, d) == 0


def test_orient3d_batch() -> None:
    from core.utils.predicates import orient3d_batch

    A = np.zeros((3, 3), dtype=np.float64)
    B = np.array([[1, 0, 0]] * 3, dtype=np.float64)
    C = np.array([[0, 1, 0]] * 3, dtype=np.float64)
    D = np.array([[0, 0, 1], [0, 0, -1], [1, 1, 0]], dtype=np.float64)
    out = orient3d_batch(A, B, C, D)
    assert out[0] == 1
    assert out[1] == -1
    assert out[2] == 0


def test_insphere_inside() -> None:
    from core.utils.predicates import insphere

    # Regular tet with vertices on unit sphere → circumsphere = unit sphere.
    # Origin 은 circumsphere 중심 → 내부.
    a = np.array([1, 1, 1], dtype=np.float64)
    b = np.array([1, -1, -1], dtype=np.float64)
    c = np.array([-1, 1, -1], dtype=np.float64)
    d = np.array([-1, -1, 1], dtype=np.float64)
    e = np.array([0, 0, 0], dtype=np.float64)   # 원점 = circumsphere 중심.
    # Sign convention: positive oriented tet 에서 내부 점은 +.
    assert insphere(a, b, c, d, e) != 0


def test_insphere_outside() -> None:
    from core.utils.predicates import insphere

    a = np.array([1, 1, 1], dtype=np.float64)
    b = np.array([1, -1, -1], dtype=np.float64)
    c = np.array([-1, 1, -1], dtype=np.float64)
    d = np.array([-1, -1, 1], dtype=np.float64)
    e = np.array([100, 100, 100], dtype=np.float64)  # 멀리.
    assert insphere(a, b, c, d, e) != 0
