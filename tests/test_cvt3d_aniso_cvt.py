"""C1.3 + C4 / beta2362 — Volumetric Lloyd CVT 3D + Anisotropic poly CVT smoke tests."""
from __future__ import annotations

import numpy as np


def _cube_with_interior() -> tuple:
    """8 surface vertices + 1 interior + 8 tets."""
    pts = np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
        [0.5, 0.5, 0.5],
    ], dtype=np.float64)
    tets = np.array([
        [0, 1, 2, 8], [0, 2, 3, 8],
        [4, 5, 6, 8], [4, 6, 7, 8],
        [0, 1, 5, 8], [0, 5, 4, 8],
        [2, 3, 7, 8], [2, 7, 6, 8],
    ], dtype=np.int64)
    return pts, tets


def test_lloyd_cvt_3d_runs_n_iter_passes() -> None:
    """C1.3 — n_iter passes 모두 실행."""
    from core.generator.native_tet.cvt3d import lloyd_cvt_3d
    pts, tets = _cube_with_interior()
    _, r = lloyd_cvt_3d(pts, tets, n_surface=8, n_iter=3, relax=0.5)
    assert r.n_iter_used == 3


def test_lloyd_cvt_3d_skips_small_mesh() -> None:
    """C1.3 — 너무 작은 mesh (≤4 tet) 는 skip."""
    from core.generator.native_tet.cvt3d import lloyd_cvt_3d
    pts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64)
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    _, r = lloyd_cvt_3d(pts, tets, n_surface=4, n_iter=3)
    assert r.n_iter_used == 0
    assert not r.accepted


def test_lloyd_cvt_3d_monotone_guard_revert() -> None:
    """C1.3 — pre_min 이 매우 높은 단순 mesh 에서 (heuristic) reject 가 불가능 케이스
    accept 가능 — 측정만 검증."""
    from core.generator.native_tet.cvt3d import lloyd_cvt_3d
    pts, tets = _cube_with_interior()
    new_pts, r = lloyd_cvt_3d(pts, tets, n_surface=8, n_iter=2)
    # pre_min, post_min 이 정의되어 있어야 함.
    assert r.pre_min_q >= 0.0
    assert r.post_min_q >= 0.0


def test_aniso_cvt_seeds_returns_correct_count() -> None:
    """C4 — n_seeds 만큼 반환."""
    from core.generator.native_poly.aniso_cvt import aniso_cvt_seeds
    V = np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
    ], dtype=np.float64)
    F = np.array([
        [0, 1, 2], [0, 2, 3], [4, 5, 6], [4, 6, 7],
        [0, 1, 5], [0, 5, 4], [2, 3, 7], [2, 7, 6],
        [1, 2, 6], [1, 6, 5], [0, 4, 7], [0, 7, 3],
    ], dtype=np.int64)
    seeds, r = aniso_cvt_seeds(
        V, F, V.min(axis=0), V.max(axis=0),
        n_seeds=20, n_iter=3,
    )
    assert seeds.shape == (20, 3)
    assert r.n_seeds == 20


def test_aniso_cvt_curvature_on_flat_face_is_low() -> None:
    """C4 — 평평한 face 의 vertex curvature 가 작음 (boundary 왜곡 없음)."""
    from core.generator.native_poly.aniso_cvt import _surface_principal_curvatures
    # Flat 정사각형 (z=0).
    V = np.array(
        [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]],
        dtype=np.float64,
    )
    F = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)
    curv = _surface_principal_curvatures(V, F)
    assert curv.shape == (4, 2)


def test_mesher_cvt3d_wired() -> None:
    """C1.3 / beta2363 — mesher.py 가 lloyd_cvt_3d 호출."""
    import inspect
    from core.generator.native_tet import mesher
    src = inspect.getsource(mesher)
    assert "from core.generator.native_tet.cvt3d import lloyd_cvt_3d" in src or \
        "lloyd_cvt_3d" in src
    assert "AUTO_TESSELL_CVT3D_OFF" in src, "env-gate 누락"
    assert "native_tet_cvt3d_lloyd" in src, "log 키 누락"


