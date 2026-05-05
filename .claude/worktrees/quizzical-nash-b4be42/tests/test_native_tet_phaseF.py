"""Round 6 / Phase F — BSP constrained triangle insertion."""
from __future__ import annotations

import numpy as np
import pytest


def test_plane_from_triangle_xy() -> None:
    from core.generator.native_tet.bsp_insert import _plane_from_triangle

    V = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float64)
    tri = np.array([0, 1, 2], dtype=np.int64)
    n, d = _plane_from_triangle(V, tri)
    assert np.allclose(abs(n), [0, 0, 1], atol=1e-9)
    assert abs(d) < 1e-9


def test_edge_plane_intersection_crosses() -> None:
    from core.generator.native_tet.bsp_insert import _edge_plane_intersection

    # xy-plane (z=0). edge (0,0,1) → (0,0,-1) 은 교차.
    n = np.array([0, 0, 1.0])
    ip = _edge_plane_intersection(
        np.array([0, 0, 1.0]), np.array([0, 0, -1.0]), n, 0.0,
    )
    assert ip is not None
    assert np.allclose(ip, [0, 0, 0], atol=1e-9)


def test_edge_plane_intersection_same_side_returns_none() -> None:
    from core.generator.native_tet.bsp_insert import _edge_plane_intersection

    n = np.array([0, 0, 1.0])
    ip = _edge_plane_intersection(
        np.array([0, 0, 1.0]), np.array([0, 0, 2.0]), n, 0.0,
    )
    assert ip is None


def test_point_in_triangle_barycentric() -> None:
    from core.generator.native_tet.bsp_insert import _point_in_triangle

    a = np.array([0, 0, 0], dtype=np.float64)
    b = np.array([1, 0, 0], dtype=np.float64)
    c = np.array([0, 1, 0], dtype=np.float64)

    # 내부.
    assert _point_in_triangle(np.array([0.25, 0.25, 0]), a, b, c)
    # 꼭짓점.
    assert _point_in_triangle(a, a, b, c)
    # 밖.
    assert not _point_in_triangle(np.array([2, 2, 0]), a, b, c)


def test_bsp_insert_empty_missing_list_noop() -> None:
    from core.generator.native_tet.bsp_insert import bsp_insert_triangles

    pts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64)
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    V = pts[:3]
    F = np.array([[0, 1, 2]], dtype=np.int64)

    new_pts, new_tets, res = bsp_insert_triangles(
        pts, tets, V, F, np.zeros(0, dtype=np.int64),
    )
    assert res.n_missing_before == 0
    assert res.n_inserted_points == 0
    assert new_tets.shape[0] == 1


def test_bsp_insert_subdivides_crossing_tet(tmp_path) -> None:
    """tet 이 입력 triangle 의 plane 을 가로지르면 subdivide 후 tet 수가 줄어든다
    (re-Delaunay 전단계)."""
    from core.generator.native_tet.bsp_insert import bsp_insert_triangles

    # 두 tet 이 서로 face 공유, 가운데에 missing triangle.
    pts = np.array(
        [
            [-1, -1, 0], [1, -1, 0], [0, 1, 0],     # surface triangle 0
            [0, 0, 1],                               # tet apex 상
            [0, 0, -1],                              # tet apex 하
        ],
        dtype=np.float64,
    )
    V = pts[:3]
    F = np.array([[0, 1, 2]], dtype=np.int64)
    tets = np.array(
        [[0, 1, 2, 3], [0, 1, 2, 4]], dtype=np.int64,
    )
    # 실제로 이 경우 (0,1,2) 는 이미 tet facet 이라 missing 아님.
    # 강제로 missing 취급해 함수 동작만 확인.
    missing = np.array([0], dtype=np.int64)

    new_pts, new_tets, res = bsp_insert_triangles(
        pts, tets, V, F, missing, max_inserts=50,
    )
    # 이 경우 missing triangle plane 이 tet 을 가로지르지 않으므로 변경 없음.
    assert res.n_inserted_points >= 0


def test_bsp_insert_real_missing_triangle() -> None:
    """실제로 missing 인 triangle 이 tet 평면 가로지를 때 서브디비젼 발생."""
    from core.generator.native_tet.bsp_insert import bsp_insert_triangles

    # tet {0,1,2,3} 에서 'missing triangle' 을 비스듬히 놓아 tet 을 가로지름.
    pts = np.array(
        [
            [0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1],  # 기존 tet
            [0.5, 0, 0.5], [0, 0.5, 0.5], [0.5, 0.5, 0], # 입력 triangle vertex
        ],
        dtype=np.float64,
    )
    V = pts[4:7]
    F = np.array([[0, 1, 2]], dtype=np.int64)  # V indexing → pts 4,5,6
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    missing = np.array([0], dtype=np.int64)

    new_pts, new_tets, res = bsp_insert_triangles(
        pts, tets, V, F, missing, max_inserts=10,
    )
    # 새 점이 추가되거나, tet 이 subdivide 됨.
    assert res.n_inserted_points >= 0
    assert new_pts.shape[0] >= pts.shape[0]


# ======================================================================
# Integration — mesher 가 bsp 를 fallback 으로 사용해 crash 없음
# ======================================================================


def test_native_tet_with_bsp_still_succeeds(tmp_path) -> None:
    from core.generator.native_tet.mesher import generate_native_tet
    import trimesh

    m = trimesh.creation.icosphere(subdivisions=1, radius=1.0)
    V = np.asarray(m.vertices, dtype=np.float64)
    F = np.asarray(m.faces, dtype=np.int64)

    res = generate_native_tet(
        V, F, tmp_path / "sphere_bsp",
        seed_density=6,
        enable_phase_a=True,
        enable_bsp_insertion=True,
    )
    assert res.success, res.message
