"""Round 3 / Phase D 부분 — BVH-anchored surface snap + vectorized smoothing."""
from __future__ import annotations

import numpy as np
import pytest


# ======================================================================
# Vectorized smoothing correctness
# ======================================================================


def test_smooth_interior_vectorized_matches_expected() -> None:
    """1 interior vertex 를 4 surface 가 둘러싼 tet 구성 — 1 iteration 후
    interior 가 centroid 방향으로 이동."""
    from core.generator.native_tet.smooth import smooth_interior

    pts = np.array(
        [
            [0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1],
            [0.9, 0.9, 0.9],
        ],
        dtype=np.float64,
    )
    tets = np.array(
        [[0, 1, 2, 4], [0, 1, 3, 4], [0, 2, 3, 4], [1, 2, 3, 4]], dtype=np.int64,
    )
    original = pts.copy()
    smooth_interior(
        pts, tets,
        locked_vertex_ids=np.array([0, 1, 2, 3], dtype=np.int64),
        n_iter=1, relax=0.5,
    )
    # surface 변화 없음.
    assert np.allclose(pts[:4], original[:4])
    # interior 이동.
    assert not np.allclose(pts[4], original[4])


def test_smooth_interior_vectorized_scales_fast() -> None:
    """100 vertex / 200 tet 규모에서 1 초 이내."""
    import time
    from core.generator.native_tet.smooth import smooth_interior
    import trimesh
    from scipy.spatial import Delaunay

    m = trimesh.creation.icosphere(subdivisions=2, radius=1.0)
    V = np.asarray(m.vertices, dtype=np.float64)
    # 내부 시드 추가.
    bmin, bmax = V.min(0), V.max(0)
    grid = np.linspace(bmin + 0.3, bmax - 0.3, 5)
    # simplified: just a single interior cluster.
    inside_pts = np.random.RandomState(0).uniform(
        bmin + 0.3, bmax - 0.3, size=(50, 3),
    )
    all_pts = np.vstack([V, inside_pts])
    dl = Delaunay(all_pts)
    tets = np.asarray(dl.simplices, dtype=np.int64)

    locked = np.arange(V.shape[0], dtype=np.int64)
    t0 = time.perf_counter()
    smooth_interior(all_pts, tets, locked_vertex_ids=locked, n_iter=3, relax=0.3)
    elapsed = time.perf_counter() - t0
    # 벡터화 전에는 수 초 이상 걸리던 규모 — 1 초 이내 기대.
    assert elapsed < 1.5, f"smoothing too slow: {elapsed:.2f}s"


# ======================================================================
# Surface snap
# ======================================================================


def test_snap_surface_vertex_to_bvh() -> None:
    """BVH 위에 존재하지 않는 점을 project 하면 가장 가까운 표면 점으로 이동."""
    from core.utils.aabb import TriangleBVH
    from core.generator.native_tet.surface_snap import snap_surface_vertices
    import trimesh

    m = trimesh.creation.box(extents=(1, 1, 1))
    V = np.asarray(m.vertices, dtype=np.float64)
    F = np.asarray(m.faces, dtype=np.int64)
    bvh = TriangleBVH.build(V, F)

    # 큐브 바깥으로 확실히 벗어난 점을 snap.
    pts = np.array([[0.7, 0.0, 0.0]], dtype=np.float64)   # 표면 x=0.5 에서 0.2 밖.
    sr = snap_surface_vertices(
        pts, bvh, np.array([0], dtype=np.int64),
        max_distance=1.0,
    )
    assert sr.n_snapped == 1
    # snap 후 점은 표면 위: BVH 거리 ≈ 0.
    _cp, d_after, _ = bvh.closest_point(pts[0])
    assert d_after < 1e-6, f"snap 후 표면 거리 {d_after}"


def test_snap_skips_locked() -> None:
    from core.utils.aabb import TriangleBVH
    from core.generator.native_tet.surface_snap import snap_surface_vertices
    import trimesh

    m = trimesh.creation.box(extents=(1, 1, 1))
    V = np.asarray(m.vertices, dtype=np.float64)
    F = np.asarray(m.faces, dtype=np.int64)
    bvh = TriangleBVH.build(V, F)

    pts = V.copy()
    pts[0] = pts[0] + np.array([0.2, 0, 0])
    before = pts[0].copy()

    sr = snap_surface_vertices(
        pts, bvh, np.array([0], dtype=np.int64),
        locked_vertex_ids=np.array([0], dtype=np.int64),
    )
    assert sr.n_snapped == 0
    assert np.allclose(pts[0], before)


def test_snap_skips_far_beyond_max_distance() -> None:
    from core.utils.aabb import TriangleBVH
    from core.generator.native_tet.surface_snap import snap_surface_vertices
    import trimesh

    m = trimesh.creation.box(extents=(1, 1, 1))
    V = np.asarray(m.vertices, dtype=np.float64)
    F = np.asarray(m.faces, dtype=np.int64)
    bvh = TriangleBVH.build(V, F)

    # 10 단위 밖으로 이동 + max_distance=0.5 → snap 하지 않음.
    pts = np.array([[10.0, 10.0, 10.0]], dtype=np.float64)
    before = pts[0].copy()
    sr = snap_surface_vertices(
        pts, bvh, np.array([0], dtype=np.int64),
        max_distance=0.5,
    )
    assert sr.n_snapped == 0
    assert np.allclose(pts[0], before)


# ======================================================================
# Integration
# ======================================================================


def test_native_tet_phase_c_with_snap_runs(tmp_path) -> None:
    from core.generator.native_tet.mesher import generate_native_tet
    import trimesh

    m = trimesh.creation.icosphere(subdivisions=1, radius=1.0)
    V = np.asarray(m.vertices, dtype=np.float64)
    F = np.asarray(m.faces, dtype=np.int64)

    case = tmp_path / "sphere_phaseD"
    res = generate_native_tet(
        V, F, case,
        seed_density=6,
        enable_phase_a=True,
        enable_phase_b=True,
        enable_phase_c=True,
        local_ops_iterations=2,
        envelope_eps_relative=0.02,
    )
    assert res.success, res.message
    assert res.n_cells > 0
