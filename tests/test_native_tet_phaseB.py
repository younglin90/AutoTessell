"""Phase B 단위 + 통합 테스트 (beta120 TetWild-lite 2 단계)."""
from __future__ import annotations

import numpy as np
import pytest


# ======================================================================
# Unit — adjacency
# ======================================================================


def test_adjacency_build_single_tet() -> None:
    from core.generator.native_tet.adjacency import TetAdjacency

    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    adj = TetAdjacency.build(tets)
    # 4 faces, 6 edges, 4 vertices.
    assert len(adj.face_to_tets) == 4
    assert len(adj.edge_to_tets) == 6
    assert len(adj.vertex_to_tets) == 4
    # 한 tet 만 있으므로 모든 face 가 boundary.
    assert len(adj.boundary_faces()) == 4


def test_adjacency_shared_face_two_tets() -> None:
    from core.generator.native_tet.adjacency import TetAdjacency

    # 두 tet 이 face (0,1,2) 공유.
    tets = np.array([[0, 1, 2, 3], [0, 1, 2, 4]], dtype=np.int64)
    adj = TetAdjacency.build(tets)
    # face (0,1,2) 는 2 owner.
    assert len(adj.face_to_tets[(0, 1, 2)]) == 2
    # boundary face 는 6 (= 4+4 - 2공유).
    assert len(adj.boundary_faces()) == 6


# ======================================================================
# Unit — local_ops.split_long_edges
# ======================================================================


def test_split_long_edges_noop_when_short() -> None:
    from core.generator.native_tet.local_ops import split_long_edges

    # 단위 tet. edge 길이 ~1. target=2 면 split 없음.
    pts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64)
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    new_pts, new_tets, n_split = split_long_edges(
        pts, tets, target_edge=2.0, ratio=4.0 / 3.0,
    )
    assert n_split == 0
    assert new_tets.shape[0] == 1


