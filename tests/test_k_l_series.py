"""L7 / beta2646 — K + L series 통합 회귀.

K1 Nastran / K2 surface_diag / K3 augmentation / K4 progress / K5 hist /
K6 plugin / L1 Abaqus / L3 feature edges 모두 single suite.
"""
from __future__ import annotations

import sys
import tempfile
import types
from pathlib import Path

import numpy as np
import pytest


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


@pytest.fixture
def fake_cube_pm(monkeypatch):
    fake_pm = {
        "points": [[0,0,0],[1,0,0],[1,1,0],[0,1,0],[0,0,1],[1,0,1],[1,1,1],[0,1,1]],
        "faces": [[0,1,2,3],[4,5,6,7],[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7]],
        "owner": [0,0,0,0,0,0],
        "neighbour": [],
        "boundary": [{"name":"walls","type":"wall","nFaces":6,"startFace":0}],
    }
    fake_mod = types.ModuleType("core.utils.poly_mesh_reader")
    fake_mod.read_poly_mesh = lambda _p: fake_pm
    monkeypatch.setitem(sys.modules, "core.utils.poly_mesh_reader", fake_mod)


# K1.
def test_k1_nastran_writer(fake_cube_pm):
    from core.utils.nastran_writer import write_nastran_bdf
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "x.bdf"; (Path(td) / "pm").mkdir()
        r = write_nastran_bdf(str(Path(td) / "pm"), str(out))
        assert r.success and r.n_grids == 8


# K2.
def test_k2_surface_diag():
    from core.analyzer.surface_diag import diagnose_surface
    V = np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1]], dtype=np.float64)
    F = np.array([[0,1,2],[0,1,3],[1,2,3],[0,2,3]], dtype=np.int64)
    r = diagnose_surface(V, F)
    assert r.n_faces == 4 and r.n_inconsistent_normals == 0


# K3.
def test_k3_rotation_augment():
    from core.generator.native_ai.training_data import augment_features_with_rotations
    coords = np.zeros((1, 12), dtype=np.float64)
    ctx = np.zeros((1, 8), dtype=np.float64)
    q = np.array([0.5], dtype=np.float64)
    c2, ctx2, q2 = augment_features_with_rotations(coords, ctx, q, n_rotations=3)
    assert c2.shape == (3, 12) and q2.shape == (3,)


# K4.
def test_k4_progress_tracker():
    from core.utils.progress import ProgressTracker, collect_callback
    events: list = []
    p = ProgressTracker(total=5, callback=collect_callback(events))
    for _ in range(5):
        p.advance("step")
    assert len(events) == 5
    assert events[-1].current == 5


# K6.
def test_k6_plugin_discovery():
    from core.generator.plugin_loader import discover_plugins, example_plugin_template
    with tempfile.TemporaryDirectory() as td:
        pdir = Path(td)
        (pdir / "myplug.py").write_text(example_plugin_template())
        plugins = discover_plugins(pdir)
        assert len(plugins) == 1
        assert plugins[0].name == "my_custom_tier"


# L1.
def test_l1_abaqus_writer(fake_cube_pm):
    from core.utils.abaqus_writer import write_abaqus_inp
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "x.inp"; (Path(td) / "pm").mkdir()
        r = write_abaqus_inp(str(Path(td) / "pm"), str(out))
        assert r.success and r.n_nodes == 8


# L3.
def test_l3_feature_edges():
    from core.analyzer.feature_edges import extract_feature_edges
    V = np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1]], dtype=np.float64)
    F = np.array([[0,1,2],[0,1,3],[1,2,3],[0,2,3]], dtype=np.int64)
    r = extract_feature_edges(V, F, return_edges=True)
    assert r.n_feature_edges == 6
    assert r.n_corner_vertices == 4


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
