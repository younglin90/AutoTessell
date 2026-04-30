"""P7 / beta2673 — P-series 통합 회귀."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def test_p1_geometry_kpi_unit_tet():
    """P1 — closed tet → χ=2, genus=0."""
    from core.analyzer.geometry_kpi import compute_geometry_kpi
    V = np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1]], dtype=np.float64)
    F = np.array([[0,2,1],[0,1,3],[1,2,3],[0,3,2]], dtype=np.int64)
    r = compute_geometry_kpi(V, F)
    assert r.n_vertices == 4 and r.n_faces == 4 and r.n_edges == 6
    assert r.euler_characteristic == 2
    assert r.genus_estimate == 0
    assert abs(r.enclosed_volume - 1.0 / 6.0) < 1e-6


def test_p2_polyhedral_check_unit_tet():
    """P2 — single tet → 1 cell, 0 inconsistent."""
    from core.analyzer.polyhedral_check import check_polyhedral_mesh
    pts = np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1]], dtype=np.float64)
    cell_face_verts = [[[0,2,1],[0,1,3],[1,2,3],[0,3,2]]]
    r = check_polyhedral_mesh(pts, [], cell_face_verts)
    assert r.n_cells == 1
    assert r.n_inconsistent_winding == 0
    assert r.avg_faces_per_cell == 4.0


def test_p3_alias_resolver():
    """P3 — alias bidirectional resolve."""
    from core.strategist.tier_selector import aliases_for_tier, resolve_either
    aliases = aliases_for_tier("tier_native_tet")
    assert "native_tet" in aliases
    assert "tier_native_tet" in aliases
    canon, all_a = resolve_either("native_tet")
    assert canon == "tier_native_tet"
    assert "native_tet" in all_a


def test_p4_bench_summary_help():
    """P4 — bench-summary 명령 노출."""
    import subprocess
    r = subprocess.run(
        [sys.executable, "-m", "cli.main", "bench-summary", "--help"],
        cwd=str(REPO), capture_output=True, text=True, timeout=10,
    )
    assert r.returncode == 0
    assert "bench-summary" in r.stdout or "bench_json" in r.stdout.lower()


def test_p5_predict_with_confidence_no_model():
    """P5 — model 미로드 시 graceful empty 반환."""
    from core.generator.native_ai.inference_batch import BatchInferenceRunner
    runner = BatchInferenceRunner("/nonexistent.pt")
    pts = np.random.rand(10, 3)
    tets = np.array([[0,1,2,3]], dtype=np.int64)
    mean_p, std_p = runner.predict_with_confidence(pts, tets, n_mc_samples=3)
    # No model → empty array.
    assert len(mean_p) == 0
    assert len(std_p) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
