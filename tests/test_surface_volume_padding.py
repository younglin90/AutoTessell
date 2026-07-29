"""Explicit planar surface padding regression tests."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from core.utils.mesh_exporter import export_planar_surface_volume_to_openfoam
from core.utils.polymesh_reader import (
    parse_foam_faces,
    parse_foam_labels,
    parse_foam_points,
)
from core.utils.surface_volume_padding import (
    _load_native_surface_padding,
    pad_axis_aligned_surface_to_volume,
)


def test_native_extension_is_primary_kernel() -> None:
    module = _load_native_surface_padding()
    assert Path(module.__file__).suffix in {".pyd", ".so"}


def test_xy_triangle_becomes_one_prism_with_mean_edge_padding() -> None:
    vertices = np.array([[0.0, 0.0, 0.0], [3.0, 0.0, 0.0], [0.0, 4.0, 0.0]])
    faces = np.array([[0, 1, 2]], dtype=np.int64)
    padded = pad_axis_aligned_surface_to_volume(vertices, faces)

    assert padded.report.plane == "xy"
    assert padded.report.normal_axis == "z"
    assert padded.report.direction == 1
    assert padded.report.prism_cells == 1
    assert padded.report.hex_cells == 0
    assert padded.report.padding_thickness == pytest.approx(4.0)
    assert len(padded.vertices) == 6
    assert len(padded.cell_faces[0]) == 5
    assert np.allclose(padded.vertices[3:, 2], 4.0)


def test_xz_quad_becomes_one_hex() -> None:
    vertices = np.array(
        [
            [0.0, 2.0, 0.0],
            [2.0, 2.0, 0.0],
            [2.0, 2.0, 2.0],
            [0.0, 2.0, 2.0],
        ]
    )
    padded = pad_axis_aligned_surface_to_volume(vertices, [[0, 1, 2, 3]])

    assert padded.report.plane == "xz"
    assert padded.report.normal_axis == "y"
    assert padded.report.hex_cells == 1
    assert padded.report.prism_cells == 0
    assert padded.report.padding_thickness == pytest.approx(2.0)
    assert len(padded.cell_faces[0]) == 6
    assert np.allclose(padded.vertices[4:, 1], 4.0)


def test_negative_direction_and_input_arrays_are_unchanged() -> None:
    vertices = np.array([[0.0, 0.0, 3.0], [1.0, 0.0, 3.0], [0.0, 1.0, 3.0]])
    original = vertices.copy()
    faces = [[0, 1, 2]]
    padded = pad_axis_aligned_surface_to_volume(vertices, faces, direction=-1)

    assert padded.report.direction == -1
    assert padded.report.padding_thickness == pytest.approx((2.0 + 2.0**0.5) / 3.0)
    assert np.allclose(padded.vertices[3:, 2], 3.0 - padded.report.padding_thickness)
    assert np.array_equal(vertices, original)
    assert faces == [[0, 1, 2]]


@pytest.mark.parametrize(
    ("vertices", "error"),
    [
        (
            np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 1.0]]),
            "axis-aligned plane",
        ),
        (
            np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 1e-3]]),
            "axis-aligned plane",
        ),
    ],
)
def test_rejects_tilted_or_nonplanar_surface(vertices: np.ndarray, error: str) -> None:
    with pytest.raises(ValueError, match=error):
        pad_axis_aligned_surface_to_volume(vertices, [[0, 1, 2]])


def test_rejects_non_tri_quad_and_degenerate_faces() -> None:
    square = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0]])
    with pytest.raises(ValueError, match="triangle or quadrilateral"):
        pad_axis_aligned_surface_to_volume(square, [[0, 1, 2, 3, 0]])

    collinear = np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 0.0], [2.0, 2.0, 0.0]])
    with pytest.raises(ValueError, match="degenerate zero-area face"):
        pad_axis_aligned_surface_to_volume(collinear, [[0, 1, 2]])


def test_openfoam_writer_writes_single_prism_poly_mesh(tmp_path: Path) -> None:
    vertices = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    report = export_planar_surface_volume_to_openfoam(
        vertices,
        [[0, 1, 2]],
        tmp_path,
        patch_name="planar_wall",
    )

    poly_dir = tmp_path / "constant" / "polyMesh"
    assert report.volume_cells == 1
    assert len(parse_foam_points(poly_dir / "points")) == 6
    assert len(parse_foam_faces(poly_dir / "faces")) == 5
    assert parse_foam_labels(poly_dir / "owner") == [0] * 5
    assert parse_foam_labels(poly_dir / "neighbour") == []
    assert "planar_wall" in (poly_dir / "boundary").read_text(encoding="utf-8")
