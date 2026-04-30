"""N7 / beta2659 — N-series 통합 회귀."""
from __future__ import annotations

import sys
import subprocess
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def test_n2_export_native_in_help():
    """N2 — export-native 명령 + 14 fmt choice 노출."""
    r = subprocess.run(
        [sys.executable, "-m", "cli.main", "export-native", "--help"],
        cwd=str(REPO), capture_output=True, text=True, timeout=10,
    )
    assert r.returncode == 0
    out = r.stdout
    for fmt in [
        "vtu", "vtu-binary", "starccm-ccmio", "cgns", "fluent", "tecplot",
        "plot3d", "avs-ucd", "gambit-neu", "nastran-bdf", "abaqus-inp",
    ]:
        assert fmt in out, f"--format choice {fmt} 누락"


def test_n5_recommend_target_edge():
    """N5 — feature-edge informed target_edge."""
    from core.preprocessor.native_remesh import recommend_target_edge_from_features
    V = np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1]], dtype=np.float64)
    F = np.array([[0,1,2],[0,1,3],[1,2,3],[0,2,3]], dtype=np.int64)
    te = recommend_target_edge_from_features(V, F, target_factor=0.5)
    assert te > 0
    # unit tet edge length ≈ 1.0 ~ √2; × 0.5 → 0.5-0.71 범위.
    assert 0.3 < te < 1.0


def test_n5_no_features_fallback():
    """N5 — feature 없는 경우 mean edge fallback."""
    from core.preprocessor.native_remesh import recommend_target_edge_from_features
    # 매우 평평한 mesh (sharp 적음).
    V = np.array([[0,0,0],[1,0,0],[2,0,0],[1,0.001,0]], dtype=np.float64)
    F = np.array([[0,1,3],[1,2,3]], dtype=np.int64)
    te = recommend_target_edge_from_features(V, F, target_factor=0.5)
    assert te > 0


def test_n6_list_tiers_runs():
    """N6 — list-tiers 명령 동작."""
    r = subprocess.run(
        [sys.executable, "-m", "cli.main", "list-tiers"],
        cwd=str(REPO), capture_output=True, text=True, timeout=10,
    )
    assert r.returncode == 0
    out = r.stdout
    # 핵심 tier 들 노출.
    for tier in ["tier_native_tet", "tier_native_hex", "tier_native_poly"]:
        assert tier in out


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
