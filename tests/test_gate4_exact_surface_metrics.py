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
    assert (
        record.source_integral_admissibility
        == "unverified_surface_not_closed_or_orientation_consistent"
    )
    assert (
        record.output_integral_admissibility
        == "unverified_surface_not_closed_or_orientation_consistent"
    )
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


def test_clean_closed_native_audit_enables_oriented_integrals_only(monkeypatch) -> None:
    class _NativeMetrics:
        @staticmethod
        def aabb_overlap_pairs(*_args):
            return np.empty((0, 2), dtype=np.int64)

        @staticmethod
        def triangle_intersections_segment(*_args):
            return 0, np.empty((0, 2), dtype=np.int64)

    monkeypatch.setattr(
        "core.utils.native_extensions.load_native_metrics", lambda: _NativeMetrics()
    )
    record = measure_gate4_exact_surface_metrics(
        _TETRA_POINTS,
        _TETRA_FACES,
        _TETRA_POINTS,
        _TETRA_FACES,
        sample_count=64,
        source_sha256="a" * 64,
        output_sha256="b" * 64,
    )

    assert record.source_self_intersection_status == "measured_no_intersections"
    assert record.output_self_intersection_status == "measured_no_intersections"
    assert (
        record.source_integral_admissibility
        == "admitted_closed_orientation_consistent_native_si_clean"
    )
    assert (
        record.output_integral_admissibility
        == "admitted_closed_orientation_consistent_native_si_clean"
    )
    assert "topology.self_intersections" in record.available_fields
    assert "topology.self_intersections" not in record.unverified_fields
    assert record.integral_status == "measured_closed_orientation_consistent_native_si_clean"
    assert record.source_signed_volume == record.output_signed_volume == 1.0 / 6.0
    assert record.volume_error_pct == 0.0
    assert record.centroid_shift_rel == 0.0
    assert "integral.volume_error_pct" in record.available_fields
    assert "integral.volume_error_pct" not in record.unverified_fields
    assert record.signed_status == "unverified_exact_signed_sample_predicate_unavailable"
    assert record.signed_mean_source_to_output is None
    assert record.source_sha256 == "a" * 64
    assert record.output_sha256 == "b" * 64
    assert record.gate4_pass is False


def test_intersection_or_missing_native_audit_keeps_integrals_unverified(monkeypatch) -> None:
    monkeypatch.setattr("core.utils.native_extensions.load_native_metrics", lambda: None)
    record = measure_gate4_exact_surface_metrics(
        _TETRA_POINTS, _TETRA_FACES, _TETRA_POINTS, _TETRA_FACES, sample_count=64
    )

    assert record.integral_status == "unverified_exhaustive_native_self_intersection_required"
    assert record.source_integral_admissibility == "unverified_native_predicate_unavailable"
    assert record.output_integral_admissibility == "unverified_native_predicate_unavailable"
    assert "topology.self_intersections" in record.unverified_fields
    assert record.volume_error_pct is None
    assert record.centroid_shift_rel is None
    assert "integral.volume_error_pct" in record.unverified_fields
    assert record.signed_status == "unverified_validated_closed_surfaces_required"
    assert record.gate4_pass is False


def test_detected_self_intersection_keeps_topology_field_unverified(monkeypatch) -> None:
    class _NativeMetrics:
        @staticmethod
        def aabb_overlap_pairs(*_args):
            return np.asarray([[0, 1]], dtype=np.int64)

        @staticmethod
        def triangle_intersections_segment(*_args):
            return 1, np.asarray([[0, 1]], dtype=np.int64)

    monkeypatch.setattr(
        "core.utils.native_extensions.load_native_metrics", lambda: _NativeMetrics()
    )
    record = measure_gate4_exact_surface_metrics(
        _TETRA_POINTS, _TETRA_FACES, _TETRA_POINTS, _TETRA_FACES, sample_count=64
    )

    assert record.source_self_intersection_status == "measured_intersections_present"
    assert record.output_self_intersection_status == "measured_intersections_present"
    assert "topology.self_intersections" not in record.available_fields
    assert "topology.self_intersections" in record.unverified_fields
    assert record.gate4_pass is False
