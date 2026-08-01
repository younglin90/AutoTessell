"""Native Poly small-target regression for the former 15-cell collapse."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from core.analyzer.readers import read_stl
from core.generator.native_poly.harness import run_native_poly_harness

_CUBE = Path(__file__).resolve().parent / "benchmarks" / "cube.stl"


@pytest.mark.parametrize("target_cells", [50, 100])
def test_small_poly_target_does_not_collapse_to_fifteen_cells(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target_cells: int,
) -> None:
    monkeypatch.setenv("AUTO_TESSELL_P4C_PYTETWILD", "0")
    mesh = read_stl(_CUBE)
    result = run_native_poly_harness(
        np.asarray(mesh.vertices),
        np.asarray(mesh.faces),
        tmp_path / f"target-{target_cells}",
        target_cells=target_cells,
        max_iter=1,
        max_tet_cells=5_000,
    )

    assert result.success is True
    assert result.final_poly_cells >= 40
    assert result.final_poly_cells <= 125
    assert result.target_cells_absolute_error is not None
    assert result.target_cells_relative_error is not None
    assert result.target_cells_status == "reported_not_gated"
