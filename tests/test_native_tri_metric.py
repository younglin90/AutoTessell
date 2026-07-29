"""Analytic checks for the native-tri Phase-2 metric primitives."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from core.analyzer.readers import read_stl
from core.preprocessor.native_tri import OperatorTransaction


def test_metric_intersection_is_idempotent_and_dominates_inputs() -> None:
    from core.preprocessor.native_tri.metric import intersect_spd_metrics

    first = np.diag([1.0, 4.0, 9.0])
    second = np.diag([4.0, 1.0, 16.0])
    result = intersect_spd_metrics(first, second)
    assert np.allclose(result, np.diag([4.0, 4.0, 16.0]))
    assert np.allclose(intersect_spd_metrics(first, first), first)
    for direction in np.eye(3):
        assert direction @ result @ direction >= direction @ first @ direction
        assert direction @ result @ direction >= direction @ second @ direction


def test_metric_intersection_is_rotation_covariant() -> None:
    from core.preprocessor.native_tri.metric import intersect_spd_metrics

    angle = 0.37
    rotation = np.array(
        [
            [np.cos(angle), -np.sin(angle), 0.0],
            [np.sin(angle), np.cos(angle), 0.0],
            [0.0, 0.0, 1.0],
        ],
    )
    first = np.diag([1.0, 4.0, 9.0])
    second = np.diag([2.0, 3.0, 16.0])
    rotated = intersect_spd_metrics(
        rotation @ first @ rotation.T,
        rotation @ second @ rotation.T,
    )
    expected = rotation @ intersect_spd_metrics(first, second) @ rotation.T
    assert np.allclose(rotated, expected, atol=1e-12)


def test_bl_metric_has_requested_tangent_and_normal_scales() -> None:
    from core.preprocessor.native_tri.metric import make_bl_metric

    metric = make_bl_metric(
        np.array([[0.0, 0.0, 1.0]]),
        tangential_length=0.5,
        normal_length=0.1,
    )[0]
    assert np.allclose(np.linalg.eigvalsh(metric), [4.0, 4.0, 100.0])
    assert metric[0, 0] == pytest.approx(4.0)
    assert metric[2, 2] == pytest.approx(100.0)


def test_metric_edge_lengths_use_endpoint_intersection() -> None:
    # Keep this test independent of an operator-loop wiring decision.  The
    # primitive is exercised through a local pair of known diagonal fields.
    from core.preprocessor.native_tri.metric import metric_edge_lengths

    vertices = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
    metrics = np.stack([np.diag([1.0, 1.0, 1.0]), np.diag([4.0, 1.0, 1.0])])
    lengths = metric_edge_lengths(vertices, np.array([[0, 1]]), metrics)
    assert lengths[0] == pytest.approx(2.0)


def test_tangent_edge_length_ignores_bl_normal_eigenvalue() -> None:
    from core.preprocessor.native_tri.metric import tangent_metric_edge_lengths

    vertices = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
    normals = np.array([[0.0, 0.0, 1.0], [0.0, 0.0, 1.0]])
    metrics = np.stack([np.diag([4.0, 4.0, 10000.0])] * 2)
    lengths = tangent_metric_edge_lengths(
        vertices, np.array([[0, 1]]), metrics, normals,
    )
    assert lengths[0] == pytest.approx(2.0)


def test_tangent_edge_rejects_explicit_normal_discontinuity() -> None:
    from core.preprocessor.native_tri.metric import tangent_metric_edge_lengths

    vertices = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
    normals = np.array([[0.0, 0.0, 1.0], [1.0, 0.0, 0.0]])
    metrics = np.stack([np.eye(3), np.eye(3)])
    with pytest.raises(ValueError, match="normal-discontinuous"):
        tangent_metric_edge_lengths(
            vertices,
            np.array([[0, 1]]),
            metrics,
            normals,
            max_normal_angle_deg=45.0,
        )


def test_tangent_edge_rejects_feature_vertex_mask() -> None:
    from core.preprocessor.native_tri.metric import tangent_metric_edge_lengths

    vertices = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
    normals = np.array([[0.0, 0.0, 1.0], [0.0, 0.0, 1.0]])
    with pytest.raises(ValueError, match="feature vertex"):
        tangent_metric_edge_lengths(
            vertices,
            np.array([[0, 1]]),
            np.stack([np.eye(3), np.eye(3)]),
            normals,
            feature_vertices=np.array([True, False]),
        )


def test_cube_has_a_reportable_feature_normal_spread() -> None:
    import trimesh

    from core.preprocessor.native_tri.metric import vertex_normal_spread_deg

    mesh = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    spread = vertex_normal_spread_deg(mesh.vertices, mesh.faces)
    assert float(spread.max()) == pytest.approx(90.0)
    assert int((spread > 45.0).sum()) == 8


def test_metric_field_drives_split_and_conservatively_remaps() -> None:
    vertices = np.array(
        [[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
    )
    faces = np.array([[0, 1, 2]], dtype=np.int64)
    metrics = np.stack([np.eye(3)] * len(vertices))
    tx = OperatorTransaction(vertices, faces, metric_field=metrics)

    assert tx.should_split_edge((0, 1))
    report = tx.split_edge((0, 1))

    assert report.accepted
    assert len(tx.state.vertices) == 4
    assert tx.metric_field is not None
    assert tx.metric_field.shape == (4, 3, 3)
    assert np.allclose(tx.metric_field[-1], np.eye(3))


def test_metric_field_drives_collapse_and_conservatively_remaps() -> None:
    mesh = read_stl(Path(__file__).parent / "benchmarks" / "cube.stl")
    vertices = np.asarray(mesh.vertices, dtype=float)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    edges = sorted(
        {
            tuple(sorted((int(face[i]), int(face[(i + 1) % 3]))))
            for face in faces.tolist()
            for i in range(3)
        },
    )
    edge = min(
        edges,
        key=lambda item: np.linalg.norm(vertices[item[0]] - vertices[item[1]]),
    )
    metrics = np.stack([np.eye(3) * 0.25] * len(vertices))
    tx = OperatorTransaction(vertices, faces, metric_field=metrics)

    assert tx.should_collapse_edge(edge)
    report = tx.collapse_edge(edge)

    assert report.accepted
    assert tx.metric_field is not None
    assert tx.metric_field.shape == (len(tx.state.vertices), 3, 3)
    assert np.linalg.eigvalsh(tx.metric_field).min() > 0.0


def test_metric_field_length_must_match_vertices() -> None:
    vertices = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    faces = np.array([[0, 1, 2]], dtype=np.int64)
    with pytest.raises(ValueError, match="length must match"):
        OperatorTransaction(vertices, faces, metric_field=np.stack([np.eye(3)] * 2))


def test_metric_field_runs_one_guarded_round_without_scalar_target() -> None:
    mesh = read_stl(Path(__file__).parent / "benchmarks" / "cube.stl")
    vertices = np.asarray(mesh.vertices, dtype=float)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    metrics = np.stack([np.eye(3)] * len(vertices))
    tx = OperatorTransaction(vertices, faces, metric_field=metrics)

    reports = tx.run_one_round(smooth=False)

    assert reports
    assert tx.metric_field is not None
    assert len(tx.metric_field) == len(tx.state.vertices)


def test_operator_uses_tangent_metric_and_locks_feature_vertices() -> None:
    from core.preprocessor.native_tri.metric import make_bl_metric

    vertices = np.array(
        [[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
    )
    faces = np.array([[0, 1, 2]], dtype=np.int64)
    normals = np.stack([[0.0, 0.0, 1.0]] * len(vertices))
    metrics = make_bl_metric(normals, tangential_length=1.0, normal_length=0.01)
    tangent_tx = OperatorTransaction(
        vertices,
        faces,
        metric_field=metrics,
        metric_normals=normals,
    )
    assert tangent_tx.should_split_edge((0, 1))

    feature_vertices = np.array([True, False, False])
    tx = OperatorTransaction(
        vertices,
        faces,
        metric_field=metrics,
        metric_normals=normals,
        metric_feature_vertices=feature_vertices,
    )
    assert not tx.should_split_edge((0, 1))
    smooth = tx.smooth_vertex(0)
    assert not smooth.accepted
    assert smooth.reason == "metric_feature_vertex_locked"


def test_operator_rejects_edges_without_a_common_tangent_plane() -> None:
    vertices = np.array(
        [[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
    )
    faces = np.array([[0, 1, 2]], dtype=np.int64)
    metrics = np.stack([np.eye(3)] * len(vertices))
    normals = np.array(
        [[0.0, 0.0, 1.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]],
    )
    tx = OperatorTransaction(
        vertices,
        faces,
        metric_field=metrics,
        metric_normals=normals,
        metric_max_normal_angle_deg=45.0,
    )

    assert not tx.should_split_edge((0, 1))


def test_bl_handoff_separates_tangent_and_normal_scales() -> None:
    from core.preprocessor.native_tri.metric import audit_bl_handoff, make_bl_metric

    normals = np.array([[0.0, 0.0, 1.0], [0.0, 0.0, 1.0]])
    metrics = make_bl_metric(normals, tangential_length=0.5, normal_length=0.1)
    report = audit_bl_handoff(metrics, normals)

    assert report.valid
    assert report.n_feature_rejected == 0
    assert report.normal_length_min == pytest.approx(0.1)
    assert report.normal_length_max == pytest.approx(0.1)
    assert report.tangent_length_min == pytest.approx(0.5)
    assert report.tangent_length_max == pytest.approx(0.5)


def test_bl_handoff_reports_feature_vertices_without_inventing_tangents() -> None:
    from core.preprocessor.native_tri.metric import audit_bl_handoff, make_bl_metric

    normals = np.array(
        [[0.0, 0.0, 1.0], [0.0, 0.0, 1.0], [0.0, 0.0, 1.0]],
    )
    metrics = make_bl_metric(normals, tangential_length=1.0, normal_length=0.1)
    report = audit_bl_handoff(
        metrics,
        normals,
        feature_vertices=np.array([True, False, False]),
    )

    assert report.valid
    assert report.n_feature_rejected == 1
    assert report.n_invalid == 0
    assert report.tangent_length_min == pytest.approx(1.0)
