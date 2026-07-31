"""Focused contracts for controlled non-promoting Gate-4 surface metrics."""

from __future__ import annotations

import numpy as np

from core.evaluator.gate4_exact_surface_metrics import (
    measure_gate4_exact_surface_metrics,
)

_TETRA_POINTS = np.asarray(
    [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
    dtype=np.float64,
)
_TETRA_FACES = np.asarray([[0, 2, 1], [0, 1, 3], [1, 2, 3], [2, 0, 3]], dtype=np.int64)


def test_identical_closed_tetra_measures_zero_distance_and_normals() -> None:
    record = measure_gate4_exact_surface_metrics(
        _TETRA_POINTS, _TETRA_FACES, _TETRA_POINTS, _TETRA_FACES, sample_count=128
    )

    assert record.status == "unverified_authority_incomplete"
    assert record.source_to_output is not None
    assert record.output_to_source is not None
    assert record.source_to_output.maximum <= 1.0e-12
    assert record.output_to_source.maximum <= 1.0e-12
    assert record.symmetric_sampled_max is not None
    assert record.symmetric_sampled_max <= 1.0e-12
    assert record.normal_status == "measured_closed_orientation_consistent"
    assert record.normal_p95_deg == 0.0
    assert record.normal_p99_deg == 0.0
    assert record.normal_flipped == 0
    assert record.gate4_pass is False
    assert "distance.signed_mean" in record.unverified_fields
    assert "provenance.source_to_output" in record.unverified_fields


def test_translated_closed_tetra_has_controlled_bidirectional_distance() -> None:
    shifted = _TETRA_POINTS + np.asarray([0.25, 0.0, 0.0])
    record = measure_gate4_exact_surface_metrics(
        _TETRA_POINTS, _TETRA_FACES, shifted, _TETRA_FACES, sample_count=128
    )

    assert record.source_to_output is not None
    assert record.output_to_source is not None
    assert record.source_to_output.maximum > 0.0
    assert record.output_to_source.maximum > 0.0
    assert record.symmetric_sampled_max == max(
        record.source_to_output.maximum, record.output_to_source.maximum
    )
    assert record.gate4_pass is False


def test_open_surface_measures_distance_but_defers_normals() -> None:
    open_faces = np.asarray([[0, 1, 2]], dtype=np.int64)
    record = measure_gate4_exact_surface_metrics(
        _TETRA_POINTS, open_faces, _TETRA_POINTS, open_faces, sample_count=32
    )

    assert record.source_to_output is not None
    assert record.normal_status == "unverified_surface_not_closed_or_orientation_consistent"
    assert record.normal_p95_deg is None
    assert record.normal_flipped is None
    assert record.gate4_pass is False


def test_invalid_surface_is_fail_closed() -> None:
    bad_points = _TETRA_POINTS.copy()
    bad_points[0, 0] = np.nan

    record = measure_gate4_exact_surface_metrics(
        bad_points, _TETRA_FACES, _TETRA_POINTS, _TETRA_FACES, sample_count=32
    )

    assert record.status == "unverified_invalid_finite_triangle_surface"
    assert record.source_to_output is None
    assert record.available_fields == ()
    assert record.gate4_pass is False


def test_non_integer_triangle_indices_are_rejected() -> None:
    non_integer_faces = _TETRA_FACES.astype(np.float64)
    record = measure_gate4_exact_surface_metrics(
        _TETRA_POINTS, non_integer_faces, _TETRA_POINTS, _TETRA_FACES, sample_count=32
    )

    assert record.status == "unverified_invalid_finite_triangle_surface"
    assert record.source_to_output is None
    assert record.gate4_pass is False


def test_sampling_is_deterministic() -> None:
    first = measure_gate4_exact_surface_metrics(
        _TETRA_POINTS, _TETRA_FACES, _TETRA_POINTS, _TETRA_FACES, sample_count=64
    )
    second = measure_gate4_exact_surface_metrics(
        _TETRA_POINTS, _TETRA_FACES, _TETRA_POINTS, _TETRA_FACES, sample_count=64
    )

    assert first == second
