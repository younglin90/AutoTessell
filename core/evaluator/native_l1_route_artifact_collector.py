"""Canonical, read-only L1 collector for native route evidence.

This adapter validates typed artifact metadata and forwards only explicit fields to
the existing C++ route-evidence matrix. It never creates authority or quality
claims from missing data.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
import hashlib
import re
from typing import Any

from core.evaluator.native_route_evidence_matrix import (
    MATRIX_PRODUCTS,
    evaluate_route_evidence_matrix,
)

_PRODUCTS = frozenset(MATRIX_PRODUCTS)
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_TOPOLOGY = (
    "invalid",
    "inverted",
    "duplicate",
    "non_manifold",
    "self_intersecting",
    "negative_measure",
)
_ORIGINS = (
    "source",
    "feature",
    "physical_group",
    "component",
    "provenance",
)
_IDENTITY_FIELDS = (
    "engine",
    "evidence_status",
    "boundary_layer",
    "identity_exact",
    "authority_state",
    "quality_accepted",
    "quality_profile_id",
    "stage_publish_receipt",
)


def _incomplete(product: Any, reason: str) -> dict[str, Any]:
    return {
        "product": product,
        "classification": "incomplete",
        "reasons": [reason],
        "publication_eligible": False,
        "runtime_route": "default_off",
    }


def _digest(record: Mapping[str, Any]) -> tuple[str | None, str | None]:
    declared = record.get("artifact_sha256")
    raw = record.get("artifact_bytes")
    if raw is not None:
        if not isinstance(raw, (bytes, bytearray, memoryview)):
            return None, "artifact_bytes_not_bytes"
        computed = hashlib.sha256(bytes(raw)).hexdigest()
        if declared is not None and declared != computed:
            return None, "artifact_digest_mismatch"
        return computed, None
    if not isinstance(declared, str) or _HEX64.fullmatch(declared) is None:
        return None, "artifact_sha256_missing_or_malformed"
    if record.get("artifact_digest_scope") != "raw_bytes":
        return None, "artifact_digest_scope_not_raw_bytes"
    return declared, None


def _validate_explicit_record(
    record: Mapping[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    product = record.get("product")
    if product not in _PRODUCTS:
        return None, "product_label_not_canonical"
    status = record.get("evidence_status")
    if status == "absent":
        return {"product": product, "evidence_status": "absent"}, None
    if status not in {"present", "observed"}:
        return None, "evidence_status_missing_or_invalid"

    digest, error = _digest(record)
    if error:
        return None, error

    for key in _IDENTITY_FIELDS:
        if key not in record:
            return None, f"field_missing:{key}"

    boundary = record["boundary_layer"]
    if not isinstance(boundary, Mapping):
        return None, "boundary_layer_not_mapping"
    required_bl = ("requested_layers", "actual_layers", "mode")
    if any(key not in boundary for key in required_bl):
        return None, "boundary_layer_field_missing"
    if not all(
        isinstance(boundary[key], int)
        and not isinstance(boundary[key], bool)
        and boundary[key] >= 0
        for key in required_bl[:2]
    ):
        return None, "boundary_layer_count_invalid"

    topology = record.get("topology")
    if not isinstance(topology, Mapping) or any(
        key not in topology
        or not isinstance(topology[key], int)
        or isinstance(topology[key], bool)
        or topology[key] < 0
        for key in _TOPOLOGY
    ):
        return None, "topology_typed_counters_missing_or_invalid"

    origins = record.get("field_origins")
    if not isinstance(origins, Mapping) or any(
        origins.get(key) != "direct" for key in _ORIGINS
    ):
        return None, "field_origins_not_direct_complete"

    authority = record.get("authority_state")
    if authority not in {"source_verified", "inferred", "incomplete"}:
        return None, "authority_state_invalid"

    source_fields = record.get("source_fields")
    if not isinstance(source_fields, Mapping) or any(
        not isinstance(source_fields.get(key), str) or not source_fields[key]
        for key in _ORIGINS
    ):
        return None, "source_feature_group_component_provenance_missing"

    row = {key: deepcopy(record[key]) for key in _IDENTITY_FIELDS}
    row["product"] = product
    row["field_origins_complete"] = True
    row["topology"] = deepcopy(topology)
    row["artifact_sha256"] = digest
    row["artifact_digest_scope"] = "raw_bytes"
    row["field_origins"] = {key: "direct" for key in _ORIGINS}
    row["source_fields"] = dict(source_fields)
    return row, None


def collect_l1_route_artifacts(
    artifacts: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Collect canonical artifacts and classify them through the read-only matrix."""
    if isinstance(artifacts, (str, bytes, bytearray)) or not isinstance(
        artifacts, Sequence
    ):
        return {
            "status": "collector_invalid_input",
            "rows": [],
            "counts": {"incomplete": 1},
            "publication_eligible": False,
            "runtime_route": "default_off",
            "route_calls": 0,
        }

    records = deepcopy(list(artifacts))
    seen: set[str] = set()
    valid_rows: list[dict[str, Any]] = []
    invalid_rows: list[dict[str, Any]] = []

    for record in records:
        if not isinstance(record, Mapping):
            invalid_rows.append(_incomplete(None, "artifact_record_not_mapping"))
            continue
        product = record.get("product")
        if product in seen:
            invalid_rows.append(_incomplete(product, "duplicate_product_artifact"))
            continue
        if product in _PRODUCTS:
            seen.add(product)
        row, error = _validate_explicit_record(record)
        if error:
            invalid_rows.append(_incomplete(product, error))
        else:
            valid_rows.append(row)

    matrix = evaluate_route_evidence_matrix(valid_rows) if valid_rows else {
        "rows": [],
        "counts": {},
        "route_calls": 0,
        "publication_eligible": False,
        "runtime_route": "default_off",
    }
    metadata = {row["product"]: row for row in valid_rows}
    for row in matrix.get("rows", []):
        original = metadata.get(row.get("product"))
        if original is not None:
            for key in ("artifact_sha256", "artifact_digest_scope", "field_origins", "source_fields"):
                row[key] = deepcopy(original[key])
    rows = invalid_rows + matrix.get("rows", [])
    counts: dict[str, int] = {}
    for row in rows:
        classification = row.get("classification", "incomplete")
        counts[classification] = counts.get(classification, 0) + 1
    return {
        "status": "collector_observed",
        "rows": rows,
        "counts": counts,
        "products_seen": sorted(seen),
        "publication_eligible": False,
        "runtime_route": "default_off",
        "route_calls": 0,
    }


__all__ = ["collect_l1_route_artifacts"]
