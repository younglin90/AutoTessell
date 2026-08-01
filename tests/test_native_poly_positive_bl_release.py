"""Actual Native Poly boundary-layer release evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from core.analyzer.readers import read_stl
from core.evaluator.strict_volume_topology import audit_strict_volume_topology
from core.evaluator.gate4_surface_topology import audit_polymesh_surface
from core.evaluator.native_poly_release_evidence import certify_native_poly_boundary_authority
from core.generator.native_poly.harness import run_native_poly_harness
from core.generator.tier_native_poly import _runner
from core.layers.poly_bl_transition import run_poly_bl_transition
from core.utils.boundary_provenance import SourceSurfacePatchClassifier


def _manifest(case_dir: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted((case_dir / "constant" / "polyMesh").iterdir()):
        if path.is_file():
            digest.update(path.name.encode("utf-8"))
            digest.update(path.read_bytes())
    return digest.hexdigest()


def test_native_poly_positive_boundary_layer_is_written_and_repeatable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AUTO_TESSELL_P4C_PYTETWILD", "0")
    mesh = read_stl(Path("tests/benchmarks/cube.stl"))
    hashes: list[str] = []
    for repeat in range(3):
        case_dir = tmp_path / f"poly-bl-{repeat}"
        result = run_native_poly_harness(
            np.asarray(mesh.vertices),
            np.asarray(mesh.faces),
            case_dir,
            target_cells=50,
            max_iter=1,
            max_tet_cells=5_000,
        )
        assert result.success, result.message
        bl = run_poly_bl_transition(
            case_dir,
            num_layers=2,
            growth_ratio=1.2,
            first_thickness=0.05,
            wall_patch_names=["defaultWall"],
            apply_bulk_dual=False,
        )
        assert bl.success, bl.message
        assert bl.n_prism_cells > 0
        strict = audit_strict_volume_topology(case_dir)
        assert strict.valid
        assert strict.n_duplicate_faces == 0
        assert strict.n_nonmanifold_faces == 0
        assert strict.n_nonmanifold_cell_edges == 0
        assert strict.n_open_cell_edges == 0
        assert strict.n_inverted_cells == 0
        assert strict.min_cell_volume is not None and strict.min_cell_volume > 0.0
        hashes.append(_manifest(case_dir))
    assert hashes == [hashes[0]] * 3


def test_native_poly_naca_positive_boundary_layer_is_strict_and_repeatable(
    tmp_path: Path,
) -> None:
    source = Path('tests/benchmarks/naca0012.stl')
    mesh = read_stl(source)
    manifests: list[str] = []
    for repeat in range(3):
        case_dir = tmp_path / f'naca-bl-{repeat}'
        result = _runner(
            np.asarray(mesh.vertices),
            np.asarray(mesh.faces),
            case_dir,
            release_route=True,
            source_path=source,
        )
        assert result.success, result.message
        bl = run_poly_bl_transition(
            case_dir,
            num_layers=1,
            growth_ratio=1.2,
            first_thickness=1.0e-4,
            wall_patch_names=['source_0_naca0012'],
            apply_bulk_dual=False,
        )
        assert bl.success, bl.message
        assert bl.n_prism_cells > 0
        strict = audit_strict_volume_topology(case_dir)
        assert strict.valid
        assert strict.n_duplicate_faces == 0
        assert strict.n_nonmanifold_faces == 0
        assert strict.n_nonmanifold_cell_edges == 0
        assert strict.n_open_cell_edges == 0
        assert strict.n_inverted_cells == 0
        assert strict.min_cell_volume is not None and strict.min_cell_volume > 0.0
        quality = json.loads(
            (case_dir / 'native_bl_quality.json').read_text(),
        )
        line_search = quality['extrusion_line_search']
        assert line_search['accepted']
        assert line_search['negative_post'] == 0
        assert quality['n_new_points'] > 0
        manifests.append(_manifest(case_dir))
    assert manifests == [manifests[0]] * 3


def test_native_poly_complex_positive_boundary_layer_is_strict_and_repeatable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AUTO_TESSELL_P4C_PYTETWILD", "0")
    cases = (
        (
            "sphere",
            Path("tests/benchmarks/sphere_watertight.stl"),
            "source_0_sphere_watertight",
        ),
        (
            "gear",
            Path("tests/stl/04_extreme_gear.stl"),
            "source_0_04_extreme_gear",
        ),
    )
    for name, source, expected_patch in cases:
        mesh = read_stl(source)
        manifests: list[str] = []
        for repeat in range(3):
            case_dir = tmp_path / f"{name}-bl-{repeat}"
            if name == "gear":
                result = _runner(
                    np.asarray(mesh.vertices),
                    np.asarray(mesh.faces),
                    case_dir,
                    release_route=True,
                    source_path=source,
                )
            else:
                result = run_native_poly_harness(
                    np.asarray(mesh.vertices),
                    np.asarray(mesh.faces),
                    case_dir,
                    seed_density=8,
                    max_iter=1,
                    max_tet_cells=15_000,
                    boundary_face_classifier=SourceSurfacePatchClassifier([source]),
                )
            assert result.success, result.message
            bl = run_poly_bl_transition(
                case_dir,
                num_layers=1,
                growth_ratio=1.2,
                first_thickness=1.0e-4,
                wall_patch_names=[expected_patch],
                apply_bulk_dual=False,
            )
            assert bl.success, bl.message
            assert bl.n_prism_cells > 0
            strict = audit_strict_volume_topology(case_dir)
            surface = audit_polymesh_surface(case_dir)
            assert strict.valid, strict.as_dict()
            assert surface.topology_valid
            assert strict.n_duplicate_faces == 0
            assert strict.n_nonmanifold_faces == 0
            assert strict.n_nonmanifold_cell_edges == 0
            assert strict.n_open_cell_edges == 0
            assert strict.n_inverted_cells == 0
            quality = json.loads((case_dir / "native_bl_quality.json").read_text())
            assert quality["extrusion_line_search"]["accepted"] is True
            assert quality["extrusion_line_search"]["negative_post"] == 0
            certificate = certify_native_poly_boundary_authority(
                case_dir,
                source,
                source_patch_ids=("wall",) * len(mesh.faces),
                source_physical_groups=("wall",) * len(mesh.faces),
                expected_boundary_patch=expected_patch,
                feature_preserved=True,
                provenance_complete=True,
            )
            assert certificate.authoritative, certificate.as_dict()
            manifests.append(_manifest(case_dir))
        assert manifests == [manifests[0]] * 3
