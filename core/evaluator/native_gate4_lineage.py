"""Explicit Gate4 output-to-source 1:N lineage witness contract."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

SCHEMA = "autotessell/gate4-lineage-witness/v1"
SOURCE_KINDS = {"stl_facet", "cad_face", "cad_edge", "stl_edge_pair"}
SCOPES = {"output_boundary", "internal_interface"}
OPERATIONS = {"identity", "surface_refine", "bl_extrude", "transition"}
ROLES = {"wall", "inner", "outer", "sidewall"}


def _sha256(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def _source_rows(manifest: Mapping[str, Any] | None) -> tuple[str | None, dict[int, Mapping[str, Any]]]:
    if not isinstance(manifest, Mapping) or not isinstance(manifest.get("rows"), list):
        return None, {}
    kind = manifest.get("entity_kind")
    rows: dict[int, Mapping[str, Any]] = {}
    for row in manifest["rows"]:
        if isinstance(row, Mapping) and isinstance(row.get("source_id"), int) and not isinstance(row.get("source_id"), bool):
            rows[row["source_id"]] = row
    return kind if isinstance(kind, str) else None, rows


def _payload(witness: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in witness.items() if key != "witness_sha256"}


def _record_reason(reasons: list[str], reason: str) -> None:
    if reason not in reasons:
        reasons.append(reason)


def validate_lineage_witness(
    witness: Mapping[str, Any] | None,
    semantic_manifest: Mapping[str, Any] | None,
    *,
    actual_output_uids: Sequence[str] | None = None,
    baseline_tree_sha256: str | None = None,
    output_tree_sha256: str | None = None,
) -> dict[str, Any]:
    """Validate source ownership, output 1:N mapping, role chains, and digest."""
    reasons: list[str] = []
    if not isinstance(witness, Mapping):
        return {"accepted": False, "reasons": ["lineage_witness_missing"]}
    if witness.get("schema") != SCHEMA:
        _record_reason(reasons, "legacy_lineage_witness_missing")
    kind, source_rows = _source_rows(semantic_manifest)
    if kind not in SOURCE_KINDS or not source_rows:
        _record_reason(reasons, "semantic_manifest_source_rows_missing")
    requested = witness.get("requested_layers")
    actual = witness.get("actual_layers")
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in (requested, actual)):
        _record_reason(reasons, "layer_count_invalid")
    elif requested != actual:
        _record_reason(reasons, "layer_count_mismatch")
    records = witness.get("records")
    if not isinstance(records, list):
        _record_reason(reasons, "lineage_records_invalid")
        records = []
    seen: set[str] = set()
    by_uid: dict[str, Mapping[str, Any]] = {}
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            _record_reason(reasons, f"record_{index}_not_object")
            continue
        uid = record.get("output_uid")
        if not isinstance(uid, str) or not uid:
            _record_reason(reasons, "output_boundary_uid_missing")
            continue
        if uid in seen:
            _record_reason(reasons, "output_uid_duplicate")
        seen.add(uid)
        by_uid[uid] = record
        if record.get("entity_scope") not in SCOPES:
            _record_reason(reasons, "entity_scope_invalid")
        source_ref = record.get("source_ref")
        if not isinstance(source_ref, Mapping) or source_ref.get("kind") not in SOURCE_KINDS:
            _record_reason(reasons, "source_entity_unknown")
            source_id = None
        else:
            source_id = source_ref.get("id")
            if isinstance(source_id, bool) or not isinstance(source_id, int) or source_id < 0:
                _record_reason(reasons, "source_entity_unknown")
                source_id = None
            elif source_ref.get("kind") != kind or source_id not in source_rows:
                _record_reason(reasons, "source_entity_unknown")
        owner = record.get("semantic_owner_id")
        expected_owner = f"sem/{kind}/{source_id}" if source_id is not None and kind else None
        if not isinstance(owner, str) or owner != expected_owner:
            _record_reason(reasons, "semantic_owner_ambiguous")
        row = source_rows.get(source_id) if source_id is not None else None
        for field in ("feature", "patch", "physical_group", "component", "provenance"):
            if not isinstance(record.get(field), str) or not record[field].strip():
                _record_reason(reasons, "semantic_payload_missing")
            elif row is not None and record[field] != row.get(field):
                _record_reason(reasons, "semantic_payload_mismatch")
        if record.get("operation") not in OPERATIONS:
            _record_reason(reasons, "operation_invalid")
        role = record.get("boundary_role")
        if role not in ROLES:
            _record_reason(reasons, "boundary_role_invalid")
        if role == "sidewall" and (not isinstance(source_ref, Mapping) or source_ref.get("kind") not in {"cad_edge", "stl_edge_pair"}):
            _record_reason(reasons, "sidewall_source_ambiguous")
        layer = record.get("layer_index")
        if isinstance(layer, bool) or not isinstance(layer, int) or layer < 0:
            _record_reason(reasons, "layer_index_invalid")
        elif isinstance(actual, int) and actual >= 0 and layer > actual:
            _record_reason(reasons, "layer_index_out_of_range")
        parent = record.get("parent_uid")
        if parent is not None and (not isinstance(parent, str) or not parent):
            _record_reason(reasons, "parent_uid_invalid")
    if actual_output_uids is not None:
        expected = list(actual_output_uids)
        if len(expected) != len(set(expected)):
            _record_reason(reasons, "actual_output_uid_duplicate")
        if set(expected) != seen:
            _record_reason(reasons, "output_boundary_uid_missing")
    if requested == 0 and actual == 0:
        if baseline_tree_sha256 is not None and output_tree_sha256 is not None and baseline_tree_sha256 != output_tree_sha256:
            _record_reason(reasons, "bl0_tree_identity_failed")
        for record in records:
            if record.get("boundary_role") != "wall" or record.get("operation") != "identity" or record.get("layer_index") != 0 or record.get("parent_uid") is not None:
                _record_reason(reasons, "bl0_role_contract_failed")
    if isinstance(actual, int) and actual > 0:
        if not any(record.get("boundary_role") == "wall" for record in records):
            _record_reason(reasons, "bl_role_chain_invalid")
        if not any(record.get("boundary_role") == "inner" for record in records):
            _record_reason(reasons, "bl_role_chain_invalid")
        if not any(record.get("boundary_role") == "outer" for record in records):
            _record_reason(reasons, "bl_role_chain_invalid")
    for uid, record in by_uid.items():
        parent = record.get("parent_uid")
        if parent is None:
            continue
        if parent not in by_uid:
            _record_reason(reasons, "parent_uid_unknown")
            continue
        parent_record = by_uid[parent]
        if parent_record.get("semantic_owner_id") != record.get("semantic_owner_id"):
            _record_reason(reasons, "parent_owner_switch")
        child_layer = record.get("layer_index")
        parent_layer = parent_record.get("layer_index")
        if isinstance(child_layer, int) and isinstance(parent_layer, int) and child_layer < parent_layer:
            _record_reason(reasons, "layer_index_reverse")
        chain: set[str] = set()
        cursor: str | None = uid
        while cursor is not None:
            if cursor in chain:
                _record_reason(reasons, "parent_cycle")
                break
            chain.add(cursor)
            current = by_uid.get(cursor)
            cursor = current.get("parent_uid") if isinstance(current, Mapping) and isinstance(current.get("parent_uid"), str) else None
    digest = witness.get("witness_sha256")
    if not isinstance(digest, str) or len(digest) != 64 or digest != _sha256(_payload(witness)):
        _record_reason(reasons, "lineage_digest_mismatch")
    return {
        "accepted": not reasons,
        "reasons": sorted(reasons),
        "witness_sha256": digest,
        "output_count": len(seen),
        "semantic_owner_count": len({record.get("semantic_owner_id") for record in records if isinstance(record, Mapping)}),
        "source_to_output_fanout": {
            owner: sum(1 for record in records if isinstance(record, Mapping) and record.get("semantic_owner_id") == owner)
            for owner in sorted({record.get("semantic_owner_id") for record in records if isinstance(record, Mapping) and isinstance(record.get("semantic_owner_id"), str)})
        },
    }


def build_lineage_witness(
    records: Sequence[Mapping[str, Any]],
    *,
    requested_layers: int,
    actual_layers: int,
    baseline_tree_sha256: str,
    output_tree_sha256: str,
) -> dict[str, Any]:
    """Create a canonical digest-sealed witness from explicit records."""
    witness: dict[str, Any] = {
        "schema": SCHEMA,
        "requested_layers": requested_layers,
        "actual_layers": actual_layers,
        "baseline_tree_sha256": baseline_tree_sha256,
        "output_tree_sha256": output_tree_sha256,
        "records": [dict(record) for record in records],
    }
    witness["witness_sha256"] = _sha256(witness)
    return witness


__all__ = ["SCHEMA", "build_lineage_witness", "validate_lineage_witness"]
