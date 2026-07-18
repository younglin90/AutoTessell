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


def test_native_generic_signed_volumes_match_python() -> None:
    native = _native_or_skip()
    assert hasattr(native, "generic_cell_signed_volumes")
    points, cells = _structured_hexes(4, 3, 2)
    rng = np.random.default_rng(13)
    points = points + rng.normal(scale=0.015, size=points.shape)
    cell_faces = [
        [[int(cell[local]) for local in face] for face in quality._HEX_FACES] for cell in cells
    ]

    native_volumes = native.generic_cell_signed_volumes(points, cell_faces)
    python_volumes: list[float] = []
    for cell in cell_faces:
        vertices = sorted({vertex for face in cell for vertex in face})
        centroid = points[np.asarray(vertices, dtype=np.int64)].mean(axis=0)
        volume = 0.0
        for face in cell:
            face_points = points[np.asarray(face, dtype=np.int64)]
            for slot in range(1, len(face) - 1):
                volume += (
                    float(
                        np.dot(
                            face_points[0] - centroid,
                            np.cross(
                                face_points[slot] - centroid,
                                face_points[slot + 1] - centroid,
                            ),
                        )
                    )
                    / 6.0
                )
        python_volumes.append(volume)

    np.testing.assert_allclose(
        native_volumes,
        python_volumes,
        rtol=2e-13,
        atol=2e-13,
    )


def test_native_generic_cell_face_signs_match_python() -> None:
    native = _native_or_skip()
    assert hasattr(native, "generic_cell_face_signs")
    points, cells = _structured_hexes(2, 1, 1)
    rng = np.random.default_rng(19)
    points = points + rng.normal(scale=0.02, size=points.shape)
    cell = [[int(cells[0, local]) for local in face] for face in quality._HEX_FACES]

    native_signs, native_magnitude = native.generic_cell_face_signs(points, cell)
    vertices = sorted({vertex for face in cell for vertex in face})
    centroid = points[np.asarray(vertices, dtype=np.int64)].mean(axis=0)
    python_signs: list[float] = []
    for face in cell:
        face_points = points[np.asarray(face, dtype=np.int64)] - centroid
        sign = 0.0
        for slot in range(1, len(face) - 1):
            sign += float(
                np.dot(
                    face_points[0],
                    np.cross(face_points[slot], face_points[slot + 1]),
                )
            )
        python_signs.append(sign)

    np.testing.assert_allclose(native_signs, python_signs, rtol=2e-13, atol=2e-13)
    assert native_magnitude == pytest.approx(
        sum(abs(value) for value in python_signs), rel=2e-13, abs=2e-13
    )


def test_native_generic_side_metrics_match_relax_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core.generator.native_hex.mesher import (  # noqa: PLC0415
        _relax_boundary_sliver_interior,
    )

    native = _native_or_skip()
    assert hasattr(native, "generic_side_metrics")
    points, cells = _structured_hexes(4, 3, 2)
    rng = np.random.default_rng(23)
    points = points + rng.normal(scale=0.02, size=points.shape)
    cell_faces = [
        [[int(cell[local]) for local in face] for face in quality._HEX_FACES] for cell in cells
    ]

    monkeypatch.setattr(quality, "_NATIVE_HEX_QUALITY", native)
    monkeypatch.setattr(quality, "_NATIVE_HEX_QUALITY_IMPORT_ATTEMPTED", True)
    native_points, native_stats = _relax_boundary_sliver_interior(points, cell_faces, iters=1)

    monkeypatch.setattr(quality, "_NATIVE_HEX_QUALITY", None)
    python_points, python_stats = _relax_boundary_sliver_interior(points, cell_faces, iters=1)

    np.testing.assert_allclose(native_points, python_points, atol=2e-13)
    assert native_stats.keys() == python_stats.keys()
    np.testing.assert_allclose(
        list(native_stats.values()),
        list(python_stats.values()),
        rtol=2e-13,
        atol=2e-13,
    )
