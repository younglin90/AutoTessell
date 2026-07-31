"""Focused source/validity admission regression for native-tet SSS relocation."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from core.analyzer.readers import read_stl
from core.generator.native_tet.mesher import generate_native_tet

_SPHERE = Path(__file__).resolve().parent / "benchmarks" / "sphere.stl"


def test_sphere_sss_relocation_rejects_source_losing_candidate(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("AUTO_TESSELL_TET_SAME_SIDE_RETRIANGULATION", "1")
    mesh = read_stl(_SPHERE)
    case_dir = tmp_path / "sphere"

    result = generate_native_tet(
        np.ascontiguousarray(mesh.vertices, dtype=np.float64),
        np.ascontiguousarray(mesh.faces, dtype=np.int64),
        case_dir,
        target_cells=2000,
        enable_bsp_insertion=False,
        enable_edge_recovery=False,
        enable_phase_b=False,
        enable_phase_c=False,
    )

    transaction = result.debug_info["sss_relocation_source_transaction"]
    assert transaction == {
        "accepted": False,
        "before_component_bijective": True,
        "candidate_component_bijective": False,
        "before_source_faces_preserved": True,
        "candidate_source_faces_preserved": False,
        "before_unowned_candidate_faces": 0,
        "candidate_unowned_candidate_faces": 1280,
        "before_boundary_valid": False,
        "candidate_boundary_valid": False,
        "before_inverted_tets": 350,
        "candidate_inverted_tets": 352,
        "before_same_side_internal_faces": 116,
        "candidate_same_side_internal_faces": 108,
        "before_ambiguous_internal_faces": 0,
        "candidate_ambiguous_internal_faces": 0,
        "exact_rollback": True,
    }
    assert result.success is True
    assert (case_dir / "constant" / "polyMesh").exists()
    source = result.debug_info["strict_source_component_bijection"]
    assert source["bijective"] is True
    assert source["source_faces_preserved"] is True
    assert source["n_missing_source_vertices"] == 0
    assert source["n_missing_source_faces"] == 0
    assert source["n_unowned_candidate_faces"] == 0
    strict = result.debug_info["strict_source_topology"]
    assert strict["valid"] is True
    assert strict["n_inverted_tets"] == 0
    assert strict["n_same_side_internal_faces"] == 0
    assert result.debug_info["same_side_retriangulation_transaction"] == {
        "accepted": True,
        "reason": "delaunay_connectivity_strictly_reduced_same_side",
        "before_n_cells": 2166,
        "candidate_n_cells": 2227,
        "before_same_side_internal_faces": 108,
        "candidate_same_side_internal_faces": 0,
        "before_ambiguous_internal_faces": 0,
        "candidate_ambiguous_internal_faces": 0,
        "before_inverted_tets": 0,
        "candidate_inverted_tets": 0,
        "source_component_bijective": True,
        "source_faces_preserved": True,
        "candidate_unowned_faces": 0,
        "exact_rollback": False,
    }
