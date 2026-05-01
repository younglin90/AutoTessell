"""BB-series (BETA2751-2756) unit tests."""
from __future__ import annotations

import numpy as np
import pytest


def test_bb1_circumsphere_regular_tet():
    from core.analyzer.tet_circumsphere import tet_circumspheres
    pts = np.array(
        [[0, 0, 0], [1, 0, 0],
         [0.5, np.sqrt(3) / 2, 0],
         [0.5, np.sqrt(3) / 6, np.sqrt(2 / 3)]],
        dtype=np.float64,
    )
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    C, R, r = tet_circumspheres(pts, tets)
    assert abs(R[0] - np.sqrt(3 / 8)) < 1e-3
    assert r.n_degenerate == 0


def test_bb1_circumsphere_unit_tet():
    from core.analyzer.tet_circumsphere import tet_circumspheres
    pts = np.array(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64
    )
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    C, R, r = tet_circumspheres(pts, tets)
    # circumcenter of (0,0,0)(1,0,0)(0,1,0)(0,0,1) is (0.5, 0.5, 0.5), R = sqrt(3)/2.
    assert np.allclose(C[0], [0.5, 0.5, 0.5], atol=1e-9)
    assert abs(R[0] - np.sqrt(3) / 2) < 1e-9


def test_bb1_circumsphere_empty():
    from core.analyzer.tet_circumsphere import tet_circumspheres
    C, R, r = tet_circumspheres(
        np.zeros((0, 3), dtype=np.float64),
        np.zeros((0, 4), dtype=np.int64),
    )
    assert r.n_tets == 0


def test_bb2_face_area_var_uniform():
    from core.analyzer.face_area_var import face_area_variance
    V = np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
    ], dtype=np.float64)
    F = np.array([
        [0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7],
        [0, 1, 5], [0, 5, 4], [2, 3, 7], [2, 7, 6],
        [1, 2, 6], [1, 6, 5], [3, 0, 4], [3, 4, 7],
    ], dtype=np.int64)
    r = face_area_variance(V, F)
    assert abs(r.area_mean - 0.5) < 1e-9
    assert r.cv < 0.01


def test_bb2_face_area_var_empty():
    from core.analyzer.face_area_var import face_area_variance
    r = face_area_variance(
        np.zeros((0, 3), dtype=np.float64),
        np.zeros((0, 3), dtype=np.int64),
    )
    assert r.n_triangles == 0


def test_bb3_train_resume_roundtrip(tmp_path):
    pytest.importorskip("torch")
    import torch
    import torch.nn as nn
    from core.generator.native_ai.train_resume import (
        save_checkpoint, load_checkpoint,
    )

    class M(nn.Module):
        def __init__(self):
            super().__init__()
            self.fc = nn.Linear(4, 1)

        def forward(self, x):
            return self.fc(x)

    m = M()
    opt = torch.optim.Adam(m.parameters(), lr=0.001)
    p = tmp_path / "ckpt.pt"
    ok = save_checkpoint(p, m, opt, epoch=7, best_val_loss=0.123)
    assert ok

    m2 = M()
    opt2 = torch.optim.Adam(m2.parameters(), lr=0.001)
    info = load_checkpoint(p, m2, opt2)
    assert info.found
    assert info.epoch == 7
    assert abs(info.best_val_loss - 0.123) < 1e-9
    for pa, pb in zip(m.parameters(), m2.parameters()):
        assert torch.allclose(pa, pb)


def test_bb3_train_resume_missing(tmp_path):
    pytest.importorskip("torch")
    import torch
    import torch.nn as nn
    from core.generator.native_ai.train_resume import load_checkpoint

    m = nn.Linear(4, 1)
    opt = torch.optim.Adam(m.parameters())
    info = load_checkpoint(tmp_path / "missing.pt", m, opt)
    assert not info.found


def test_bb4_bench_parallel_summary(tmp_path):
    import json
    from scripts.bench_parallel import _summarize_one
    p = tmp_path / "x.json"
    p.write_text(json.dumps([
        {"engine": "x", "grade": "A", "success": True},
        {"engine": "y", "grade": "B", "success": False},
    ]))
    r = _summarize_one(p)
    assert r["n_total"] == 2
    assert r["n_ok"] == 1
    assert r["n_a"] == 1


def test_bb4_bench_parallel_missing(tmp_path):
    from scripts.bench_parallel import _summarize_one
    r = _summarize_one(tmp_path / "missing.json")
    assert "error" in r


def test_bb5_stl_validate_binary(tmp_path):
    import struct
    from core.analyzer.stl_validate import validate_stl
    p = tmp_path / "test.stl"
    with p.open("wb") as f:
        f.write(b"\0" * 80)
        f.write(struct.pack("<I", 2))
        f.write(b"\0" * 100)
    r = validate_stl(p)
    assert r.is_binary
    assert r.estimated_n_faces == 2
    assert not r.issues


def test_bb5_stl_validate_ascii(tmp_path):
    from core.analyzer.stl_validate import validate_stl
    p = tmp_path / "a.stl"
    p.write_text("solid foo\n" + "facet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 1 0 0\nvertex 0 1 0\nendloop\nendfacet\n" * 5 + "endsolid foo\n")
    r = validate_stl(p)
    assert r.is_ascii
    assert r.estimated_n_faces == 5


def test_bb5_stl_validate_missing(tmp_path):
    from core.analyzer.stl_validate import validate_stl
    r = validate_stl(tmp_path / "nope.stl")
    assert not r.exists
    assert r.issues


def test_bb6_hex_inverted_detect():
    from core.evaluator.hex_inverted import detect_inverted_hexes
    pts = np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
    ], dtype=np.float64)
    hexes = np.array([
        [0, 1, 2, 3, 4, 5, 6, 7],
        [0, 1, 2, 3, 5, 4, 7, 6],   # inverted
    ], dtype=np.int64)
    r = detect_inverted_hexes(pts, hexes)
    assert r.n_inverted == 1
    assert r.inverted_indices == [1]


def test_bb6_hex_inverted_empty():
    from core.evaluator.hex_inverted import detect_inverted_hexes
    r = detect_inverted_hexes(
        np.zeros((0, 3), dtype=np.float64),
        np.zeros((0, 8), dtype=np.int64),
    )
    assert r.n_hexes == 0
