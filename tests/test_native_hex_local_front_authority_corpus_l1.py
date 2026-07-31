"""L1 corpus contract for report-only native-hex local-front authority."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import cast

import numpy as np
import pytest

from core.analyzer.readers import read_stl
from core.analyzer.readers.step import load_cad_native_with_provenance
from core.generator.native_hex.local_front_authority_corpus_l1 import (
    LocalFrontCorpusAuthorityMetadataL2,
    LocalFrontCorpusSidecarL1,
    LocalFrontCorpusSourceDigestL3,
    audit_local_front_authority_corpus_l1,
    audit_local_front_authority_manifest_l2,
    audit_local_front_authority_source_digest_l3,
)
from core.generator.native_hex.source_feature_sidecar_l1 import (
    AuthoritativeSourceFeatureManifest,
    ordered_triangle_coordinate_sha256,
)

_ROOT = Path(__file__).resolve().parents[1]


def _manifest(
    path: Path,
    vertices: np.ndarray,
    faces: np.ndarray,
    entities: tuple[tuple[str, str], ...],
) -> AuthoritativeSourceFeatureManifest:
    return AuthoritativeSourceFeatureManifest(
        sha256(path.read_bytes()).hexdigest(),
        ordered_triangle_coordinate_sha256(vertices, faces),
        entities,
    )


def _forbidden(*_args: object, **_kwargs: object) -> None:
    raise AssertionError("report-only authority corpus must not invoke mesh output")


def _tree_paths(root: Path) -> tuple[str, ...]:
    return tuple(str(path.relative_to(root)) for path in sorted(root.rglob("*")))


def _ocp_available() -> bool:
    try:
        from OCP.STEPControl import STEPControl_Reader  # noqa: F401

        return True
    except ImportError:
        return False


def test_l1_checked_in_cube_sidecar_preflights_three_times_without_artifact(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from core.generator.native_hex import mesher

    monkeypatch.setattr(mesher, "generate_native_hex", _forbidden)
    monkeypatch.setattr(mesher, "_write_polymesh_hex", _forbidden)
    path = _ROOT / "tests" / "benchmarks" / "cube.stl"
    mesh = read_stl(path)
    sidecar = LocalFrontCorpusSidecarL1(
        "checked_in_fixture",
        _manifest(path, mesh.vertices, mesh.faces, (("cube_fixture", "wall"),) * len(mesh.faces)),
        True,
    )
    source_hash = sha256(mesh.vertices.tobytes() + mesh.faces.tobytes()).hexdigest()
    before = _tree_paths(tmp_path)
    reports = [
        audit_local_front_authority_corpus_l1(
            mesh.vertices,
            mesh.faces,
            source_path=str(path),
            sidecar=sidecar,
            requested_step=0.1,
        )
        for _ in range(3)
    ]

    assert reports == [reports[0]] * 3
    report = reports[0]
    assert report.status == "pass_authoritative_local_front_preflight"
    assert report.sidecar_status == "pass_authoritative_feature_sidecar"
    assert report.preflight_invoked and report.preflight_admitted
    assert report.source_face_count == 12
    assert report.two_manifold_edge_count == 18
    assert not report.candidate_constructed and not report.production_mesh_changed
    assert report.artifact_delta == 0 and _tree_paths(tmp_path) == before
    assert sha256(mesh.vertices.tobytes() + mesh.faces.tobytes()).hexdigest() == source_hash


@pytest.mark.skipif(not _ocp_available(), reason="OCP not installed")
def test_l1_t_junction_cad_sidecar_reports_known_physical_group_gap_without_preflight(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from core.generator.native_hex import mesher

    monkeypatch.setattr(mesher, "generate_native_hex", _forbidden)
    monkeypatch.setattr(mesher, "_write_polymesh_hex", _forbidden)
    path = _ROOT / "tests" / "benchmarks" / "t_junction.step"
    loaded = load_cad_native_with_provenance(path, ".step")
    cad = loaded.provenance
    vertices = loaded.vertices[cad.canonical_vertex_source_ids]
    faces = cad.oriented_canonical_faces
    sidecar = LocalFrontCorpusSidecarL1(
        "cad_brep",
        _manifest(
            path,
            vertices,
            faces,
            tuple(("t-junction", f"brep-face-{int(face)}") for face in cad.triangle_face_ordinals),
        ),
        False,
        cad,
    )
    before = _tree_paths(tmp_path)
    reports = [
        audit_local_front_authority_corpus_l1(
            vertices,
            faces,
            source_path=str(path),
            sidecar=sidecar,
            requested_step=0.1,
        )
        for _ in range(3)
    ]

    assert reports == [reports[0]] * 3
    report = reports[0]
    assert report.status == "reject_cad_physical_groups_unknown"
    assert report.sidecar_status == "pass_authoritative_feature_sidecar"
    assert report.cad_face_count == 12 and report.cad_topological_edge_count == 18
    assert report.source_face_count == 3392
    assert report.two_manifold_edge_count == 5088
    assert report.entity_boundary_edge_count == 1696
    assert not report.physical_groups_authoritative
    assert not report.preflight_invoked and not report.preflight_admitted
    assert not report.candidate_constructed and not report.production_mesh_changed
    assert report.artifact_delta == 0 and _tree_paths(tmp_path) == before


@pytest.mark.parametrize("authority_kind", ("unknown", "synthetic"))
def test_l1_unknown_or_synthetic_bracket_rejects_before_preflight_or_artifact(
    authority_kind: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from core.generator.native_hex import mesher

    monkeypatch.setattr(mesher, "generate_native_hex", _forbidden)
    monkeypatch.setattr(mesher, "_write_polymesh_hex", _forbidden)
    path = _ROOT / "tests" / "stl" / "03_hard_bracket.stl"
    mesh = read_stl(path)
    fabricated = _manifest(
        path,
        mesh.vertices,
        mesh.faces,
        (("synthetic_fixture", "wall"),) * len(mesh.faces),
    )
    sidecar = LocalFrontCorpusSidecarL1(
        authority_kind,  # type: ignore[arg-type]
        fabricated if authority_kind == "synthetic" else None,
        False,
    )
    source_hash = sha256(mesh.vertices.tobytes() + mesh.faces.tobytes()).hexdigest()
    before = _tree_paths(tmp_path)
    reports = [
        audit_local_front_authority_corpus_l1(
            mesh.vertices,
            mesh.faces,
            source_path=str(path),
            sidecar=sidecar,
            requested_step=0.05,
        )
        for _ in range(3)
    ]

    assert reports == [reports[0]] * 3
    report = reports[0]
    assert report.status == "reject_non_authoritative_corpus_sidecar"
    assert report.sidecar_status is None
    assert not report.preflight_invoked and not report.preflight_admitted
    assert not report.candidate_constructed and not report.production_mesh_changed
    assert report.artifact_delta == 0 and _tree_paths(tmp_path) == before
    assert sha256(mesh.vertices.tobytes() + mesh.faces.tobytes()).hexdigest() == source_hash


def test_l1_checked_in_cube_hash_or_face_order_mismatch_rejects_before_preflight() -> None:
    path = _ROOT / "tests" / "benchmarks" / "cube.stl"
    mesh = read_stl(path)
    manifest = _manifest(
        path,
        mesh.vertices,
        mesh.faces,
        (("cube_fixture", "wall"),) * len(mesh.faces),
    )
    bad_file = LocalFrontCorpusSidecarL1(
        "checked_in_fixture",
        AuthoritativeSourceFeatureManifest(
            "0" * 64,
            manifest.ordered_triangle_coordinate_sha256,
            manifest.face_entities,
        ),
        True,
    )
    report = audit_local_front_authority_corpus_l1(
        mesh.vertices,
        mesh.faces,
        source_path=str(path),
        sidecar=bad_file,
        requested_step=0.1,
    )
    reordered = audit_local_front_authority_corpus_l1(
        mesh.vertices,
        mesh.faces[::-1].copy(),
        source_path=str(path),
        sidecar=LocalFrontCorpusSidecarL1("checked_in_fixture", manifest, True),
        requested_step=0.1,
    )

    assert report.status == "reject_authoritative_corpus_sidecar_identity"
    assert reordered.status == "reject_authoritative_corpus_sidecar_identity"
    assert not report.preflight_invoked and not reordered.preflight_invoked


def test_l0_unrecognized_authority_kind_rejects_valid_cube_before_sidecar_or_preflight() -> None:
    path = _ROOT / "tests" / "benchmarks" / "cube.stl"
    mesh = read_stl(path)
    manifest = _manifest(
        path,
        mesh.vertices,
        mesh.faces,
        (("cube_fixture", "wall"),) * len(mesh.faces),
    )
    sidecar = LocalFrontCorpusSidecarL1(
        "unrecognized",  # type: ignore[arg-type]
        manifest,
        True,
    )

    report = audit_local_front_authority_corpus_l1(
        mesh.vertices,
        mesh.faces,
        source_path=str(path),
        sidecar=sidecar,
        requested_step=0.1,
    )

    assert report.status == "reject_unknown_corpus_authority_kind"
    assert report.sidecar_status is None
    assert not report.preflight_invoked and not report.preflight_admitted
    assert not report.candidate_constructed and not report.production_mesh_changed
    assert report.artifact_delta == 0


def _canonical_authority_metadata_l2() -> tuple[LocalFrontCorpusAuthorityMetadataL2, ...]:
    rows = (
        ("fixture:cube", 0, _ROOT / "tests" / "benchmarks" / "cube.stl"),
        ("fixture:cylinder", 1, _ROOT / "tests" / "benchmarks" / "cylinder.stl"),
        ("fixture:sphere", 2, _ROOT / "tests" / "benchmarks" / "sphere.stl"),
    )
    assert all(path.is_file() for _, _, path in rows)
    return tuple(
        LocalFrontCorpusAuthorityMetadataL2(key, order, str(path)) for key, order, path in rows
    )


def _assert_no_mesh_path(report: object) -> None:
    assert getattr(report, "sidecar_invoked") is False
    assert getattr(report, "numeric_preflight_invoked") is False
    assert getattr(report, "candidate_constructed") is False
    assert getattr(report, "production_mesh_changed") is False
    assert getattr(report, "artifact_delta") == 0


def test_l2_canonical_authority_manifest_is_order_independent_before_sidecar_or_preflight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import core.generator.native_hex.local_front_authority_corpus_l1 as authority

    monkeypatch.setattr(authority, "audit_authoritative_source_feature_sidecar_l1", _forbidden)
    monkeypatch.setattr(authority, "audit_local_front_admission_l0", _forbidden)
    rows = _canonical_authority_metadata_l2()
    reports = tuple(
        audit_local_front_authority_manifest_l2(order)
        for order in (rows, tuple(reversed(rows)), rows)
    )

    assert reports == (reports[0],) * 3
    report = reports[0]
    assert report.status == "pass_unambiguous_authority_corpus_metadata"
    assert report.metadata_count == 3
    assert report.canonical_authority_keys == (
        "fixture:cube",
        "fixture:cylinder",
        "fixture:sphere",
    )
    assert not report.duplicate_authority_keys and not report.duplicate_manifest_orders
    _assert_no_mesh_path(report)


def test_l2_duplicate_authority_key_rejects_canonical_rows_before_sidecar_or_preflight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import core.generator.native_hex.local_front_authority_corpus_l1 as authority

    monkeypatch.setattr(authority, "audit_authoritative_source_feature_sidecar_l1", _forbidden)
    monkeypatch.setattr(authority, "audit_local_front_admission_l0", _forbidden)
    cube, cylinder, sphere = _canonical_authority_metadata_l2()
    report = audit_local_front_authority_manifest_l2(
        (cube, replace(cylinder, authority_key=cube.authority_key), sphere)
    )

    assert report.status == "reject_duplicate_authority_key"
    assert report.duplicate_authority_keys == ("fixture:cube",)
    assert report.duplicate_manifest_orders == ()
    _assert_no_mesh_path(report)


def test_l2_manifest_order_tie_rejects_canonical_rows_before_sidecar_or_preflight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import core.generator.native_hex.local_front_authority_corpus_l1 as authority

    monkeypatch.setattr(authority, "audit_authoritative_source_feature_sidecar_l1", _forbidden)
    monkeypatch.setattr(authority, "audit_local_front_admission_l0", _forbidden)
    cube, cylinder, sphere = _canonical_authority_metadata_l2()
    report = audit_local_front_authority_manifest_l2(
        (cube, cylinder, replace(sphere, manifest_order=cylinder.manifest_order))
    )

    assert report.status == "reject_manifest_order_ambiguity"
    assert report.duplicate_authority_keys == ()
    assert report.duplicate_manifest_orders == (1,)
    _assert_no_mesh_path(report)


@pytest.mark.parametrize(
    "invalid_row",
    (
        LocalFrontCorpusAuthorityMetadataL2(cast(str, 1), 0, "tests/benchmarks/cube.stl"),
        LocalFrontCorpusAuthorityMetadataL2("fixture:cube", 0, cast(str, 1)),
        LocalFrontCorpusAuthorityMetadataL2(
            "fixture:cube", cast(int, "1"), "tests/benchmarks/cube.stl"
        ),
        LocalFrontCorpusAuthorityMetadataL2(
            "fixture:cube", cast(int, True), "tests/benchmarks/cube.stl"
        ),
    ),
)
def test_l2_runtime_invalid_metadata_rejects_before_sidecar_or_preflight(
    invalid_row: LocalFrontCorpusAuthorityMetadataL2,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import core.generator.native_hex.local_front_authority_corpus_l1 as authority

    monkeypatch.setattr(authority, "audit_authoritative_source_feature_sidecar_l1", _forbidden)
    monkeypatch.setattr(authority, "audit_local_front_admission_l0", _forbidden)
    report = audit_local_front_authority_manifest_l2((invalid_row,))

    assert report.status == "reject_invalid_authority_corpus_metadata"
    assert report.metadata_count == 1
    assert report.canonical_authority_keys == ()
    assert report.duplicate_authority_keys == ()
    assert report.duplicate_manifest_orders == ()
    _assert_no_mesh_path(report)


def _cube_source_digest_l3() -> LocalFrontCorpusSourceDigestL3:
    path = _ROOT / "tests" / "benchmarks" / "cube.stl"
    return LocalFrontCorpusSourceDigestL3(
        LocalFrontCorpusAuthorityMetadataL2("fixture:cube", 0, str(path)),
        sha256(path.read_bytes()).hexdigest(),
    )


def _assert_no_l3_downstream_path(report: object) -> None:
    assert getattr(report, "sidecar_invoked") is False
    assert getattr(report, "numeric_preflight_invoked") is False
    assert getattr(report, "candidate_constructed") is False
    assert getattr(report, "production_mesh_changed") is False
    assert getattr(report, "artifact_delta") == 0


def test_l3_canonical_cube_source_digest_is_deterministic_before_sidecar_or_preflight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import core.generator.native_hex.local_front_authority_corpus_l1 as authority

    monkeypatch.setattr(authority, "audit_authoritative_source_feature_sidecar_l1", _forbidden)
    monkeypatch.setattr(authority, "audit_local_front_admission_l0", _forbidden)
    row = _cube_source_digest_l3()
    monkeypatch.setattr(Path, "read_bytes", _forbidden)
    reports = tuple(audit_local_front_authority_source_digest_l3((row,)) for _ in range(3))

    assert reports == (reports[0],) * 3
    report = reports[0]
    assert report.status == "pass_immutable_source_digest_authority"
    assert report.metadata_status == "pass_unambiguous_authority_corpus_metadata"
    assert report.metadata_count == 1
    assert report.canonical_authority_keys == ("fixture:cube",)
    assert report.source_file_exists and report.source_digest_matches
    _assert_no_l3_downstream_path(report)


def test_l3_altered_cube_digest_rejects_before_sidecar_or_preflight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import core.generator.native_hex.local_front_authority_corpus_l1 as authority

    monkeypatch.setattr(authority, "audit_authoritative_source_feature_sidecar_l1", _forbidden)
    monkeypatch.setattr(authority, "audit_local_front_admission_l0", _forbidden)
    row = _cube_source_digest_l3()
    report = audit_local_front_authority_source_digest_l3(
        (replace(row, source_file_sha256="0" * 64),)
    )

    assert report.status == "reject_source_digest_mismatch"
    assert report.metadata_status == "pass_unambiguous_authority_corpus_metadata"
    assert report.source_file_exists and not report.source_digest_matches
    _assert_no_l3_downstream_path(report)


def test_l3_missing_cube_source_rejects_before_sidecar_or_preflight(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import core.generator.native_hex.local_front_authority_corpus_l1 as authority

    monkeypatch.setattr(authority, "audit_authoritative_source_feature_sidecar_l1", _forbidden)
    monkeypatch.setattr(authority, "audit_local_front_admission_l0", _forbidden)
    row = _cube_source_digest_l3()
    missing = replace(row.metadata, source_path=str(tmp_path / "cube_missing.stl"))
    report = audit_local_front_authority_source_digest_l3((replace(row, metadata=missing),))

    assert report.status == "reject_source_digest_file_not_found"
    assert report.metadata_status == "pass_unambiguous_authority_corpus_metadata"
    assert not report.source_file_exists and not report.source_digest_matches
    _assert_no_l3_downstream_path(report)


def test_l3_unreadable_cube_source_rejects_before_sidecar_or_preflight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import core.generator.native_hex.local_front_authority_corpus_l1 as authority

    monkeypatch.setattr(authority, "audit_authoritative_source_feature_sidecar_l1", _forbidden)
    monkeypatch.setattr(authority, "audit_local_front_admission_l0", _forbidden)
    row = _cube_source_digest_l3()
    source_path = Path(row.metadata.source_path)
    original_open = Path.open

    def unreadable(path: Path, *args: object, **kwargs: object) -> object:
        if path == source_path:
            raise OSError("fixture read denied")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", unreadable)
    report = audit_local_front_authority_source_digest_l3((row,))

    assert report.status == "reject_source_digest_file_unreadable"
    assert report.source_file_exists and not report.source_digest_matches
    _assert_no_l3_downstream_path(report)
