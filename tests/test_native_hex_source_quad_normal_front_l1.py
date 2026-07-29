"""L1 full inner-front normal-offset candidate tests; no writer path exists."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import numpy as np

from core.analyzer.readers import read_stl
from core.generator.native_hex.source_feature_sidecar_l1 import (
    AuthoritativeSourceFeatureManifest,
    ordered_triangle_coordinate_sha256,
)
from core.generator.native_hex.source_quad_normal_front_l1 import (
    NormalFrontShellAudit,
    audit_normal_front_shell_l1,
)


_ROOT = Path(__file__).resolve().parents[1]


def _manifest(
    path: Path, vertices: np.ndarray, faces: np.ndarray, entities: tuple[tuple[str, str], ...]
) -> AuthoritativeSourceFeatureManifest:
    return AuthoritativeSourceFeatureManifest(
        sha256(path.read_bytes()).hexdigest(),
        ordered_triangle_coordinate_sha256(vertices, faces),
        entities,
    )


def _audit(
    path: Path, entities: tuple[tuple[str, str], ...], thickness: float
) -> NormalFrontShellAudit:
    mesh = read_stl(path)
    return audit_normal_front_shell_l1(
        mesh.vertices,
        mesh.faces,
        source_path=path,
        manifest=_manifest(path, mesh.vertices, mesh.faces, entities),
        thickness=thickness,
    )


def test_labelled_cube_normal_front_has_positive_hexes_and_no_nonadjacent_front_contact() -> None:
    path = _ROOT / "tests" / "benchmarks" / "cube.stl"
    mesh = read_stl(path)
    report = _audit(path, (("cube", "wall"),) * len(mesh.faces), 0.1)

    assert report.status == "pass_normal_front_candidate"
    assert report.hex_count == 36
    assert report.raw_negative_hex_count == 0
    assert report.inner_front_triangle_count == 72
    assert report.inner_front_intersection_pair_count == 0
    assert report.inner_front_coplanar_pair_count == 0
    assert report.outer_quad_set_preserved
    assert report.source_vertex_prefix_identical
    assert report.source_geometry_unchanged
    assert not report.production_mesh_changed


def test_synthetic_labelled_bracket_normal_front_rejects_full_front_or_hex_geometry() -> None:
    path = _ROOT / "tests" / "stl" / "03_hard_bracket.stl"
    mesh = read_stl(path)
    report = _audit(path, (("synthetic_fixture", "wall"),) * len(mesh.faces), 0.05)

    assert report.status == "reject_normal_front_geometry"
    assert report.hex_count == 1248
    assert report.raw_negative_hex_count > 0 or report.inner_front_intersection_pair_count > 0
    assert report.outer_quad_set_preserved
    assert report.source_vertex_prefix_identical
    assert report.source_geometry_unchanged
    assert not report.production_mesh_changed


def test_missing_manifest_rejects_before_candidate_geometry_is_constructed() -> None:
    path = _ROOT / "tests" / "benchmarks" / "cube.stl"
    mesh = read_stl(path)
    report = audit_normal_front_shell_l1(
        mesh.vertices, mesh.faces, source_path=path, manifest=None, thickness=0.1
    )

    assert report.status == "reject_authoritative_feature_sidecar"
    assert report.hex_count == 0
    assert report.inner_front_triangle_count == 0
