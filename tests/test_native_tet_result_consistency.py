"""Regression checks for the final native-tet result contract."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from core.analyzer.file_reader import load_mesh
from core.generator.native_tet.mesher import generate_native_tet
from core.utils.polymesh_reader import parse_foam_faces, parse_foam_labels, parse_foam_points


CYLINDER = Path(__file__).resolve().parent / "benchmarks" / "cylinder.stl"


def test_result_counts_arrays_and_disk_are_one_final_mesh(tmp_path, monkeypatch) -> None:
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

    assert result.success, result.message
    assert result.tet_points is not None
    assert result.tets is not None
    assert result.n_points == result.tet_points.shape[0]
    assert result.n_cells == result.tets.shape[0]

    poly_dir = case_dir / "constant" / "polyMesh"
    disk_points = np.asarray(parse_foam_points(poly_dir / "points"), dtype=float)
    disk_faces = parse_foam_faces(poly_dir / "faces")
    owner = np.asarray(parse_foam_labels(poly_dir / "owner"), dtype=np.int64)
    neighbour = np.asarray(parse_foam_labels(poly_dir / "neighbour"), dtype=np.int64)
    assert disk_points.shape == result.tet_points.shape
    assert np.allclose(disk_points, result.tet_points, rtol=0.0, atol=1e-8)
    assert int(max(owner.max(), neighbour.max())) + 1 == result.n_cells
    assert len(disk_faces) == owner.size
    assert neighbour.size <= owner.size
