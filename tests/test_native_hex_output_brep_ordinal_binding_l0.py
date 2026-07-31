from __future__ import annotations

import json
from hashlib import sha256

import numpy as np

from core.analyzer.readers.step import CadEntityProvenance, CadNativeTriangulation
from core.analyzer.readers.step_snapshot_provenance_l0 import (
    CadSnapshotProvenanceL0,
    canonical_cad_reader_payload_sha256,
)
from core.generator.native_hex.output_brep_ordinal_binding_l0 import (
    diagnose_hex_output_brep_ordinal_binding_l0,
)

_ENV = "AUTO_TESSELL_HEX_OUTPUT_BREP_ORDINAL_BINDING_L0"


def _ro(value):
    value.setflags(write=False)
    return value


def _digest(value, dtype):
    return sha256(np.ascontiguousarray(value, dtype=dtype).tobytes()).hexdigest()


def _source():
    vertices = np.asarray(((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (1.0, 1.0, 0.0)))
    faces = np.asarray(((0, 1, 2), (1, 3, 2)), dtype=np.int64)
    ords, rev, seams, sources = (
        _ro(np.asarray(x, dtype=d))
        for x, d in (
            ((0, 1), np.int64),
            ((False, True), np.bool_),
            ((0, 1, 2, 3), np.int64),
            ((0, 1, 2, 3), np.int64),
        )
    )
    oriented = faces.copy()
    oriented[rev] = oriented[rev][:, (0, 2, 1)]
    canonical = _ro(seams[oriented])
    xde = {
        "face_names": (None, None),
        "layer_names": ((), ()),
        "surface_colors": (None, None),
        "assembly_paths": (None, None),
        "layer_authoritative": False,
        "physical_group_authoritative": False,
    }
    p = CadEntityProvenance(
        "partial_authority_physical_groups_unavailable",
        2,
        5,
        ords,
        rev,
        seams,
        sources,
        canonical,
        (None, None),
        (None, None),
        ((), ()),
        (None, None),
        (None, None),
        False,
        0,
        False,
        False,
        True,
        True,
        True,
        False,
        _digest(vertices[faces], "<f8"),
        _digest(ords, "<i8"),
        _digest(rev, "u1"),
        _digest(canonical, "<i8"),
        sha256(json.dumps(xde, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
    )
    tri = CadNativeTriangulation(vertices, faces, p)
    return CadSnapshotProvenanceL0(
        "report_snapshot_reader_provenance_unverified",
        True,
        "1" * 64,
        1,
        canonical_cad_reader_payload_sha256(tri),
        True,
        True,
        True,
        True,
        True,
        True,
        False,
        (),
        False,
        False,
        0,
        False,
        False,
        False,
        "x",
        tri,
    )


def _payload(source):
    tri = source.triangulation
    p = tri.provenance
    return (
        _ro(tri.vertices[p.canonical_vertex_source_ids].copy()),
        _ro(np.asarray((7, 11), dtype=np.int64)),
        _ro(p.oriented_canonical_faces.copy()),
        _ro(np.arange(len(p.canonical_vertex_source_ids), dtype=np.int64)),
        _ro(np.arange(len(tri.faces), dtype=np.int64)),
        _ro(p.triangle_face_ordinals.copy()),
    )


def test_default_off_and_exact_identity(monkeypatch):
    source = _source()
    payload = _payload(source)
    monkeypatch.delenv(_ENV, raising=False)
    assert (
        diagnose_hex_output_brep_ordinal_binding_l0(source, *payload).status
        == "disabled_hex_output_brep_ordinal_binding_l0"
    )
    monkeypatch.setenv(_ENV, "1")
    report = diagnose_hex_output_brep_ordinal_binding_l0(source, *payload)
    assert report.status == "report_hex_output_brep_ordinal_identity_unverified"
    assert report.output_mapping_complete and not report.accepted
    assert (
        not report.candidate_constructed
        and not report.production_mesh_changed
        and report.artifact_delta == 0
    )


def test_moved_reversed_wrong_or_ambiguous_reject(monkeypatch):
    monkeypatch.setenv(_ENV, "1")
    source = _source()
    vertices, ids, faces, mapping, triangles, ordinals = _payload(source)
    moved = _ro(vertices.copy())
    moved.setflags(write=True)
    moved[0, 0] = 2
    moved.setflags(write=False)
    reversed_faces = _ro(faces[:, (0, 2, 1)].copy())
    wrong = _ro(ordinals[::-1].copy())
    ambiguous = _ro(np.asarray((0, 0), dtype=np.int64))
    reports = (
        diagnose_hex_output_brep_ordinal_binding_l0(
            source, moved, ids, faces, mapping, triangles, ordinals
        ),
        diagnose_hex_output_brep_ordinal_binding_l0(
            source, vertices, ids, reversed_faces, mapping, triangles, ordinals
        ),
        diagnose_hex_output_brep_ordinal_binding_l0(
            source, vertices, ids, faces, mapping, triangles, wrong
        ),
        diagnose_hex_output_brep_ordinal_binding_l0(
            source, vertices, ids, faces, mapping, ambiguous, ordinals
        ),
    )
    assert [report.status for report in reports] == [
        "reject_output_brep_binding_moved",
        "reject_output_brep_binding_reversed_or_moved",
        "reject_output_brep_binding_wrong_ordinal",
        "reject_output_brep_binding_ambiguous",
    ]
    assert all(not report.accepted and not report.candidate_constructed for report in reports)
