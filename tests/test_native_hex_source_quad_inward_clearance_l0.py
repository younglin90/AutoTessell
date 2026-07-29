"""L0 manifest-gated inward-clearance prefilter tests."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import numpy as np

from core.analyzer.readers import read_stl
from core.generator.native_hex.source_feature_sidecar_l1 import (
    AuthoritativeSourceFeatureManifest,
    ordered_triangle_coordinate_sha256,
)
from core.generator.native_hex.source_quad_inward_clearance_l0 import (
    SampledInwardClearanceAudit,
    audit_sampled_inward_clearance_l0,
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
    path: Path, entities: tuple[tuple[str, str], ...], required: float
) -> SampledInwardClearanceAudit:
    mesh = read_stl(path)
    return audit_sampled_inward_clearance_l0(
        mesh.vertices,
        mesh.faces,
        source_path=path,
        manifest=_manifest(path, mesh.vertices, mesh.faces, entities),
        required_clearance=required,
    )


def test_labelled_cube_has_uniform_sampled_opposite_front_clearance() -> None:
    path = _ROOT / "tests" / "benchmarks" / "cube.stl"
    mesh = read_stl(path)
    report = _audit(path, (("cube", "wall"),) * len(mesh.faces), 0.5)

    assert report.status == "pass_sampled_inward_clearance"
    assert report.ray_hit_face_count == len(mesh.faces)
    assert report.minimum_clearance == 1.0
    assert report.fifth_percentile_clearance == 1.0
    assert report.faces_below_required_clearance == 0
    assert report.source_geometry_unchanged
    assert not report.production_mesh_changed


def test_synthetic_labelled_bracket_rejects_insufficient_sampled_clearance() -> None:
    path = _ROOT / "tests" / "stl" / "03_hard_bracket.stl"
    mesh = read_stl(path)
    report = _audit(path, (("synthetic_fixture", "wall"),) * len(mesh.faces), 0.05)

    assert report.status == "reject_sampled_inward_clearance"
    assert report.ray_hit_face_count == len(mesh.faces)
    assert report.minimum_clearance is not None and 0.04 < report.minimum_clearance < 0.041
    assert report.fifth_percentile_clearance is not None and report.fifth_percentile_clearance < 0.05
    assert report.faces_below_required_clearance > 0
    assert report.source_geometry_unchanged
    assert not report.production_mesh_changed


def test_missing_manifest_rejects_before_any_clearance_ray_is_used() -> None:
    path = _ROOT / "tests" / "benchmarks" / "cube.stl"
    mesh = read_stl(path)
    report = audit_sampled_inward_clearance_l0(
        mesh.vertices, mesh.faces, source_path=path, manifest=None, required_clearance=0.1
    )

    assert report.status == "reject_authoritative_feature_sidecar"
    assert report.ray_hit_face_count == 0
    assert report.minimum_clearance is None
