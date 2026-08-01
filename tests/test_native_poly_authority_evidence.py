"""Native Poly authoritative source/patch Gate4 evidence."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from core.analyzer.readers import read_stl
from core.evaluator.gate4_surface_topology import audit_polymesh_surface
from core.evaluator.native_poly_release_evidence import certify_native_poly_boundary_authority
from core.evaluator.strict_volume_topology import audit_strict_volume_topology
from core.generator.native_poly.harness import run_native_poly_harness
from core.utils.boundary_provenance import SourceSurfacePatchClassifier


def test_native_poly_sphere_written_boundary_is_source_bound_and_strict(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AUTO_TESSELL_P4C_PYTETWILD", "0")
    source_path = Path("tests/benchmarks/sphere_watertight.stl")
    mesh = read_stl(source_path)
    classifier = SourceSurfacePatchClassifier([source_path])
    result = run_native_poly_harness(
        np.asarray(mesh.vertices),
        np.asarray(mesh.faces),
        tmp_path,
        seed_density=8,
        max_iter=1,
        max_tet_cells=15_000,
        boundary_face_classifier=classifier,
    )
    assert result.success, result.message
    strict = audit_strict_volume_topology(tmp_path)
    assert strict.valid
    surface = audit_polymesh_surface(tmp_path)
    assert surface.topology_valid
    assert surface.artifact is not None
    assert surface.artifact.sha256 == strict.artifact_sha256
    boundary = (tmp_path / "constant" / "polyMesh" / "boundary").read_text()
    assert "source_0_sphere_watertight" in boundary
    certificate = certify_native_poly_boundary_authority(
        tmp_path,
        source_path,
        source_patch_ids=("sphere-wall",) * len(mesh.faces),
        source_physical_groups=("sphere-wall",) * len(mesh.faces),
        expected_boundary_patch="source_0_sphere_watertight",
        feature_preserved=True,
        provenance_complete=True,
    )
    assert certificate.authoritative, certificate.as_dict()
    assert certificate.shape_preserved
    assert certificate.source_shape_sha256 and certificate.output_shape_sha256
    assert certificate.shape_preserved
    assert certificate.source_shape_sha256 and certificate.output_shape_sha256

@pytest.mark.parametrize("source_name", ("cylinder", "trimesh_duct"))
def test_native_poly_complex_written_boundary_is_source_bound(
    source_name: str, tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.setenv("AUTO_TESSELL_P4C_PYTETWILD", "0")
    source_path = Path("tests/benchmarks") / f"{source_name}.stl"
    mesh = read_stl(source_path)
    result = run_native_poly_harness(
        np.asarray(mesh.vertices), np.asarray(mesh.faces), tmp_path,
        seed_density=8, max_iter=1, max_tet_cells=15_000,
        boundary_face_classifier=SourceSurfacePatchClassifier([source_path]),
    )
    assert result.success, result.message
    strict = audit_strict_volume_topology(tmp_path)
    surface = audit_polymesh_surface(tmp_path)
    expected_patch = f"source_0_{source_name}"
    boundary = (tmp_path / "constant" / "polyMesh" / "boundary").read_text()
    certificate = certify_native_poly_boundary_authority(
        tmp_path, source_path,
        source_patch_ids=("wall",) * len(mesh.faces),
        source_physical_groups=("wall",) * len(mesh.faces),
        expected_boundary_patch=expected_patch,
        feature_preserved=True, provenance_complete=True,
    )
    assert strict.valid
    assert surface.topology_valid
    assert expected_patch in boundary
    assert certificate.authoritative, certificate.as_dict()
