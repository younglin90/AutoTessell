"""Native Poly release-route fallback contract."""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

from core.generator.tier_native_poly import _runner


def test_native_poly_release_route_never_falls_back_on_failure(tmp_path: Path) -> None:
    result = _runner(
        np.empty((0, 3), dtype=np.float64),
        np.empty((0, 3), dtype=np.int64),
        tmp_path,
        release_route=True,
    )
    assert result.success is False
    assert result.route == "poly_harness_release"
    assert result.fallback_reason == "release_route_fallback_forbidden"

def test_native_poly_release_route_naca_is_source_bound(tmp_path: Path) -> None:
    from core.evaluator.gate4_surface_topology import audit_polymesh_surface
    from core.evaluator.native_poly_release_evidence import certify_native_poly_boundary_authority
    from core.evaluator.strict_volume_topology import audit_strict_volume_topology
    from core.analyzer.readers import read_stl

    source = Path("tests/benchmarks/naca0012.stl")
    mesh = read_stl(source)
    result = _runner(
        np.asarray(mesh.vertices), np.asarray(mesh.faces), tmp_path,
        release_route=True, source_path=source,
    )
    assert result.success, result.message
    strict = audit_strict_volume_topology(tmp_path)
    surface = audit_polymesh_surface(tmp_path)
    expected = "source_0_naca0012"
    boundary = (tmp_path / "constant" / "polyMesh" / "boundary").read_text()
    certificate = certify_native_poly_boundary_authority(
        tmp_path, source,
        source_patch_ids=("naca-wall",) * len(mesh.faces),
        source_physical_groups=("naca-wall",) * len(mesh.faces),
        expected_boundary_patch=expected,
        feature_preserved=True, provenance_complete=True,
    )
    assert result.route == "poly_harness_release"
    assert result.contract_details["mode"] == "harness"
    assert strict.valid
    assert surface.topology_valid
    assert expected in boundary
    assert certificate.authoritative, certificate.as_dict()

def test_native_poly_release_route_gear_is_repeatable_and_source_bound(
    tmp_path: Path,
) -> None:
    from core.evaluator.gate4_surface_topology import audit_polymesh_surface
    from core.evaluator.native_poly_release_evidence import certify_native_poly_boundary_authority
    from core.evaluator.strict_volume_topology import audit_strict_volume_topology
    from core.analyzer.readers import read_stl

    source = Path("tests/stl/04_extreme_gear.stl")
    mesh = read_stl(source)
    manifests = []
    for repeat in range(3):
        case_dir = tmp_path / f"gear-{repeat}"
        result = _runner(
            np.asarray(mesh.vertices), np.asarray(mesh.faces), case_dir,
            release_route=True, source_path=source,
        )
        assert result.success, result.message
        strict = audit_strict_volume_topology(case_dir)
        surface = audit_polymesh_surface(case_dir)
        expected = "source_0_04_extreme_gear"
        boundary = (case_dir / "constant" / "polyMesh" / "boundary").read_text()
        certificate = certify_native_poly_boundary_authority(
            case_dir, source,
            source_patch_ids=("gear-wall",) * len(mesh.faces),
            source_physical_groups=("gear-wall",) * len(mesh.faces),
            expected_boundary_patch=expected,
            feature_preserved=True, provenance_complete=True,
        )
        assert strict.valid
        assert surface.topology_valid
        assert expected in boundary
        assert certificate.authoritative, certificate.as_dict()
        digest = hashlib.sha256()
        for path in sorted((case_dir / "constant" / "polyMesh").iterdir()):
            if path.is_file():
                digest.update(path.name.encode())
                digest.update(path.read_bytes())
        manifests.append(digest.hexdigest())
    assert manifests == [manifests[0]] * 3
