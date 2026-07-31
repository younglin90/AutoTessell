"""Fail-closed completeness inventory for legacy Gate-4 geometry metrics."""

from __future__ import annotations

import math

from core.schemas import (
    Gate4MetricCompletenessEvidence,
    Gate4OutputArtifactIdentity,
    Gate4SourceIdentity,
    GeometryFidelity,
)

REQUIRED_GATE4_FIELDS = (
    "distance.d_0_to_h.rms",
    "distance.d_0_to_h.p95",
    "distance.d_0_to_h.p99",
    "distance.d_0_to_h.max",
    "distance.d_h_to_0.rms",
    "distance.d_h_to_0.p95",
    "distance.d_h_to_0.p99",
    "distance.d_h_to_0.max",
    "distance.hausdorff_symmetric",
    "distance.signed_mean",
    "normals.p95_deg",
    "normals.p99_deg",
    "normals.flipped",
    "features.critical_missing",
    "features.coverage",
    "features.distance_p95",
    "integral.area_error_pct",
    "integral.volume_error_pct",
    "integral.centroid_shift_rel",
    "topology.components_match",
    "topology.genus_match",
    "topology.boundary_loops_match",
    "topology.holes_introduced",
    "topology.self_intersections",
    "topology.nonmanifold_edges",
    "topology.nonmanifold_vertices",
    "patches.compared",
    "patches.missing",
    "patches.wrong_type",
    "patches.adjacency_graph_match",
    "physical_groups.authoritative_mapping",
    "provenance.source_to_output",
)


Gate4MetricCompletenessReport = Gate4MetricCompletenessEvidence
def _canonical_sha256(value: object) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == 64
        and value == value.lower()
        and all(character in "0123456789abcdef" for character in value)
    )


def _valid_source_identity(source: Gate4SourceIdentity | None) -> bool:
    return bool(
        source is not None
        and source.original_path
        and source.snapshot_path
        and source.byte_count >= 0
        and _canonical_sha256(source.sha256)
    )


def _valid_output_identity(output: Gate4OutputArtifactIdentity | None) -> bool:
    return bool(
        output is not None
        and output.poly_mesh_path
        and _canonical_sha256(output.sha256)
        and output.file_sha256
        and all(_canonical_sha256(digest) for digest in output.file_sha256.values())
    )


def _finite(value: float | None) -> bool:
    return value is not None and math.isfinite(value)


def report_gate4_metric_completeness(
    *,
    legacy_metric: GeometryFidelity | None,
    source: Gate4SourceIdentity | None,
    output: Gate4OutputArtifactIdentity | None,
) -> Gate4MetricCompletenessEvidence:
    """Inventory available legacy observations without inventing Gate-4 fields."""
    missing: list[str] = []
    if not _valid_source_identity(source):
        missing.append("identity.source_snapshot")
    if not _valid_output_identity(output):
        missing.append("identity.output_artifact")
    if legacy_metric is None:
        missing.append("legacy_geometry_fidelity")
        return Gate4MetricCompletenessReport(
            status="unverified_metric_missing",
            source=source,
            output=output,
            available_fields=(),
            missing_fields=tuple(missing) + REQUIRED_GATE4_FIELDS,
            gate4_pass=False,
        )

    available: list[str] = []
    legacy_fields = (
        ("legacy.distance.hausdorff_symmetric_approx", legacy_metric.hausdorff_distance),
        ("legacy.distance.hausdorff_relative_approx", legacy_metric.hausdorff_relative),
        ("legacy.distance.combined_rms", legacy_metric.distance_rms),
        ("legacy.distance.combined_p95", legacy_metric.distance_p95),
        ("legacy.distance.combined_p99", legacy_metric.distance_p99),
        ("legacy.normals.absolute_max_deg", legacy_metric.normal_deviation_max_deg),
        ("legacy.features.normal_proxy", legacy_metric.feature_preservation_score),
        ("legacy.integral.area_error_pct", legacy_metric.surface_area_deviation_percent),
    )
    for name, value in legacy_fields:
        if _finite(value):
            available.append(name)
        else:
            missing.append(name)

    return Gate4MetricCompletenessReport(
        status=(
            "unverified_metric_incomplete"
            if available and not any(item.startswith("identity.") for item in missing)
            else "unverified_metric_missing"
        ),
        source=source,
        output=output,
        available_fields=tuple(available),
        missing_fields=tuple(missing) + REQUIRED_GATE4_FIELDS,
        gate4_pass=False,
    )