def test_split_long_edges_splits_when_long() -> None:
    from core.generator.native_tet.local_ops import split_long_edges

    pts = np.array([[0, 0, 0], [10, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64)
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    # target=1, ratio=1.2 → threshold=1.2. edge(0-1)=10 > 1.2 → split.
    new_pts, new_tets, n_split = split_long_edges(
        pts, tets, target_edge=1.0, ratio=1.2,
    )
    assert n_split >= 1
    # split 후 tet 수는 2 이상 (1→2 per split).
    assert new_tets.shape[0] >= 2


# ======================================================================
# Unit — local_ops.collapse_short_edges
# ======================================================================


def test_collapse_short_edges_noop_when_long() -> None:
    from core.generator.native_tet.local_ops import collapse_short_edges

    pts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64)
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    new_pts, new_tets, n_c = collapse_short_edges(
        pts, tets, target_edge=0.5, ratio=4.0 / 5.0,
    )
    assert n_c == 0


def test_collapse_short_edges_skips_both_locked() -> None:
    """둘 다 locked 인 edge 는 collapse 안 됨."""
    from core.generator.native_tet.local_ops import collapse_short_edges

    pts = np.array(
        [[0, 0, 0], [0.01, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64,
    )
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    # target=1, ratio=0.8 → thresh=0.8. edge(0-1)=0.01 < 0.8 → short.
    # 하지만 둘 다 locked → no collapse.
    new_pts, new_tets, n_c = collapse_short_edges(
        pts, tets, target_edge=1.0, ratio=0.8,
        locked_vertices=np.array([0, 1], dtype=np.int64),
    )
    assert n_c == 0


# ======================================================================
# Unit — flip.flip_faces_23
# ======================================================================


def test_flip_faces_23_returns_valid_tets() -> None:
    """단일 face 공유 2 tet → 2-3 flip 유효성."""
    from core.generator.native_tet.flip import flip_faces_23

    # bi-pyramid: face (0,1,2) 공유, apex 3 과 4.
    pts = np.array(
        [
            [0, 0, 0], [1, 0, 0], [0.5, 0.866, 0],     # base triangle
            [0.5, 0.289, 0.6],                          # apex top
            [0.5, 0.289, -0.6],                         # apex bottom
        ],
        dtype=np.float64,
    )
    tets = np.array([[0, 1, 2, 3], [0, 1, 2, 4]], dtype=np.int64)
    out, n = flip_faces_23(pts, tets, min_quality_improvement=-1.0)
    # 원본 2 tet 또는 flip 후 3 tet.
    assert out.shape[0] in (2, 3)
    if n > 0:
        assert out.shape[0] == 3


# ======================================================================
# Unit — smooth.smooth_tangent_surface
# ======================================================================


def test_smooth_tangent_surface_keeps_on_plane() -> None:
    """평평한 surface 의 vertex 는 normal 방향으로 움직이지 않음."""
    from core.generator.native_tet.smooth import smooth_tangent_surface

    # xy 평면 위의 4 vertex + interior 1.
    pts = np.array(
        [
            [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
            [0.5, 0.5, 1],
        ],
        dtype=np.float64,
    )
    tets = np.array(
        [[0, 1, 2, 4], [0, 2, 3, 4]], dtype=np.int64,
    )
    # surface 는 0..3, normal 은 +z.
    vn = np.tile(np.array([0, 0, 1.0]), (5, 1))
    original = pts.copy()
    smooth_tangent_surface(
        pts, tets,
        surface_vertex_ids=np.array([0, 1, 2, 3], dtype=np.int64),
        vertex_normals=vn,
        n_iter=3, relax=0.5,
    )
    # surface vertex 는 z=0 유지.
    assert np.allclose(pts[:4, 2], original[:4, 2])


# ======================================================================
# Integration — generate_native_tet Phase B on
# ======================================================================


def test_native_tet_phase_b_runs_on_cube(tmp_path) -> None:
    from core.generator.native_tet.mesher import generate_native_tet
    import trimesh

    m = trimesh.creation.box(extents=(1, 1, 1))
    V = np.asarray(m.vertices, dtype=np.float64)
    F = np.asarray(m.faces, dtype=np.int64)

    case = tmp_path / "cube_phaseB"
    res = generate_native_tet(
        V, F, case,
        seed_density=4,
        enable_phase_a=True,
        enable_phase_b=True,
        local_ops_iterations=1,
        flip_iterations=1,
        tangent_smooth_iterations=1,
    )
    assert res.success, res.message
    assert res.n_cells > 0


def test_native_tet_phase_b_off_legacy(tmp_path) -> None:
    from core.generator.native_tet.mesher import generate_native_tet
    import trimesh

    m = trimesh.creation.icosphere(subdivisions=1, radius=1.0)
    V = np.asarray(m.vertices, dtype=np.float64)
    F = np.asarray(m.faces, dtype=np.int64)

    case = tmp_path / "sphere_phaseA_only"
    res = generate_native_tet(
        V, F, case,
        seed_density=6,
        enable_phase_a=True,
        enable_phase_b=False,
    )
    assert res.success, res.message
    assert res.n_cells > 0


def test_native_tet_phase_b_improves_or_preserves_cell_count(tmp_path) -> None:
    """Phase B 가 cell 수를 비정상적으로 망가뜨리지 않음 (최소 sanity)."""
    from core.generator.native_tet.mesher import generate_native_tet
    import trimesh

    m = trimesh.creation.icosphere(subdivisions=2, radius=1.0)
    V = np.asarray(m.vertices, dtype=np.float64)
    F = np.asarray(m.faces, dtype=np.int64)

    case_a = tmp_path / "sphere_A"
    case_b = tmp_path / "sphere_B"
    res_a = generate_native_tet(
        V, F, case_a, seed_density=8,
        enable_phase_a=True, enable_phase_b=False,
    )
    res_b = generate_native_tet(
        V, F, case_b, seed_density=8,
        enable_phase_a=True, enable_phase_b=True,
        local_ops_iterations=1, flip_iterations=1,
        tangent_smooth_iterations=1,
    )
    assert res_a.success and res_b.success
    # Phase B 가 cell 수 반토막 이하로 깎거나 10 배로 부풀리지 않아야 한다.
    assert res_b.n_cells > res_a.n_cells * 0.3
    assert res_b.n_cells < res_a.n_cells * 10


def test_collapse_short_edges_default_locks_surface_vertex() -> None:
    """beta2309 — allow_surface_keeper=False (default) → surface vertex 포함
    edge collapse 가 reject (Round 66 보존성 backward 호환).
    """
    from core.generator.native_tet.local_ops import collapse_short_edges
    pts = np.array(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0.05, 0.05, 0.5]],
        dtype=np.float64,
    )
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    locked = np.array([0, 1, 2], dtype=np.int64)  # surface lock.

    _, _, n_c = collapse_short_edges(
        pts, tets, target_edge=2.0, ratio=1.0,
        locked_vertices=locked,
    )
    assert n_c == 0, "default 에서 surface-involving collapse 가 일어남"


def test_collapse_short_edges_allow_surface_keeper_unlocks_ftetwild_3_4() -> None:
    """beta2309 — allow_surface_keeper=True 시 surface→interior collapse 활성.

    fTetWild §3.4 동등: surface vertex 가 keeper (위치 불변), interior vertex
    가 victim. envelope check 없이도 surface 위치 보존."""
    from core.generator.native_tet.local_ops import collapse_short_edges
    pts = np.array(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0],
         [0.05, 0.05, 0.5],  # interior, near surface vertex 0.
         [1, 1, 1]],
        dtype=np.float64,
    )
    tets = np.array(
        [[0, 1, 2, 3], [1, 2, 4, 3]],
        dtype=np.int64,
    )
    locked = np.array([0, 1, 2, 4], dtype=np.int64)

    new_pts, _, n_c = collapse_short_edges(
        pts, tets, target_edge=2.0, ratio=1.0,
        locked_vertices=locked,
        allow_surface_keeper=True,
    )
    assert n_c >= 1, "surface→interior collapse 가 발생해야 함"
    # surface vertex 0 의 위치는 변경되지 않음 (line 339-340 guard).
    assert np.allclose(new_pts[0], pts[0]), "surface vertex 0 위치가 변경됨"
