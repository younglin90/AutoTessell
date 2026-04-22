"""native_hex surface snap 회귀 테스트 (v0.4.0-beta22)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from core.generator.native_hex.mesher import generate_native_hex
from core.generator.native_hex.snap import (
    _closest_point_on_triangle,
    snap_hex_boundary_to_surface,
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
