from __future__ import annotations

import struct
from pathlib import Path

import numpy as np
import pytest

from core.analyzer.readers import read_stl
from core.preprocessor.native_tri.cad_stl_authority_ingress import (
    admit_native_tri_authority_certificate,
    make_external_trust_anchor,
    semantic_ledger_from_faces,
    validate_native_tri_authority_source,
)


def _tetra_facets():
    return [
        ((0.0, 0.0, -1.0), ((0.0, 0.0, 0.0), (0.0, 1.0, 0.0), (1.0, 0.0, 0.0))),
        ((0.0, -1.0, 0.0), ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0))),
        ((-1.0, 0.0, 0.0), ((0.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 1.0, 0.0))),
        ((1.0, 1.0, 1.0), ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))),
    ]


def _write_ascii_tetra(path: Path) -> None:
    lines = ["solid tetra"]
    for normal, vertices in _tetra_facets():
        lines.append(f"  facet normal {normal[0]} {normal[1]} {normal[2]}")
        lines.append("    outer loop")
        for point in vertices:
            lines.append(f"      vertex {point[0]} {point[1]} {point[2]}")
        lines.extend(("    endloop", "  endfacet"))
    lines.append("endsolid tetra")
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def _write_binary_tetra(path: Path) -> None:
    payload = bytearray(b"native-tri-binary".ljust(80, b"\0"))
    payload.extend(struct.pack("<I", len(_tetra_facets())))
    for normal, vertices in _tetra_facets():
        payload.extend(struct.pack("<3f", *normal))
        for point in vertices:
            payload.extend(struct.pack("<3f", *point))
        payload.extend(struct.pack("<H", 0))
    path.write_bytes(bytes(payload))


def _canonical_raw_stl(path: Path):
    mesh = read_stl(path, dedupe=False)
    point_ids: dict[tuple[float, float, float], int] = {}
    points: list[tuple[float, float, float]] = []
    faces: list[list[int]] = []
    for point in np.asarray(mesh.vertices, dtype=np.float64):
        key = tuple(0.0 if float(value) == 0.0 else float(value) for value in point)
        if key not in point_ids:
            point_ids[key] = len(points)
            points.append(key)
    for raw_face in np.asarray(mesh.faces, dtype=np.int64):
        faces.append(
            [
                point_ids[
                    tuple(
                        0.0 if float(value) == 0.0 else float(value)
                        for value in mesh.vertices[int(vertex)]
                    )
                ]
                for vertex in raw_face
            ]
        )
    return np.asarray(points, dtype=np.float64), np.asarray(faces, dtype=np.int64)


def _certificate_fixture(tmp_path: Path, binary: bool = False):
    source = tmp_path / ("tetra-binary.stl" if binary else "tetra-ascii.stl")
    (_write_binary_tetra if binary else _write_ascii_tetra)(source)
    points, faces = _canonical_raw_stl(source)
    ledger = semantic_ledger_from_faces(
        faces,
        feature="tetra-surface",
        patch="outer-wall",
        physical_group="fluid-wall",
        component="tetra-0",
        provenance="registered-stl-facet",
    )
    trust = make_external_trust_anchor(
        source, ledger, issuer="test-registry", key_id="tri-key-v2"
    )
    return source, points, faces, ledger, trust


@pytest.mark.parametrize("binary", (False, True))
def test_cpp_certificate_reads_ascii_and_binary_stl_deterministically(tmp_path: Path, binary: bool):
    source, points, faces, ledger, trust = _certificate_fixture(tmp_path, binary)
    results = [
        validate_native_tri_authority_source(source, ledger, trust, requested_layers=0)
        for _ in range(3)
    ]
    assert all(result["accepted"] for result in results), results
    assert all(result["certificate_accepted"] for result in results)
    assert {result["certificate"]["source_kind"] for result in results} == {
        "stl_binary" if binary else "stl_ascii"
    }
    assert len({result["source_certificate_sha256"] for result in results}) == 1
    assert len({result["certificate"]["certificate_sha256"] for result in results}) == 1
    first = results[0]
    assert first["source_face_count"] == 4
    assert first["source_vertex_count"] == 4
    assert np.array_equal(np.asarray(first["certificate"]["canonical_triangles"]), faces)
    assert first["certificate"]["topology"]["strict_zero"] is True
    assert first["certificate"]["physical_groups_inferred"] is False
    assert first["certificate"]["canonicalization"] == "exact_coordinate_identity_only"
    admission = admit_native_tri_authority_certificate(first, requested_layers=0)
    assert admission["accepted"] is True, admission
    assert admission["generated_faces"] == []
    assert admission["publication_eligible"] is False


def test_positive_boundary_layer_is_an_atomic_refusal_after_source_certificate(tmp_path: Path):
    source, _points, _faces, ledger, trust = _certificate_fixture(tmp_path)
    result = validate_native_tri_authority_source(source, ledger, trust, requested_layers=1)
    assert result["accepted"] is False, result
    assert result["certificate_accepted"] is True
    assert result["reason"] == "native_tri_bl_writer_unavailable"
    assert result["actual_layers"] == 0
    assert result["generated_faces"] == []
    assert result["generated_vertices"] == []
    assert result["candidate_discarded"] is True
    admission = admit_native_tri_authority_certificate(result, requested_layers=1)
    assert admission["accepted"] is False
    assert admission["reason"] == "native_tri_bl_writer_unavailable"


