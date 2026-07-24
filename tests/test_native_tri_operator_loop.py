"""Phase-0 safety tests for the separate native-tri operator skeleton."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from core.analyzer.readers import read_stl
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
    report = tx.attempt(OperatorKind.SPLIT, (vertices, bad_faces))
    assert not report.accepted
    assert report.reason == "link_condition_failed"
    np.testing.assert_array_equal(tx.state.vertices, before.vertices)
    np.testing.assert_array_equal(tx.state.faces, before.faces)


def test_reserved_collapse_and_flip_are_rejected_without_mutation() -> None:
    vertices, faces = _tet_surface()
    tx = OperatorTransaction(vertices, faces)
    before = tx.state.copy()
    for operator in (OperatorKind.COLLAPSE, OperatorKind.FLIP):
        report = tx.attempt(operator, (vertices, faces))
        assert not report.accepted
        assert report.reason == "operator_not_implemented"
        np.testing.assert_array_equal(tx.state.vertices, before.vertices)
        np.testing.assert_array_equal(tx.state.faces, before.faces)


def test_split_uses_botsch_dunyach_upper_hysteresis_bound() -> None:
    vertices = np.array([[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    faces = np.array([[0, 1, 2]], dtype=np.int64)
    tx = OperatorTransaction(vertices, faces, target_edge_length=1.5)
    before = tx.state.copy()

    assert not tx.should_split_edge((0, 1))  # 2 == 4L/3: hysteresis is strict.
    report = tx.split_edge((0, 1))
    assert not report.accepted
    assert report.reason == "split_threshold_not_exceeded"
    np.testing.assert_array_equal(tx.state.vertices, before.vertices)
    np.testing.assert_array_equal(tx.state.faces, before.faces)


def test_cube_split_commits_and_foldover_rejection_rolls_back() -> None:
    cube_path = Path(__file__).parent / "benchmarks" / "cube.stl"
    mesh = read_stl(cube_path)
    vertices = np.asarray(mesh.vertices, dtype=float)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    edges = sorted(
        {
            tuple(sorted((int(face[i]), int(face[(i + 1) % 3]))))
            for face in faces.tolist()
            for i in range(3)
        }
    )
    long_edges = [
        edge for edge in edges if np.linalg.norm(vertices[edge[0]] - vertices[edge[1]]) > 4.0 / 3.0
    ]
    assert long_edges

    tx = OperatorTransaction(vertices, faces, target_edge_length=1.0)
    report = tx.split_edge(long_edges[0])
    assert report.accepted
    assert len(tx.state.vertices) == len(vertices) + 1
    assert len(tx.state.faces) == len(faces) + 2

    rejected = OperatorTransaction(vertices, faces, target_edge_length=1.0)
    bad_faces = faces.copy()
    bad_faces[0] = bad_faces[0][[0, 2, 1]]
    before = rejected.state.copy()
    report = rejected.attempt(OperatorKind.SPLIT, (vertices, bad_faces))
    assert not report.accepted
    assert report.reason == "foldover_guard_failed"
    np.testing.assert_array_equal(rejected.state.vertices, before.vertices)
    np.testing.assert_array_equal(rejected.state.faces, before.faces)
