"""Disk binding for an explicit writer-owned Native Tet 1:N ledger."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.generator.native_tet.disk_receipt_graph import (
    _SEMANTIC_KEYS,
    _hex64,
    _refusal,
    _same_directed_cycle,
)
from core.utils.native_extensions import import_native_extension
from core.utils.polymesh_reader import (
    parse_foam_boundary,
    parse_foam_faces,
    parse_foam_labels,
)


def audit_disk_receipt_graph_1_to_n(
    poly_mesh: Path,
    receipt: Mapping[str, Any],
    interfaces: list[Any],
) -> dict[str, Any]:
    """Validate explicit source-face -> child-face IDs against disk output.

    The writer supplies both the output ID and its disk face ID. No coordinate,
    nearest-neighbour, ordinal, or reconstructed geometric matching is used.
    """
    source_digest = str(receipt.get("source_sha256", ""))
    semantic_digest = str(receipt.get("semantic_ledger_sha256", ""))
    if not _hex64(source_digest) or not _hex64(semantic_digest):
        return _refusal("receipt_graph_authority_digest_missing")
    try:
        faces = [list(map(int, row)) for row in parse_foam_faces(poly_mesh / "faces")]
        owner = parse_foam_labels(poly_mesh / "owner")
        neighbour = parse_foam_labels(poly_mesh / "neighbour")
        patches = parse_foam_boundary(poly_mesh / "boundary")
    except Exception as exc:
        return _refusal(f"receipt_graph_disk_reread_failed:{type(exc).__name__}")
    if len(owner) != len(faces) or len(neighbour) > len(faces):
        return _refusal("receipt_graph_incidence_array_mismatch")
    internal_count = len(neighbour)
    boundary_ids = set(range(internal_count, len(faces)))
    patch_by_face: dict[int, Mapping[str, Any]] = {}
    for patch in patches:
        try:
            start = int(patch["startFace"])
            count = int(patch["nFaces"])
        except (KeyError, TypeError, ValueError):
            return _refusal("receipt_graph_boundary_patch_invalid")
        for face_id in range(start, start + count):
            if face_id in patch_by_face:
                return _refusal("receipt_graph_boundary_patch_overlap")
            patch_by_face[face_id] = patch
    if set(patch_by_face) != boundary_ids:
        return _refusal("receipt_graph_boundary_coverage_gap")
    if not isinstance(interfaces, list) or not interfaces:
        return _refusal("receipt_graph_interface_children_missing")

    source_rows: list[dict[str, Any]] = []
    output_rows: list[dict[str, Any]] = []
    matched_disk_faces: set[int] = set()
    seen_output_ids: set[str] = set()
    for raw in interfaces:
        if not isinstance(raw, Mapping):
            return _refusal("receipt_graph_interface_children_row_invalid")
        try:
            source_id = str(raw["source_face"])
            source_vertices = [int(value) for value in raw["source_vertex_ids"]]
            semantics = {key: str(raw[key]) for key in _SEMANTIC_KEYS}
            children = raw["children"]
        except (KeyError, TypeError, ValueError):
            return _refusal("receipt_graph_interface_children_semantic_invalid")
        if not source_id or not isinstance(children, list) or not children:
            return _refusal("receipt_graph_interface_children_empty")
        child_ids: list[str] = []
        source_row = {
            "source_face_id": source_id,
            "source_vertex_ids": source_vertices,
            "child_output_face_ids": child_ids,
        }
        source_row.update(semantics)
        source_rows.append(source_row)
        for child in children:
            if not isinstance(child, Mapping):
                return _refusal("receipt_graph_child_row_invalid", source_face_id=source_id)
            try:
                output_id = str(child["output_face_id"])
                disk_face_id = int(child["disk_face_id"])
                output_vertices = [int(value) for value in child["output_vertex_ids"]]
            except (KeyError, TypeError, ValueError):
                return _refusal("receipt_graph_child_binding_invalid", source_face_id=source_id)
            if not output_id or output_id in seen_output_ids:
                return _refusal("receipt_graph_output_face_duplicate", output_face_id=output_id)
            if disk_face_id not in boundary_ids or disk_face_id in matched_disk_faces:
                return _refusal("receipt_graph_child_disk_face_invalid", output_face_id=output_id)
            if not _same_directed_cycle(output_vertices, faces[disk_face_id]):
                return _refusal(
                    "receipt_graph_child_disk_binding_invalid",
                    output_face_id=output_id,
                    disk_face_id=disk_face_id,
                )
            if str(patch_by_face[disk_face_id].get("type", "")) != semantics["patch"]:
                return _refusal("receipt_graph_patch_type_mismatch", source_face_id=source_id)
            seen_output_ids.add(output_id)
            matched_disk_faces.add(disk_face_id)
            child_ids.append(output_id)
            output_row = {
                "source_face_id": source_id,
                "output_face_id": output_id,
                "output_vertex_ids": faces[disk_face_id],
                "incidence": 1,
            }
            output_row.update(semantics)
            output_rows.append(output_row)
    if matched_disk_faces != boundary_ids:
        return _refusal(
            "receipt_graph_source_output_coverage_mismatch",
            matched_face_count=len(matched_disk_faces),
            disk_boundary_face_count=len(boundary_ids),
        )
    try:
        native = import_native_extension("native_tet_receipt_graph_1_to_n")
        graph = dict(native.build_graph(
            source_rows, output_rows, source_digest, semantic_digest, 1
        ))
    except Exception as exc:
        return _refusal(f"receipt_graph_native_1_to_n_oracle_unavailable:{type(exc).__name__}")
    graph["disk_face_count"] = len(faces)
    graph["disk_boundary_face_count"] = len(boundary_ids)
    graph["source_output_exact"] = graph.get("accepted") is True
    graph["source_output_1_to_n"] = graph.get("accepted") is True
    graph["publication_eligible"] = False
    return graph


__all__ = ["audit_disk_receipt_graph_1_to_n"]
