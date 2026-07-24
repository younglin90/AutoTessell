"""Log-only boundary invariant diagnostic tests."""

from __future__ import annotations

import numpy as np

from core.generator.native_tet.boundary_invariant import check_boundary_invariant


def _two_tet_mesh() -> tuple[np.ndarray, np.ndarray]:
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [1.0, 1.0, 1.0],
        ]
    )
    tets = np.array([[0, 1, 2, 3], [1, 2, 3, 4]], dtype=np.int64)
    return points, tets


def test_boundary_invariant_reports_preserved_mesh() -> None:
    points, tets = _two_tet_mesh()
    report = check_boundary_invariant(points, tets, points, tets, "same")
    assert report.preserved
    assert report.before_face_count == report.after_face_count
    assert report.added_faces == report.removed_faces == 0


def test_boundary_invariant_is_log_only_and_reports_face_change() -> None:
    points, tets = _two_tet_mesh()
    changed = tets.copy()
    changed[1] = [0, 1, 2, 4]
    report = check_boundary_invariant(
        points,
        tets,
        points,
        changed,
        "changed",
        log_only=True,
    )
    assert not report.preserved
    assert report.keys_equal is False
