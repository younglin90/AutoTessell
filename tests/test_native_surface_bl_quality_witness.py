"""C++23 wall-edge BL quality witness contract and deterministic metrics."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "auto_tessell_core" / "build"
if BUILD.exists():
    sys.path.insert(0, str(BUILD))
native = pytest.importorskip("native_surface_bl_quality")


def _inputs(layer_points: np.ndarray, provenance: list[dict[str, object]], layers: int):
    return native.evaluate_wall_edge_stack(
        np.asarray([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]], dtype=np.float64),
        np.asarray([[17, 0, 1, 0]], dtype=np.int64),
        layer_points,
        np.asarray([[0.0, 0.0, 1.0]], dtype=np.float64),
        provenance,
        layers,
    )


def _lineage(layer: int) -> dict[str, object]:
    return {
        "source_wall_edge": 17,
        "source_face": 3,
        "layer": layer,
        "patch": "wall",
        "feature": "straight",
        "physical_group": "fluid",
        "provenance": "source-ledger",
        "generated_vertices": (0, 1),
    }


def test_bl0_is_identity_and_planar_bl1_has_physical_metrics() -> None:
    disabled = _inputs(np.empty((0, 1, 2, 3)), [], 0)
    assert disabled["accepted"] is True
    assert disabled["status"] == "disabled_identity"
    assert disabled["actual_layers"] == 0
    assert disabled["generated_vertices"] == []

    layers = np.asarray([[[[0.0, 0.1, 0.0], [1.0, 0.1, 0.0]]]], dtype=np.float64)
    first = _inputs(layers, [_lineage(1)], 1)
    second = _inputs(layers, [_lineage(1)], 1)
    assert first == second
    assert first["accepted"] is True
    assert first["actual_layers"] == first["requested_layers"] == 1
    assert first["quality"]["wall_edge_non_orthogonality"]["max"] == 0.0
    assert first["quality"]["tangential_skewness"]["max"] == 0.0
    assert first["quality"]["metric_distortion"]["max"] == 1.0
    assert first["quality"]["raw_aspect_ratio"]["max"] == 10.0
    assert first["topology"] == {
        "invalid": 0,
        "inverted": 0,
        "duplicate": 0,
        "non_manifold": 0,
        "self_intersecting": 0,
    }


def test_three_layers_have_exact_coverage_and_repeatable_growth() -> None:
    layers = np.asarray(
        [
            [[[0.0, 0.1, 0.0], [1.0, 0.1, 0.0]]],
            [[[0.0, 0.22, 0.0], [1.0, 0.22, 0.0]]],
            [[[0.0, 0.364, 0.0], [1.0, 0.364, 0.0]]],
        ],
        dtype=np.float64,
    )
    provenance = [_lineage(1), _lineage(2), _lineage(3)]
    first = _inputs(layers, provenance, 3)
    second = _inputs(layers, provenance, 3)
    assert first == second
    assert first["accepted"] is True
    assert first["actual_layers"] == 3
    assert len(first["per_entity"]) == 3
    assert first["quality"]["wall_edge_non_orthogonality"]["max"] == 0.0
    assert first["quality"]["metric_distortion"]["max"] == 1.0

def test_oblique_advance_reports_skew_but_can_pass_and_layers_are_exact() -> None:
    layers = np.asarray([[[[0.02, 0.1, 0.0], [1.02, 0.1, 0.0]]]], dtype=np.float64)
    result = _inputs(layers, [_lineage(1)], 1)
    assert result["accepted"] is True
    assert 0.0 < result["quality"]["tangential_skewness"]["max"] < 0.25
    assert result["actual_layers"] == 1


@pytest.mark.parametrize(
    "layer_points, provenance, layers",
    [
        (
            np.asarray([[[[0.0, -0.1, 0.0], [1.0, -0.1, 0.0]]]], dtype=np.float64),
            [_lineage(1)],
            1,
        ),
        (
            np.asarray(
                [
                    [[[0.0, 0.0, 0.1], [1.0, 0.0, 0.1]]],
                    [[[0.0, 0.0, 0.2], [1.0, 0.0, 0.2]]],
                ],
                dtype=np.float64,
            ),
            [_lineage(1), _lineage(1)],
            2,
        ),
        (
            np.asarray([[[[0.0, 0.1, 0.0], [1.0, 0.1, 0.0]]]], dtype=np.float64),
            [{"source_wall_edge": 17}],
            1,
        ),
    ],
)
def test_bad_orientation_or_lineage_refuses_atomically(layer_points, provenance, layers) -> None:
    result = _inputs(layer_points, provenance, layers)
    assert result["accepted"] is False
    assert result["status"] == "quality_gate_refused"
    assert result["actual_layers"] == 0


def test_fresh_config_is_default_off_and_not_shipped() -> None:
    cmake = (ROOT / "auto_tessell_core" / "CMakeLists.txt").read_text(encoding="utf-8")
    contract = (ROOT / "auto_tessell_core" / "native_build_contract.json").read_text(encoding="utf-8")
    assert 'option(BUILD_NATIVE_SURFACE_BL_QUALITY "Build optional report-only native surface boundary-layer quality witness" OFF)' in cmake
    assert "list(APPEND _AUTOTESSELL_FIRST_PARTY_NATIVE_TARGETS native_surface_bl_quality)" not in cmake
    assert '"native_surface_bl_quality"' not in contract
