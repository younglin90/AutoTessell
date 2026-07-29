"""L1 authoritative source-feature sidecar contract tests."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import numpy as np

from core.analyzer.readers import read_stl
from core.generator.native_hex.source_feature_sidecar_l1 import (
    AuthoritativeSourceFeatureManifest,
    audit_authoritative_source_feature_sidecar_l1,
    ordered_triangle_coordinate_sha256,
)


_ROOT = Path(__file__).resolve().parents[1]


def _cube_entities(vertices: np.ndarray, faces: np.ndarray) -> tuple[tuple[str, str], ...]:
    labels: list[tuple[str, str]] = []
    for face in faces:
        centre = np.mean(vertices[face], axis=0)
        axis = int(np.argmax(np.abs(centre)))
        labels.append(("cube", f"axis_{axis}_{'high' if centre[axis] > 0.0 else 'low'}"))
    return tuple(labels)


def _manifest(path: Path, vertices: np.ndarray, faces: np.ndarray) -> AuthoritativeSourceFeatureManifest:
    return AuthoritativeSourceFeatureManifest(
        sha256(path.read_bytes()).hexdigest(),
        ordered_triangle_coordinate_sha256(vertices, faces),
        _cube_entities(vertices, faces),
    )


def test_sidecar_binds_authoritative_entities_to_exact_file_and_face_order() -> None:
    path = _ROOT / "tests" / "benchmarks" / "cube.stl"
    mesh = read_stl(path)
    report = audit_authoritative_source_feature_sidecar_l1(
        mesh.vertices, mesh.faces, source_path=path, manifest=_manifest(path, mesh.vertices, mesh.faces)
    )

    assert report.status == "pass_authoritative_feature_sidecar"
    assert report.source_file_hash_matches
    assert report.ordered_face_coordinate_hash_matches
    assert report.provenance is not None
    assert report.provenance.supplied_entities_are_authoritative
    assert len(report.provenance.entity_boundaries) == 12
    assert report.source_geometry_unchanged
    assert not report.production_mesh_changed


def test_missing_or_wrong_file_sidecar_fails_closed_without_geometry_inference() -> None:
    path = _ROOT / "tests" / "benchmarks" / "cube.stl"
    mesh = read_stl(path)
    missing = audit_authoritative_source_feature_sidecar_l1(
        mesh.vertices, mesh.faces, source_path=path, manifest=None
    )
    wrong_file = AuthoritativeSourceFeatureManifest(
        "0" * 64,
        ordered_triangle_coordinate_sha256(mesh.vertices, mesh.faces),
        _cube_entities(mesh.vertices, mesh.faces),
    )
    mismatch = audit_authoritative_source_feature_sidecar_l1(
        mesh.vertices, mesh.faces, source_path=path, manifest=wrong_file
    )

    assert missing.status == "reject_missing_authoritative_feature_manifest"
    assert mismatch.status == "reject_manifest_source_identity_mismatch"
    assert not mismatch.source_file_hash_matches
    assert mismatch.ordered_face_coordinate_hash_matches
    assert mismatch.provenance is None


def test_face_reordering_invalidates_sidecar_even_when_the_geometry_set_is_unchanged() -> None:
    path = _ROOT / "tests" / "benchmarks" / "cube.stl"
    mesh = read_stl(path)
    report = audit_authoritative_source_feature_sidecar_l1(
        mesh.vertices,
        mesh.faces[::-1].copy(),
        source_path=path,
        manifest=_manifest(path, mesh.vertices, mesh.faces),
    )

    assert report.status == "reject_manifest_source_identity_mismatch"
    assert report.source_file_hash_matches
    assert not report.ordered_face_coordinate_hash_matches
    assert report.provenance is None


def test_sidecar_contract_is_value_identical_on_repeat() -> None:
    path = _ROOT / "tests" / "benchmarks" / "cube.stl"
    mesh = read_stl(path)
    manifest = _manifest(path, mesh.vertices, mesh.faces)

    assert audit_authoritative_source_feature_sidecar_l1(
        mesh.vertices, mesh.faces, source_path=path, manifest=manifest
    ) == audit_authoritative_source_feature_sidecar_l1(
        mesh.vertices, mesh.faces, source_path=path, manifest=manifest
    )
