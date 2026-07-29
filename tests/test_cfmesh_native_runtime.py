"""Vendored cfMesh runtime smoke tests."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from core.evaluator.native_checker import NativeMeshChecker


_REPO = Path(__file__).resolve().parents[1]
_BUILD = _REPO / "auto_tessell_core" / "build"
_CUBE = _REPO / "tests" / "benchmarks" / "cube.stl"


def test_vendored_cfmesh_cartesian_runtime_cube(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Vendored executable receives a valid OpenFOAM global runtime root."""
    if not _CUBE.exists():
        pytest.skip("cube STL unavailable")
    if str(_BUILD) not in sys.path:
        sys.path.insert(0, str(_BUILD))
    cfm = pytest.importorskip("cfmesh_native")
    # A stale OpenFOAM shell setting must not reintroduce the pre-startup
    # segfault; the wrapper falls through to a validated runtime root.
    monkeypatch.setenv("WM_PROJECT_DIR", str(tmp_path / "missing-openfoam"))
    result = cfm.cartesian_mesh(
        str(_CUBE), str(tmp_path),
        max_cell_size=0.2,
        min_cell_size=0.2,
        boundary_cell_size=0.0,
        bl_n_layers=0,
        bl_thickness_ratio=1.2,
        bl_max_first_layer=0.0,
        feature_angle_deg=30.0,
        keep_cells_intersecting_boundary=True,
    )
    assert result["success"], result["log"][-800:]
    checked = NativeMeshChecker().run(tmp_path)
    assert checked.cells > 0
    assert checked.negative_volumes == 0
    assert checked.mesh_ok


def test_vendored_cfmesh_boundary_layers_change_mesh(tmp_path: Path) -> None:
    """Tier15 owns its BL stack; post native_bl must not duplicate it."""
    if str(_BUILD) not in sys.path:
        sys.path.insert(0, str(_BUILD))
    cfm = pytest.importorskip("cfmesh_native")
    common = dict(
        max_cell_size=0.05,
        min_cell_size=0.0,
        boundary_cell_size=0.0,
        bl_thickness_ratio=1.2,
        bl_max_first_layer=0.001,
        feature_angle_deg=30.0,
        keep_cells_intersecting_boundary=True,
    )
    no_layers = tmp_path / "no_layers"
    with_layers = tmp_path / "with_layers"
    assert cfm.cartesian_mesh(
        str(_CUBE), str(no_layers), bl_n_layers=0, **common
    )["success"]
    assert cfm.cartesian_mesh(
        str(_CUBE), str(with_layers), bl_n_layers=2, **common
    )["success"]
    base = NativeMeshChecker().run(no_layers)
    layered = NativeMeshChecker().run(with_layers)
    assert layered.cells > base.cells
    assert layered.negative_volumes == 0
    assert layered.mesh_ok
