"""L0 contract tests for the metric-tensor source-surface transaction."""

from __future__ import annotations

import numpy as np
import pytest

from core.generator.native_tet.rescue_gate import has_strict_writer_topology
from core.generator.native_tet.surface_transaction_gate import (
    apply_metric_surface_transaction,
    metric_source_transaction_enabled,
)


def _tetrahedron() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    vertices = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )
    faces = np.array(
        [[0, 1, 2], [0, 1, 3], [0, 2, 3], [1, 2, 3]],
        dtype=np.int64,
    )
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    return vertices, faces, tets


def test_metric_source_transaction_is_default_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUTO_TESSELL_TET_METRIC_SOURCE_TXN", raising=False)
    assert not metric_source_transaction_enabled()

    monkeypatch.setenv("AUTO_TESSELL_TET_METRIC_SOURCE_TXN", "1")
    assert metric_source_transaction_enabled()

    monkeypatch.setenv("AUTO_TESSELL_TET_METRIC_SOURCE_TXN", "true")
    assert not metric_source_transaction_enabled()


def test_metric_source_transaction_rolls_back_shifted_strict_topology_candidate() -> None:
    vertices, faces, tets = _tetrahedron()
    pre_points = vertices.copy()
    pre_tets = tets.copy()
    # This mocks a sweep candidate which remains writer-topology safe but has
    # moved the entire boundary away from the original source surface.
    candidate_points = pre_points + np.array([0.1, 0.0, 0.0])
    candidate_tets = pre_tets.copy()

    assert has_strict_writer_topology(candidate_points, candidate_tets)
    points, output_tets, report = apply_metric_surface_transaction(
        vertices,
        faces,
        pre_points,
        pre_tets,
        candidate_points,
        candidate_tets,
    )

    assert not report.accepted
    assert "hausdorff_relative_worsened" in report.reason
    assert report.post.hausdorff_relative > report.pre.hausdorff_relative
    # Exact snapshot objects, not a repaired or partially committed candidate.
    assert points is pre_points
    assert output_tets is pre_tets
    assert np.array_equal(points, pre_points)
    assert np.array_equal(output_tets, pre_tets)


def test_metric_source_transaction_commits_source_equivalent_candidate() -> None:
    vertices, faces, tets = _tetrahedron()
    pre_points = vertices.copy()
    pre_tets = tets.copy()
    candidate_points = pre_points.copy()
    candidate_tets = pre_tets.copy()

    points, output_tets, report = apply_metric_surface_transaction(
        vertices,
        faces,
        pre_points,
        pre_tets,
        candidate_points,
        candidate_tets,
    )

    assert report.accepted, report.reason
    assert points is candidate_points
    assert output_tets is candidate_tets
