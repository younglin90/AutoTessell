"""Regression checks for the final native-tet result contract."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from core.analyzer.file_reader import load_mesh
from core.generator.native_tet.hausdorff import hausdorff_vs_input
from core.generator.native_tet.mesher import generate_native_tet
from core.generator.native_tet.quality import snapshot
from core.generator.native_tet.rescue_gate import audit_tet_boundary
from core.generator.native_tet.source_facet_provenance import (
    audit_source_facet_provenance_python,
)
from core.utils.polymesh_reader import (
    parse_foam_faces,
    parse_foam_labels,
    parse_foam_points,
)

CYLINDER = Path(__file__).resolve().parent / "benchmarks" / "cylinder.stl"
CUBE = Path(__file__).resolve().parent / "benchmarks" / "cube.stl"
SPHERE = Path(__file__).resolve().parent / "benchmarks" / "sphere.stl"


def _assert_disk_source_facets(mesh: Any, case_dir: Path) -> None:
    poly_mesh = case_dir / "constant" / "polyMesh"
    disk_points = np.asarray(parse_foam_points(poly_mesh / "points"), dtype=np.float64)
    disk_faces = np.asarray(parse_foam_faces(poly_mesh / "faces"), dtype=np.int64)
    n_internal = len(parse_foam_labels(poly_mesh / "neighbour"))
    report = audit_source_facet_provenance_python(
        np.asarray(mesh.vertices, dtype=np.float64),
        np.asarray(mesh.faces, dtype=np.int64),
        disk_points,
        disk_faces[n_internal:],
    )
    assert report["source_faces_preserved"] is True
    assert report["n_unowned_candidate_faces"] == 0


def test_cylinder_boundary_is_locked_and_written_deterministically(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AUTO_TESSELL_P4C_PYTETWILD", "0")
    monkeypatch.setenv("AUTO_TESSELL_CONVEX_EXTRUSION_RESCUE", "0")
    mesh = load_mesh(CYLINDER)
    signatures: list[tuple[str, str]] = []
    reports: list[dict[str, int | bool]] = []
    for repeat in range(3):
        case_dir = tmp_path / f"cylinder_{repeat}"
        result = generate_native_tet(
            np.asarray(mesh.vertices, dtype=np.float64),
            np.asarray(mesh.faces, dtype=np.int64),
            case_dir,
            target_cells=2000,
            enable_bsp_insertion=False,
            enable_edge_recovery=False,
            enable_phase_b=False,
            enable_phase_c=False,
        )

        assert result.success, result.message
        assert (case_dir / "constant" / "polyMesh").exists()
        _assert_disk_source_facets(mesh, case_dir)
        audit = audit_tet_boundary(result.tet_points, result.tets)
        assert audit.valid
        assert audit.n_inverted_tets == 0
        assert audit.n_degenerate_tets == 0
        hausdorff = hausdorff_vs_input(
            np.asarray(mesh.vertices, dtype=np.float64),
            np.asarray(mesh.faces, dtype=np.int64),
            result.tet_points,
            result.tets,
        )
        bbox_diag = float(np.linalg.norm(np.ptp(mesh.vertices, axis=0)))
        assert hausdorff.h_symmetric / bbox_diag <= 1e-12
        # Cycle-38 accepted baseline was 0.201; fixed predeclared tolerance is 1e-3.
        assert snapshot(result.tet_points, result.tets).mean_q >= 0.200
        report = result.debug_info["strict_source_component_bijection"]
        assert report["bijective"] is True
        assert report["n_candidate_boundary_faces"] == 216
        assert report["n_owned_candidate_faces"] == 216
        assert report["n_unowned_candidate_faces"] == 0
        assert report["n_area_mismatch_patches"] == 0
        assert report["n_feature_boundary_mismatches"] == 0
        assert report["n_overlap_pairs"] == 0
        assert report["source_faces_preserved"] is True
        assert result.n_points == 353
        assert result.n_cells == 1489
        reports.append(report)
        signatures.append(
            (
                hashlib.sha256(np.ascontiguousarray(result.tet_points)).hexdigest(),
                hashlib.sha256(np.ascontiguousarray(result.tets)).hexdigest(),
            )
        )

    assert reports[1:] == reports[:-1]
    assert signatures[1:] == signatures[:-1]
    assert signatures[0] == (
        "85ad5dd102c51a66b668f4b6251e934665ec5b9fcb54fdec570b2309f83f7824",
        "6093f8e12ae9a1584d75b63af05a28bd979bb44f0a7ad914705663e6828ca210",
    )


@pytest.mark.parametrize(
    ("fixture", "expected_points", "expected_cells", "expected_faces", "min_mean_q"),
    (
        (CUBE, 300, 1299, 318, 0.3563),
        (SPHERE, 735, 2164, 1280, 0.2573),
    ),
)
def test_boundary_lock_preserves_cube_and_sphere_contracts(
    fixture: Path,
    expected_points: int,
    expected_cells: int,
    expected_faces: int,
    min_mean_q: float,
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Current-boundary locking must not regress representative fixtures."""
    monkeypatch.setenv("AUTO_TESSELL_P4C_PYTETWILD", "0")
    monkeypatch.setenv("AUTO_TESSELL_CONVEX_EXTRUSION_RESCUE", "0")
    mesh = load_mesh(fixture)
    result = generate_native_tet(
        np.asarray(mesh.vertices, dtype=np.float64),
        np.asarray(mesh.faces, dtype=np.int64),
        tmp_path / fixture.stem,
        target_cells=2000,
        enable_bsp_insertion=False,
        enable_edge_recovery=False,
        enable_phase_b=False,
        enable_phase_c=False,
    )

    assert result.success, result.message
    _assert_disk_source_facets(mesh, tmp_path / fixture.stem)
    assert result.n_points == expected_points
    assert result.n_cells == expected_cells
    audit = audit_tet_boundary(result.tet_points, result.tets)
    assert audit.valid
    assert audit.n_inverted_tets == 0
    assert audit.n_degenerate_tets == 0
    report = result.debug_info["strict_source_component_bijection"]
    assert report["source_faces_preserved"] is True
    assert report["n_owned_candidate_faces"] == expected_faces
    assert report["n_unowned_candidate_faces"] == 0
    assert report["n_area_mismatch_patches"] == 0
    assert report["n_feature_boundary_mismatches"] == 0
    assert snapshot(result.tet_points, result.tets).mean_q >= min_mean_q
    hausdorff = hausdorff_vs_input(
        np.asarray(mesh.vertices, dtype=np.float64),
        np.asarray(mesh.faces, dtype=np.int64),
        result.tet_points,
        result.tets,
    )
    bbox_diag = float(np.linalg.norm(np.ptp(mesh.vertices, axis=0)))
    assert hausdorff.h_symmetric / bbox_diag <= 1e-12
