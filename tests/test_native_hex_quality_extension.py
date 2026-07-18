"""Parity tests for native hexahedral quality primitives."""

from __future__ import annotations

from dataclasses import astuple
from typing import Any

import numpy as np
import pytest

from core.generator.native_hex import quality


def _native_or_skip() -> Any:
    module = quality._load_native_hex_quality()
    if module is None or not hasattr(module, "hex_quality_primitives"):
        pytest.skip("native_hex_quality extension is not built")
    return module


def _structured_hexes(nx: int, ny: int, nz: int) -> tuple[np.ndarray, np.ndarray]:
    x, y, z = np.meshgrid(
        np.arange(nx + 1, dtype=np.float64),
        np.arange(ny + 1, dtype=np.float64),
        np.arange(nz + 1, dtype=np.float64),
        indexing="ij",
    )
    points = np.stack((x, y, z), axis=-1).reshape(-1, 3)
    ids = np.arange(points.shape[0], dtype=np.int64).reshape(nx + 1, ny + 1, nz + 1)
    cells: list[list[int]] = []
    for i in range(nx):
        for j in range(ny):
            for k in range(nz):
                cells.append(
                    [
                        ids[i, j, k],
                        ids[i + 1, j, k],
                        ids[i + 1, j + 1, k],
                        ids[i, j + 1, k],
                        ids[i, j, k + 1],
                        ids[i + 1, j, k + 1],
                        ids[i + 1, j + 1, k + 1],
                        ids[i, j + 1, k + 1],
                    ]
                )
    return points, np.asarray(cells, dtype=np.int64)


def _reports(
    monkeypatch: pytest.MonkeyPatch,
    points: np.ndarray,
    cells: np.ndarray,
) -> tuple[quality.HexQualityReport, quality.HexQualityReport]:
    native = _native_or_skip()
    monkeypatch.setattr(quality, "_NATIVE_HEX_QUALITY", native)
    monkeypatch.setattr(quality, "_NATIVE_HEX_QUALITY_IMPORT_ATTEMPTED", True)
    native_report = quality.hex_quality_report(points, cells)

    monkeypatch.setattr(quality, "_NATIVE_HEX_QUALITY", None)
    python_report = quality.hex_quality_report(points, cells)
    return native_report, python_report


def _assert_reports_equal(
    native_report: quality.HexQualityReport,
    python_report: quality.HexQualityReport,
) -> None:
    assert native_report.n_cells == python_report.n_cells
    assert native_report.n_faces == python_report.n_faces
    np.testing.assert_allclose(
        astuple(native_report)[2:],
        astuple(python_report)[2:],
        rtol=2e-13,
        atol=2e-13,
        equal_nan=True,
    )


@pytest.mark.parametrize("shape", [(1, 1, 1), (2, 1, 1), (4, 3, 2)])
def test_native_quality_matches_structured_grids(
    monkeypatch: pytest.MonkeyPatch,
    shape: tuple[int, int, int],
) -> None:
    points, cells = _structured_hexes(*shape)
    if len(cells) > 2:
        rng = np.random.default_rng(42)
        points = points + rng.normal(scale=0.025, size=points.shape)

    native_report, python_report = _reports(monkeypatch, points, cells)

    _assert_reports_equal(native_report, python_report)


def test_native_quality_duplicate_non_manifold_cells_match_python(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    points, cells = _structured_hexes(1, 1, 1)
    duplicate_cells = np.repeat(cells, 3, axis=0)

    native_report, python_report = _reports(monkeypatch, points, duplicate_cells)

    _assert_reports_equal(native_report, python_report)
    assert native_report.n_faces == 6
    assert native_report.min_face_area == 0.0


def test_native_quality_negative_indices_and_nan_match_python(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    points, cells = _structured_hexes(2, 1, 1)
    cells = cells.copy()
    cells[cells == points.shape[0] - 1] = -1
    points = points.copy()
    points[0, 2] = np.nan

    native_report, python_report = _reports(monkeypatch, points, cells)

    _assert_reports_equal(native_report, python_report)


def test_native_quality_failure_uses_python_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    points, cells = _structured_hexes(2, 2, 2)

    class FailingNative:
        @staticmethod
        def hex_quality_primitives(*_args: Any) -> None:
            raise RuntimeError("forced native hex quality failure")

    monkeypatch.setattr(quality, "_NATIVE_HEX_QUALITY", FailingNative())
    monkeypatch.setattr(quality, "_NATIVE_HEX_QUALITY_IMPORT_ATTEMPTED", True)
    failed_report = quality.hex_quality_report(points, cells)

    monkeypatch.setattr(quality, "_NATIVE_HEX_QUALITY", None)
    python_report = quality.hex_quality_report(points, cells)

    _assert_reports_equal(failed_report, python_report)
