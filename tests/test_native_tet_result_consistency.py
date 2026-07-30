"""Regression checks for the final native-tet result contract."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from core.analyzer.file_reader import load_mesh
from core.generator.native_tet.mesher import generate_native_tet
from core.generator.native_tet.rescue_gate import audit_tet_boundary
from core.generator.native_tet.writer_topology import audit_written_polymesh

CYLINDER = Path(__file__).resolve().parent / "benchmarks" / "cylinder.stl"


def test_exact_duplicate_groups_restore_strict_native_tet_topology(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AUTO_TESSELL_P4C_PYTETWILD", "0")
    monkeypatch.setenv("AUTO_TESSELL_CONVEX_EXTRUSION_RESCUE", "0")
    mesh = load_mesh(CYLINDER)
    case_dir = tmp_path / "cylinder"
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

    assert result.success
    assert result.n_cells == 1495
    repair = result.debug_info["strict_topology_duplicate_group_repair"]
    assert repair == {
        "applied": True,
        "n_duplicate_groups": 2,
        "n_removed_tets": 4,
        "reason": "exact_duplicate_groups_removed_with_boundary_preserved",
        "boundary_preserved": True,
        "before_nonmanifold_faces": 4,
        "after_nonmanifold_faces": 0,
    }
    assert "native_tet_strict_topology_duplicate_groups_removed: 4" in (
        result.warnings or []
    )

    tet_audit = audit_tet_boundary(result.tet_points, result.tets)
    assert tet_audit.n_nonmanifold_faces == 0
    assert tet_audit.n_duplicate_tets == 0
    assert tet_audit.n_degenerate_tets == 0
    assert tet_audit.n_open_edges == 0
    assert tet_audit.n_nonmanifold_edges == 0

    written = audit_written_polymesh(case_dir / "constant" / "polyMesh")
    assert written.n_cells == result.n_cells
    assert all(cell.is_tetrahedron_encoding for cell in written.cells)
