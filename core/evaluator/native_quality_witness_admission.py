"""Fail-closed admission for the first-party native quality witness."""
from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

_DEFAULT_LIMITS = {
    "internal_non_orthogonality": (35.0, 50.0),
    "release_skew": (0.25, 0.50),
    "aspect_ratio": (10.0, 20.0),  # p99, max
}
_PARTITIONS = {"core", "boundary_layer", "transition"}


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _metric(witness: Mapping[str, Any], name: str, p95_limit: float,
            max_limit: float, reasons: list[str], *,
            percentile_key: str = "p95") -> Mapping[str, Any] | None:
    quality = witness.get("quality")
    report = quality.get(name) if isinstance(quality, Mapping) else None
    if not isinstance(report, Mapping):
        reasons.append(f"quality_{name}_unmeasured")
        return None
    if report.get("status") == "not_applicable" and report.get("count") == 0:
        return report
    if report.get("status") != "measured":
        reasons.append(f"quality_{name}_unmeasured")
        return None
    for key in ("p95", "p99", "max"):
        if not _finite(report.get(key)):
            reasons.append(f"quality_{name}_{key}_invalid")
    if _finite(report.get(percentile_key)) and float(report[percentile_key]) > p95_limit:
        reasons.append(f"quality_{name}_{percentile_key}_gate_failed")
    if _finite(report.get("max")) and float(report["max"]) > max_limit:
        reasons.append(f"quality_{name}_max_gate_failed")
    count = report.get("count", 0)
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        reasons.append(f"quality_{name}_count_invalid")
    if count > 0 and not isinstance(report.get("worst_uid"), str):
        reasons.append(f"quality_{name}_worst_uid_missing")
    return report


def validate_native_quality_witness(
    witness: Any,
    *,
    requested_layers: int = 0,
    require_lineage: bool = True,
    limits: Mapping[str, tuple[float, float]] | None = None,
) -> dict[str, Any]:
    """Validate exhaustive C++ witness population and release thresholds."""
    reasons: list[str] = []
    if not isinstance(witness, Mapping):
        return {"accepted": False, "reasons": ["witness_object_required"]}
    if witness.get("accepted") is not True:
        reasons.append("witness_not_accepted")
    if not isinstance(witness.get("schema"), str) or not witness["schema"].endswith("/v2"):
        reasons.append("witness_schema")
    if witness.get("full_population") is not True or witness.get("orientation_checked") is not True:
        reasons.append("witness_full_population_or_orientation_missing")
    if witness.get("volume_quality", {}).get("positive_geometry") is not True:
        reasons.append("witness_positive_geometry_missing")
    quality_limits = dict(_DEFAULT_LIMITS)
    if limits is not None:
        quality_limits.update(limits)
    for name, (p95_limit, max_limit) in quality_limits.items():
        _metric(
            witness, name, float(p95_limit), float(max_limit), reasons,
            percentile_key="p99" if name == "aspect_ratio" else "p95",
        )

    volume = witness.get("volume_quality")
    cells = volume.get("cells") if isinstance(volume, Mapping) else None
    faces = witness.get("faces")
    if not isinstance(cells, list) or not cells:
        reasons.append("witness_cell_records_missing")
    else:
        cell_uids: set[str] = set()
        for row in cells:
            if not isinstance(row, Mapping):
                reasons.append("witness_cell_record_invalid")
                continue
            uid = row.get("cell_uid")
            if not isinstance(uid, str) or not uid or uid in cell_uids:
                reasons.append("witness_cell_uid_missing_or_duplicate")
            else:
                cell_uids.add(uid)
            if row.get("partition") not in _PARTITIONS:
                reasons.append("witness_cell_partition_invalid")
            if not _finite(row.get("volume")) or float(row["volume"]) <= 0.0:
                reasons.append("witness_cell_volume_invalid")
            if not _finite(row.get("aspect_ratio")):
                reasons.append("witness_cell_aspect_invalid")
        partitions = volume.get("partitions") if isinstance(volume, Mapping) else None
        if not isinstance(partitions, Mapping):
            reasons.append("witness_partition_distribution_missing")
    if not isinstance(faces, list) or not faces:
        reasons.append("witness_face_records_missing")
    else:
        for row in faces:
            if not isinstance(row, Mapping):
                reasons.append("witness_face_record_invalid")
                continue
            if not isinstance(row.get("face_uid"), str) or not row["face_uid"]:
                reasons.append("witness_face_uid_missing")
            if not isinstance(row.get("owner_cell_uid"), str) or not row["owner_cell_uid"]:
                reasons.append("witness_owner_uid_missing")
            if not _finite(row.get("skewness")):
                reasons.append("witness_face_skewness_invalid")
            if row.get("face_class") == "internal":
                if not _finite(row.get("non_orthogonality")):
                    reasons.append("witness_internal_non_orthogonality_invalid")
                if not isinstance(row.get("neighbour_cell_uid"), str) or not row["neighbour_cell_uid"]:
                    reasons.append("witness_neighbour_uid_missing")

    if isinstance(requested_layers, bool) or not isinstance(requested_layers, int) or requested_layers < 0:
        reasons.append("requested_layers_invalid")
    elif requested_layers > 0:
        boundary = witness.get("boundary_layer")
        if not isinstance(boundary, Mapping):
            reasons.append("positive_boundary_layer_witness_missing")
        else:
            if boundary.get("requested_layers") != requested_layers or boundary.get("actual_layers") != requested_layers:
                reasons.append("positive_boundary_layer_count_mismatch")
            for key in ("positive_thickness", "lineage_complete"):
                if boundary.get(key) is not True:
                    reasons.append(f"positive_boundary_layer_{key}_missing")

    if require_lineage:
        lineage = witness.get("entity_lineage")
        if not isinstance(lineage, Mapping) or not lineage:
            reasons.append("entity_lineage_missing")
        else:
            for key in ("feature", "patch", "physical_group", "component", "provenance"):
                if key not in lineage:
                    reasons.append(f"entity_lineage_{key}_missing")
    return {"accepted": not reasons, "reasons": sorted(set(reasons))}


__all__ = ["validate_native_quality_witness"]
