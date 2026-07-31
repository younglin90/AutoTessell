"""L1 corpus contract for report-only native-hex local-front authority."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import numpy as np
import pytest

from core.analyzer.readers import read_stl
from core.analyzer.readers.step import load_cad_native_with_provenance
from core.generator.native_hex.local_front_authority_corpus_l1 import (
    LocalFrontCorpusSidecarL1,
    audit_local_front_authority_corpus_l1,
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
