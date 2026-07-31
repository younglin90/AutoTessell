"""Gate-4 evidence: CAD input hashes cannot yet certify generated Hex faces."""

from __future__ import annotations

from dataclasses import fields
from pathlib import Path

from core.analyzer.readers.step import CadEntityProvenance, CadNativeTriangulation

_ROOT = Path(__file__).resolve().parents[1]
_HEX_MESHER = _ROOT / "core" / "generator" / "native_hex" / "mesher.py"


def test_cad_reader_preserves_deterministic_input_side_brep_certificate_fields() -> None:
    names = {field.name for field in fields(CadEntityProvenance)}

    assert {
        "face_count",
        "triangle_face_ordinals",
        "triangle_orientation_reversed",
        "seam_vertex_ids",
        "canonical_vertex_source_ids",
        "oriented_canonical_faces",
        "face_ordinals_authoritative",
        "face_orientation_authoritative",
        "seam_connectivity_authoritative",
        "ordered_triangle_coordinate_sha256",
        "ordered_face_ordinal_sha256",
        "ordered_orientation_sha256",
        "seam_connectivity_sha256",
    } <= names
    assert tuple(field.name for field in fields(CadNativeTriangulation)) == (
        "vertices",
        "faces",
        "provenance",
    )


def test_hex_lane_has_no_generated_boundary_face_to_brep_face_binding() -> None:
    source_text = _HEX_MESHER.read_text(encoding="utf-8")

    assert "CadEntityProvenance" not in source_text
    assert "CadNativeTriangulation" not in source_text
