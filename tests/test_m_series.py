"""M7 / beta2652 — M-series 통합 회귀.

M1 VTU binary / M3 batch inference / M4 volume_stats.
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


def test_m1_vtu_binary_attribute(fake_cube_pm):
    """M1 — binary 모드 attribute 노출."""
    from core.utils.vtk_writer import write_vtu
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "x.vtu"; (Path(td) / "pm").mkdir()
        r = write_vtu(str(Path(td) / "pm"), str(out), binary=True)
        assert r.success
        c = out.read_text(encoding="utf-8")
        assert 'format="binary"' in c


def test_m3_batch_runner_init():
    """M3 — BatchInferenceRunner 인스턴스화 (load 시도)."""
    from core.generator.native_ai.inference_batch import BatchInferenceRunner
    runner = BatchInferenceRunner("non_existent.pt")
    # _ensure_loaded → False (모델 없음).
    assert not runner._ensure_loaded()


def test_m4_volume_stats_unit_tet():
    """M4 — unit tet 의 quality 통계."""
    from core.analyzer.volume_stats import compute_tet_stats
    pts = np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1]], dtype=np.float64)
    tets = np.array([[0,1,2,3]], dtype=np.int64)
    r = compute_tet_stats(pts, tets, n_bins=10)
    assert r.n_cells == 1
    assert r.quality_min == r.quality_max  # 단일 cell.
    assert r.volume_total > 0
    assert r.n_negative_volume == 0
    assert len(r.histogram_bins) == 10


def test_m4_volume_stats_negative_detect():
    """M4 — inverted tet 검출."""
    from core.analyzer.volume_stats import compute_tet_stats
    # 정상 + inverted (winding 반대).
    pts = np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1]], dtype=np.float64)
    tets = np.array([[0,1,2,3], [0,2,1,3]], dtype=np.int64)  # 두번째는 inverted.
    r = compute_tet_stats(pts, tets)
    assert r.n_negative_volume == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
