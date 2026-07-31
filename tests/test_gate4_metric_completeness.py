from __future__ import annotations

from core.evaluator.gate4_metric_completeness import (
    REQUIRED_GATE4_FIELDS,
    report_gate4_metric_completeness,
)
from core.schemas import (
    Gate4OutputArtifactIdentity,
    Gate4SourceIdentity,
    GeometryFidelity,
)


def _source() -> Gate4SourceIdentity:
    return Gate4SourceIdentity(
        original_path="/input/source.stl",
        snapshot_path="/case/_work/gate4-source/source.stl",
        byte_count=12,
        sha256="a" * 64,
    )


def _output() -> Gate4OutputArtifactIdentity:
    return Gate4OutputArtifactIdentity(
        poly_mesh_path="/case/constant/polyMesh",
        file_sha256={
            name: "b" * 64 for name in ("points", "faces", "owner", "neighbour", "boundary")
        },
        sha256="c" * 64,
    )


def _legacy_metric(**overrides: float | None) -> GeometryFidelity:
    values: dict[str, float | None] = {
        "hausdorff_distance": 0.1,
        "hausdorff_relative": 0.01,
        "surface_area_deviation_percent": 0.2,
        "distance_rms": 0.03,
        "distance_p95": 0.04,
        "distance_p99": 0.05,
        "normal_deviation_max_deg": 6.0,
        "feature_preservation_score": 0.8,
    }
    values.update(overrides)
    return GeometryFidelity(**values)


def test_missing_legacy_metric_is_fail_closed() -> None:
    report = report_gate4_metric_completeness(
        legacy_metric=None,
        source=_source(),
        output=_output(),
    )

    assert report.status == "unverified_metric_missing"
    assert report.available_fields == ()
    assert "legacy_geometry_fidelity" in report.missing_fields
    assert set(REQUIRED_GATE4_FIELDS).issubset(report.missing_fields)
    assert report.gate4_pass is False


def test_legacy_values_are_observations_not_complete_gate4_metrics() -> None:
    report = report_gate4_metric_completeness(
        legacy_metric=_legacy_metric(),
        source=_source(),
        output=_output(),
    )

    assert report.status == "unverified_metric_incomplete"
    assert "legacy.distance.hausdorff_symmetric_approx" in report.available_fields
    assert "legacy.integral.area_error_pct" in report.available_fields
    assert "distance.d_0_to_h.rms" in report.missing_fields
    assert "distance.signed_mean" in report.missing_fields
    assert "integral.volume_error_pct" in report.missing_fields
    assert "features.coverage" in report.missing_fields
    assert "physical_groups.authoritative_mapping" in report.missing_fields
    assert report.gate4_pass is False


def test_missing_or_malformed_identity_is_fail_closed() -> None:
    malformed_source = _source().model_copy(update={"sha256": "not-a-digest"})
    report = report_gate4_metric_completeness(
        legacy_metric=_legacy_metric(),
        source=malformed_source,
        output=None,
    )

    assert report.status == "unverified_metric_missing"
    assert "identity.source_snapshot" in report.missing_fields
    assert "identity.output_artifact" in report.missing_fields
    assert report.gate4_pass is False


def test_nonfinite_legacy_field_is_not_relabelled_as_available() -> None:
    report = report_gate4_metric_completeness(
        legacy_metric=_legacy_metric(distance_rms=float("nan")),
        source=_source(),
        output=_output(),
    )

    assert report.status == "unverified_metric_incomplete"
    assert "legacy.distance.combined_rms" not in report.available_fields
    assert "legacy.distance.combined_rms" in report.missing_fields
    assert report.gate4_pass is False
