"""Phase C 단위 테스트 (beta125 TetWild-lite 3 단계 — 기본 구성)."""
from __future__ import annotations

import numpy as np
import pytest


# ======================================================================
# AABB (core/utils/aabb.py)
# ======================================================================


def test_aabb_closest_point_on_triangle() -> None:
    from core.utils.aabb import _closest_point_on_triangle

    a = np.array([0, 0, 0], dtype=np.float64)
    b = np.array([1, 0, 0], dtype=np.float64)
    c = np.array([0, 1, 0], dtype=np.float64)

    # 점이 triangle 안 (0.25, 0.25, 0.5) → closest 는 (0.25, 0.25, 0), d=0.5.
    cp, d = _closest_point_on_triangle(
        np.array([0.25, 0.25, 0.5]), a, b, c,
    )
    assert np.allclose(cp, [0.25, 0.25, 0.0], atol=1e-6)
    assert abs(d - 0.5) < 1e-6

    # vertex 영역: p 는 a 쪽.
    cp, d = _closest_point_on_triangle(
        np.array([-1.0, -1.0, 0.0]), a, b, c,
    )
    assert np.allclose(cp, a)


def test_aabb_bvh_build_and_query() -> None:
    from core.utils.aabb import TriangleBVH

    # 단위 큐브 표면.
    import trimesh
    m = trimesh.creation.box(extents=(1, 1, 1))
    V = np.asarray(m.vertices, dtype=np.float64)
    F = np.asarray(m.faces, dtype=np.int64)

    bvh = TriangleBVH.build(V, F)
    assert len(bvh.nodes) > 0
    # 큐브 중심 (0,0,0) 에서 표면까지 거리는 0.5.
    _cp, d, _ti = bvh.closest_point(np.array([0.0, 0.0, 0.0]))
    assert abs(d - 0.5) < 1e-5

    # 큐브 한참 밖 (10, 0, 0) 에서 표면까지 9.5.
    _cp, d, _ti = bvh.closest_point(np.array([10.0, 0.0, 0.0]))
    assert abs(d - 9.5) < 1e-5


def test_aabb_unsigned_distances_batch() -> None:
    from core.utils.aabb import TriangleBVH
    import trimesh

    m = trimesh.creation.icosphere(subdivisions=2, radius=1.0)
    V = np.asarray(m.vertices, dtype=np.float64)
    F = np.asarray(m.faces, dtype=np.int64)
    bvh = TriangleBVH.build(V, F)

    # sphere 표면의 점 (V[0]) 거리는 0.
    d = bvh.unsigned_distances(V[:5])
    assert np.all(d < 1e-5)

    # 원점 (sphere 중심) 거리는 ≈ 1 (icosphere r=1).
    d = bvh.unsigned_distances(np.array([[0.0, 0.0, 0.0]]))
    assert 0.9 < d[0] < 1.0   # subdivided icosphere 는 내접 반지름 < 1


# ======================================================================
# Envelope
# ======================================================================


def test_envelope_contains_surface_vertex() -> None:
    from core.generator.native_tet.envelope import Envelope
    import trimesh

    m = trimesh.creation.box(extents=(1, 1, 1))
    V = np.asarray(m.vertices, dtype=np.float64)
    F = np.asarray(m.faces, dtype=np.int64)

    env = Envelope.build(V, F, eps_relative=0.01)
    # 모든 surface vertex 는 envelope 안 (거리 0).
    mask = env.contains_points(V)
    assert mask.all()


def test_envelope_rejects_far_point() -> None:
    from core.generator.native_tet.envelope import Envelope
    import trimesh

    m = trimesh.creation.box(extents=(1, 1, 1))
    V = np.asarray(m.vertices, dtype=np.float64)
    F = np.asarray(m.faces, dtype=np.int64)

    env = Envelope.build(V, F, eps_relative=0.001)
    # 큐브 밖 10 단위 거리 점은 envelope 밖.
    far = np.array([[10.0, 10.0, 10.0]])
    mask = env.contains_points(far)
    assert not mask.any()


