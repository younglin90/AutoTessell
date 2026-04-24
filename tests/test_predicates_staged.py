"""Round 45 — staged predicates tests."""
from __future__ import annotations

import numpy as np
import pytest


def test_staged_orient3d_basic_signs() -> None:
    from core.utils.predicates_staged import orient3d_staged

    a = (0, 0, 0); b = (1, 0, 0); c = (0, 1, 0); d = (0, 0, 1)
    assert orient3d_staged(a, b, c, d) == 1
    d2 = (0, 0, -1)
    assert orient3d_staged(a, b, c, d2) == -1


def test_staged_orient3d_coplanar() -> None:
    from core.utils.predicates_staged import orient3d_staged

    a = (0, 0, 0); b = (1, 0, 0); c = (0, 1, 0); d = (1, 1, 0)
    assert orient3d_staged(a, b, c, d) == 0


def test_staged_orient3d_drops_to_exact_on_thin_tet() -> None:
    """Stage 1 의 bound 안쪽 (near coplanar) 이면 stage 3 로 drop."""
    from core.utils.predicates_staged import orient3d_staged

    # z 가 매우 작아 double 에서는 불확실, exact 는 +1.
    a = (0, 0, 0); b = (1, 0, 0); c = (0, 1, 0)
    d = (0.5, 0.5, 1e-18)
    assert orient3d_staged(a, b, c, d) == 1


def test_staged_orient3d_batch_mixed() -> None:
    from core.utils.predicates_staged import orient3d_staged_batch

    A = np.zeros((3, 3), dtype=np.float64)
    B = np.array([[1, 0, 0]] * 3, dtype=np.float64)
    C = np.array([[0, 1, 0]] * 3, dtype=np.float64)
    D = np.array(
        [[0, 0, 1], [0, 0, -1], [1, 1, 0]], dtype=np.float64,
    )
    out = orient3d_staged_batch(A, B, C, D)
    assert out[0] == 1
    assert out[1] == -1
    assert out[2] == 0
