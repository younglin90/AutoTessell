"""Boolean occupancy wiring for native hex and hex-backed poly paths."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from core.generator.native_hex import generate_native_hex
from core.generator.native_poly import generate_native_poly_voronoi
from core.utils.boolean_surfaces import BooleanSurfaceSet
from core.utils.polymesh_reader import parse_foam_boundary
from core.utils.stl_writer import write_stl_binary


def _cube(lo: float, hi: float) -> tuple[np.ndarray, np.ndarray]:
    vertices = np.array(
        [
            [lo, lo, lo], [hi, lo, lo], [hi, hi, lo], [lo, hi, lo],
            [lo, lo, hi], [hi, lo, hi], [hi, hi, hi], [lo, hi, hi],
        ],
        dtype=np.float64,
    )
    faces = np.array(
        [
            [0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7],
            [0, 1, 5], [0, 5, 4], [2, 3, 7], [2, 7, 6],
            [1, 2, 6], [1, 6, 5], [0, 4, 7], [0, 7, 3],
        ],
        dtype=np.int64,
    )
    return vertices, faces


def _write_cube(path: Path, lo: float, hi: float) -> tuple[np.ndarray, np.ndarray]:
    vertices, faces = _cube(lo, hi)
    result = write_stl_binary(vertices, faces, path)
    assert result.success, result.message
    return vertices, faces


def _sources(tmp_path: Path):
    a_path = tmp_path / "body.stl"
    b_path = tmp_path / "tool.stl"
    va, fa = _write_cube(a_path, 0.0, 1.0)
    vb, fb = _write_cube(b_path, 0.5, 1.5)
    vertices = np.concatenate([va, vb], axis=0)
    faces = np.concatenate([fa, fb + len(va)], axis=0)
    return a_path, b_path, vertices, faces


@pytest.mark.parametrize(
    ("operation", "expected"),
    [
        ("union", [True, True, True, False]),
        ("intersection", [False, True, False, False]),
        ("difference", [True, False, False, False]),
    ],
)
def test_boolean_surface_set_operations(
    tmp_path: Path, operation: str, expected: list[bool]
) -> None:
    a_path, b_path, _, _ = _sources(tmp_path)
    points = np.array(
        [[0.25, 0.25, 0.25], [0.75, 0.75, 0.75],
         [1.25, 1.25, 1.25], [2.0, 2.0, 2.0]],
        dtype=np.float64,
    )
    surfaces = BooleanSurfaceSet(
        [a_path, b_path], operation=operation, source_names=["body", "tool"]
    )

    assert surfaces.contains(points).tolist() == expected
    assert surfaces.patch_classifier.patch_names == (
        "source_0_body", "source_1_tool"
    )


def test_native_hex_boolean_union_writes_source_patches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AUTO_TESSELL_WWW7_OFF", "1")
    monkeypatch.setenv("AUTO_TESSELL_HEX_QUALITY1_OFF", "1")
    a_path, b_path, vertices, faces = _sources(tmp_path)
    case_dir = tmp_path / "hex_case"

    result = generate_native_hex(
        vertices,
        faces,
        case_dir,
        target_edge_length=0.25,
        max_cells_per_axis=12,
        boolean_input_paths=[str(a_path), str(b_path)],
        boolean_source_names=["body", "tool"],
        boolean_operation="union",
    )

    assert result.success, result.message
    assert result.n_cells > 0
    patches = parse_foam_boundary(case_dir / "constant" / "polyMesh" / "boundary")
    assert [patch["name"] for patch in patches] == [
        "source_0_body", "source_1_tool"
    ]
    assert all(int(patch["nFaces"]) > 0 for patch in patches)


def test_native_poly_boolean_uses_validated_hex_backing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AUTO_TESSELL_WWW7_OFF", "1")
    monkeypatch.setenv("AUTO_TESSELL_HEX_QUALITY1_OFF", "1")
    a_path, b_path, vertices, faces = _sources(tmp_path)
    case_dir = tmp_path / "poly_case"

    result = generate_native_poly_voronoi(
        vertices,
        faces,
        case_dir,
        seed_density=8,
        auto_escalate_max=2,
        boolean_input_paths=[str(a_path), str(b_path)],
        boolean_source_names=["body", "tool"],
        boolean_operation="intersection",
    )

    assert result.success, result.message
    assert result.n_cells > 0
    patches = parse_foam_boundary(case_dir / "constant" / "polyMesh" / "boundary")
    assert [patch["name"] for patch in patches] == [
        "source_0_body", "source_1_tool"
    ]
