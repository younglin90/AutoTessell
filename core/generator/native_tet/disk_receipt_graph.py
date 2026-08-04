"""Actual-writer OpenFOAM source/output receipt graph adapter.

The file parsing is deliberately limited to orchestration.  The immutable
cycle, semantic, incidence, duplicate-ID, and digest gate is delegated to the
C++ ``native_tet_receipt_graph`` oracle.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.utils.native_extensions import import_native_extension
from core.utils.polymesh_reader import (
    parse_foam_boundary,
    parse_foam_faces,
    parse_foam_labels,
)


_SEMANTIC_KEYS = ("feature", "patch", "physical_group", "component", "provenance")


def _hex64(value: Any) -> bool:
    text = str(value)
    return len(text) == 64 and all(character in "0123456789abcdef" for character in text.lower())


def _same_directed_cycle(expected: list[int], actual: list[int]) -> bool:
    if len(expected) != len(actual) or len(expected) < 3:
        return False
    return any(actual == expected[offset:] + expected[:offset] for offset in range(len(expected)))


def _refusal(reason: str, **extra: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "accepted": False,
        "publication_eligible": False,
        "candidate_discarded": True,
        "reason": reason,
    }
    result.update(extra)
    return result


def audit_disk_receipt_graph(
    poly_mesh: Path,
    receipt: Mapping[str, Any],
) -> dict[str, Any]:
    """Rebuild source-to-disk boundary binding from actual writer files."""
    source_digest = str(receipt.get("source_sha256", ""))
    semantic_digest = str(receipt.get("semantic_ledger_sha256", ""))
    if not _hex64(source_digest) or not _hex64(semantic_digest):
        return _refusal("receipt_graph_authority_digest_missing")
    child_interfaces = receipt.get("interface_children")
    if child_interfaces is not None:
        from core.generator.native_tet.disk_receipt_graph_1_to_n import audit_disk_receipt_graph_1_to_n
        return audit_disk_receipt_graph_1_to_n(poly_mesh, receipt, child_interfaces)
    interfaces = receipt.get("interface_triangles")
    if not isinstance(interfaces, list) or not interfaces:
        return _refusal("receipt_graph_interface_missing")
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

    source_rows: list[dict[str, Any]] = []
    output_rows: list[dict[str, Any]] = []
    matched_faces: set[int] = set()
    for raw in interfaces:
        if not isinstance(raw, Mapping):
            return _refusal("receipt_graph_interface_row_invalid")
        try:
            source_id = str(raw["source_face"])
            triangle = [int(value) for value in raw["triangle"]]
            semantics = {key: str(raw[key]) for key in _SEMANTIC_KEYS}
        except (KeyError, TypeError, ValueError):
            return _refusal("receipt_graph_interface_semantic_invalid")
        source_row = {"source_face_id": source_id, "source_vertex_ids": triangle}
        source_row.update(semantics)
        source_rows.append(source_row)
        matches = [
            face_id
            for face_id in sorted(boundary_ids)
            if _same_directed_cycle(triangle, faces[face_id])
        ]
        if len(matches) != 1:
            return _refusal(
                "receipt_graph_source_face_disk_match_invalid",
                source_face_id=source_id,
                match_count=len(matches),
            )
        face_id = matches[0]
        if face_id in matched_faces:
            return _refusal("receipt_graph_output_face_duplicate", output_face_id=face_id)
        matched_faces.add(face_id)
        patch = patch_by_face[face_id]
        if str(patch.get("type", "")) != semantics["patch"]:
            return _refusal(
                "receipt_graph_patch_type_mismatch",
                source_face_id=source_id,
                expected_patch_type=semantics["patch"],
                actual_patch_type=str(patch.get("type", "")),
            )
        output_row = {
            "source_face_id": source_id,
            "output_face_id": f"disk-face-{face_id}",
            "output_vertex_ids": faces[face_id],
            "incidence": 1,
        }
        output_row.update(semantics)
        output_rows.append(output_row)
    if matched_faces != boundary_ids:
        return _refusal(
            "receipt_graph_source_output_coverage_mismatch",
            matched_face_count=len(matched_faces),
            disk_boundary_face_count=len(boundary_ids),
        )
    try:
        native = import_native_extension("native_tet_receipt_graph")
        graph = dict(native.build_graph(
            source_rows,
            output_rows,
            source_digest,
            semantic_digest,
            1,
        ))
    except Exception as exc:
        return _refusal(f"receipt_graph_native_oracle_unavailable:{type(exc).__name__}")
    graph["disk_face_count"] = len(faces)
    graph["disk_boundary_face_count"] = len(boundary_ids)
    graph["source_output_exact"] = graph.get("accepted") is True
    graph["publication_eligible"] = False
    return graph


__all__ = ["audit_disk_receipt_graph"]
