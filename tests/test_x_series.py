"""X-series (BETA2723-2728) unit tests."""
from __future__ import annotations

import numpy as np
import pytest


def _unit_cube_surface():
    V = np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
    ], dtype=np.float64)
    F = np.array([
        [0, 2, 1], [0, 3, 2],
        [4, 5, 6], [4, 6, 7],
        [0, 1, 5], [0, 5, 4],
        [2, 3, 7], [2, 7, 6],
        [1, 2, 6], [1, 6, 5],
        [3, 0, 4], [3, 4, 7],
    ], dtype=np.int64)
    return V, F


def test_x1_tet_face_adj_two_tets():
    from core.analyzer.tet_face_adj import build_tet_face_adjacency
    tets = np.array([[0, 1, 2, 3], [4, 1, 2, 3]], dtype=np.int64)
    adj, r = build_tet_face_adjacency(tets)
    # face 0 of tet 0 = vertices (1,2,3) — shared.
    assert adj[0, 0] == 1
    assert adj[1, 0] == 0
    assert r.n_interior_faces == 1
    assert r.n_boundary_faces == 6


def test_x1_tet_face_adj_single():
    from core.analyzer.tet_face_adj import build_tet_face_adjacency
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    adj, r = build_tet_face_adjacency(tets)
    assert (adj == -1).all()
    assert r.n_boundary_faces == 4


def test_x1_tet_face_adj_empty():
    from core.analyzer.tet_face_adj import build_tet_face_adjacency
    adj, r = build_tet_face_adjacency(np.zeros((0, 4), dtype=np.int64))
    assert r.n_tets == 0


def test_x2_surface_volume_unit_cube():
    from core.analyzer.surface_volume import surface_volume_integral
    V, F = _unit_cube_surface()
    r = surface_volume_integral(V, F)
    assert abs(r.surface_area - 6.0) < 1e-9
    assert abs(abs(r.enclosed_volume) - 1.0) < 1e-9
    assert abs(r.fill_ratio - 1.0) < 1e-9


def test_x2_surface_volume_empty():
    from core.analyzer.surface_volume import surface_volume_integral
    r = surface_volume_integral(
        np.zeros((0, 3), dtype=np.float64),
        np.zeros((0, 3), dtype=np.int64),
    )
    assert r.n_triangles == 0
    assert r.surface_area == 0.0


def test_x3_aniso_tensor_regular():
    from core.analyzer.aniso_tensor import tet_aniso_tensor
    pts = np.array(
        [[0, 0, 0], [1, 0, 0],
         [0.5, np.sqrt(3) / 2, 0],
         [0.5, np.sqrt(3) / 6, np.sqrt(2 / 3)]],
        dtype=np.float64,
    )
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    ratio, r = tet_aniso_tensor(pts, tets)
    assert ratio[0] < 1.5


def test_x3_aniso_tensor_thin():
    from core.analyzer.aniso_tensor import tet_aniso_tensor
    pts = np.array(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 0.001]], dtype=np.float64
    )
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    ratio, r = tet_aniso_tensor(pts, tets)
    assert ratio[0] > 5.0
    assert r.n_above_5 == 1


def test_x4_model_descriptor(tmp_path):
    pytest.importorskip("torch")
    import torch
    import torch.nn as nn
    from core.generator.native_ai.model_descriptor import export_descriptor

    p = tmp_path / "m.pt"
    m = nn.Linear(4, 1)
    torch.save({
        "model_state_dict": m.state_dict(),
        "architecture": "tiny",
        "input_dim": 4,
        "final_val_loss": 0.05,
        "n_train": 100,
    }, p)
    desc = export_descriptor(p)
    assert desc is not None
    assert desc.architecture == "tiny"
    assert desc.input_dim == 4
    assert desc.n_parameters == 5  # 4 + 1 bias
    assert abs(desc.val_loss - 0.05) < 1e-9


def test_x4_model_descriptor_missing(tmp_path):
    from core.generator.native_ai.model_descriptor import export_descriptor
    desc = export_descriptor(tmp_path / "missing.pt")
    assert desc is None


def test_x5_bench_summary_load(tmp_path):
    import json
    from scripts.bench_summary import _load_all
    p = tmp_path / "x.json"
    p.write_text(json.dumps([
        {"engine": "a", "grade": "A", "success": True, "elapsed": 1.0},
    ]))
    rows = _load_all([p])
    assert len(rows) == 1
    assert rows[0]["engine"] == "a"


def test_x6_mesh_split_by_region():
    from core.utils.mesh_split import split_by_region
    pts = np.array(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1], [2, 2, 2]],
        dtype=np.float64,
    )
    tets = np.array([[0, 1, 2, 3], [1, 2, 3, 4]], dtype=np.int64)
    rid = np.array([0, 1], dtype=np.int64)
    regs = split_by_region(pts, tets, rid)
    assert len(regs) == 2
    assert regs[0].n_vertices == 4
    assert regs[0].n_tets == 1
    assert regs[1].n_vertices == 4


def test_x6_mesh_split_single_region():
    from core.utils.mesh_split import split_by_region
    pts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64)
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    rid = np.array([5], dtype=np.int64)
    regs = split_by_region(pts, tets, rid)
    assert len(regs) == 1
    assert regs[0].region_id == 5


def test_x6_mesh_split_empty():
    from core.utils.mesh_split import split_by_region
    regs = split_by_region(
        np.zeros((0, 3), dtype=np.float64),
        np.zeros((0, 4), dtype=np.int64),
        np.zeros((0,), dtype=np.int64),
    )
    assert regs == []
