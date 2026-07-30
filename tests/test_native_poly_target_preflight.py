from pathlib import Path

import numpy as np
import pytest

import core.generator.native_poly.harness as harness


def test_expensive_below_floor_target_refuses_before_tet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(harness, "generate_native_tet", lambda *_a, **_k: pytest.fail("tet called"))
    v = np.asarray([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    r = harness.run_native_poly_harness(
        v, np.asarray([[0, 1, 2]]), tmp_path, target_cells=50, target_edge_length=0.02
    )
    assert r.success is False
    assert r.message.startswith("target_poly_budget_unreachable:")


def test_empty_input_skips_preflight_and_reaches_tet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        harness,
        "generate_native_tet",
        lambda *_a, **_k: type(
            "R", (), {"success": False, "tets": None, "message": "native validation"}
        )(),
    )
    r = harness.run_native_poly_harness(
        np.zeros((0, 3)),
        np.zeros((0, 3), dtype=int),
        tmp_path,
        target_cells=50,
        target_edge_length=0.02,
        max_iter=1,
    )
    assert r.success is False
    assert "target_poly_budget_unreachable" not in r.message
