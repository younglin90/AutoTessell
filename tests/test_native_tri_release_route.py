"""Measured independent Native-Tri release-route evidence."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from core.analyzer.readers import read_stl
from core.evaluator.surface_physical_group_provenance import (
    AuthoritativePhysicalGroupMapping,
)
from core.preprocessor.native_tri.release_route import (
    NativeTriSourceAuthority,
    run_native_tri_release,
)


def test_cube_native_tri_release_route_is_actual_transaction_with_authority(monkeypatch) -> None:
    monkeypatch.setenv("AUTO_TESSELL_NATIVE_TRI_RELEASE", "1")
    mesh = read_stl(Path("tests/benchmarks/cube.stl"))
    vertices = np.ascontiguousarray(mesh.vertices, dtype=np.float64)
    faces = np.ascontiguousarray(mesh.faces, dtype=np.int64)
    edge_lengths = np.concatenate(
        [
            np.linalg.norm(
                vertices[faces[:, index]] - vertices[faces[:, (index + 1) % 3]],
                axis=1,
            )
            for index in range(3)
        ]
    )
    authority = NativeTriSourceAuthority(
        patch_ids=tuple(range(len(faces))),
        physical_groups=AuthoritativePhysicalGroupMapping(
            tuple("wall" for _ in faces), True
        ),
        # This corpus case intentionally declares no CAD feature edges; the
        # route records that declaration instead of inferring sharp edges.
        feature_edges=(),
        feature_authoritative=True,
    )
    results = [
        run_native_tri_release(
            vertices,
            faces,
            target_edge_length=float(np.median(edge_lengths) * 0.5),
            source_authority=authority,
            max_rounds=1,
        )
        for _ in range(3)
    ]
    assert all(result.accepted for result in results)
    assert all(result.independent_route and result.transaction_applied for result in results)
    assert {(len(result.vertices), len(result.faces)) for result in results} == {(26, 48)}
    assert all(result.source_topology_valid and result.output_topology_valid for result in results)
    assert all(result.source_envelope_preserved for result in results)
    assert all(result.feature_edges_total == 0 and result.feature_recall == 1.0 for result in results)
    assert all(result.source_face_provenance for result in results)
    assert all(len(result.output_physical_groups) == len(result.faces) for result in results)
    assert all(set(result.output_physical_groups) == {"wall"} for result in results)
    assert len({result.output_faces_sha256 for result in results}) == 1


def test_native_tri_release_preserves_explicit_cube_sharp_edges(monkeypatch) -> None:
    from core.analyzer.readers import read_stl
    from core.evaluator.surface_physical_group_provenance import AuthoritativePhysicalGroupMapping
    from core.preprocessor.native_tri.release_route import NativeTriSourceAuthority, run_native_tri_release

    monkeypatch.setenv("AUTO_TESSELL_NATIVE_TRI_RELEASE", "1")
    mesh = read_stl(Path("tests/benchmarks/cube.stl"))
    coordinates = np.asarray(mesh.vertices)
    feature_edges = tuple(
        (first, second)
        for first in range(len(coordinates))
        for second in range(first + 1, len(coordinates))
        if int(np.count_nonzero(np.abs(coordinates[first] - coordinates[second]) > 0.9)) == 1
    )
    authority = NativeTriSourceAuthority(
        tuple("wall" for _ in range(len(mesh.faces))),
        AuthoritativePhysicalGroupMapping(tuple("wall" for _ in range(len(mesh.faces))), True),
        feature_edges,
    )
    result = run_native_tri_release(
        np.asarray(mesh.vertices),
        np.asarray(mesh.faces),
        target_edge_length=0.3,
        source_authority=authority,
    )
    assert result.accepted
    assert result.transaction_applied
    assert result.independent_route
    assert result.feature_edges_total == 12
    assert result.feature_edges_preserved == 12
    assert result.feature_recall == 1.0


def test_native_tri_release_records_authoritative_cad_source_digest(monkeypatch) -> None:
    monkeypatch.setenv('AUTO_TESSELL_NATIVE_TRI_RELEASE', '1')
    from dataclasses import replace
    from hashlib import sha256

    import pytest
    from core.analyzer.readers.step import load_cad_native_with_provenance
    from core.evaluator.surface_physical_group_provenance import AuthoritativePhysicalGroupMapping
    from core.preprocessor.native_tri.release_route import NativeTriSourceAuthority, run_native_tri_release

    try:
        cad = load_cad_native_with_provenance(Path("tests/benchmarks/box.step"), ".step")
    except Exception as exc:
        pytest.skip(f"CAD reader unavailable: {exc}")
    provenance = replace(
        cad.provenance,
        physical_group_names=tuple(f"brep-face-{index}" for index in range(cad.provenance.face_count)),
        physical_groups_authoritative=True,
    )
    vertices = cad.vertices[cad.provenance.canonical_vertex_source_ids]
    faces = provenance.oriented_canonical_faces
    groups = tuple(provenance.physical_group_names[int(index)] for index in provenance.triangle_face_ordinals)
    authority = NativeTriSourceAuthority(groups, AuthoritativePhysicalGroupMapping(groups, True), ())
    results = [
        run_native_tri_release(
            vertices, faces, target_edge_length=0.3, source_authority=authority,
            source_path=Path("tests/benchmarks/box.step"), source_provenance=provenance,
        )
        for _ in range(3)
    ]
    assert all(result.accepted for result in results)
    assert all(result.independent_route and result.transaction_applied for result in results)
    assert all(result.source_provenance_authoritative for result in results)
    expected_sha = sha256(Path("tests/benchmarks/box.step").read_bytes()).hexdigest()
    assert all(result.source_file_sha256 == expected_sha for result in results)
    assert len({result.output_faces_sha256 for result in results}) == 1


def test_native_tri_release_sphere_corpus_is_repeatable_and_group_bound(
    monkeypatch, tmp_path: Path,
) -> None:
    from hashlib import sha256

    monkeypatch.setenv("AUTO_TESSELL_NATIVE_TRI_RELEASE", "1")
    mesh = read_stl(Path("tests/benchmarks/sphere_watertight.stl"))
    vertices = np.ascontiguousarray(mesh.vertices, dtype=np.float64)
    faces = np.ascontiguousarray(mesh.faces, dtype=np.int64)
    groups = tuple("sphere-wall" for _ in faces)
    authority = NativeTriSourceAuthority(
        patch_ids=groups,
        physical_groups=AuthoritativePhysicalGroupMapping(groups, True),
        feature_edges=(),
        feature_authoritative=True,
    )
    hashes: list[tuple[str, str]] = []
    for _ in range(3):
        result = run_native_tri_release(
            vertices, faces, target_edge_length=0.3,
            source_authority=authority, max_rounds=1,
            source_path=Path("tests/benchmarks/sphere_watertight.stl"),
        )
        assert result.accepted
        assert result.independent_route
        assert result.transaction_applied
        assert result.source_topology_valid
        assert result.output_topology_valid
        assert result.source_envelope_preserved
        assert result.source_face_provenance
        assert result.source_file_sha256 == sha256(
            Path("tests/benchmarks/sphere_watertight.stl").read_bytes()
        ).hexdigest()
        assert result.source_provenance_authoritative
        assert set(result.output_physical_groups) == {"sphere-wall"}
        hashes.append((result.source_vertices_sha256, result.output_vertices_sha256))
    assert hashes == [hashes[0]] * 3

def test_native_tri_release_naca_stl_corpus_is_repeatable(monkeypatch) -> None:
    monkeypatch.setenv("AUTO_TESSELL_NATIVE_TRI_RELEASE", "1")
    mesh = read_stl(Path("tests/benchmarks/naca0012.stl"))
    vertices = np.ascontiguousarray(mesh.vertices, dtype=np.float64)
    faces = np.ascontiguousarray(mesh.faces, dtype=np.int64)
    groups = tuple("naca-wall" for _ in faces)
    authority = NativeTriSourceAuthority(
        patch_ids=groups,
        physical_groups=AuthoritativePhysicalGroupMapping(groups, True),
        feature_edges=(),
        feature_authoritative=True,
    )
    results = [
        run_native_tri_release(
            vertices, faces, target_edge_length=0.15,
            source_authority=authority, max_rounds=1,
            source_path=Path("tests/benchmarks/naca0012.stl"),
        )
        for _ in range(3)
    ]
    assert all(result.accepted for result in results)
    assert all(result.transaction_applied for result in results)
    assert all(result.source_provenance_authoritative for result in results)
    assert all(result.output_topology_valid for result in results)
    assert all(result.feature_recall == 1.0 for result in results)
    assert len({result.output_faces_sha256 for result in results}) == 1

def test_native_tri_release_naca_authority_adapter_is_authoritative(monkeypatch) -> None:
    from core.evaluator.native_tri_release_evidence import certify_native_tri_release_result
    from core.analyzer.readers import read_stl

    monkeypatch.setenv("AUTO_TESSELL_NATIVE_TRI_RELEASE", "1")
    source = Path("tests/benchmarks/naca0012.stl")
    mesh = read_stl(source)
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    groups = tuple("naca-wall" for _ in faces)
    authority = NativeTriSourceAuthority(
        patch_ids=groups,
        physical_groups=AuthoritativePhysicalGroupMapping(groups, True),
        feature_edges=(),
        feature_authoritative=True,
    )
    result = run_native_tri_release(
        vertices, faces, target_edge_length=0.15,
        source_authority=authority, max_rounds=1, source_path=source,
    )
    evidence = certify_native_tri_release_result(result, source, faces)
    assert evidence["authoritative"] is True
    assert evidence["shape_preserved"] is True
    assert evidence["source_face_provenance"] is True
    assert evidence["surface_topology"]["kind"] == "surface"
    assert evidence["surface_topology"]["n_open_edges"] == 0
