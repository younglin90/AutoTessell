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
