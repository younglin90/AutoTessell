"""Route contract: primal-vertex target failures must not silently fallback."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import core.generator.tier_native_poly as tier


def test_target_vertex_floor_failure_bypasses_voronoi_and_keeps_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vertices = np.asarray([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]])
    faces = np.asarray([[0, 1, 2]])
    seen: dict[str, np.ndarray] = {}

    def failed_harness(v, f, *_args, **_kwargs):
        seen["vertices"] = v.copy()
        seen["faces"] = f.copy()
        return SimpleNamespace(success=False, message="target_primal_vertex_floor_unmet: actual=15")

    monkeypatch.setattr(tier, "run_native_poly_harness", failed_harness)
    monkeypatch.setattr(
        tier,
        "generate_native_poly_voronoi",
        lambda *_args, **_kwargs: pytest.fail("fallback called"),
    )
    result = tier._runner(vertices, faces, tmp_path, target_cells=50, bl_layers=0)
    assert result.success is False
    np.testing.assert_array_equal(seen["vertices"], vertices)
    np.testing.assert_array_equal(seen["faces"], faces)


def test_generic_harness_failure_keeps_existing_voronoi_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = {"fallback": 0}
    monkeypatch.setattr(
        tier,
        "run_native_poly_harness",
        lambda *_args, **_kwargs: SimpleNamespace(success=False, message="tet failed"),
    )
    def fallback(*_args, **_kwargs):
        calls["fallback"] += 1
        return SimpleNamespace(success=True, message="voronoi")
    monkeypatch.setattr(tier, "generate_native_poly_voronoi", fallback)
    result = tier._runner(
        np.zeros((3, 3)), np.zeros((1, 3), dtype=int), tmp_path
    )
    assert result.success is True
    assert calls["fallback"] == 1
