"""Read-only TET-FLOW-3 ladder diagnostics."""

from __future__ import annotations

import numpy as np

from core.generator.native_tet.flow3 import run_flow3_diagnostic
from core.generator.native_tet.near_wall import boundary_face_keys


def test_flow3_diagnostic_does_not_mutate_input_on_single_tet() -> None:
    points = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    before = tets.copy()
    out, report = run_flow3_diagnostic(points, tets, epsilons=(0.4,), rounds_per_rung=1)
    assert np.array_equal(tets, before)
    assert np.array_equal(out, before)
    assert report["input_unchanged"] is True
    assert report["boundary_preserved"] is True


def test_flow3_diagnostic_boundary_is_transactional_on_fsl_mesh() -> None:
    with np.load("harness/_fsl4_mesh.npz", allow_pickle=False) as data:
        points = np.asarray(data["pts"], dtype=np.float64)
        tets = np.asarray(data["tets"], dtype=np.int64)
    before_faces = boundary_face_keys(tets)
    before = tets.copy()
    out, report = run_flow3_diagnostic(
        points, tets, epsilons=(0.4,), rounds_per_rung=1, max_bad_tets=8
    )
    assert np.array_equal(tets, before)
    assert report["input_unchanged"] is True
    assert report["boundary_preserved"] is True
    assert boundary_face_keys(out) == before_faces
    assert report["surface_vertices_moved"] is False
