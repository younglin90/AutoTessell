"""L0 target-cell forwarding contract for the native-poly harness route."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import core.generator.native_poly.harness as harness_module
import core.generator.tier_native_poly as tier_module
from core.generator.native_poly.harness import PolyHarnessResult, run_native_poly_harness

_VERTICES = np.asarray(
    [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
    dtype=np.float64,
)
_FACES = np.asarray(
    [[0, 1, 2], [0, 1, 3], [1, 2, 3], [0, 2, 1]], dtype=np.int64,
)


@pytest.mark.parametrize("target_cells", [None, 321])
def test_harness_forwards_target_cells_and_source_surface(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target_cells: int | None,
) -> None:
    """Harness must forward the exact target and unchanged source V/F to tet."""
    captured: dict[str, object] = {}

    def fake_generate(vertices, faces, _case_dir, **kwargs):
        captured["vertices"] = vertices
        captured["faces"] = faces
        captured["target_cells"] = kwargs.get("target_cells")
        return SimpleNamespace(success=False, message="forced tet failure")

    monkeypatch.setattr(harness_module, "generate_native_tet", fake_generate)

    result = run_native_poly_harness(
        _VERTICES,
        _FACES,
        tmp_path / "case",
        target_cells=target_cells,
        max_iter=1,
    )

    assert result.success is False
    assert captured["target_cells"] == target_cells
    assert np.array_equal(captured["vertices"], _VERTICES)
    assert np.array_equal(captured["faces"], _FACES)


@pytest.mark.parametrize("target_cells", [None, 321])
def test_bl0_route_uses_harness_without_layer_budget_or_voronoi_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target_cells: int | None,
) -> None:
    """BL=0 preserves the harness route and forwards target without reserving layers."""
    captured: dict[str, object] = {}

    def fake_harness(vertices, faces, case_dir, **kwargs):
        captured["vertices"] = vertices
        captured["faces"] = faces
        captured["target_cells"] = kwargs.get("target_cells")
        captured["kwargs"] = kwargs
        return PolyHarnessResult(success=True, elapsed=0.0, iterations=1, n_cells=12)

    def fail_voronoi(*_args, **_kwargs):
        raise AssertionError("BL=0 must not reserve a layer budget through Voronoi routing")

    monkeypatch.setattr(tier_module, "run_native_poly_harness", fake_harness)
    monkeypatch.setattr(tier_module, "generate_native_poly_voronoi", fail_voronoi)

    result = tier_module._runner(
        _VERTICES,
        _FACES,
        tmp_path / "case",
        target_cells=target_cells,
        bl_layers=0,
        post_layers_num_layers=0,
    )

    assert result.success is True
    assert captured["target_cells"] == target_cells
    assert "bl_layers" not in captured["kwargs"]
    assert "post_layers_num_layers" not in captured["kwargs"]
    assert np.array_equal(captured["vertices"], _VERTICES)
    assert np.array_equal(captured["faces"], _FACES)
