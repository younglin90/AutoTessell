"""L0 contracts for the disconnected Hex CAD/B-Rep source-front audit."""

from __future__ import annotations

import json
from dataclasses import replace
from hashlib import sha256

import numpy as np

from core.analyzer.readers.step import CadEntityProvenance, CadNativeTriangulation
from core.generator.native_hex.brep_source_front_authority_l0 import (
    HexBrepSourceFrontAuthorityDeclarationL0,
    diagnose_hex_brep_source_front_authority_l0,
)

_ENABLE = "AUTO_TESSELL_HEX_BREP_SOURCE_FRONT_AUTHORITY_L0"


def _readonly(values: np.ndarray) -> np.ndarray:
    values.setflags(write=False)
    return values


def _array_hash(values: np.ndarray, dtype: str) -> str:
    return sha256(np.ascontiguousarray(values, dtype=dtype).tobytes()).hexdigest()


def _triangulation() -> CadNativeTriangulation:
    vertices = _readonly(
        np.asarray(
            ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (1.0, 1.0, 0.0)),
            dtype=np.float64,
        )
    )
    faces = _readonly(np.asarray(((0, 1, 2), (1, 3, 2)), dtype=np.int64))
    ordinals = _readonly(np.asarray((0, 1), dtype=np.int64))
    orientation = _readonly(np.asarray((False, True), dtype=np.bool_))
    seams = _readonly(np.asarray((0, 1, 2, 3), dtype=np.int64))
    canonical_sources = _readonly(np.asarray((0, 1, 2, 3), dtype=np.int64))
    oriented_faces = faces.copy()
    oriented_faces[orientation] = oriented_faces[orientation][:, (0, 2, 1)]
    canonical_faces = _readonly(seams[oriented_faces])
    xde_payload = {
        "face_names": (None, None),
        "layer_names": ((), ()),
        "surface_colors": (None, None),
        "assembly_paths": (None, None),
        "layer_authoritative": False,
        "physical_group_authoritative": False,
    }
    provenance = CadEntityProvenance(
        status="partial_authority_physical_groups_unavailable",
        face_count=2,
        topological_edge_count=5,
        triangle_face_ordinals=ordinals,
        triangle_orientation_reversed=orientation,
        seam_vertex_ids=seams,
        canonical_vertex_source_ids=canonical_sources,
        oriented_canonical_faces=canonical_faces,
        face_names=(None, None),
        physical_group_names=(None, None),
        xde_layer_names=((), ()),
        xde_surface_colors=(None, None),
        xde_assembly_paths=(None, None),
        xde_layer_authoritative=False,
        xde_layer_coverage_count=0,
        xde_color_display_metadata_authoritative=False,
        xde_assembly_identity_authoritative=False,
        face_ordinals_authoritative=True,
        face_orientation_authoritative=True,
        seam_connectivity_authoritative=True,
        physical_groups_authoritative=False,
        ordered_triangle_coordinate_sha256=_array_hash(vertices[faces], "<f8"),
        ordered_face_ordinal_sha256=_array_hash(ordinals, "<i8"),
        ordered_orientation_sha256=_array_hash(orientation, "u1"),
        seam_connectivity_sha256=_array_hash(canonical_faces, "<i8"),
        xde_metadata_sha256=sha256(
            json.dumps(xde_payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    )
    return CadNativeTriangulation(vertices, faces, provenance)


def _declaration() -> HexBrepSourceFrontAuthorityDeclarationL0:
    return HexBrepSourceFrontAuthorityDeclarationL0(
        authority_kind="cad_brep",
        authority_key="fixture/cad-brep-front",
        source_file_sha256=sha256(b"immutable-source").hexdigest(),
        triangulation=_triangulation(),
    )


def _never_success(report: object) -> None:
    assert getattr(report, "reader_invoked") is False
    assert getattr(report, "candidate_constructed") is False
    assert getattr(report, "production_mesh_changed") is False
    assert getattr(report, "artifact_delta") == 0
    assert getattr(report, "accepted") is False
    assert getattr(report, "mesher_success_allowed") is False
    assert getattr(report, "product_claimed") is False


def test_default_off_does_not_access_invalid_declaration(monkeypatch) -> None:
    monkeypatch.delenv(_ENABLE, raising=False)

    report = diagnose_hex_brep_source_front_authority_l0(object())

    assert report.status == "disabled_hex_brep_source_front_authority_l0"
    assert report.enabled is False
    _never_success(report)


def test_valid_immutable_brep_front_is_deterministic_but_unverified(monkeypatch) -> None:
    monkeypatch.setenv(_ENABLE, "1")
    declaration = _declaration()

    reports = tuple(diagnose_hex_brep_source_front_authority_l0(declaration) for _ in range(3))

    assert reports == (reports[0],) * 3
    report = reports[0]
    assert report.status == "report_brep_source_front_authority_unverified"
    assert report.input_brep_payload_valid is True
    assert report.source_file_digest_declared is True
    assert report.source_bytes_to_reader_payload_bound is False
    assert report.source_face_count == 2
    assert report.triangle_count == 2
    assert report.missing_evidence == (
        "source_bytes_to_reader_payload",
        "output_boundary_face_to_source_brep",
        "physical_group",
    )
    _never_success(report)


def test_unknown_or_malformed_authority_rejects_before_payload_access(monkeypatch) -> None:
    monkeypatch.setenv(_ENABLE, "1")
    monkeypatch.setattr(
        "core.analyzer.readers.step.load_cad_native_with_provenance",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("reader must not run")),
    )
    declaration = _declaration()
    unknown = replace(declaration, authority_kind="unknown")
    malformed = replace(declaration, source_file_sha256="bad")

    unknown_report = diagnose_hex_brep_source_front_authority_l0(unknown)
    malformed_report = diagnose_hex_brep_source_front_authority_l0(malformed)

    assert unknown_report.status == "reject_unknown_brep_source_authority_kind"
    assert malformed_report.status == "reject_malformed_brep_source_authority_declaration"
    assert unknown_report.input_brep_payload_valid is False
    assert malformed_report.input_brep_payload_valid is False
    _never_success(unknown_report)
    _never_success(malformed_report)


def test_hash_array_and_coverage_tampering_rejects(monkeypatch) -> None:
    monkeypatch.setenv(_ENABLE, "1")
    source = _triangulation()
    hash_bad = replace(
        source,
        provenance=replace(source.provenance, ordered_face_ordinal_sha256="0" * 64),
    )
    writable = source.provenance.triangle_face_ordinals.copy()
    array_bad = replace(
        source,
        provenance=replace(source.provenance, triangle_face_ordinals=writable),
    )
    coverage = _readonly(np.asarray((0, 0), dtype=np.int64))
    coverage_bad = replace(
        source,
        provenance=replace(source.provenance, triangle_face_ordinals=coverage),
    )

    reports = tuple(
        diagnose_hex_brep_source_front_authority_l0(replace(_declaration(), triangulation=value))
        for value in (hash_bad, array_bad, coverage_bad)
    )

    assert reports[0].malformed_evidence == ("provenance_hashes",)
    assert reports[1].malformed_evidence == ("provenance_arrays",)
    assert reports[2].malformed_evidence == ("provenance_coverage",)
    for report in reports:
        assert report.status == "reject_malformed_brep_source_front_payload"
        _never_success(report)


def test_authority_flag_and_physical_group_injection_rejects(monkeypatch) -> None:
    monkeypatch.setenv(_ENABLE, "1")
    source = _triangulation()
    flag_bad = replace(
        source,
        provenance=replace(source.provenance, seam_connectivity_authoritative=False),
    )
    physical_bad = replace(
        source,
        provenance=replace(
            source.provenance,
            physical_groups_authoritative=True,
            physical_group_names=("inlet", "wall"),
        ),
    )

    reports = tuple(
        diagnose_hex_brep_source_front_authority_l0(replace(_declaration(), triangulation=value))
        for value in (flag_bad, physical_bad)
    )

    assert reports[0].malformed_evidence == ("brep_authority_flags",)
    assert reports[1].malformed_evidence == ("physical_groups",)
    for report in reports:
        assert report.status == "reject_malformed_brep_source_front_payload"
        _never_success(report)
