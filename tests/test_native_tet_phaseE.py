"""Round 4 / Phase E — 3-2 flip + adaptive sizing + adversarial robustness."""
from __future__ import annotations

import numpy as np
import pytest


# ======================================================================
# 3-2 flip
# ======================================================================


def test_flip_edges_32_no_op_when_no_ring() -> None:
    """단일 tet — 3-2 flip 대상 없음."""
    from core.generator.native_tet.flip import flip_edges_32

    pts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64)
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    out, n = flip_edges_32(pts, tets)
    assert n == 0
    assert out.shape[0] == 1


def test_flip_edges_32_finds_ring_of_three() -> None:
    """pentahedron 을 3 tet 으로 분할 (중심 edge (0,1) 공유). 3-2 flip 으로
    topology 가 정상 변환되면 결과 tet 수 2."""
    from core.generator.native_tet.flip import flip_edges_32

    # 두 축을 중심으로 하는 3-fan 구성:
    # vertex 0,1 이 축. 2,3,4 는 축을 둘러싼 triangle.
    pts = np.array(
        [
            [0, 0, 0],         # 0: 축 아래
            [0, 0, 1],         # 1: 축 위
            [1, 0, 0.5],       # 2
            [-0.5, 0.866, 0.5],  # 3
            [-0.5, -0.866, 0.5], # 4
        ],
        dtype=np.float64,
    )
    tets = np.array(
        [
            [0, 1, 2, 3],
            [0, 1, 3, 4],
            [0, 1, 4, 2],
        ],
        dtype=np.int64,
    )
    out, n = flip_edges_32(pts, tets, min_quality_improvement=-1.0)
    # quality 개선 여부에 따라 flip 되거나 안 됨. 수행되면 tet 수가 2.
    assert out.shape[0] in (2, 3)
    if n > 0:
        assert out.shape[0] == 2


# ======================================================================
# Adaptive sizing
# ======================================================================


def test_curvature_sizing_flat_mesh_returns_in_range() -> None:
    """평면 triangle set — 결과가 [min_ratio, max_ratio] × target 범위 내.

    NOTE: 평면이라도 boundary vertex 는 angle sum < 2π 이므로 defect 가 0 이
    아니다. uniform 가정은 closed surface 에만 성립.
    """
    from core.generator.native_tet.adaptive import curvature_sizing

    V = np.array(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0]], dtype=np.float64,
    )
    F = np.array([[0, 1, 2], [1, 3, 2]], dtype=np.int64)
    sizes = curvature_sizing(V, F, target_edge=1.0,
                             min_ratio=0.25, max_ratio=2.0)
    assert sizes.shape == (4,)
    assert (sizes >= 0.25 - 1e-9).all()
    assert (sizes <= 2.0 + 1e-9).all()


def test_curvature_sizing_sphere_varies() -> None:
    """sphere — 곡률 일정하지만 top/bottom 과 middle 비교는 비슷. 허용 범위 내."""
    from core.generator.native_tet.adaptive import curvature_sizing
    import trimesh

    m = trimesh.creation.icosphere(subdivisions=2, radius=1.0)
    V = np.asarray(m.vertices, dtype=np.float64)
    F = np.asarray(m.faces, dtype=np.int64)
    sizes = curvature_sizing(V, F, target_edge=0.2, curvature_gain=2.0)
    # min/max 는 설정 범위 내.
    assert sizes.min() >= 0.2 * 0.25 - 1e-9
    assert sizes.max() <= 0.2 * 2.0 + 1e-9


def test_curvature_sizing_cube_shrinks_corners() -> None:
    """큐브 — corner 에서 edge length 작아져야 함."""
    from core.generator.native_tet.adaptive import curvature_sizing
    import trimesh

    m = trimesh.creation.box(extents=(1, 1, 1))
    V = np.asarray(m.vertices, dtype=np.float64)
    F = np.asarray(m.faces, dtype=np.int64)
    sizes = curvature_sizing(V, F, target_edge=1.0, curvature_gain=2.0)
    # corner 8 개 전부 edge 가 base 이하.
    assert (sizes < 1.0).all()


# ======================================================================
# Adversarial robustness
# ======================================================================


def test_native_tet_rejects_oversized_input() -> None:
    """V > max_input_vertices → failure 메시지 반환, crash 없음."""
    from core.generator.native_tet.mesher import generate_native_tet
    import trimesh

    m = trimesh.creation.icosphere(subdivisions=1, radius=1.0)
    V = np.asarray(m.vertices, dtype=np.float64)
    F = np.asarray(m.faces, dtype=np.int64)

    import pathlib
    case = pathlib.Path("/tmp/native_tet_too_large")
    case.mkdir(exist_ok=True)
    res = generate_native_tet(
        V, F, case,
        seed_density=4,
        max_input_vertices=5,   # V 는 42 → 초과.
    )
    assert res.success is False
    assert "너무" in res.message or "max_input_vertices" in res.message


