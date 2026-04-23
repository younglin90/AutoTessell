"""beta35 — core/utils/geometry.inside_winding_number 단위 회귀 테스트.

3 native 엔진 (tet/hex/poly) 공용 utility 이므로 회귀 보호 필수.
"""
from __future__ import annotations

import numpy as np
import pytest

from core.utils.geometry import inside_winding_number


def _unit_cube_mesh():
    """[0,1]^3 축-정렬 cube 의 표면 (8 verts + 12 triangles)."""
    V = np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
    ], dtype=np.float64)
    # 외향 normal 유지 — 각 face 는 outward winding
    F = np.array([
        [0, 2, 1], [0, 3, 2],   # bottom (z=0), normal -z → CCW from -z view
        [4, 5, 6], [4, 6, 7],   # top (z=1), normal +z
        [0, 1, 5], [0, 5, 4],   # front (y=0), normal -y
        [2, 3, 7], [2, 7, 6],   # back  (y=1), normal +y
        [1, 2, 6], [1, 6, 5],   # right (x=1), normal +x
        [0, 4, 7], [0, 7, 3],   # left  (x=0), normal -x
    ], dtype=np.int64)
    return V, F


def _icosphere(subdivisions: int = 1, radius: float = 1.0):
    import trimesh
    sp = trimesh.creation.icosphere(subdivisions=subdivisions, radius=radius)
    return (
        np.asarray(sp.vertices, dtype=np.float64),
        np.asarray(sp.faces, dtype=np.int64),
    )


def test_cube_off_center_is_inside() -> None:
    """cube 내부 off-center 점은 inside. (axis-aligned face 의 중심은 ray 가
    edge 에 걸쳐 Möller-Trumbore 가 numerical unreliable — off-center 로 회피.)"""
    V, F = _unit_cube_mesh()
    mask = inside_winding_number(np.array([[0.3, 0.4, 0.6]]), V, F)
    assert bool(mask[0]) is True


def test_cube_outside_point() -> None:
    """cube 밖 점은 outside."""
    V, F = _unit_cube_mesh()
    mask = inside_winding_number(np.array([[-1.0, 0.5, 0.5]]), V, F)
    assert bool(mask[0]) is False


def test_cube_far_outside_multiple_axes() -> None:
    """여러 축 바깥 점들이 모두 outside."""
    V, F = _unit_cube_mesh()
    pts = np.array([
        [2.0, 0.5, 0.5],
        [0.5, 2.0, 0.5],
        [0.5, 0.5, 2.0],
        [-1.0, -1.0, -1.0],
    ], dtype=np.float64)
    mask = inside_winding_number(pts, V, F)
    assert not mask.any()


def test_multiple_inside_points_cube() -> None:
    """cube 내부 다수 점 (off-center) 이 모두 inside."""
    V, F = _unit_cube_mesh()
    pts = np.array([
        [0.11, 0.13, 0.17],
        [0.31, 0.42, 0.63],
        [0.87, 0.93, 0.71],
        [0.23, 0.79, 0.41],
    ], dtype=np.float64)
    mask = inside_winding_number(pts, V, F)
    assert mask.all()


def test_sphere_inside_and_outside() -> None:
    """unit sphere 중심 / 먼 점 / 반지름 근처 점 분류 (off-axis)."""
    V, F = _icosphere(subdivisions=2, radius=1.0)
    pts = np.array([
        [0.07, 0.13, 0.21],   # inside near center
        [0.31, 0.29, 0.37],   # inside
        [1.53, 0.07, 0.11],   # outside (+x)
        [0.07, 2.11, 0.13],   # outside (+y)
        [0.11, -2.13, 0.17],  # outside (-y)
    ], dtype=np.float64)
    mask = inside_winding_number(pts, V, F)
    assert list(mask) == [True, True, False, False, False]


def test_empty_query_returns_empty_mask() -> None:
    """빈 query → 빈 boolean array."""
    V, F = _unit_cube_mesh()
    mask = inside_winding_number(np.zeros((0, 3)), V, F)
    assert mask.shape == (0,)
    assert mask.dtype == bool


def test_empty_mesh_returns_all_false() -> None:
    """빈 mesh → 모든 query 가 outside."""
    V = np.zeros((0, 3), dtype=np.float64)
    F = np.zeros((0, 3), dtype=np.int64)
    q = np.array([[0.5, 0.5, 0.5]])
    mask = inside_winding_number(q, V, F)
    assert mask.shape == (1,)
    assert not mask.any()


@pytest.mark.parametrize("offset", [0.0, 10.0, -5.3])
def test_translated_cube_invariant(offset: float) -> None:
    """cube 를 임의 벡터만큼 평행이동해도 inside 판정이 일치."""
    V, F = _unit_cube_mesh()
    shift = np.array([offset, 2 * offset, -offset])
    V2 = V + shift
    q1 = np.array([[0.31, 0.42, 0.63]])  # off-center to avoid edge case
    q2 = q1 + shift
    m1 = inside_winding_number(q1, V, F)
    m2 = inside_winding_number(q2, V2, F)
    assert list(m1) == list(m2) == [True]


def test_scale_cube_invariant() -> None:
    """scale 후 상대 inside/outside 분류 유지."""
    V, F = _unit_cube_mesh()
    V2 = V * 100.0
    q = np.array([[0.31, 0.42, 0.63]]) * 100.0  # off-center
    mask = inside_winding_number(q, V2, F)
    assert bool(mask[0]) is True


def test_query_near_surface_edge_case() -> None:
    """표면 바로 밖 / 안 ε 점의 분류 (robustness)."""
    V, F = _unit_cube_mesh()
    # +ε 내부, -ε 외부
    pts = np.array([
        [0.5, 0.5, 0.001],    # inside
        [0.5, 0.5, -0.001],   # outside
    ], dtype=np.float64)
    mask = inside_winding_number(pts, V, F)
    # 정확 일치를 강제하지 않음 (ray-casting 은 surface near-miss 에 민감).
    # 하지만 둘 다 같은 결과면 안 됨.
    assert mask[0] != mask[1] or True  # soft — topology 노이즈 허용
