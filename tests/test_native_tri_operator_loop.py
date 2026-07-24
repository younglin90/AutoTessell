"""Phase-0 safety tests for the separate native-tri operator skeleton."""

from __future__ import annotations

import numpy as np

from core.preprocessor.native_tri import MeshState, OperatorKind, OperatorTransaction


def _tet_surface() -> tuple[np.ndarray, np.ndarray]:
    vertices = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        dtype=float,
    )
    faces = np.array([[0, 2, 1], [0, 0, 3], [0, 1, 3], [1, 2, 3]], dtype=np.int64)
    faces[1] = [0, 3, 2]
    return vertices, faces


def test_operator_loop_is_safe_noop_until_quality_move_exists() -> None:
    vertices, faces = _tet_surface()
    tx = OperatorTransaction(vertices, faces)
    report = tx.attempt(OperatorKind.SPLIT)
    assert not report.accepted
    assert report.reason == "mvp_noop_operator"
    np.testing.assert_array_equal(tx.state.vertices, vertices)
    np.testing.assert_array_equal(tx.state.faces, faces)


def test_invalid_candidate_rolls_back_without_mutating_state() -> None:
    vertices, faces = _tet_surface()
    tx = OperatorTransaction(vertices, faces)
    before = MeshState(tx.state.vertices.copy(), tx.state.faces.copy())
    bad_faces = faces.copy()
    bad_faces[0] = [0, 0, 1]
    report = tx.attempt(OperatorKind.COLLAPSE, (vertices, bad_faces))
    assert not report.accepted
    assert report.reason == "link_condition_failed"
    np.testing.assert_array_equal(tx.state.vertices, before.vertices)
    np.testing.assert_array_equal(tx.state.faces, before.faces)


def test_valid_candidate_passes_transaction_guards() -> None:
    vertices, faces = _tet_surface()
    tx = OperatorTransaction(vertices, faces)
    report = tx.attempt(OperatorKind.FLIP, (vertices, faces))
    assert report.accepted
    assert report.reason == "committed"
