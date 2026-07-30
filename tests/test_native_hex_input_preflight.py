"""Fail-closed ingress contracts for the native hex mesher."""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest

from core.analyzer.readers import read_stl
from core.generator.native_hex import generate_native_hex
from core.generator.native_hex import mesher as native_hex_mesher

_REPO = Path(__file__).resolve().parents[1]
_CUBE_STL = _REPO / "tests" / "benchmarks" / "cube.stl"
_POLYMESH_FILES = ("points", "faces", "owner", "neighbour", "boundary")
_CUBE_SEED_DENSITY_6_POLYMESH_SHA256 = (
    "d30ab5470929ae6d7594d6b13a259f2c008889ad69c2e9008066ee0c450efaa9"
)
_TETRA_POINTS = np.array(
    ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
)
_TETRA_FACES = np.array(((0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3)), dtype=np.int64)


def _polymesh_sha256(case_dir: Path) -> str:
    poly_dir = case_dir / "constant" / "polyMesh"
    return hashlib.sha256(
        b"".join((poly_dir / name).read_bytes() for name in _POLYMESH_FILES)
    ).hexdigest()


@pytest.mark.parametrize(
    ("vertices", "faces", "reason"),
    (
        (_TETRA_POINTS[:, :2], _TETRA_FACES, "vertices_must_have_shape_n_by_3"),
        (np.array(((np.nan, 0.0, 0.0), *(_TETRA_POINTS[1:]))), _TETRA_FACES, "non_finite_vertex"),
        (
            _TETRA_POINTS.astype(np.complex128) + 1j,
            _TETRA_FACES,
            "complex_vertex",
        ),
        (
            np.asarray(_TETRA_POINTS.astype(np.complex128) + 1j, dtype=object),
            _TETRA_FACES,
            "complex_vertex",
        ),
        (_TETRA_POINTS, _TETRA_FACES[:, :2], "faces_must_have_shape_n_by_3"),
        (_TETRA_POINTS, np.array(((False, True, True),)), "boolean_face_index"),
        (
            _TETRA_POINTS,
            np.asarray(((False, True, True),), dtype=object),
            "boolean_face_index",
        ),
        (_TETRA_POINTS, np.array(((0.0, 1.0, 2.0j),)), "complex_face_index"),
        (
            _TETRA_POINTS,
            np.asarray(((0.0, 1.0, 2.0j),), dtype=object),
            "complex_face_index",
        ),
        (_TETRA_POINTS, np.array(((0, 1, np.nan),)), "non_finite_face_index"),
        (_TETRA_POINTS, np.array(((0.0, 1.5, 2.0),)), "non_integral_face_index"),
        (_TETRA_POINTS, np.array(((0, 1, 8),)), "face_index_out_of_range"),
        (_TETRA_POINTS, np.array(((0, 1, 1),)), "repeated_face_vertex"),
    ),
)
def test_native_hex_rejects_malformed_surface_before_meshing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    vertices: np.ndarray,
    faces: np.ndarray,
    reason: str,
) -> None:
    """Malformed arrays cannot reach winding/octree work or create a case."""

    def _unexpected_meshing_path(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("malformed input reached native hex meshing")

    monkeypatch.setattr(native_hex_mesher, "_inside_winding_number", _unexpected_meshing_path)
    case_dir = tmp_path / "malformed_case"

    result = generate_native_hex(vertices, faces, case_dir)

    assert not result.success
    assert result.message == f"native_hex_invalid_input:{reason}"
    assert not case_dir.exists()


def test_native_hex_preflight_preserves_valid_cube_input_and_output(tmp_path: Path) -> None:
    """Ingress validation leaves valid caller arrays and deterministic output unchanged."""
    if not _CUBE_STL.exists():
        pytest.skip("cube.stl 없음")
    mesh = read_stl(_CUBE_STL)
    vertices, faces = mesh.vertices.copy(), mesh.faces.copy()
    vertices_before, faces_before = vertices.copy(), faces.copy()
    first_dir, second_dir = tmp_path / "first", tmp_path / "second"

    first = generate_native_hex(vertices, faces, first_dir, seed_density=6)
    second = generate_native_hex(vertices, faces, second_dir, seed_density=6)

    assert first.success, first.message
    assert second.success, second.message
    assert np.array_equal(vertices, vertices_before)
    assert np.array_equal(faces, faces_before)
    assert first.n_cells == second.n_cells
    for name in _POLYMESH_FILES:
        first_file = first_dir / "constant" / "polyMesh" / name
        second_file = second_dir / "constant" / "polyMesh" / name
        assert first_file.read_bytes() == second_file.read_bytes(), name
    assert _polymesh_sha256(first_dir) == _CUBE_SEED_DENSITY_6_POLYMESH_SHA256
    assert _polymesh_sha256(second_dir) == _CUBE_SEED_DENSITY_6_POLYMESH_SHA256
