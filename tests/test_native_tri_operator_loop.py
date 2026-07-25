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


def test_collapse_and_flip_safe_rejections_leave_state_unchanged() -> None:
    vertices, faces = _tet_surface()
    collapse_tx = OperatorTransaction(vertices, faces, target_edge_length=2.0)
    before = collapse_tx.state.copy()
    report = collapse_tx.collapse_edge((0, 1))
    assert not report.accepted
    assert report.reason == "link_condition_failed"
    np.testing.assert_array_equal(collapse_tx.state.vertices, before.vertices)
    np.testing.assert_array_equal(collapse_tx.state.faces, before.faces)

    flip_tx = OperatorTransaction(vertices, faces)
    before = flip_tx.state.copy()
    report = flip_tx.flip_edge((0, 1))
    assert not report.accepted
    assert report.reason == "flip_not_improved"
    np.testing.assert_array_equal(flip_tx.state.vertices, before.vertices)
    np.testing.assert_array_equal(flip_tx.state.faces, before.faces)


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


def test_collapse_uses_strict_lower_hysteresis_bound() -> None:
    vertices = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    faces = np.array([[0, 1, 2]], dtype=np.int64)
    tx = OperatorTransaction(vertices, faces, target_edge_length=1.25)
    before = tx.state.copy()

    assert not tx.should_collapse_edge((0, 1))  # 1 == 4L/5: strict inequality.
    report = tx.collapse_edge((0, 1))
    assert not report.accepted
    assert report.reason == "collapse_threshold_not_exceeded"
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


def _edge_incidence(faces: np.ndarray) -> dict[tuple[int, int], list[int]]:
    incidence: dict[tuple[int, int], list[int]] = {}
    for face in faces.tolist():
        for u, v in zip(face, face[1:] + face[:1]):
            edge = (min(int(u), int(v)), max(int(u), int(v)))
            direction = 1 if (int(u), int(v)) == edge else -1
            incidence.setdefault(edge, []).append(direction)
    return incidence


def test_collapse_commits_only_for_a_valid_short_cube_edge() -> None:
    cube_path = Path(__file__).parent / "benchmarks" / "cube.stl"
    mesh = read_stl(cube_path)
    vertices = np.asarray(mesh.vertices, dtype=float)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    edge = min(
        {
            tuple(sorted((int(face[i]), int(face[(i + 1) % 3]))))
            for face in faces.tolist()
            for i in range(3)
        },
        key=lambda item: np.linalg.norm(vertices[item[0]] - vertices[item[1]]),
    )

    tx = OperatorTransaction(vertices, faces, target_edge_length=2.0)
    assert tx.should_collapse_edge(edge)
    report = tx.collapse_edge(edge)
    assert report.accepted
    assert len(tx.state.vertices) == len(vertices) - 1
    assert len(tx.state.faces) == len(faces) - 2
    incidence = _edge_incidence(tx.state.faces)
    assert all(len(faces_for_edge) == 2 for faces_for_edge in incidence.values())


def test_flip_rejects_boundary_and_non_improving_candidates() -> None:
    vertices = np.array(
        [[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [0.0, 1.0, 0.0], [2.0, 1.0, 0.0]],
    )
    faces = np.array([[0, 1, 2], [1, 3, 2]], dtype=np.int64)
    tx = OperatorTransaction(vertices, faces)
    before = tx.state.copy()
    report = tx.flip_edge((0, 1))
    assert not report.accepted
    assert report.reason == "link_condition_failed"
    np.testing.assert_array_equal(tx.state.vertices, before.vertices)
    np.testing.assert_array_equal(tx.state.faces, before.faces)

    report = tx.flip_edge((1, 2))
    assert not report.accepted
    assert report.reason == "flip_not_improved"
    np.testing.assert_array_equal(tx.state.vertices, before.vertices)
    np.testing.assert_array_equal(tx.state.faces, before.faces)


def test_flip_commits_when_local_quality_improves() -> None:
    vertices = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 1.0, 0.0], [0.0, 1.0, 0.0]],
    )
    faces = np.array([[0, 1, 2], [1, 3, 2]], dtype=np.int64)
    tx = OperatorTransaction(vertices, faces)
    assert tx.should_flip_edge((1, 2))
    report = tx.flip_edge((1, 2))
    assert report.accepted
    assert len(tx.state.faces) == len(faces)
    assert {tuple(sorted(face)) for face in tx.state.faces.tolist()} == {
        (0, 1, 3),
        (0, 2, 3),
    }


def test_one_round_keeps_cube_manifold_and_watertight_without_smoothing() -> None:
    cube_path = Path(__file__).parent / "benchmarks" / "cube.stl"
    mesh = read_stl(cube_path)
    vertices = np.asarray(mesh.vertices, dtype=float)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    tx = OperatorTransaction(vertices, faces, target_edge_length=1.0)
    reports = tx.run_one_round()

    incidence = _edge_incidence(tx.state.faces)
    assert incidence
    assert all(len(directions) == 2 for directions in incidence.values())
    assert all(sorted(directions) == [-1, 1] for directions in incidence.values())
    assert len(tx.state.vertices) - len(incidence) + len(tx.state.faces) == 2
    assert all(isinstance(report.operator, OperatorKind) for report in reports)
    order = {OperatorKind.SPLIT: 0, OperatorKind.COLLAPSE: 1, OperatorKind.FLIP: 2}
    accepted = [order[report.operator] for report in reports if report.accepted]
    assert accepted == sorted(accepted)
