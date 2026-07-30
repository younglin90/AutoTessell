"""Final native-tet evidence must certify the immutable caller input."""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

from core.generator.native_tet.mesher import NativeTetResult, generate_native_tet

_POINTS = np.asarray(
    ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
    dtype=np.float64,
)
_FACES = np.asarray(
    ((0, 2, 1), (0, 1, 3), (1, 2, 3), (2, 0, 3)),
    dtype=np.int64,
)
_POLYMESH_FILES = ("points", "faces", "owner", "neighbour", "boundary")
_VALID_POINT_SHA256 = "4165a5be53209fff5ace98d58c3de63f2de6ef10a25df234d95a52b06bca362f"
_VALID_TET_SHA256 = "e12414338bdb3184808636b59b3a3d9396c9c42204715b055a3f2569b8adb15e"
_VALID_FILE_SHA256 = {
    "points": "abf3ef72a9664ed2db70b97db09f5ca73fde009a231827f904ce5fe5c52ef5dc",
    "faces": "6a6d7371d0366795c449283952a4716ed00d612199d024774975e56106fafa35",
    "owner": "5c0977e5c44bcbc5f53cdb2bb0080a388c169dfad9d8498519628c6bebc46440",
    "neighbour": "6f96684a25759c24c7b8cd4161ac6d9a2fe9b545404fa8fd1e691f4324180950",
    "boundary": "f42e4d01286952eea4540c2b8389afe68b59734b5af395eed39432242a528fa6",
}


def _generate(
    points: np.ndarray,
    faces: np.ndarray,
    case_dir: Path,
) -> NativeTetResult:
    return generate_native_tet(
        points,
        faces,
        case_dir,
        target_cells=50,
        enable_bsp_insertion=False,
        enable_edge_recovery=False,
        enable_phase_b=False,
        enable_phase_c=False,
    )


def _digest(array: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(array)).hexdigest()


def test_valid_tetrahedron_remains_byte_exact(tmp_path: Path) -> None:
    points = _POINTS.copy()
    faces = _FACES.copy()
    point_bytes = points.tobytes()
    face_bytes = faces.tobytes()
    case_dir = tmp_path / "valid"

    result = _generate(points, faces, case_dir)

    assert result.success, result.message
    assert result.n_points == 4
    assert result.n_cells == 1
    assert _digest(result.tet_points) == _VALID_POINT_SHA256
    assert _digest(result.tets) == _VALID_TET_SHA256
    poly_mesh = case_dir / "constant" / "polyMesh"
    assert {
        name: hashlib.sha256((poly_mesh / name).read_bytes()).hexdigest()
        for name in _POLYMESH_FILES
    } == _VALID_FILE_SHA256
    assert points.tobytes() == point_bytes
    assert faces.tobytes() == face_bytes


def test_auto_fix_cannot_replace_immutable_duplicate_coordinate_source(
    tmp_path: Path,
) -> None:
    points = np.vstack((_POINTS, _POINTS[0])).astype(np.float64, copy=False)
    faces = np.asarray(
        ((4, 2, 1), (0, 1, 3), (1, 2, 3), (2, 4, 3)),
        dtype=np.int64,
    )
    point_bytes = points.tobytes()
    face_bytes = faces.tobytes()
    case_dir = tmp_path / "duplicate_source_coordinate"

    result = _generate(points, faces, case_dir)

    assert not result.success
    assert result.n_points == 4
    assert result.n_cells == 1
    assert "source_points contains ambiguous duplicate coordinates" in result.message
    assert result.debug_info["strict_source_topology_error"] == (
        "ValueError: source_points contains ambiguous duplicate coordinates"
    )
    assert not (case_dir / "constant" / "polyMesh").exists()
    assert points.tobytes() == point_bytes
    assert faces.tobytes() == face_bytes


def test_vertex_and_face_reorder_still_certifies_original_source(tmp_path: Path) -> None:
    order = np.asarray((3, 0, 2, 1), dtype=np.int64)
    old_to_new = np.empty(order.size, dtype=np.int64)
    old_to_new[order] = np.arange(order.size, dtype=np.int64)
    points = _POINTS[order].copy()
    faces = old_to_new[_FACES[::-1, ::-1]].copy()
    point_bytes = points.tobytes()
    face_bytes = faces.tobytes()

    result = _generate(points, faces, tmp_path / "reordered")

    assert result.success, result.message
    assert result.debug_info["strict_source_topology"]["valid"] is True
    assert result.debug_info["strict_source_component_bijection"]["bijective"] is True
    assert (
        result.debug_info["strict_source_component_bijection"]["source_faces_preserved"]
        is True
    )
    assert points.tobytes() == point_bytes
    assert faces.tobytes() == face_bytes
