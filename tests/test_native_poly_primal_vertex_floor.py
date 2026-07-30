"""Native-poly must refuse a collapsed primal mesh before dual conversion."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import core.generator.native_poly.harness as harness_module
from core.generator.native_poly.harness import run_native_poly_harness


def test_targeted_poly_refuses_primal_vertex_floor_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vertices = np.asarray([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.], [0., 0., 1.]])
    faces = np.asarray([[0, 1, 2], [0, 1, 3], [1, 2, 3], [0, 2, 1]])
    seen: dict[str, object] = {}

    def fake_tet(*_args, **kwargs):
        seen["floor"] = kwargs["min_final_vertices"]
        return SimpleNamespace(
            success=False,
            tets=None,
            message="target_primal_vertex_floor_unmet: actual=15, required=25",
        )

    monkeypatch.setattr(harness_module, "generate_native_tet", fake_tet)
    monkeypatch.setattr(
        harness_module, "tet_to_poly_dual", lambda *_args, **_kwargs: pytest.fail("dual called")
    )
    result = run_native_poly_harness(
        vertices, faces, tmp_path / "case", target_cells=50, max_iter=1
    )
    assert seen["floor"] == 25
    assert result.success is False
    assert result.message == "target_primal_vertex_floor_unmet: actual=15, required=25"


def test_zero_iteration_remains_graceful_generic_failure(tmp_path: Path) -> None:
    result = run_native_poly_harness(
        np.zeros((0, 3)),
        np.zeros((0, 3), dtype=int),
        tmp_path / "case",
        max_iter=0,
    )
    assert result.success is False
    assert result.message.startswith("native_poly_harness FAIL after 0 iter")
