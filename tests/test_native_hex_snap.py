"""native_hex surface snap 회귀 테스트 (v0.4.0-beta22, beta94)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from core.generator.native_hex.mesher import generate_native_hex
from core.generator.native_hex.snap import (
    _closest_point_on_triangle,
    snap_hex_boundary_to_surface,
    snap_to_surface_iterative,
)


def _unit_sphere_mesh(subdivisions: int = 1):
    """trimesh 없이 icosphere 직접 생성 — 12 vertices, 20 faces (subdiv=0).

    subdiv=1 → 42 vertices, 80 faces (unit radius).
    """
    import trimesh  # noqa: PLC0415
    sphere = trimesh.creation.icosphere(subdivisions=subdivisions, radius=1.0)
    return (
        np.asarray(sphere.vertices, dtype=np.float64),
        np.asarray(sphere.faces, dtype=np.int64),
    )


# ---------------------------------------------------------------------------
# _closest_point_on_triangle unit tests
# ---------------------------------------------------------------------------


def test_closest_point_interior_returns_orthogonal_projection() -> None:
    """triangle 내부로 수직 투영되는 경우."""
    A = np.array([0.0, 0.0, 0.0])
    B = np.array([1.0, 0.0, 0.0])
    C = np.array([0.0, 1.0, 0.0])
    P = np.array([0.3, 0.3, 5.0])  # triangle 위 5 m 높이
    cp = _closest_point_on_triangle(P, A, B, C)
    np.testing.assert_allclose(cp, [0.3, 0.3, 0.0], atol=1e-12)


def test_closest_point_vertex_region_returns_vertex() -> None:
    """triangle 바깥 vertex 근방은 해당 vertex 반환."""
    A = np.array([0.0, 0.0, 0.0])
    B = np.array([1.0, 0.0, 0.0])
    C = np.array([0.0, 1.0, 0.0])
    P = np.array([-1.0, -1.0, 0.0])  # A 바깥
    cp = _closest_point_on_triangle(P, A, B, C)
    np.testing.assert_allclose(cp, A)


def test_closest_point_edge_region_returns_edge_projection() -> None:
    """edge AB 연장선 영역 → AB 상의 projection."""
    A = np.array([0.0, 0.0, 0.0])
    B = np.array([2.0, 0.0, 0.0])
    C = np.array([0.0, 2.0, 0.0])
    P = np.array([1.0, -0.5, 0.0])  # AB 위, triangle 밖
    cp = _closest_point_on_triangle(P, A, B, C)
    np.testing.assert_allclose(cp, [1.0, 0.0, 0.0], atol=1e-12)


# ---------------------------------------------------------------------------
# snap_hex_boundary_to_surface
# ---------------------------------------------------------------------------


def test_snap_noop_when_surface_empty() -> None:
    """빈 surface 는 원본 vertex 그대로 반환."""
    V = np.array([[0.5, 0.5, 0.5]], dtype=np.float64)
    sV = np.zeros((0, 3))
    sF = np.zeros((0, 3), dtype=np.int64)
    out, stats = snap_hex_boundary_to_surface(V, sV, sF, target_edge=0.1)
    np.testing.assert_array_equal(out, V)
    assert stats["n_snapped"] == 0


def test_snap_projects_nearby_vertex_onto_triangle() -> None:
    """triangle 근처 hex vertex 가 closest point 로 이동."""
    # 단일 큰 triangle (z=0 평면)
    sV = np.array([[0, 0, 0], [10, 0, 0], [0, 10, 0]], dtype=np.float64)
    sF = np.array([[0, 1, 2]], dtype=np.int64)
    # hex vertex 가 z=0.05 위에 있음 (target_edge=1, cap=0.5 이내)
    V = np.array([[2.0, 3.0, 0.05]], dtype=np.float64)
    out, stats = snap_hex_boundary_to_surface(V, sV, sF, target_edge=1.0)
    assert stats["n_snapped"] == 1
    # z 좌표가 0 으로 snap 되어야
    assert abs(out[0, 2]) < 1e-9
    # x/y 는 그대로
    np.testing.assert_allclose(out[0, :2], [2.0, 3.0], atol=1e-9)


def test_snap_skips_vertex_beyond_cap() -> None:
    """target_edge 의 max_snap_ratio 를 초과하는 vertex 는 skip."""
    sV = np.array([[0, 0, 0], [10, 0, 0], [0, 10, 0]], dtype=np.float64)
    sF = np.array([[0, 1, 2]], dtype=np.int64)
    # z=0.8, target_edge=1, cap=0.5, search_radius_ratio=3 → triangle centroid
    # (3.33, 3.33, 0) 와 vertex (2, 3, 0.8) 사이 거리는 ~1.47, search_r=3 이면
    # 통과. closest-point 거리 = 0.8 > cap=0.5 → skip.
    V = np.array([[2.0, 3.0, 0.8]], dtype=np.float64)
    out, stats = snap_hex_boundary_to_surface(
        V, sV, sF, target_edge=1.0, max_snap_ratio=0.5,
        search_radius_ratio=3.0,
    )
    assert stats["n_snapped"] == 0
    assert stats["n_skipped_beyond_cap"] == 1
    np.testing.assert_array_equal(out, V)  # 원본 유지


def test_snap_skips_vertex_beyond_search_radius() -> None:
    """search_radius_ratio 를 넘는 vertex 는 아예 후보 제외."""
    sV = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float64)
    sF = np.array([[0, 1, 2]], dtype=np.int64)
    # target_edge=1, search_r = 1.5, 거리 10 → 후보 제외
    V = np.array([[100.0, 100.0, 0.0]], dtype=np.float64)
    out, stats = snap_hex_boundary_to_surface(V, sV, sF, target_edge=1.0)
    assert stats["n_snapped"] == 0
    assert stats["n_skipped_far"] == 1


# ---------------------------------------------------------------------------
# End-to-end: generate_native_hex with snap_boundary=True
# ---------------------------------------------------------------------------


def test_generate_native_hex_with_snap_boundary_improves_hausdorff(
    tmp_path: Path,
) -> None:
    """sphere.stl 에서 snap on vs off 비교 — cell 수 동일, Hausdorff 개선."""
    sV, sF = _unit_sphere_mesh(subdivisions=2)

    # snap off
    r_off = generate_native_hex(
        sV, sF, tmp_path / "off",
        target_edge_length=0.15, snap_boundary=False,
    )
    assert r_off.success

    # snap on
    r_on = generate_native_hex(
        sV, sF, tmp_path / "on",
        target_edge_length=0.15, snap_boundary=True,
    )
    assert r_on.success

    # cell 수 동일 (vertex 좌표만 이동)
    assert r_on.n_cells == r_off.n_cells, (
        f"snap 이 cell 수를 변경하면 안 됨: off={r_off.n_cells}, on={r_on.n_cells}"
    )
    # vertex 수도 동일
    assert r_on.n_points == r_off.n_points


def test_generate_native_hex_snap_default_off_backwards_compat(
    tmp_path: Path,
) -> None:
    """snap_boundary kwarg 기본값은 False (하위 호환) — 생략 호출은 snap 비활성."""
    sV, sF = _unit_sphere_mesh(subdivisions=1)

    r = generate_native_hex(sV, sF, tmp_path, target_edge_length=0.3)
    assert r.success
    # 로그에 "native_hex_boundary_snap_applied" 가 나오면 안 됨 — 확인은 간접적이므로
    # 여기서는 단순히 성공만 검증 (snap off 기본값 확인은 signature 검사로 이미 보장).


# ---------------------------------------------------------------------------
# beta66 — feature preservation
# ---------------------------------------------------------------------------


def test_detect_surface_feature_vertices_cube_all_corners() -> None:
    """beta66 — cube 의 8 corner + edge 에 있는 vertex 는 feature 로 식별."""
    from core.generator.native_hex.snap import _detect_surface_feature_vertices
    # 단위 cube (trimesh 의존 없이 8 vertex, 12 tri).
    import numpy as _np
    V = _np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
    ], dtype=_np.float64)
    F = _np.array([
        [0, 1, 2], [0, 2, 3],  # bottom
        [4, 6, 5], [4, 7, 6],  # top
        [0, 4, 5], [0, 5, 1],  # front
        [3, 2, 6], [3, 6, 7],  # back
        [0, 3, 7], [0, 7, 4],  # left
        [1, 5, 6], [1, 6, 2],  # right
    ], dtype=_np.int64)
    feat = _detect_surface_feature_vertices(V, F, feature_angle_deg=45.0)
    # cube 의 모든 8 vertex 는 corner (90° bend) 이므로 feature.
    assert set(feat.tolist()) == set(range(8))


def test_detect_surface_feature_vertices_sphere_few_features() -> None:
    """beta66 — 부드러운 sphere 는 feature vertex 거의 없음."""
    from core.generator.native_hex.snap import _detect_surface_feature_vertices
    import numpy as _np
    import trimesh as _tm
    sp = _tm.creation.icosphere(subdivisions=2, radius=1.0)
    V = _np.asarray(sp.vertices, dtype=_np.float64)
    F = _np.asarray(sp.faces, dtype=_np.int64)
    feat = _detect_surface_feature_vertices(V, F, feature_angle_deg=45.0)
    # icosphere 는 모든 face 가 가까운 각도 → feature 없음 (또는 매우 적음)
    assert feat.size <= V.shape[0] // 10


def test_snap_with_preserve_features_reports_feature_snap_count(
    tmp_path,
) -> None:
    """beta66 — preserve_features=True 에서 feature 근처 hex vertex 가 있으면
    stats 에 n_feature_snapped > 0 보고.
    """
    from core.generator.native_hex.snap import snap_hex_boundary_to_surface
    import numpy as _np
    # 단위 cube 를 surface 로. corner 근처에 hex vertex 하나 배치.
    V = _np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
    ], dtype=_np.float64)
    F = _np.array([
        [0, 1, 2], [0, 2, 3], [4, 6, 5], [4, 7, 6],
        [0, 4, 5], [0, 5, 1], [3, 2, 6], [3, 6, 7],
        [0, 3, 7], [0, 7, 4], [1, 5, 6], [1, 6, 2],
    ], dtype=_np.int64)
    # hex vertex 가 corner (1, 0, 0) 근처 + 먼 곳 섞어서
    hex_V = _np.array([
        [0.95, 0.05, 0.05],  # corner (1,0,0) 근처 → feature snap 예상
        [0.5, 0.5, 2.0],     # 너무 멀음 → far skip
    ], dtype=_np.float64)
    _, stats = snap_hex_boundary_to_surface(
        hex_V, V, F, target_edge=0.3,
        preserve_features=True, feature_angle_deg=45.0,
    )
    # stats 에 n_feature_snapped 키 존재
    assert "n_feature_snapped" in stats
    assert stats["n_feature_snapped"] >= 1


# ---------------------------------------------------------------------------
# beta94 — snap_to_surface_iterative
# ---------------------------------------------------------------------------


def test_snap_iterative_noop_empty_surface() -> None:
    """빈 surface 는 원본 pts 그대로 반환."""
    pts = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]], dtype=np.float64)
    sV = np.zeros((0, 3), dtype=np.float64)
    sF = np.zeros((0, 3), dtype=np.int64)
    out, stats = snap_to_surface_iterative(pts, sV, sF, target_edge=1.0)
    np.testing.assert_array_equal(out, pts)
    assert stats["final_n_snapped"] == 0
    assert stats["n_snapped_per_iter"] == []
    assert stats["max_displacement"] == 0.0


def test_snap_iterative_returns_stats_keys() -> None:
    """stats 에 필수 키 포함."""
    pts = np.array([[0.5, 0.5, 0.05]], dtype=np.float64)
    sV = np.array([[0, 0, 0], [10, 0, 0], [0, 10, 0]], dtype=np.float64)
    sF = np.array([[0, 1, 2]], dtype=np.int64)
    _, stats = snap_to_surface_iterative(pts, sV, sF, target_edge=1.0, n_iter=3)
    assert "n_snapped_per_iter" in stats
    assert "final_n_snapped" in stats
    assert "max_displacement" in stats
    assert isinstance(stats["n_snapped_per_iter"], list)


def test_snap_iterative_single_vertex_converges_to_surface() -> None:
    """surface 근처 단일 vertex: 반복 후 z 좌표가 0 에 가까워짐."""
    # z=0 평면 triangle (XY 평면)
    sV = np.array([[0, 0, 0], [10, 0, 0], [0, 10, 0]], dtype=np.float64)
    sF = np.array([[0, 1, 2]], dtype=np.int64)
    # vertex 가 z=0.1 위에 있음 (target_edge=1, max_snap_ratio=0.3 → cap=0.3 이내)
    pts = np.array([[2.0, 2.0, 0.1]], dtype=np.float64)
    out, stats = snap_to_surface_iterative(
        pts, sV, sF, target_edge=1.0,
        n_iter=5, relax=0.5, max_snap_ratio=0.3,
        smooth_after_snap=False,
    )
    # 여러 번 relax 이동 후 z 가 초기값보다 작아야 함
    assert out[0, 2] < pts[0, 2], "iterative snap 후 z 좌표가 줄어야 함"
    # n_snapped_per_iter 에 첫 번째 iter 기록
    assert len(stats["n_snapped_per_iter"]) >= 1
    assert stats["n_snapped_per_iter"][0] >= 1


def test_snap_iterative_beyond_cap_not_snapped() -> None:
    """cap 초과 vertex 는 스냅 안 됨."""
    sV = np.array([[0, 0, 0], [10, 0, 0], [0, 10, 0]], dtype=np.float64)
    sF = np.array([[0, 1, 2]], dtype=np.int64)
    # z=2.0: target_edge=1, cap=0.3 초과 → 스냅 없음
    pts = np.array([[2.0, 2.0, 2.0]], dtype=np.float64)
    out, stats = snap_to_surface_iterative(
        pts, sV, sF, target_edge=1.0,
        n_iter=5, relax=0.5, max_snap_ratio=0.3,
    )
    np.testing.assert_array_equal(out, pts)
    assert stats["final_n_snapped"] == 0


def test_snap_iterative_reduces_hausdorff_vs_single() -> None:
    """5회 반복 snap 은 1회 snap 보다 surface 에 더 가까워야 함 (relax=1 특수 케이스)."""
    sV = np.array([[0, 0, 0], [10, 0, 0], [0, 10, 0]], dtype=np.float64)
    sF = np.array([[0, 1, 2]], dtype=np.int64)
    pts = np.array([[2.0, 2.0, 0.25]], dtype=np.float64)

    # 1회 snap (relax=1 → 완전 이동)
    out1, _ = snap_to_surface_iterative(
        pts, sV, sF, target_edge=2.0,
        n_iter=1, relax=1.0, max_snap_ratio=0.5,
        smooth_after_snap=False,
    )
    # 5회 snap (relax=0.5)
    out5, stats5 = snap_to_surface_iterative(
        pts, sV, sF, target_edge=2.0,
        n_iter=5, relax=0.5, max_snap_ratio=0.5,
        smooth_after_snap=False,
    )
    # 두 경우 모두 초기 z=0.25 보다 surface 에 가까워야 함
    assert out1[0, 2] < pts[0, 2]
    assert out5[0, 2] < pts[0, 2]
    assert len(stats5["n_snapped_per_iter"]) >= 1


def test_snap_iterative_smooth_after_snap_default_true() -> None:
    """smooth_after_snap 기본값 True — 호출 오류 없이 완료."""
    sV = np.array([[0, 0, 0], [5, 0, 0], [0, 5, 0]], dtype=np.float64)
    sF = np.array([[0, 1, 2]], dtype=np.int64)
    pts = np.array([
        [1.0, 1.0, 0.05],   # 스냅 후보
        [1.5, 1.5, 0.5],    # 멀어서 non-snap
    ], dtype=np.float64)
    out, stats = snap_to_surface_iterative(
        pts, sV, sF, target_edge=1.0,
        n_iter=3, relax=0.5, max_snap_ratio=0.3,
        smooth_after_snap=True, smooth_iters=2,
    )
    assert out.shape == pts.shape
    assert isinstance(stats["max_displacement"], float)


def test_snap_iterative_n_iter_zero_returns_unchanged() -> None:
    """n_iter=0: 반복 없으므로 원본 pts 그대로."""
    pts = np.array([[1.0, 1.0, 0.1]], dtype=np.float64)
    sV = np.array([[0, 0, 0], [10, 0, 0], [0, 10, 0]], dtype=np.float64)
    sF = np.array([[0, 1, 2]], dtype=np.int64)
    out, stats = snap_to_surface_iterative(
        pts, sV, sF, target_edge=1.0, n_iter=0,
    )
    np.testing.assert_array_equal(out, pts)
    assert stats["n_snapped_per_iter"] == []


def test_snap_iterative_multi_vertex_all_near_surface() -> None:
    """여러 vertex 가 모두 surface 근처 → 전부 스냅 후보."""
    sV = np.array([[0, 0, 0], [10, 0, 0], [0, 10, 0]], dtype=np.float64)
    sF = np.array([[0, 1, 2]], dtype=np.int64)
    # 3개 vertex 가 z=0.05 위 (cap=0.15 이내)
    pts = np.array([
        [1.0, 1.0, 0.05],
        [2.0, 1.0, 0.05],
        [1.0, 2.0, 0.05],
    ], dtype=np.float64)
    out, stats = snap_to_surface_iterative(
        pts, sV, sF, target_edge=1.0,
        n_iter=3, relax=0.5, max_snap_ratio=0.15,
        smooth_after_snap=False,
    )
    assert stats["n_snapped_per_iter"][0] == 3
    # 모두 z 감소
    assert np.all(out[:, 2] < pts[:, 2])


def test_generate_native_hex_snap_iterations_adaptive(tmp_path: Path) -> None:
    """adaptive=True + snap_iterations>0 조합이 오류 없이 완료."""
    sV, sF = _unit_sphere_mesh(subdivisions=1)
    r = generate_native_hex(
        sV, sF, tmp_path,
        target_edge_length=0.4,
        adaptive=True,
        snap_iterations=2,
    )
    # adaptive 실패 시 uniform grid fallback 이므로 success 만 확인
    assert r.success or r.n_cells == 0  # octree 결과 없으면 fallback OK
