"""Fail-closed validator for the complete Native Tet BL lineage contract."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def _hex64(value: Any) -> bool:
    text = str(value)
    return len(text) == 64 and all(c in "0123456789abcdef" for c in text.lower())


def _graph_digest(payload: Mapping[str, Any]) -> str:
    body = dict(payload)
    body.pop("graph_sha256", None)
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def validate_native_tet_full_ledger(
    payload_or_path: Mapping[str, Any] | str | Path,
    *,
    source_sha256: str,
    requested_layers: int,
) -> dict[str, Any]:
    if isinstance(payload_or_path, Mapping):
        payload = dict(payload_or_path)
    else:
        try:
            payload = json.loads(Path(payload_or_path).read_text(encoding="utf-8"))
        except Exception as exc:
            return {"accepted": False, "reason": f"full_ledger_read_failed:{type(exc).__name__}"}
    errors: list[str] = []
    if payload.get("schema") != "native-tet-bl-writer-ledger/v2":
        errors.append("schema_mismatch")
    for key in (
        "source_sha256", "semantic_ledger_sha256", "bl_config_sha256",
        "quality_policy_sha256", "graph_sha256", "artifact_tree_sha256",
    ):
        if not _hex64(payload.get(key, "")):
            errors.append(f"digest_invalid:{key}")
    if str(payload.get("source_sha256")) != str(source_sha256):
        errors.append("source_digest_mismatch")
    if payload.get("writer_owned") is not True:
        errors.append("writer_owned_missing")
    try:
        actual_layers = int(payload["actual_layers"])
    except (KeyError, TypeError, ValueError):
        errors.append("actual_layers_missing")
        actual_layers = -1
    if actual_layers != int(requested_layers):
        errors.append("layer_count_mismatch")
    if str(payload.get("graph_sha256")) != _graph_digest(payload):
        errors.append("graph_digest_mismatch")

    source_faces = payload.get("source_faces")
    boundary = payload.get("boundary_children")
    interfaces = payload.get("interface_children")
    edge_children = payload.get("edge_children")
    prisms = payload.get("prisms")
    cells = payload.get("cells")
    inverse = payload.get("inverse")
    if not all(isinstance(value, list) for value in (source_faces, boundary, interfaces, edge_children, prisms, cells)):
        errors.append("full_ledger_section_missing")
        source_faces = source_faces if isinstance(source_faces, list) else []
        boundary = boundary if isinstance(boundary, list) else []
        interfaces = interfaces if isinstance(interfaces, list) else []
        edge_children = edge_children if isinstance(edge_children, list) else []
        prisms = prisms if isinstance(prisms, list) else []
        cells = cells if isinstance(cells, list) else []
    if not isinstance(inverse, Mapping):
        errors.append("inverse_section_missing")
        inverse = {}

    source_ids: set[str] = set()
    edge_ids: set[str] = set()
    source_semantics: dict[str, tuple[str, ...]] = {}
    for row in source_faces:
        if not isinstance(row, Mapping):
            errors.append("source_face_row_invalid")
            continue
        source_id = str(row.get("source_face_id", ""))
        if not source_id or source_id in source_ids:
            errors.append("source_face_duplicate_or_empty")
        source_ids.add(source_id)
        cycle = row.get("source_vertex_ids")
        if not isinstance(cycle, list) or len(cycle) < 3:
            errors.append("source_face_cycle_invalid")
        for edge_id in row.get("source_edge_ids", []):
            edge_text = str(edge_id)
            edge_ids.add(edge_text)
        source_semantics[source_id] = tuple(
            str(row.get(key, "")) for key in ("feature", "patch", "physical_group", "component", "provenance")
        )

    def validate_face_section(section: list[Any], label: str) -> set[str]:
        seen: set[str] = set()
        parents: set[str] = set()
        for row in section:
            if not isinstance(row, Mapping):
                errors.append(f"{label}_row_invalid")
                continue
            parent = str(row.get("source_face_id", ""))
            if parent not in source_ids:
                errors.append(f"{label}_source_unknown")
            parents.add(parent)
            children = row.get("children")
            if not isinstance(children, list) or not children:
                errors.append(f"{label}_children_missing")
                continue
            for child in children:
                if not isinstance(child, Mapping):
                    errors.append(f"{label}_child_invalid")
                    continue
                child_id = str(child.get("output_face_id", ""))
                if not child_id or child_id in seen:
                    errors.append(f"{label}_child_duplicate")
                seen.add(child_id)
                cycle = child.get("vertex_ids")
                if not isinstance(cycle, list) or len(cycle) < 3:
                    errors.append(f"{label}_child_cycle_invalid")
                if "disk_face_id" not in child:
                    errors.append(f"{label}_disk_id_missing")
        if parents != source_ids:
            errors.append(f"{label}_source_coverage_mismatch")
        return seen

    boundary_ids = validate_face_section(boundary, "boundary")
    interface_ids = validate_face_section(interfaces, "interface")
    all_face_ids = boundary_ids | interface_ids
    edge_child_ids: set[str] = set()
    for row in edge_children:
        if not isinstance(row, Mapping):
            errors.append("edge_child_row_invalid")
            continue
        parent = str(row.get("source_edge_id", ""))
        if parent not in edge_ids:
            errors.append("edge_child_source_unknown")
        children = row.get("children")
        if not isinstance(children, list) or not children:
            errors.append("edge_child_children_missing")
            continue
        for child in children:
            child_id = str(child.get("output_edge_id", "")) if isinstance(child, Mapping) else ""
            if not child_id or child_id in edge_child_ids:
                errors.append("edge_child_duplicate")
            edge_child_ids.add(child_id)
    if {str(row.get("source_edge_id", "")) for row in edge_children if isinstance(row, Mapping)} != edge_ids:
        errors.append("edge_source_coverage_mismatch")

    prism_ids: set[str] = set()
    cell_ids: set[str] = set()
    prism_children: dict[str, set[str]] = {}
    for row in prisms:
        if not isinstance(row, Mapping):
            errors.append("prism_row_invalid")
            continue
        prism_id = str(row.get("prism_parent_id", ""))
        source_id = str(row.get("source_face_id", ""))
        if not prism_id or prism_id in prism_ids:
            errors.append("prism_id_duplicate_or_empty")
        prism_ids.add(prism_id)
        if source_id not in source_ids:
            errors.append("prism_source_unknown")
        if not isinstance(row.get("vertex_ids"), list) or len(row["vertex_ids"]) != 6:
            errors.append("prism_vertex_contract_invalid")
        children = {str(value) for value in row.get("child_tet_ids", [])}
        if not children:
            errors.append("prism_child_tets_missing")
        prism_children[prism_id] = children
    for row in cells:
        if not isinstance(row, Mapping):
            errors.append("cell_row_invalid")
            continue
        cell_id = str(row.get("output_cell_id", ""))
        if not cell_id or cell_id in cell_ids:
            errors.append("cell_id_duplicate_or_empty")
        cell_ids.add(cell_id)
        parent = str(row.get("prism_parent_id", ""))
        if parent not in prism_ids:
            errors.append("cell_prism_parent_unknown")
        if cell_id not in prism_children.get(parent, set()):
            errors.append("cell_inverse_missing")
        if not isinstance(row.get("vertex_ids"), list) or len(row["vertex_ids"]) != 4:
            errors.append("cell_vertex_contract_invalid")
        try:
            if float(row["signed_volume"]) <= 0.0:
                errors.append("cell_signed_volume_nonpositive")
        except (KeyError, TypeError, ValueError):
            errors.append("cell_signed_volume_missing")
    if (set().union(*prism_children.values()) if prism_children else set()) != cell_ids:
        errors.append("prism_cell_coverage_mismatch")

    boundary_inverse = inverse.get("boundary_face_to_source", {})
    tet_inverse = inverse.get("tet_to_prism", {})
    if not isinstance(boundary_inverse, Mapping) or set(map(str, boundary_inverse)) != boundary_ids:
        errors.append("boundary_inverse_coverage_mismatch")
    if not isinstance(tet_inverse, Mapping) or set(map(str, tet_inverse)) != cell_ids:
        errors.append("tet_inverse_coverage_mismatch")
    return {
        "accepted": not errors,
        "release_eligible": False,
        "reason": "full_ledger_verified" if not errors else "full_ledger_refused",
        "errors": errors,
        "source_face_count": len(source_ids),
        "source_edge_count": len(edge_ids),
        "boundary_child_count": len(boundary_ids),
        "interface_child_count": len(interface_ids),
        "prism_count": len(prism_ids),
        "cell_count": len(cell_ids),
    }


__all__ = ["validate_native_tet_full_ledger"]
