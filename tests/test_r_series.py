"""R6 / beta2686 — R-series 통합 회귀."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def test_r1_diag_json():
    from core.utils.diag_json import write_failed_mesh_diagnostic
    V = np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1]], dtype=np.float64)
    F = np.array([[0,2,1],[0,1,3],[1,2,3],[0,3,2]], dtype=np.int64)
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "d.json"
        r = write_failed_mesh_diagnostic(out, V=V, F=F, failure_reason="test")
        assert r.success
        d = json.loads(out.read_text())
        assert "input_stats" in d
        assert "recommendations" in d
        assert d["input_stats"].get("n_vertices") == 4


def test_r2_adjacency_isolated():
    """R2 — 단일 isolated tet."""
    from core.analyzer.adjacency_graph import build_tet_adjacency
    tets = np.array([[0,1,2,3]], dtype=np.int64)
    adj, r = build_tet_adjacency(tets)
    assert r.n_cells == 1
    assert r.n_isolated_cells == 1
    assert r.n_edges == 0


def test_r2_adjacency_triangle():
    """R2 — 3 tets in triangle adjacency."""
    from core.analyzer.adjacency_graph import build_tet_adjacency
    tets = np.array([[0,1,2,3],[0,1,2,4],[0,1,3,4]], dtype=np.int64)
    adj, r = build_tet_adjacency(tets)
    assert r.n_cells == 3
    assert r.n_edges == 3


def test_r3_sampling_count():
    from core.utils.sampling import sample_surface_uniform
    V = np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1]], dtype=np.float64)
    F = np.array([[0,1,2],[0,1,3],[1,2,3],[0,2,3]], dtype=np.int64)
    pts, r = sample_surface_uniform(V, F, n_samples=50)
    assert pts.shape == (50, 3)
    assert r.n_samples == 50


def test_r4_curvature_gauss_bonnet():
    """R4 — closed sphere ∫K dA = 4π."""
    from core.analyzer.curvature import vertex_gaussian_curvature
    V = np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1]], dtype=np.float64)
    F = np.array([[0,2,1],[0,1,3],[1,2,3],[0,3,2]], dtype=np.int64)
    K, r = vertex_gaussian_curvature(V, F)
    # χ=2 closed → ∫K dA ≈ 4π (12.566).
    assert abs(r.curvature_total - 4 * np.pi) < 0.01


def test_r5_doctor_json_runs():
    """R5 — doctor --json 동작."""
    import subprocess
    r = subprocess.run(
        [sys.executable, "-m", "cli.main", "doctor", "--json"],
        cwd=str(REPO), capture_output=True, text=True, timeout=15,
    )
    assert r.returncode == 0
    # 첫 줄이 { 로 시작.
    assert r.stdout.strip().startswith("{")
    out = json.loads(r.stdout)
    assert "dependencies" in out
    assert "ml" in out
    assert "cuda" in out


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