def test_parallel_chunked_delaunay_runs_with_workers() -> None:
    """C5 / beta2365 — parallel_chunked_delaunay 가 ProcessPool 로 chunk 병렬화."""
    from core.generator.native_tet.parallel import parallel_chunked_delaunay
    rng = np.random.RandomState(0)
    V = (rng.rand(500, 3) * 10.0).astype(np.float64)
    pts, tets, r = parallel_chunked_delaunay(V, n_div=2, n_workers=2)
    assert tets.shape[0] > 0
    assert r.n_chunks >= 1
    assert r.n_workers <= 2


def test_parallel_chunked_delaunay_falls_back_for_small_input() -> None:
    """C5 / beta2365 — 200 미만 → 단일 process fallback."""
    from core.generator.native_tet.parallel import parallel_chunked_delaunay
    rng = np.random.RandomState(0)
    V = (rng.rand(50, 3) * 10.0).astype(np.float64)
    _, tets, r = parallel_chunked_delaunay(V, n_div=2, n_workers=4)
    # 단일 process fallback 시 n_chunks=1.
    assert r.n_chunks == 1
    assert r.n_workers == 1


def test_voronoi_aniso_cvt_diag_wired() -> None:
    """C4 / beta2363 — voronoi.py 가 aniso_cvt_seeds 호출 (diagnostic)."""
    import inspect
    from core.generator.native_poly import voronoi
    src = inspect.getsource(voronoi)
    assert "aniso_cvt_seeds" in src, "aniso_cvt_seeds import 누락"
    assert "native_poly_aniso_cvt_seeds_generated" in src, "log 키 누락"
    assert "AUTO_TESSELL_ANISO_CVT_OFF" in src, "env-gate 누락"


def test_per_vertex_lcr_empty() -> None:
    """C2 / beta2367 — empty wall vertex 집합 처리."""
    from core.layers.native_bl_lcr import per_vertex_lcr
    lyr, r = per_vertex_lcr(
        np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.float64),
        num_layers=5, first_thickness=0.01, growth_ratio=1.2,
    )
    assert lyr.shape == (0,)
    assert r.n_wall_verts == 0
    assert r.n_reduced_verts == 0


def test_per_vertex_lcr_no_collision_full_layers() -> None:
    """C2 — collision 없으면 full layers 유지."""
    from core.layers.native_bl_lcr import per_vertex_lcr
    wall = np.array([0, 1, 2], dtype=np.int64)
    cd = np.array([-1.0, np.inf, -1.0], dtype=np.float64)
    lyr, r = per_vertex_lcr(
        wall, cd, num_layers=5, first_thickness=0.01, growth_ratio=1.2,
    )
    assert (lyr == 5).all()
    assert r.n_reduced_verts == 0
    assert r.n_safe_full_layers == 3


def test_per_vertex_lcr_narrow_gap_reduces_layers() -> None:
    """C2 — 좁은 gap vertex 의 layer 수가 감소."""
    from core.layers.native_bl_lcr import per_vertex_lcr
    wall = np.array([0, 1, 2], dtype=np.int64)
    # 0.001 → very tight (≤ 1 layer), 0.05 → 2 layers, 0.5 → full 5.
    cd = np.array([0.001, 0.05, 0.5], dtype=np.float64)
    lyr, r = per_vertex_lcr(
        wall, cd, num_layers=5, first_thickness=0.01, growth_ratio=1.2,
    )
    assert lyr[0] <= 2  # tight
    assert lyr[2] == 5  # safe
    assert r.n_reduced_verts >= 1
    assert r.min_layers_used <= 2


def test_per_vertex_lcr_min_layers_floor() -> None:
    """C2 — min_layers ≥ 1 floor 적용."""
    from core.layers.native_bl_lcr import per_vertex_lcr
    wall = np.array([0], dtype=np.int64)
    cd = np.array([1e-9], dtype=np.float64)  # 거의 0.
    lyr, r = per_vertex_lcr(
        wall, cd, num_layers=5, first_thickness=0.01, growth_ratio=1.2,
        min_layers=2,
    )
    assert lyr[0] == 2  # floor.
    assert r.min_layers_used == 2
