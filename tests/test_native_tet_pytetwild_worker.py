"""pytetwild must not share a process with the pipeline."""

from __future__ import annotations

import importlib.util

import pytest
import trimesh

from core.generator.native_tet.pytetwild_worker import tetrahedralize


pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("pytetwild") is None,
    reason="optional pytetwild extension unavailable",
)


def test_pytetwild_worker_returns_tets_without_host_teardown() -> None:
    cube = trimesh.creation.box()

    points, tets = tetrahedralize(
        cube.vertices,
        cube.faces,
        edge_length_fac=0.2,
        epsilon=1.0e-3,
        simplify=True,
        stop_energy=10.0,
        num_threads=1,
        num_opt_iter=8,
    )

    assert points.ndim == 2 and points.shape[1] == 3
    assert tets.ndim == 2 and tets.shape[1] == 4
    assert len(tets) > 0