def test_envelope_check_operation_ok() -> None:
    from core.generator.native_tet.envelope import Envelope, check_operation
    import trimesh

    m = trimesh.creation.box(extents=(1, 1, 1))
    V = np.asarray(m.vertices, dtype=np.float64)
    F = np.asarray(m.faces, dtype=np.int64)

    env = Envelope.build(V, F, eps_relative=0.01)
    ok, dist = check_operation(env, V)
    assert ok
    assert dist < env.eps


def test_envelope_project_to_surface() -> None:
    from core.generator.native_tet.envelope import Envelope
    import trimesh

    m = trimesh.creation.box(extents=(1, 1, 1))
    V = np.asarray(m.vertices, dtype=np.float64)
    F = np.asarray(m.faces, dtype=np.int64)

    env = Envelope.build(V, F)
    # 큐브 밖 점 (2, 0, 0) 의 projection 은 face x=0.5 근처.
    p = np.array([2.0, 0.0, 0.0])
    proj = env.project(p)
    # x 좌표 = 0.5 (큐브 가장 가까운 면).
    assert abs(proj[0] - 0.5) < 1e-5


# ======================================================================
# Quality / stop criterion
# ======================================================================


def test_quality_tet_shape_quality_regular_tet() -> None:
    from core.generator.native_tet.quality import tet_shape_quality

    # 정사면체 (approximate): q ≈ 1.
    pts = np.array(
        [
            [1, 1, 1], [-1, -1, 1], [-1, 1, -1], [1, -1, -1],
        ],
        dtype=np.float64,
    )
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    q = tet_shape_quality(pts, tets)
    assert q.shape == (1,)
    # 정사면체 shape quality 는 1 근처 (8.48·V/e_max^3).
    assert 0.8 < q[0] < 1.05


def test_quality_snapshot_empty() -> None:
    from core.generator.native_tet.quality import snapshot

    s = snapshot(np.zeros((0, 3)), np.zeros((0, 4), dtype=np.int64))
    assert s.n_tets == 0
    assert s.min_q == 0.0


def test_quality_should_stop_target() -> None:
    from core.generator.native_tet.quality import (
        QualitySnapshot, should_stop,
    )

    hist = [QualitySnapshot(100, 0.4, 0.5, 0.5, 3.0)]
    stop, reason = should_stop(hist, target_min_q=0.3)
    assert stop and reason == "target"


def test_quality_should_stop_plateau() -> None:
    from core.generator.native_tet.quality import (
        QualitySnapshot, should_stop,
    )

    hist = [
        QualitySnapshot(100, 0.10, 0.2, 0.2, 10.0),
        QualitySnapshot(100, 0.101, 0.2, 0.2, 10.0),
        QualitySnapshot(100, 0.102, 0.2, 0.2, 10.0),
    ]
    stop, reason = should_stop(
        hist, target_min_q=0.3, improvement_eps=0.01, window=3,
    )
    assert stop and reason == "plateau"


def test_quality_should_stop_continue() -> None:
    from core.generator.native_tet.quality import (
        QualitySnapshot, should_stop,
    )

    hist = [
        QualitySnapshot(100, 0.1, 0.2, 0.2, 10.0),
        QualitySnapshot(100, 0.2, 0.3, 0.3, 5.0),
    ]
    stop, _reason = should_stop(hist, target_min_q=0.3, window=3)
    assert not stop


# ======================================================================
# Integration — Phase C on
# ======================================================================


def test_native_tet_phase_c_runs_on_sphere(tmp_path) -> None:
    from core.generator.native_tet.mesher import generate_native_tet
    import trimesh

    m = trimesh.creation.icosphere(subdivisions=1, radius=1.0)
    V = np.asarray(m.vertices, dtype=np.float64)
    F = np.asarray(m.faces, dtype=np.int64)

    case = tmp_path / "sphere_phaseC"
    res = generate_native_tet(
        V, F, case,
        seed_density=6,
        enable_phase_a=True,
        enable_phase_b=True,
        enable_phase_c=True,
        local_ops_iterations=2,
        flip_iterations=1,
        tangent_smooth_iterations=1,
        envelope_eps_relative=0.02,
        quality_target_min_q=0.2,
    )
    assert res.success, res.message
    assert res.n_cells > 0
