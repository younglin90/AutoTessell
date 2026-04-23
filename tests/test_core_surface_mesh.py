"""beta54 — CoreSurfaceMesh dedicated 회귀."""
from __future__ import annotations

import numpy as np
import pytest

from core.analyzer.readers.core_mesh import CoreSurfaceMesh


def test_construct_from_lists_coerces_to_numpy() -> None:
    """list 입력을 float64 / int64 ndarray 로 변환."""
    m = CoreSurfaceMesh(
        vertices=[[0, 0, 0], [1, 0, 0], [0, 1, 0]],
        faces=[[0, 1, 2]],
    )
    assert m.vertices.dtype == np.float64
    assert m.faces.dtype == np.int64
    assert m.n_vertices == 3
    assert m.n_faces == 1


def test_construct_empty_mesh() -> None:
    """빈 mesh (V=0, F=0) 생성 가능."""
    m = CoreSurfaceMesh(
        vertices=np.zeros((0, 3)),
        faces=np.zeros((0, 3), dtype=np.int64),
    )
    assert m.n_vertices == 0
    assert m.n_faces == 0


def test_construct_invalid_vertex_shape_raises() -> None:
    """vertices 가 (V, 3) 이 아니면 ValueError."""
    with pytest.raises(ValueError, match="vertices shape"):
        CoreSurfaceMesh(vertices=np.zeros((5, 2)), faces=np.zeros((0, 3)))


def test_construct_invalid_face_shape_raises() -> None:
    """faces 가 (F, 3) 이 아니면 ValueError (quads 등 지원 안 함)."""
    with pytest.raises(ValueError, match="faces shape"):
        CoreSurfaceMesh(
            vertices=np.zeros((4, 3)),
            faces=np.array([[0, 1, 2, 3]]),  # quad
        )


def test_n_vertices_and_n_faces_properties() -> None:
    m = CoreSurfaceMesh(
        vertices=np.random.default_rng(0).uniform(-1, 1, (10, 3)),
        faces=np.array([[0, 1, 2], [3, 4, 5], [6, 7, 8]], dtype=np.int64),
    )
    assert m.n_vertices == 10
    assert m.n_faces == 3


def test_compute_face_normals_unit_triangle_z_axis() -> None:
    """x-y 평면 삼각형 → normal 방향 +z."""
    V = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float64)
    F = np.array([[0, 1, 2]], dtype=np.int64)
    m = CoreSurfaceMesh(vertices=V, faces=F)
    n = m.compute_face_normals()
    assert n.shape == (1, 3)
    # cross((1,0,0),(0,1,0)) = (0,0,1)
    np.testing.assert_allclose(n[0], [0, 0, 1], atol=1e-12)


def test_compute_face_normals_empty_mesh() -> None:
    """빈 mesh → (0, 3) empty array."""
    m = CoreSurfaceMesh(vertices=np.zeros((0, 3)), faces=np.zeros((0, 3), dtype=np.int64))
    n = m.compute_face_normals()
    assert n.shape == (0, 3)


def test_compute_face_areas_unit_triangle() -> None:
    """(0,0,0)-(1,0,0)-(0,1,0) 삼각형 → 면적 0.5."""
    m = CoreSurfaceMesh(
        vertices=np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float64),
        faces=np.array([[0, 1, 2]], dtype=np.int64),
    )
    a = m.compute_face_areas()
    assert a.shape == (1,)
    np.testing.assert_allclose(a[0], 0.5, atol=1e-12)


def test_compute_face_areas_empty_mesh() -> None:
    m = CoreSurfaceMesh(vertices=np.zeros((0, 3)), faces=np.zeros((0, 3), dtype=np.int64))
    a = m.compute_face_areas()
    assert a.shape == (0,)


def test_compute_face_areas_multiple_triangles() -> None:
    """여러 삼각형의 면적 합이 정확."""
    V = np.array([
        [0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1],
    ], dtype=np.float64)
    F = np.array([
        [0, 1, 2],  # z=0 unit triangle: area=0.5
        [0, 1, 3],  # y=0 unit triangle: area=0.5
    ], dtype=np.int64)
    m = CoreSurfaceMesh(vertices=V, faces=F)
    a = m.compute_face_areas()
    np.testing.assert_allclose(a, [0.5, 0.5], atol=1e-12)


def test_compute_bounding_box() -> None:
    V = np.array([
        [-1, -2, 5], [3, 4, -1], [0, 0, 0],
    ], dtype=np.float64)
    m = CoreSurfaceMesh(vertices=V, faces=np.array([[0, 1, 2]], dtype=np.int64))
    bmin, bmax = m.compute_bounding_box()
    np.testing.assert_array_equal(bmin, [-1, -2, -1])
    np.testing.assert_array_equal(bmax, [3, 4, 5])


def test_compute_bounding_box_empty_mesh() -> None:
    """빈 mesh → (0,0,0), (0,0,0)."""
    m = CoreSurfaceMesh(vertices=np.zeros((0, 3)), faces=np.zeros((0, 3), dtype=np.int64))
    bmin, bmax = m.compute_bounding_box()
    np.testing.assert_array_equal(bmin, [0, 0, 0])
    np.testing.assert_array_equal(bmax, [0, 0, 0])


def test_metadata_default_empty_dict() -> None:
    m = CoreSurfaceMesh(vertices=np.zeros((3, 3)), faces=np.array([[0, 1, 2]]))
    assert m.metadata == {}


def test_metadata_custom_values() -> None:
    m = CoreSurfaceMesh(
        vertices=np.zeros((3, 3)),
        faces=np.array([[0, 1, 2]]),
        metadata={"format": "stl", "comment": "test"},
    )
    assert m.metadata["format"] == "stl"
    assert m.metadata["comment"] == "test"


def test_repr_includes_counts() -> None:
    m = CoreSurfaceMesh(
        vertices=np.zeros((5, 3)),
        faces=np.array([[0, 1, 2], [2, 3, 4]]),
        metadata={"src": "x"},
    )
    s = repr(m)
    assert "V=5" in s
    assert "F=2" in s
    assert "src" in s
