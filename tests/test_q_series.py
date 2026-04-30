"""Q7 / beta2680 — Q-series 통합 회귀."""
from __future__ import annotations

import struct
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def test_q1_stl_binary():
    """Q1 — STL binary header + tri count."""
    from core.utils.stl_writer import write_stl_binary
    V = np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1]], dtype=np.float64)
    F = np.array([[0,1,2],[0,1,3]], dtype=np.int64)
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "x.stl"
        r = write_stl_binary(V, F, out)
        assert r.success and r.n_triangles == 2
        with out.open("rb") as f:
            f.read(80)
            n_tri = struct.unpack("<I", f.read(4))[0]
            assert n_tri == 2
        # binary smaller than ASCII (1032 vs 220 for 4 tri).
        size = out.stat().st_size
        assert size < 200  # 80 + 4 + 2 × 50 = 184.


def test_q4_signed_distance():
    """Q4 — signed distance signed=unsigned×sign."""
    from core.utils.signed_distance import signed_distance
    V = np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1]], dtype=np.float64)
    F = np.array([[0,1,2],[0,1,3],[1,2,3],[0,2,3]], dtype=np.int64)
    q = np.array([[10, 10, 10]], dtype=np.float64)  # far outside.
    sd, r = signed_distance(q, V, F)
    assert r.n_query == 1
    # Far from tet → signed should be > 0 (outside).
    assert abs(sd[0]) > 0


def test_q5_edge_stats():
    """Q5 — unit tet edge length: 6 unique, min=1.0, max=√2."""
    from core.analyzer.edge_stats import compute_edge_stats
    V = np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1]], dtype=np.float64)
    F = np.array([[0,1,2],[0,1,3],[1,2,3],[0,2,3]], dtype=np.int64)
    r = compute_edge_stats(V, F)
    assert r.n_edges_unique == 6
    assert abs(r.edge_min - 1.0) < 1e-6
    assert abs(r.edge_max - np.sqrt(2)) < 1e-6


def test_q6_grade_default_thresholds():
    """Q6 — default thresholds A/B/C/D."""
    from core.generator.native_tet.quality import compute_quality_grade
    assert compute_quality_grade(0.15, 0.5) == "A"
    assert compute_quality_grade(0.07, 0.4) == "B"
    assert compute_quality_grade(0.02, 0.2) == "C"
    assert compute_quality_grade(0.005, 0.1) == "D"
    assert compute_quality_grade(0.0, 0.0) == "F"


def test_q6_grade_env_override(monkeypatch):
    """Q6 — env override 적용."""
    from core.generator.native_tet.quality import compute_quality_grade
    monkeypatch.setenv("AUTO_TESSELL_GRADE_A_MIN_Q", "0.05")
    monkeypatch.setenv("AUTO_TESSELL_GRADE_A_MEAN_Q", "0.20")
    # min=0.07, mean=0.5 → A under override.
    assert compute_quality_grade(0.07, 0.5) == "A"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
