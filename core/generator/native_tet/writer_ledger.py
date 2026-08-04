"""Validation of the writer-emitted Native Tet positive-BL ledger."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def _digest_payload(payload: dict[str, Any]) -> str:
    body = dict(payload)
    body.pop("graph_sha256", None)
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def validate_native_tet_writer_ledger(
    path: str | Path,
    *,
    source_sha256: str,
    requested_layers: int,
) -> dict[str, Any]:
    """Validate immutable writer IDs and inverse child coverage.

    This validator is intentionally independent of geometry matching. It checks
    the writer's persisted identity graph and is therefore suitable for the
    receipt-stage admission gate before disk topology/quality reread.
    """
    errors: list[str] = []
    ledger_path = Path(path)
    try:
        payload = json.loads(ledger_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"accepted": False, "release_eligible": False,
                "reason": f"writer_ledger_read_failed:{type(exc).__name__}"}
    if not isinstance(payload, dict):
        return {"accepted": False, "release_eligible": False,
                "reason": "writer_ledger_payload_invalid"}
    if payload.get("schema") != "native-tet-bl-writer-ledger/v1":
        errors.append("schema_mismatch")
    if payload.get("writer_owned_id_capsule") is not True:
        errors.append("writer_owned_id_capsule_missing")
    if str(payload.get("source_sha256", "")) != str(source_sha256):
        errors.append("source_digest_mismatch")
    try:
        actual_layers = int(payload["actual_layers"])
        emitted_requested = int(payload["requested_layers"])
    except (KeyError, TypeError, ValueError):
        errors.append("layer_count_missing")
        actual_layers = emitted_requested = -1
    if emitted_requested != int(requested_layers) or actual_layers != int(requested_layers):
        errors.append("layer_count_mismatch")
    if str(payload.get("graph_sha256", "")) != _digest_payload(payload):
        errors.append("writer_ledger_graph_digest_mismatch")
    records = payload.get("records")
    if not isinstance(records, list) or not records:
        errors.append("writer_ledger_records_missing")
        records = []
    source_ids: set[str] = set()
    child_ids: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            errors.append("writer_ledger_record_invalid")
            continue
        source_id = str(record.get("source_face_id", ""))
        if not source_id or source_id in source_ids:
            errors.append("source_face_id_duplicate_or_empty")
        source_ids.add(source_id)
        children = record.get("children")
        if not isinstance(children, dict):
            errors.append("writer_ledger_children_missing")
            continue
        record_child_count = 0
        for kind in ("boundary_faces", "front_faces"):
            entries = children.get(kind, [])
            if not isinstance(entries, list):
                errors.append(f"writer_ledger_{kind}_invalid")
                continue
            for child in entries:
                record_child_count += 1
                if not isinstance(child, dict):
                    errors.append("writer_ledger_child_invalid")
                    continue
                child_id = str(child.get("output_face_id", ""))
                if not child_id or child_id in child_ids:
                    errors.append("output_face_id_duplicate_or_empty")
                child_ids.add(child_id)
                try:
                    int(child["disk_face_id"])
                    layer = int(child["layer"])
                    vertices = child["vertex_ids"]
                except (KeyError, TypeError, ValueError):
                    errors.append("writer_ledger_child_identity_missing")
                    continue
                if layer < 0 or not isinstance(vertices, list) or len(vertices) < 3:
                    errors.append("writer_ledger_child_geometry_invalid")
        cells = children.get("cells", [])
        if not isinstance(cells, list) or not cells:
            errors.append("writer_ledger_cell_children_missing")
        if record_child_count == 0:
            errors.append("writer_ledger_record_has_no_face_children")
    return {
        "accepted": not errors,
        "release_eligible": False,
        "reason": "writer_ledger_verified" if not errors else "writer_ledger_refused",
        "errors": errors,
        "source_face_count": len(source_ids),
        "child_id_count": len(child_ids),
        "graph_sha256": str(payload.get("graph_sha256", "")),
        "actual_layers": actual_layers,
    }


__all__ = ["validate_native_tet_writer_ledger"]