def test_source_ledger_trust_and_file_identity_tamper_refuse(tmp_path: Path):
    source, _points, _faces, ledger, trust = _certificate_fixture(tmp_path)
    tampered_trust = dict(trust, source_sha256="0" * 64)
    result = validate_native_tri_authority_source(source, ledger, tampered_trust)
    assert result["accepted"] is False
    assert result["reason"] == "tri_external_source_registration_mismatch"
    tampered_count = dict(trust, source_byte_count=int(trust["source_byte_count"]) + 1)
    result = validate_native_tri_authority_source(source, ledger, tampered_count)
    assert result["accepted"] is False
    assert result["reason"] == "tri_external_source_byte_count_mismatch"
    tampered_ledger = [dict(row) for row in ledger]
    tampered_ledger[0]["physical_group"] = "forged-group"
    result = validate_native_tri_authority_source(source, tampered_ledger, trust)
    assert result["accepted"] is False
    assert result["reason"] == "tri_external_semantic_ledger_registration_mismatch"
    missing = [dict(row) for row in ledger[:-1]]
    result = validate_native_tri_authority_source(source, missing, trust)
    assert result["accepted"] is False
    assert result["reason"] == "tri_semantic_ledger_coverage_incomplete"


def test_step_and_symlink_are_not_authoritative_fallbacks(tmp_path: Path):
    step = tmp_path / "model.step"
    step.write_text("ISO-10303-21;", encoding="ascii")
    result = validate_native_tri_authority_source(step, [], {}, requested_layers=0)
    assert result["accepted"] is False
    assert result["reason"] == "occt_sdk_unavailable"
    source, _points, _faces, ledger, trust = _certificate_fixture(tmp_path)
    link = tmp_path / "linked.stl"
    try:
        link.symlink_to(source)
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")
    result = validate_native_tri_authority_source(link, ledger, trust)
    assert result["accepted"] is False
    assert result["reason"] == "tri_source_file_not_regular_or_readable"


def test_certificate_can_bind_an_actual_cube_release_evidence(monkeypatch):
    from core.evaluator.native_tri_release_evidence import certify_native_tri_release_result
    from core.evaluator.surface_physical_group_provenance import (
        AuthoritativePhysicalGroupMapping,
    )
    from core.preprocessor.native_tri.release_route import (
        NativeTriSourceAuthority,
        run_native_tri_release,
    )

    source = Path("tests/benchmarks/cube.stl")
    points, faces = _canonical_raw_stl(source)
    ledger = semantic_ledger_from_faces(
        faces,
        feature="cube-surface",
        patch="cube-wall",
        physical_group="cube-fluid-wall",
        component="cube",
        provenance="registered-release-stl-facet",
    )
    trust = make_external_trust_anchor(
        source, ledger, issuer="release-registry-test", key_id="tri-release-v2"
    )
    certificate = validate_native_tri_authority_source(source, ledger, trust)
    assert certificate["accepted"] is True, certificate
    monkeypatch.setenv("AUTO_TESSELL_NATIVE_TRI_RELEASE", "1")
    groups = tuple("cube-fluid-wall" for _ in faces)
    authority = NativeTriSourceAuthority(
        tuple(range(len(faces))),
        AuthoritativePhysicalGroupMapping(groups, True),
        (),
    )
    edge_lengths = np.concatenate(
        [
            np.linalg.norm(
                points[faces[:, index]] - points[faces[:, (index + 1) % 3]],
                axis=1,
            )
            for index in range(3)
        ]
    )
    result = run_native_tri_release(
        points,
        faces,
        target_edge_length=float(np.median(edge_lengths) * 0.5),
        source_authority=authority,
        max_rounds=1,
        source_path=source,
        source_certificate=certificate,
    )
    assert result.accepted is True
    assert result.source_certificate_sha256 == certificate["certificate"]["certificate_sha256"]
    assert result.source_semantic_ledger_sha256 == certificate["semantic_ledger_sha256"]
    evidence = certify_native_tri_release_result(result, source, faces)
    assert evidence["authoritative"] is True, evidence
    assert evidence["certificate_binding"] is True
    assert evidence["source_certificate_sha256"] == result.source_certificate_sha256


@pytest.mark.parametrize("name", ("cube.stl", "sphere_watertight.stl", "naca0012.stl"))
def test_release_stl_corpus_has_actual_source_certificate(tmp_path: Path, name: str):
    source = Path("tests/benchmarks") / name
    points, faces = _canonical_raw_stl(source)
    ledger = semantic_ledger_from_faces(
        faces,
        feature=f"{source.stem}-surface",
        patch=f"{source.stem}-wall",
        physical_group=f"{source.stem}-physical-wall",
        component=source.stem,
        provenance="registered-release-stl-facet",
    )
    trust = make_external_trust_anchor(
        source, ledger, issuer="release-registry-test", key_id="tri-release-v2"
    )
    result = validate_native_tri_authority_source(source, ledger, trust)
    assert result["accepted"] is True, result
    assert result["certificate_accepted"] is True
    assert result["source_face_count"] == len(faces)
    assert result["certificate"]["topology"]["strict_zero"] is True
    assert result["certificate"]["semantic_ledger_sha256"] == trust[
        "semantic_ledger_sha256"
    ]
