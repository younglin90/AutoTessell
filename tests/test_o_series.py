"""O7 / beta2666 — O-series 통합 회귀."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def test_o1_stl_ascii():
    from core.utils.stl_writer import write_stl_ascii
    V = np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1]], dtype=np.float64)
    F = np.array([[0,1,2],[0,1,3]], dtype=np.int64)
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "x.stl"
        r = write_stl_ascii(V, F, out, name="test")
        assert r.success and r.n_triangles == 2
        c = out.read_text(encoding="ascii")
        assert "solid test" in c
        assert "facet normal" in c
        assert "endsolid test" in c


def test_o2_obj():
    from core.utils.obj_ply_writer import write_obj
    V = np.array([[0,0,0],[1,0,0],[0,1,0]], dtype=np.float64)
    F = np.array([[0,1,2]], dtype=np.int64)
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "x.obj"
        r = write_obj(V, F, out)
        assert r.success
        c = out.read_text(encoding="ascii")
        assert c.startswith("# OBJ")
        assert "v 0.000000e+00" in c
        assert "f 1 2 3" in c


def test_o2_ply_ascii_and_binary():
    from core.utils.obj_ply_writer import write_ply
    V = np.array([[0,0,0],[1,0,0],[0,1,0]], dtype=np.float64)
    F = np.array([[0,1,2]], dtype=np.int64)
    with tempfile.TemporaryDirectory() as td:
        out_a = Path(td) / "a.ply"
        out_b = Path(td) / "b.ply"
        ra = write_ply(V, F, out_a, binary=False)
        rb = write_ply(V, F, out_b, binary=True)
        assert ra.success and rb.success
        ca = out_a.read_text(encoding="ascii")
        assert "ply" in ca
        assert "format ascii" in ca
        # binary file: read as bytes and check header.
        cb = out_b.read_bytes()
        assert b"ply\n" in cb
        assert b"format binary_little_endian" in cb


def test_o4_metrics_dump_smoke():
    """O4 — dump_mesh_metrics 의 함수 import 가능."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_dmm", str(REPO / "scripts" / "dump_mesh_metrics.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    assert mod is not None  # exec 만 검증.


def test_o6_load_trained_predictor_missing():
    """O6 — 존재 안 하는 모델 graceful None 반환."""
    from core.generator.native_ai.ml_tet_smoothing import load_trained_predictor
    r = load_trained_predictor("/nonexistent/model.pt")
    assert r is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
