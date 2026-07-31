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


def test_cylinder_overlap_candidate_rolls_back_deterministically(
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
        assert audit.n_internal_faces == 2172
        assert audit.n_same_side_internal_faces == 0
        assert audit.n_ambiguous_internal_faces == 0
        assert audit.n_duplicate_tets == 0
        assert audit.n_nonmanifold_faces == 0
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
        assert result.n_cells == 1140
        strict = result.debug_info["strict_source_topology"]
        assert strict["valid"] is True
        transaction = result.debug_info["smooth_then_drop_sidedness_transaction"]
        assert transaction == {
            "accepted": False,
            "before_same_side_internal_faces": 0,
            "candidate_same_side_internal_faces": 166,
            "before_ambiguous_internal_faces": 412,
            "candidate_ambiguous_internal_faces": 4,
            "exact_rollback": True,
            "n_moved": 254,
            "n_dropped": 0,
        }
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
        "453039a0fb6341d8d05d6985bf88f5188a0e86d9214ee0d7979a632167348f04",
        "6f50e4cab807dc21c4d4433550bb410fc97af72084f048e8e6023eb1453a3426",
    )


def test_cube_cvt3d_overlap_rolls_back_before_later_mutation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """A CVT quality gain must not hide a new internal-face overlap.

    The frozen cube reaches the first persistent post-JJ3 transition with
    five degenerate tets and no definite same-side face.  CVT removes those
    degenerates, but creates four definite overlaps.  The only truthful
    result is the exact pre-CVT mesh and an early refusal; later passes must
    not get an opportunity to mutate the returned arrays.
    """
    monkeypatch.setenv("AUTO_TESSELL_P4C_PYTETWILD", "0")
    monkeypatch.setenv("AUTO_TESSELL_CONVEX_EXTRUSION_RESCUE", "0")
    mesh = load_mesh(CUBE)
    case_dir = tmp_path / "cube"
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

    assert result.success is False
    assert result.message == ("native_tet CVT candidate increases strict internal-face debt")
    assert result.n_points == 300
    assert result.n_cells == 1286
    assert not (case_dir / "constant" / "polyMesh").exists()
    audit = audit_tet_boundary(result.tet_points, result.tets)
    assert audit.n_same_side_internal_faces == 0
    assert audit.n_ambiguous_internal_faces == 20
    assert audit.n_degenerate_tets == 5
    assert audit.n_inverted_tets == 34
    transaction = result.debug_info["cvt3d_sidedness_transaction"]
    assert transaction == {
        "accepted": False,
        "before_same_side_internal_faces": 0,
        "candidate_same_side_internal_faces": 4,
        "before_ambiguous_internal_faces": 20,
        "candidate_ambiguous_internal_faces": 0,
        "exact_rollback": True,
        "before_degenerate_tets": 5,
        "candidate_degenerate_tets": 0,
        "n_iter": 3,
        "n_moved": 411,
    }


@pytest.mark.parametrize(
    (
        "fixture",
        "expected_points",
        "expected_cells",
        "expected_faces",
        "expected_same_side",
        "expected_duplicates",
        "expected_nonmanifold",
        "transaction_accepted",
        "transaction_before_same",
        "transaction_candidate_same",
        "min_mean_q",
    ),
    ((SPHERE, 735, 2164, 1280, 108, 0, 0, True, 120, 120, 0.2573),),
)
def test_boundary_lock_refuses_cube_and_sphere_internal_overlap(
    fixture: Path,
    expected_points: int,
    expected_cells: int,
    expected_faces: int,
    expected_same_side: int,
    expected_duplicates: int,
    expected_nonmanifold: int,
    transaction_accepted: bool,
    transaction_before_same: int,
    transaction_candidate_same: int,
    min_mean_q: float,
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Source-preserving but overlapping meshes must not reach disk."""
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

    assert result.success is False
    assert not (tmp_path / fixture.stem / "constant" / "polyMesh").exists()
    assert result.n_points == expected_points
    assert result.n_cells == expected_cells
    audit = audit_tet_boundary(result.tet_points, result.tets)
    assert audit.valid is False
    assert audit.n_same_side_internal_faces == expected_same_side
    assert audit.n_ambiguous_internal_faces == 0
    assert audit.n_duplicate_tets == expected_duplicates
    assert audit.n_nonmanifold_faces == expected_nonmanifold
    assert audit.n_inverted_tets == 0
    assert audit.n_degenerate_tets == 0
    report = result.debug_info["strict_source_component_bijection"]
    assert report["source_faces_preserved"] is True
    assert report["n_owned_candidate_faces"] == expected_faces
    assert report["n_unowned_candidate_faces"] == 0
    assert report["n_area_mismatch_patches"] == 0
    assert report["n_feature_boundary_mismatches"] == 0
    strict = result.debug_info["strict_source_topology"]
    assert strict["valid"] is False
    assert strict["polymesh_artifacts_removed"] is True
    transaction = result.debug_info["smooth_then_drop_sidedness_transaction"]
    assert transaction["accepted"] is transaction_accepted
    assert transaction["before_same_side_internal_faces"] == (transaction_before_same)
    assert transaction["candidate_same_side_internal_faces"] == (transaction_candidate_same)
    assert snapshot(result.tet_points, result.tets).mean_q >= min_mean_q
    hausdorff = hausdorff_vs_input(
        np.asarray(mesh.vertices, dtype=np.float64),
        np.asarray(mesh.faces, dtype=np.int64),
        result.tet_points,
        result.tets,
    )
    bbox_diag = float(np.linalg.norm(np.ptp(mesh.vertices, axis=0)))
    assert hausdorff.h_symmetric / bbox_diag <= 1e-12
