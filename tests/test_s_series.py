"""S7 / beta2694 — S-series 통합 회귀."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def test_s1_mesh_crop():
    """S1 — bbox crop 동작."""
    from core.utils.mesh_crop import crop_tet_mesh_bbox
    pts = np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1],[3,3,3],[4,3,3],[3,4,3],[3,3,4]], dtype=np.float64)
    tets = np.array([[0,1,2,3],[4,5,6,7]], dtype=np.int64)
    new_p, new_t, r = crop_tet_mesh_bbox(
        pts, tets,
        np.array([2.5, 2.5, 2.5]), np.array([5, 5, 5]),
    )
    assert r.n_input_cells == 2
    assert r.n_output_cells == 1
    assert new_p.shape == (4, 3)


def test_s1_mesh_crop_empty():
    """S1 — 빈 bbox → 0 output."""
    from core.utils.mesh_crop import crop_tet_mesh_bbox
    pts = np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1]], dtype=np.float64)
    tets = np.array([[0,1,2,3]], dtype=np.int64)
    new_p, new_t, r = crop_tet_mesh_bbox(
        pts, tets,
        np.array([10, 10, 10]), np.array([20, 20, 20]),
    )
    assert r.n_output_cells == 0
    assert new_t.shape == (0, 4)


def test_s3_quality_delta_unchanged():
    """S3 — translated tet → quality unchanged."""
    from core.analyzer.quality_delta import compute_quality_delta
    pts1 = np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1]], dtype=np.float64)
    tets = np.array([[0,1,2,3]], dtype=np.int64)
    pts2 = pts1 + np.array([5, 0, 0])  # pure translation.
    r = compute_quality_delta(pts1, tets, pts2, tets)
    assert abs(r.delta_mean) < 1e-9
    assert r.n_unchanged == 1


def test_s4_list_all_tiers():
    """S4 — programmatic tier list."""
    from core.strategist.tier_selector import list_all_tiers, is_native_tier, is_external_tier
    tiers = list_all_tiers()
    assert len(tiers) >= 20  # 21 expected.
    canon_set = {t["canonical"] for t in tiers}
    assert "tier_native_tet" in canon_set
    assert is_native_tier("tier_native_tet")
    assert is_external_tier("tetwild")


def test_s5_doctor_env_in_json():
    """S5 — doctor JSON 의 environment key."""
    import subprocess, json
    r = subprocess.run(
        [sys.executable, "-m", "cli.main", "doctor", "--json"],
        cwd=str(REPO), capture_output=True, text=True, timeout=15,
    )
    assert r.returncode == 0
    out = json.loads(r.stdout)
    assert "environment" in out
    env = out["environment"]
    assert "python_version" in env
    assert "platform" in env
    assert "cpu_count" in env


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
