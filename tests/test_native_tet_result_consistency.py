"""Regression checks for the final native-tet result contract."""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

from core.analyzer.file_reader import load_mesh
from core.generator.native_tet.mesher import generate_native_tet
from core.generator.native_tet.rescue_gate import audit_tet_boundary

CYLINDER = Path(__file__).resolve().parent / "benchmarks" / "cylinder.stl"


def test_cylinder_off_surface_boundary_fails_before_writer_deterministically(
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

        assert not result.success
        assert result.message == "native_tet source-aware strict topology is invalid"
        assert not (case_dir / "constant" / "polyMesh").exists()
        assert audit_tet_boundary(result.tet_points, result.tets).valid
        report = result.debug_info["strict_source_component_bijection"]
        assert report["bijective"] is True
        assert report["n_candidate_boundary_faces"] == 216
        assert report["n_owned_candidate_faces"] == 119
        assert report["n_unowned_candidate_faces"] == 97
        assert report["n_area_mismatch_patches"] == 2
        assert report["n_feature_boundary_mismatches"] == 2
        assert report["source_faces_preserved"] is False
        reports.append(report)
        signatures.append(
            (
                hashlib.sha256(np.ascontiguousarray(result.tet_points)).hexdigest(),
                hashlib.sha256(np.ascontiguousarray(result.tets)).hexdigest(),
            )
        )

    assert reports[1:] == reports[:-1]
    assert signatures[1:] == signatures[:-1]
