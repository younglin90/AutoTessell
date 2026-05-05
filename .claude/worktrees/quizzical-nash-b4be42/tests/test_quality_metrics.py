"""Round 69 — tet aspect ratio + dihedral tests."""
from __future__ import annotations

import numpy as np
import pytest


def test_aspect_ratio_regular_tet() -> None:
    from core.generator.native_tet.quality import tet_aspect_ratio

    # Regular tet — aspect ratio = R/r ≈ 3.
    pts = np.array(
        [[1, 1, 1], [1, -1, -1], [-1, 1, -1], [-1, -1, 1]], dtype=np.float64,
    )
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    a = tet_aspect_ratio(pts, tets)
    assert a.shape == (1,)
    # regular tet 는 낮은 aspect (2~10 범위).
    assert 1.0 <= a[0] <= 20.0


def test_aspect_ratio_degenerate() -> None:
    from core.generator.native_tet.quality import tet_aspect_ratio

    # 공면 tet — inradius ≈ 0 → aspect 매우 크거나 1e6 (degenerate 보호값).
    pts = np.array(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0]], dtype=np.float64,
    )
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    a = tet_aspect_ratio(pts, tets)
    assert a[0] > 100.0


def test_min_dihedral_regular_tet() -> None:
    from core.generator.native_tet.quality import tet_min_dihedral_deg

    pts = np.array(
        [[1, 1, 1], [1, -1, -1], [-1, 1, -1], [-1, -1, 1]], dtype=np.float64,
    )
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    d = tet_min_dihedral_deg(pts, tets)
    # 정사면체 dihedral = 70.53° 정확.
    assert abs(d[0] - 70.53) < 1.0


def test_min_dihedral_degenerate() -> None:
    from core.generator.native_tet.quality import tet_min_dihedral_deg

    pts = np.array(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0]], dtype=np.float64,
    )
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    d = tet_min_dihedral_deg(pts, tets)
    # 거의 공면 → 매우 작은 dihedral (< 1°).
    assert d[0] < 1.0
