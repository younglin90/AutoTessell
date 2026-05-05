"""Round 35 — Bowyer-Watson incremental insertion tests."""
from __future__ import annotations

import numpy as np
import pytest


def test_in_circumsphere_inside() -> None:
    from core.generator.native_tet.bowyer_watson import _in_circumsphere

    # Regular tet centered at origin.
    a = np.array([1, 1, 1], dtype=np.float64)
    b = np.array([1, -1, -1], dtype=np.float64)
    c = np.array([-1, 1, -1], dtype=np.float64)
    d = np.array([-1, -1, 1], dtype=np.float64)
    # 원점 = circumcenter.
    assert _in_circumsphere(np.array([0.0, 0, 0]), a, b, c, d)


def test_in_circumsphere_outside() -> None:
    from core.generator.native_tet.bowyer_watson import _in_circumsphere

    a = np.array([1, 1, 1], dtype=np.float64)
    b = np.array([1, -1, -1], dtype=np.float64)
    c = np.array([-1, 1, -1], dtype=np.float64)
    d = np.array([-1, -1, 1], dtype=np.float64)
    # circumradius ≈ sqrt(3), 멀리 있는 점.
    assert not _in_circumsphere(np.array([10.0, 0, 0]), a, b, c, d)


def test_boundary_faces_of_cavity_single_tet() -> None:
    from core.generator.native_tet.bowyer_watson import _boundary_faces_of_cavity

    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    mask = np.array([True], dtype=bool)
    b = _boundary_faces_of_cavity(tets, mask)
    # 단일 tet 의 4 face 전부 boundary.
    assert len(b) == 4


def test_boundary_faces_of_cavity_two_adjacent() -> None:
    from core.generator.native_tet.bowyer_watson import _boundary_faces_of_cavity

    # face (0,1,2) 공유 2 tet.
    tets = np.array([[0, 1, 2, 3], [0, 1, 2, 4]], dtype=np.int64)
    mask = np.array([True, True], dtype=bool)
    b = _boundary_faces_of_cavity(tets, mask)
    # 공유 face 제외 6 boundary.
    assert len(b) == 6


def test_bowyer_watson_insert_noop_empty() -> None:
    from core.generator.native_tet.bowyer_watson import bowyer_watson_insert

    pts = np.zeros((0, 3), dtype=np.float64)
    tets = np.zeros((0, 4), dtype=np.int64)
    new_pts = np.array([[0, 0, 0]], dtype=np.float64)
    _, _, res = bowyer_watson_insert(pts, tets, new_pts)
    assert res.n_inserted == 0


def test_bowyer_watson_insert_adds_point_into_tet() -> None:
    """정사면체 안에 점 하나 삽입 → cavity=1, 새 tet=4."""
    from core.generator.native_tet.bowyer_watson import bowyer_watson_insert

    pts = np.array(
        [
            [1, 1, 1], [1, -1, -1], [-1, 1, -1], [-1, -1, 1],
        ],
        dtype=np.float64,
    )
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    # 원점 = circumcenter → circumsphere 중심, 내부.
    new_pts = np.array([[0.0, 0, 0]], dtype=np.float64)

    new_all_pts, new_tets, res = bowyer_watson_insert(pts, tets, new_pts)
    assert res.n_inserted == 1
    assert res.n_cavity_total == 1
    # 4 boundary face × 1 새 점 → 4 new tet.
    assert res.n_new_tets_total == 4
    assert new_tets.shape[0] == 4
    assert new_all_pts.shape[0] == 5


def test_bowyer_watson_skips_too_large_cavity() -> None:
    """max_cavity_size 이하 cavity 만 진행 (degenerate 방지)."""
    from core.generator.native_tet.bowyer_watson import bowyer_watson_insert

    # 간단히 max_cavity_size=0 으로 강제 skip.
    pts = np.array(
        [[1, 1, 1], [1, -1, -1], [-1, 1, -1], [-1, -1, 1]], dtype=np.float64,
    )
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    new_pts = np.array([[0.0, 0, 0]], dtype=np.float64)

    _, _, res = bowyer_watson_insert(pts, tets, new_pts, max_cavity_size=0)
    assert res.n_inserted == 0
