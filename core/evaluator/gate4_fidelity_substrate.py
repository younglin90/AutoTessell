"""Fail-closed, non-promoting evidence substrate for Gate-4 fidelity.

This module binds a Gate-4 comparison to an exact byte snapshot of the
caller-provided source and to one stable OpenFOAM ``polyMesh`` artifact.  It
intentionally does not decide Gate 4: the legacy geometry metric is incomplete
for the Gate-4 contract, so every result remains ``UNVERIFIED``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING

from core.schemas import (
    Gate4ActualSurfaceMetricEvidence,
    Gate4DirectedSurfaceDistanceEvidence,
    Gate4FidelityEvidence,
    Gate4OutputArtifactIdentity,
    Gate4SourceIdentity,
)
from core.utils.polymesh_reader import (
    parse_foam_boundary,
    parse_foam_faces,
    parse_foam_labels_array,
    parse_foam_points_array,
)

if TYPE_CHECKING:
    from core.evaluator.fidelity import GeometryFidelityChecker


_REQUIRED_POLYMESH_FILES = ("points", "faces", "owner", "neighbour", "boundary")
_EXACT_METRIC_SAMPLE_COUNT = 10_000
_ACTUAL_UNVERIFIED_FIELDS = (
    "distance.signed_mean",
    "topology.self_intersections",
    "integral.volume_error_pct",
    "integral.centroid_shift_rel",
    "features.authoritative_ids",
    "features.critical_missing",
    "patches.compared",
    "physical_groups.authoritative_mapping",
    "provenance.source_to_output",
)


def capture_immutable_source(
    source_path: Path,
    snapshot_dir: Path,
) -> Gate4SourceIdentity:
    """Write one exact source-byte snapshot before pipeline mutations begin."""
    resolved = source_path.resolve(strict=True)
    source_bytes = resolved.read_bytes()
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    suffix = resolved.suffix or ".bin"
    snapshot_path = snapshot_dir / f"gate4-original-{source_sha256}{suffix}"
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    if snapshot_path.exists():
        if snapshot_path.is_symlink() or snapshot_path.read_bytes() != source_bytes:
            raise ValueError("immutable Gate-4 source snapshot collision")
    else:
        snapshot_path.write_bytes(source_bytes)

    return Gate4SourceIdentity(
        original_path=str(resolved),
        snapshot_path=str(snapshot_path.resolve()),
        byte_count=len(source_bytes),
        sha256=source_sha256,
    )


def inspect_gate4_output_artifact(case_dir: Path) -> Gate4OutputArtifactIdentity | None:
    """Return the canonical identity for the mandatory Gate-4 polyMesh files."""
    poly_mesh = case_dir / "constant" / "polyMesh"
    if not poly_mesh.is_dir() or poly_mesh.is_symlink():
        return None

    files: dict[str, str] = {}
    for name in _REQUIRED_POLYMESH_FILES:
        candidate = poly_mesh / name
        if not candidate.is_file() or candidate.is_symlink():
            return None
        files[name] = hashlib.sha256(candidate.read_bytes()).hexdigest()

    aggregate = hashlib.sha256(
        json.dumps(files, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return Gate4OutputArtifactIdentity(
        poly_mesh_path=str(poly_mesh.resolve()),
        file_sha256=files,
        sha256=aggregate,
    )


def _unverified_actual_metric(
    status: str,
    *,
    sample_count: int,
) -> Gate4ActualSurfaceMetricEvidence:
    return Gate4ActualSurfaceMetricEvidence(
        status=status,
        sample_count=sample_count,
        method="deterministic_area_samples+exact_point_to_triangle_bvh",
        normal_status="unverified_not_measured",
        unverified_fields=_ACTUAL_UNVERIFIED_FIELDS,
        gate4_pass=False,
    )


def _strict_boundary_triangles(case_dir: Path):
    """Return every validated polyMesh boundary polygon as fan triangles.

    This intentionally avoids the legacy evaluator's name-based geometry-patch
    heuristic.  The caller must first require the strict combinatorial audit.
    """
    poly_mesh = case_dir / "constant" / "polyMesh"
    try:
        points = parse_foam_points_array(poly_mesh / "points")
        faces = parse_foam_faces(poly_mesh / "faces")
        owner = parse_foam_labels_array(poly_mesh / "owner")
        neighbour = parse_foam_labels_array(poly_mesh / "neighbour")
        patches = parse_foam_boundary(poly_mesh / "boundary")
    except Exception:  # noqa: BLE001
        return None
    if len(owner) != len(faces) or len(neighbour) > len(faces):
        return None
    expected_start = int(len(neighbour))
    boundary_indices: list[int] = []
    names: set[str] = set()
    for patch in patches:
        name = patch.get("name")
        start = patch.get("startFace")
        count = patch.get("nFaces")
        if (
            not isinstance(name, str)
            or not name
            or name in names
            or isinstance(start, bool)
            or not isinstance(start, int)
            or isinstance(count, bool)
            or not isinstance(count, int)
            or count < 0
            or start != expected_start
            or start + count > len(faces)
        ):
            return None
        names.add(name)
        boundary_indices.extend(range(start, start + count))
        expected_start += count
    if expected_start != len(faces):
        return None
    triangles: list[tuple[int, int, int]] = []
    for face_index in boundary_indices:
        face = faces[face_index]
        if len(face) < 3:
            return None
        first = int(face[0])
        triangles.extend(
            (first, int(face[index]), int(face[index + 1])) for index in range(1, len(face) - 1)
        )
    if not triangles:
        return None
    return points, triangles


def _as_actual_metric_evidence(record) -> Gate4ActualSurfaceMetricEvidence:
    def direction(value):
        if value is None:
            return None
        return Gate4DirectedSurfaceDistanceEvidence(
            rms=value.rms,
            p95=value.p95,
            p99=value.p99,
            maximum=value.maximum,
        )

    return Gate4ActualSurfaceMetricEvidence(
        status=record.status,
        sample_count=record.sample_count,
        method=record.method,
        source_to_output=direction(record.source_to_output),
        output_to_source=direction(record.output_to_source),
        symmetric_sampled_max=record.symmetric_sampled_max,
        normal_status=record.normal_status,
        normal_p95_deg=record.normal_p95_deg,
        normal_p99_deg=record.normal_p99_deg,
        normal_flipped=record.normal_flipped,
        available_fields=record.available_fields,
        unverified_fields=record.unverified_fields,
        gate4_pass=False,
    )


def _measure_actual_surface_metrics(
    *,
    source: Gate4SourceIdentity,
    case_dir: Path,
    topology_valid: bool,
    sample_count: int,
) -> Gate4ActualSurfaceMetricEvidence:
    """Bind C109 metrics only to a snapshot and strict polyMesh surface."""
    if not topology_valid:
        return _unverified_actual_metric(
            "unverified_output_surface_topology_invalid",
            sample_count=sample_count,
        )
    strict_output = _strict_boundary_triangles(case_dir)
    if strict_output is None:
        return _unverified_actual_metric(
            "unverified_output_surface_triangulation_invalid",
            sample_count=sample_count,
        )
    try:
        from core.analyzer.readers import read_stl  # noqa: PLC0415
        from core.evaluator.gate4_exact_surface_metrics import (  # noqa: PLC0415
            measure_gate4_exact_surface_metrics,
        )

        source_mesh = read_stl(Path(source.snapshot_path))
        output_points, output_triangles = strict_output
        record = measure_gate4_exact_surface_metrics(
            source_mesh.vertices,
            source_mesh.faces,
            output_points,
            output_triangles,
            sample_count=sample_count,
        )
    except Exception:  # noqa: BLE001
        return _unverified_actual_metric(
            "unverified_actual_surface_metric_input_invalid",
            sample_count=sample_count,
        )
    return _as_actual_metric_evidence(record)


def evaluate_gate4_fidelity_evidence(
    *,
    source: Gate4SourceIdentity | None,
    source_status: str,
    case_dir: Path,
    diagonal: float | None,
    checker: GeometryFidelityChecker,
    exact_metric_sample_count: int = _EXACT_METRIC_SAMPLE_COUNT,
) -> Gate4FidelityEvidence:
    """Return structured Gate-4 evidence without issuing a Gate verdict."""
    if source is None:
        return Gate4FidelityEvidence(
            status=source_status,
            metric_status="not_attempted",
            gate4_pass=False,
        )

    snapshot_path = Path(source.snapshot_path)
    if (
        not snapshot_path.is_file()
        or snapshot_path.is_symlink()
        or hashlib.sha256(snapshot_path.read_bytes()).hexdigest() != source.sha256
    ):
        return Gate4FidelityEvidence(
            status="unverified_source_snapshot_changed",
            source=source,
            metric_status="not_attempted",
            gate4_pass=False,
        )

    before = inspect_gate4_output_artifact(case_dir)
    if before is None:
        return Gate4FidelityEvidence(
            status="unverified_output_artifact_missing",
            source=source,
            metric_status="not_attempted",
            gate4_pass=False,
        )

    try:
        metric = checker.compute(
            original_stl=snapshot_path,
            case_dir=case_dir,
            diagonal=max(float(diagonal or 0.0), 1.0e-30),
        )
    except Exception:  # noqa: BLE001
        metric = None

    after = inspect_gate4_output_artifact(case_dir)
    if after is None or after.sha256 != before.sha256:
        return Gate4FidelityEvidence(
            status="unverified_output_artifact_changed",
            source=source,
            output=before,
            metric_status="not_attempted",
            gate4_pass=False,
        )
    from core.evaluator.gate4_metric_completeness import (  # noqa: PLC0415
        report_gate4_metric_completeness,
    )
    from core.evaluator.gate4_surface_topology import audit_polymesh_surface  # noqa: PLC0415

    surface_topology = audit_polymesh_surface(case_dir)
    post_topology = inspect_gate4_output_artifact(case_dir)
    if post_topology is None or post_topology.sha256 != before.sha256:
        return Gate4FidelityEvidence(
            status="unverified_output_artifact_changed",
            source=source,
            output=before,
            metric_status="not_attempted",
            gate4_pass=False,
        )

    actual_surface_metrics = _measure_actual_surface_metrics(
        source=source,
        case_dir=case_dir,
        topology_valid=surface_topology.topology_valid,
        sample_count=exact_metric_sample_count,
    )
    if (
        not snapshot_path.is_file()
        or snapshot_path.is_symlink()
        or hashlib.sha256(snapshot_path.read_bytes()).hexdigest() != source.sha256
    ):
        return Gate4FidelityEvidence(
            status="unverified_source_snapshot_changed",
            source=source,
            output=before,
            metric_status="not_attempted",
            gate4_pass=False,
        )
    post_actual_metric = inspect_gate4_output_artifact(case_dir)
    if post_actual_metric is None or post_actual_metric.sha256 != before.sha256:
        return Gate4FidelityEvidence(
            status="unverified_output_artifact_changed",
            source=source,
            output=before,
            metric_status="not_attempted",
            gate4_pass=False,
        )

    metric_completeness = report_gate4_metric_completeness(
        legacy_metric=metric,
        source=source,
        output=before,
    )
    if metric is None:
        return Gate4FidelityEvidence(
            status="unverified_metric_missing",
            source=source,
            output=before,
            metric_status="missing",
            surface_topology=surface_topology,
            actual_surface_metrics=actual_surface_metrics,
            metric_completeness=metric_completeness,
            gate4_pass=False,
        )
    return Gate4FidelityEvidence(
        status="unverified_metric_incomplete",
        source=source,
        output=before,
        metric_status="legacy_partial",
        geometry_fidelity=metric,
        surface_topology=surface_topology,
        actual_surface_metrics=actual_surface_metrics,
        metric_completeness=metric_completeness,
        gate4_pass=False,
    )
