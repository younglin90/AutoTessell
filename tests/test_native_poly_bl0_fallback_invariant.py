"""Boundary-layer request invariants for native-Poly Voronoi fallback."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest

import core.generator.native_poly.voronoi as voronoi
import core.generator.tier_native_poly as tier
from core.analyzer.readers import read_stl
from core.generator.native_poly import NativePolyResult
from core.generator.native_poly.harness import PolyHarnessResult

_REPO = Path(__file__).resolve().parents[1]
_TETRA_VERTICES = np.asarray(
    [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
    dtype=np.float64,
)
_TETRA_FACES = np.asarray(
    [[0, 2, 1], [0, 1, 3], [1, 2, 3], [2, 0, 3]],
    dtype=np.int64,
)


@pytest.mark.parametrize("auto_escalate", [False, True])
@pytest.mark.parametrize("requested_layers", [0, 1, 2, 3])
def test_public_generate_forwards_exact_layer_request_to_inner_calls(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    auto_escalate: bool,
    requested_layers: int,
) -> None:
    captured: list[int] = []

    def fake_inner(*_args: Any, **kwargs: Any) -> NativePolyResult:
        captured.append(int(kwargs["bl_layers"]))
        return NativePolyResult(True, 0.0, n_cells=4, quality_grade="A")

    def fake_hex(*_args: Any, **_kwargs: Any) -> NativePolyResult:
        return NativePolyResult(False, 0.0, message="forced hex failure")

    monkeypatch.setattr(voronoi, "_generate_native_poly_voronoi_inner", fake_inner)
    monkeypatch.setattr(voronoi, "_hex_to_poly_fallback", fake_hex)

    result = voronoi.generate_native_poly_voronoi(
        _TETRA_VERTICES,
        _TETRA_FACES,
        tmp_path,
        auto_escalate=auto_escalate,
        bl_layers=requested_layers,
    )

    assert result.success
    assert captured
    assert captured == [requested_layers] * len(captured)


def test_tier_fallback_preserves_explicit_zero_layers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: list[int] = []

    def fail_harness(*_args: Any, **_kwargs: Any) -> PolyHarnessResult:
        return PolyHarnessResult(False, 0.0, 1, message="forced harness failure")

    def fake_voronoi(*_args: Any, **kwargs: Any) -> NativePolyResult:
        captured.append(int(kwargs["bl_layers"]))
        return NativePolyResult(False, 0.0, message="truthful refusal")

    monkeypatch.setattr(tier, "run_native_poly_harness", fail_harness)
    monkeypatch.setattr(tier, "generate_native_poly_voronoi", fake_voronoi)

    result = tier._runner(
        _TETRA_VERTICES,
        _TETRA_FACES,
        tmp_path,
        bl_layers=0,
    )

    assert not result.success
    assert captured == [0]


@pytest.mark.parametrize("requested_layers, expected_extrusions", [(0, 0), (1, 1), (2, 2), (3, 2)])
def test_inner_executes_only_requested_safe_layer_count(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    requested_layers: int,
    expected_extrusions: int,
) -> None:
    mesh = read_stl(_REPO / "tests" / "benchmarks" / "sphere.stl")
    calls: list[float] = []

    def preserve_mesh(
        _wall_adj: set[int],
        vertices: np.ndarray,
        cells: list[list[list[int]]],
        *_args: Any,
        step: float,
        **_kwargs: Any,
    ) -> tuple[np.ndarray, list[list[list[int]]]]:
        calls.append(float(step))
        return vertices, cells

    monkeypatch.setattr(voronoi, "_find_wall_adjacent_cells", lambda *_args: {0})
    monkeypatch.setattr(voronoi, "_extrude_prism_layer", preserve_mesh)

    voronoi._generate_native_poly_voronoi_inner(
        mesh.vertices,
        mesh.faces,
        tmp_path,
        seed_density=8,
        n_lloyd=0,
        bl_layers=requested_layers,
    )

    assert len(calls) == expected_extrusions
