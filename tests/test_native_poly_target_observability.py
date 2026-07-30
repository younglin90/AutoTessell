"""L0 report-only target-cell evidence for the native-poly harness."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import core.generator.native_poly.harness as harness_module
from core.generator.native_poly.harness import run_native_poly_harness

_VERTICES = np.asarray(
    [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
    dtype=np.float64,
)
_FACES = np.asarray(
    [[0, 1, 2], [0, 1, 3], [1, 2, 3], [0, 2, 1]], dtype=np.int64,
)


@pytest.mark.parametrize(
    ("target_cells", "expected_absolute", "expected_relative", "expected_status"),
    [
        (None, None, None, "not_requested"),
        (50, 37, 0.74, "reported_not_gated"),
        (100, 87, 0.87, "reported_not_gated"),
    ],
)
def test_target_observation_reports_exact_counts_without_mutating_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target_cells: int | None,
    expected_absolute: int | None,
    expected_relative: float | None,
    expected_status: str,
) -> None:
    captured: dict[str, object] = {}

    def fake_tet(vertices, faces, _case_dir, **kwargs):
        captured["vertices"] = vertices.copy()
        captured["faces"] = faces.copy()
        captured["target_cells"] = kwargs.get("target_cells")
        return SimpleNamespace(
            success=True,
            tets=np.zeros((7, 4), dtype=np.int64),
            tet_points=_VERTICES.copy(),
        )

    monkeypatch.setattr(harness_module, "generate_native_tet", fake_tet)
    monkeypatch.setattr(
        harness_module,
        "tet_to_poly_dual",
        lambda *_args, **_kwargs: SimpleNamespace(success=True, message="ok"),
    )
    monkeypatch.setattr(
        harness_module,
        "_evaluate_poly_mesh",
        lambda _case: (
            True,
            {
                "cells": 13,
                "points": 9,
                "max_non_orthogonality": 1.0,
                "max_skewness": 0.2,
                "negative_volumes": 0,
                "mesh_ok": True,
            },
        ),
    )
    monkeypatch.setattr(harness_module, "_install_polymesh_only", lambda *_args: None)

    result = run_native_poly_harness(
        _VERTICES,
        _FACES,
        tmp_path / "case",
        target_cells=target_cells,
        max_iter=1,
    )

    assert result.success is True
    assert result.tet_cells_by_iteration == (7,)
    assert result.final_poly_cells == 13
    assert result.target_cells_requested == target_cells
    assert result.target_cells_absolute_error == expected_absolute
    assert result.target_cells_relative_error == expected_relative
    assert result.target_cells_status == expected_status
    assert captured["target_cells"] == target_cells
    np.testing.assert_array_equal(captured["vertices"], _VERTICES)
    np.testing.assert_array_equal(captured["faces"], _FACES)