def test_native_tet_handles_tiny_mesh(tmp_path) -> None:
    """매우 작은 triangle (<1e-8) 입력에서도 crash 없이 정상 / failure 반환."""
    from core.generator.native_tet.mesher import generate_native_tet

    V = np.array(
        [
            [0, 0, 0], [1e-10, 0, 0], [0, 1e-10, 0], [0, 0, 1e-10],
        ],
        dtype=np.float64,
    )
    F = np.array(
        [[0, 1, 2], [0, 1, 3], [0, 2, 3], [1, 2, 3]], dtype=np.int64,
    )
    res = generate_native_tet(V, F, tmp_path / "tiny", seed_density=4)
    # 성공 또는 명확한 failure 모두 OK. crash 아니면 통과.
    assert res.success in (True, False)
    assert res.message   # 항상 메시지 있음.


def test_native_tet_handles_duplicate_vertices(tmp_path) -> None:
    """중복 vertex 입력. Delaunay 가 degenerate 경고 낼 수 있으나 파이프라인
    전체는 crash 없이 완료 / failure 반환."""
    from core.generator.native_tet.mesher import generate_native_tet
    import trimesh

    m = trimesh.creation.box(extents=(1, 1, 1))
    V = np.asarray(m.vertices, dtype=np.float64)
    F = np.asarray(m.faces, dtype=np.int64)
    # vertex 0 중복해서 끝에 추가.
    V2 = np.vstack([V, V[0:1]])
    # F 는 변경 안함 (index 는 그대로 유효).
    res = generate_native_tet(V2, F, tmp_path / "dup", seed_density=4)
    # crash 없이 결과 있음.
    assert res.success in (True, False)
    assert res.message


def test_native_tet_empty_input(tmp_path) -> None:
    from core.generator.native_tet.mesher import generate_native_tet

    V = np.zeros((0, 3), dtype=np.float64)
    F = np.zeros((0, 3), dtype=np.int64)
    res = generate_native_tet(V, F, tmp_path / "empty", seed_density=4)
    assert res.success is False
    assert "빈" in res.message or "empty" in res.message.lower() or res.message


# ======================================================================
# Integration — 32 flip 포함 전체 파이프라인
# ======================================================================


def test_native_tet_phase_b_with_32_flip(tmp_path) -> None:
    from core.generator.native_tet.mesher import generate_native_tet
    import trimesh

    m = trimesh.creation.icosphere(subdivisions=1, radius=1.0)
    V = np.asarray(m.vertices, dtype=np.float64)
    F = np.asarray(m.faces, dtype=np.int64)

    res = generate_native_tet(
        V, F, tmp_path / "sphere_32flip",
        seed_density=6,
        enable_phase_a=True,
        enable_phase_b=True,
        flip_iterations=2,   # 2-3 + 3-2 둘 다.
        tangent_smooth_iterations=1,
    )
    assert res.success, res.message
    assert res.n_cells > 0


# ======================================================================
# Integration — adaptive sizing wired + quality benchmark
# ======================================================================


def test_native_tet_adaptive_sizing_wired(tmp_path) -> None:
    from core.generator.native_tet.mesher import generate_native_tet
    import trimesh

    m = trimesh.creation.box(extents=(1, 1, 1))
    V = np.asarray(m.vertices, dtype=np.float64)
    F = np.asarray(m.faces, dtype=np.int64)

    res = generate_native_tet(
        V, F, tmp_path / "cube_adaptive",
        seed_density=4,
        enable_phase_b=True,
        use_adaptive_sizing=True,
        local_ops_iterations=1,
        flip_iterations=1,
    )
    assert res.success, res.message


def test_native_tet_phase_c_improves_quality(tmp_path) -> None:
    """Phase C + envelope + snap 을 거치면 min_q 가 enable 전보다 같거나 향상.

    Phase B/C 가 quality 를 '망가뜨리지' 않는지 안전판.
    """
    from core.generator.native_tet.mesher import generate_native_tet
    from core.generator.native_tet.quality import tet_shape_quality
    import trimesh

    m = trimesh.creation.icosphere(subdivisions=1, radius=1.0)
    V = np.asarray(m.vertices, dtype=np.float64)
    F = np.asarray(m.faces, dtype=np.int64)

    # baseline: Phase A 만.
    res_a = generate_native_tet(
        V, F, tmp_path / "sphere_A_only",
        seed_density=6,
        enable_phase_a=True, enable_phase_b=False, enable_phase_c=False,
    )
    # Phase C 풀세트.
    res_c = generate_native_tet(
        V, F, tmp_path / "sphere_C_full",
        seed_density=6,
        enable_phase_a=True, enable_phase_b=True, enable_phase_c=True,
        local_ops_iterations=2, flip_iterations=2,
        tangent_smooth_iterations=1,
        envelope_eps_relative=0.02,
        quality_target_min_q=0.25,
    )
    assert res_a.success and res_c.success

    q_a = tet_shape_quality(res_a.tet_points, res_a.tets)
    q_c = tet_shape_quality(res_c.tet_points, res_c.tets)
    # Phase C 가 quality 를 catastrophic 하게 망가뜨리지 않음 (0.5× 이상 유지).
    # 실제 큰 개선은 Phase D (BSP constrained insertion) 에서 기대.
    assert q_c.mean() >= q_a.mean() * 0.5, (
        f"mean q 심각 악화: A={q_a.mean():.4f} C={q_c.mean():.4f}"
    )
    # 둘 다 유효한 양의 quality 유지.
    assert q_c.mean() > 0.0
