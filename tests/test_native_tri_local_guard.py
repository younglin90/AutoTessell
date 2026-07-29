"""Equivalence tests for the opt-in native-tri local guard experiment."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from core.analyzer.readers import read_stl
from core.preprocessor.native_tri import OperatorTransaction


def _run(
    flag: str | None,
    *,
    set_flag,
) -> tuple[tuple[object, ...], np.ndarray, np.ndarray]:
    cube_path = Path(__file__).parent / "benchmarks" / "cube.stl"
    mesh = read_stl(cube_path)
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    lengths = np.concatenate(
        [
            np.linalg.norm(vertices[faces[:, index]] - vertices[faces[:, (index + 1) % 3]], axis=1)
            for index in range(3)
        ]
    )
    target = float(np.median(lengths[lengths > 0.0]))
    if flag is None:
        set_flag.delenv("AUTO_TESSELL_TRI_LOCAL_GUARDS1", raising=False)
    else:
        set_flag.setenv("AUTO_TESSELL_TRI_LOCAL_GUARDS1", flag)
    tx = OperatorTransaction(vertices, faces, target_edge_length=target)
    reports = tx.run_one_round(target_edge_length=target, smooth=False)
    return reports, tx.state.vertices.copy(), tx.state.faces.copy()


def test_local_guard_matches_default_cube_result(monkeypatch) -> None:
    off_reports, off_vertices, off_faces = _run(None, set_flag=monkeypatch)
    on_reports, on_vertices, on_faces = _run("1", set_flag=monkeypatch)
    assert [(report.accepted, report.reason) for report in on_reports] == [
        (report.accepted, report.reason) for report in off_reports
    ]
    np.testing.assert_array_equal(on_vertices, off_vertices)
    np.testing.assert_array_equal(on_faces, off_faces)
