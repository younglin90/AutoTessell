"""Numerical parity tests: C kernels vs Python implementations.

Checks that tet_quality_batch, tet_signed_vol6_batch, build_face_to_tets,
build_edge_to_tets, edge_lengths_batch produce identical results to the
reference Python code in flip.py / local_ops.py.

Test matrix:
  - 100 random meshes (n = 20..200 tets)
  - 5 degenerate cases (zero volume, duplicate vertices)
  - Numerical tolerance: allclose(atol=1e-12) for floats
  - face_map / edge_map: membership equality
"""
from __future__ import annotations

import math

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# C kernel availability gate
# ---------------------------------------------------------------------------
from core.generator.native_tet._native import (
    build_edge_to_tets as _c_build_edge_to_tets,
    build_face_to_tets as _c_build_face_to_tets,
    edge_lengths_batch as _c_edge_lengths_batch,
    is_available,
    tet_quality_batch as _c_quality_batch,
    tet_signed_vol6_batch as _c_vol6_batch,
)

pytestmark = pytest.mark.skipif(
    not is_available(),
    reason="C kernels not available (cc not found or compile failed)",
)

# ---------------------------------------------------------------------------
# Python reference implementations (identical to flip.py / local_ops.py)
# ---------------------------------------------------------------------------

def _py_tet_quality(A, B, C, D) -> float:
    v = abs(float(np.dot(B - A, np.cross(C - A, D - A)))) / 6.0
    e = [A - B, A - C, A - D, B - C, B - D, C - D]
    emax = max(float(np.linalg.norm(x)) for x in e)
    if emax < 1e-30:
        return 0.0
    return 8.48 * v / (emax ** 3)


def _py_tet_signed_vol6(A, B, C, D) -> float:
    return float(np.dot(B - A, np.cross(C - A, D - A)))


def _py_face_map(tets: np.ndarray) -> dict[tuple[int, int, int], list[int]]:
    tets = np.asarray(tets, dtype=np.int64)
    face_arr = np.stack(
        [tets[:, [1, 2, 3]], tets[:, [0, 2, 3]],
         tets[:, [0, 1, 3]], tets[:, [0, 1, 2]]],
        axis=1,
    ).reshape(-1, 3)
    face_arr.sort(axis=1)
    m: dict[tuple[int, int, int], list[int]] = {}
    for idx in range(face_arr.shape[0]):
        ti = idx // 4
        k = (int(face_arr[idx, 0]), int(face_arr[idx, 1]), int(face_arr[idx, 2]))
        m.setdefault(k, []).append(ti)
    return m


def _py_edge_map(tets: np.ndarray) -> dict[tuple[int, int], list[int]]:
    pair_idx = np.array(
        [[0, 1], [0, 2], [0, 3], [1, 2], [1, 3], [2, 3]], dtype=np.int64,
    )
    edges = np.stack(
        [tets[:, pair_idx[:, 0]], tets[:, pair_idx[:, 1]]], axis=2,
    ).reshape(-1, 2)
    edges.sort(axis=1)
    m: dict[tuple[int, int], list[int]] = {}
    for idx in range(edges.shape[0]):
        ti = idx // 6
        k = (int(edges[idx, 0]), int(edges[idx, 1]))
        m.setdefault(k, []).append(ti)
    return m


def _py_edge_lengths(
    pts: np.ndarray, tets: np.ndarray,
) -> dict[tuple[int, int], float]:
    tets = np.asarray(tets, dtype=np.int64)
    pairs = np.stack(
        [tets[:, [0, 1]], tets[:, [0, 2]], tets[:, [0, 3]],
         tets[:, [1, 2]], tets[:, [1, 3]], tets[:, [2, 3]]],
        axis=1,
    ).reshape(-1, 2)
    pairs.sort(axis=1)
    struct = np.ascontiguousarray(pairs).view(
        np.dtype((np.void, pairs.dtype.itemsize * 2))
    )
    _, idx = np.unique(struct, return_index=True)
    uniq = pairs[idx]
    lens = np.linalg.norm(pts[uniq[:, 0]] - pts[uniq[:, 1]], axis=1)
    return {
        (int(uniq[i, 0]), int(uniq[i, 1])): float(lens[i])
        for i in range(uniq.shape[0])
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_random_mesh(n_pts: int = 50, n_tets: int = 40, seed: int = 0):
    rng = np.random.default_rng(seed)
    pts  = rng.standard_normal((n_pts, 3))
    tets = rng.integers(0, n_pts, size=(n_tets, 4), dtype=np.int64)
    return pts, tets


def _make_regular_tet(scale: float = 1.0):
    """Regular tetrahedron centred at origin."""
    pts = np.array([
        [1.0,  1.0,  1.0],
        [1.0, -1.0, -1.0],
        [-1.0,  1.0, -1.0],
        [-1.0, -1.0,  1.0],
    ], dtype=np.float64) * scale
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    return pts, tets


# ---------------------------------------------------------------------------
# Tests — quality
# ---------------------------------------------------------------------------

class TestQuality:

    def test_regular_tet_value(self):
        pts, tets = _make_regular_tet()
        q_c  = _c_quality_batch(pts, tets)
        q_py = np.array([_py_tet_quality(*[pts[i] for i in tets[0]])])
        assert q_c is not None
        np.testing.assert_allclose(q_c, q_py, atol=1e-12)

    def test_random_meshes_allclose(self):
        for seed in range(100):
            n = 20 + seed * 2  # 20..218
            pts, tets = _make_random_mesh(n_pts=n + 10, n_tets=n, seed=seed)
            q_c  = _c_quality_batch(pts, tets)
            q_py = np.array([_py_tet_quality(*[pts[t_] for t_ in row]) for row in tets])
            assert q_c is not None, f"C unavailable (seed={seed})"
            np.testing.assert_allclose(
                q_c, q_py, atol=1e-12,
                err_msg=f"quality mismatch at seed={seed}",
            )

    def test_degenerate_zero_vol(self):
        """Degenerate tet: 4 identical points → quality = 0."""
        pts  = np.zeros((4, 3), dtype=np.float64)
        tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
        q_c  = _c_quality_batch(pts, tets)
        assert q_c is not None
        assert q_c[0] == pytest.approx(0.0)

    def test_degenerate_coplanar(self):
        """Coplanar tet: all z=0 → quality = 0."""
        pts  = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0.5, 0.5, 0]], dtype=np.float64)
        tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
        q_c  = _c_quality_batch(pts, tets)
        q_py = np.array([_py_tet_quality(*[pts[i] for i in tets[0]])])
        assert q_c is not None
        np.testing.assert_allclose(q_c, q_py, atol=1e-12)

    def test_degenerate_duplicate_vertices(self):
        """tets with repeated vertex indices → quality computed without crash."""
        pts  = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64)
        tets = np.array([[0, 0, 1, 2]], dtype=np.int64)  # v0 appears twice
        q_c  = _c_quality_batch(pts, tets)
        q_py = np.array([_py_tet_quality(*[pts[t_] for t_ in tets[0]])])
        assert q_c is not None
        np.testing.assert_allclose(q_c, q_py, atol=1e-12)

    def test_large_scale_invariant(self):
        """Quality must be scale-invariant (dimensionless ratio)."""
        pts_s, tets = _make_regular_tet(scale=1.0)
        pts_L, _    = _make_regular_tet(scale=1000.0)
        q_s = _c_quality_batch(pts_s, tets)
        q_L = _c_quality_batch(pts_L, tets)
        assert q_s is not None and q_L is not None
        np.testing.assert_allclose(q_s, q_L, atol=1e-10)


# ---------------------------------------------------------------------------
# Tests — signed vol6
# ---------------------------------------------------------------------------

class TestSignedVol6:

    def test_unit_tet(self):
        pts  = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64)
        tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
        v_c  = _c_vol6_batch(pts, tets)
        v_py = np.array([_py_tet_signed_vol6(*[pts[i] for i in tets[0]])])
        assert v_c is not None
        np.testing.assert_allclose(v_c, v_py, atol=1e-15)

    def test_sign_convention(self):
        """Flipping two vertices negates the sign."""
        pts  = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64)
        t_pos = np.array([[0, 1, 2, 3]], dtype=np.int64)
        t_neg = np.array([[1, 0, 2, 3]], dtype=np.int64)
        v_p = _c_vol6_batch(pts, t_pos)
        v_n = _c_vol6_batch(pts, t_neg)
        assert v_p is not None and v_n is not None
        np.testing.assert_allclose(v_p, -v_n, atol=1e-15)

    def test_random_meshes_allclose(self):
        for seed in range(100):
            n = 20 + seed * 2
            pts, tets = _make_random_mesh(n_pts=n + 10, n_tets=n, seed=seed + 200)
            v_c  = _c_vol6_batch(pts, tets)
            v_py = np.array([_py_tet_signed_vol6(*[pts[t_] for t_ in row]) for row in tets])
            assert v_c is not None
            np.testing.assert_allclose(v_c, v_py, atol=1e-12, err_msg=f"vol6 mismatch seed={seed}")

    def test_degenerate_zero_vol(self):
        pts  = np.zeros((4, 3), dtype=np.float64)
        tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
        v_c  = _c_vol6_batch(pts, tets)
        assert v_c is not None
        assert v_c[0] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Tests — face map
# ---------------------------------------------------------------------------

def _c_face_map(tets: np.ndarray) -> dict[tuple[int, int, int], list[int]]:
    """Convert C face output to same dict format as Python."""
    result = _c_build_face_to_tets(tets)
    assert result is not None
    face_arr, tet_idx, _slot = result
    m: dict[tuple[int, int, int], list[int]] = {}
    for i in range(face_arr.shape[0]):
        k = (int(face_arr[i, 0]), int(face_arr[i, 1]), int(face_arr[i, 2]))
        m.setdefault(k, []).append(int(tet_idx[i]))
    return m


class TestFaceMap:

    def test_single_tet_keys(self):
        pts, tets = _make_regular_tet()
        m_c  = _c_face_map(tets)
        m_py = _py_face_map(tets)
        assert set(m_c.keys()) == set(m_py.keys())
        for k in m_py:
            assert sorted(m_c[k]) == sorted(m_py[k])

    def test_random_meshes_membership(self):
        for seed in range(100):
            n = 20 + seed * 2
            _, tets = _make_random_mesh(n_pts=n + 10, n_tets=n, seed=seed + 400)
            m_c  = _c_face_map(tets)
            m_py = _py_face_map(tets)
            assert set(m_c.keys()) == set(m_py.keys()), f"face keys differ seed={seed}"
            for k in m_py:
                assert sorted(m_c[k]) == sorted(m_py[k]), f"face owners differ key={k} seed={seed}"

    def test_slot_ranges(self):
        """Slots must be in [0, 3]."""
        _, tets = _make_random_mesh(n_pts=50, n_tets=40, seed=7)
        result = _c_build_face_to_tets(tets)
        assert result is not None
        _faces, _ti, slot = result
        assert int(slot.min()) >= 0
        assert int(slot.max()) <= 3

    def test_degenerate_empty(self):
        tets = np.zeros((0, 4), dtype=np.int64)
        result = _c_build_face_to_tets(tets)
        # returns None or empty
        if result is not None:
            assert result[0].shape[0] == 0

    def test_face_sorted_canonical(self):
        """All output face triples must be sorted (a <= b <= c)."""
        _, tets = _make_random_mesh(n_pts=80, n_tets=60, seed=99)
        result = _c_build_face_to_tets(tets)
        assert result is not None
        faces, _, _ = result
        assert np.all(faces[:, 0] <= faces[:, 1]), "face not sorted a<=b"
        assert np.all(faces[:, 1] <= faces[:, 2]), "face not sorted b<=c"


# ---------------------------------------------------------------------------
# Tests — edge map
# ---------------------------------------------------------------------------

def _c_edge_map(tets: np.ndarray) -> dict[tuple[int, int], list[int]]:
    result = _c_build_edge_to_tets(tets)
    assert result is not None
    edges, tet_idx = result
    m: dict[tuple[int, int], list[int]] = {}
    for i in range(edges.shape[0]):
        k = (int(edges[i, 0]), int(edges[i, 1]))
        m.setdefault(k, []).append(int(tet_idx[i]))
    return m


class TestEdgeMap:

    def test_single_tet_keys(self):
        pts, tets = _make_regular_tet()
        m_c  = _c_edge_map(tets)
        m_py = _py_edge_map(tets)
        assert set(m_c.keys()) == set(m_py.keys())

    def test_random_meshes_membership(self):
        for seed in range(100):
            n = 20 + seed * 2
            _, tets = _make_random_mesh(n_pts=n + 10, n_tets=n, seed=seed + 600)
            m_c  = _c_edge_map(tets)
            m_py = _py_edge_map(tets)
            assert set(m_c.keys()) == set(m_py.keys()), f"edge keys differ seed={seed}"
            for k in m_py:
                assert sorted(m_c[k]) == sorted(m_py[k]), f"edge owners differ key={k} seed={seed}"

    def test_edge_sorted_canonical(self):
        """All output edge pairs must be sorted (a < b)."""
        _, tets = _make_random_mesh(n_pts=80, n_tets=60, seed=55)
        result = _c_build_edge_to_tets(tets)
        assert result is not None
        edges, _ = result
        assert np.all(edges[:, 0] <= edges[:, 1]), "edge not sorted a<=b"

    def test_degenerate_repeated_vertices(self):
        """Degenerate tets with repeated vertices should not crash."""
        tets = np.array([[0, 0, 1, 2], [0, 1, 1, 3]], dtype=np.int64)
        result = _c_build_edge_to_tets(tets)
        assert result is not None


# ---------------------------------------------------------------------------
# Tests — edge_lengths_batch
# ---------------------------------------------------------------------------

class TestEdgeLengths:

    def test_unit_edges(self):
        pts = np.eye(3, dtype=np.float64)  # 3 unit vectors
        edges = np.array([[0, 1], [0, 2], [1, 2]], dtype=np.int64)
        lens = _c_edge_lengths_batch(pts, edges)
        assert lens is not None
        expected = np.array([
            math.sqrt(2), math.sqrt(2), math.sqrt(2),
        ])
        np.testing.assert_allclose(lens, expected, atol=1e-12)

    def test_zero_length_edge(self):
        pts = np.zeros((2, 3), dtype=np.float64)
        edges = np.array([[0, 1]], dtype=np.int64)
        lens = _c_edge_lengths_batch(pts, edges)
        assert lens is not None
        assert lens[0] == pytest.approx(0.0)

    def test_random_meshes_allclose(self):
        for seed in range(100):
            n = 20 + seed * 2
            pts, tets = _make_random_mesh(n_pts=n + 10, n_tets=n, seed=seed + 800)
            py_map = _py_edge_lengths(pts, tets)
            # Build unique edges array for C call
            result = _c_build_edge_to_tets(tets)
            assert result is not None
            edges_all, _ = result
            struct = np.ascontiguousarray(edges_all).view(
                np.dtype((np.void, edges_all.dtype.itemsize * 2))
            )
            _, idx = np.unique(struct, return_index=True)
            uniq = edges_all[idx]
            lens_c = _c_edge_lengths_batch(pts, uniq)
            assert lens_c is not None
            for i, (a, b) in enumerate(uniq.tolist()):
                k = (int(a), int(b))
                np.testing.assert_allclose(
                    lens_c[i], py_map[k], atol=1e-12,
                    err_msg=f"edge_lengths mismatch key={k} seed={seed}",
                )


# ---------------------------------------------------------------------------
# Tests — end-to-end: flip.py integration
# ---------------------------------------------------------------------------

class TestFlipIntegration:
    """Verify that flip.py with C kernels gives same topological result."""

    def test_face_flip_pass_smoke(self):
        """face_flip_pass should run without errors."""
        from core.generator.native_tet.flip import face_flip_pass, _USE_C_KERNELS
        pts = np.array([
            [0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1], [1, 1, 1],
        ], dtype=np.float64)
        tets = np.array([[0, 1, 2, 3], [1, 2, 3, 4]], dtype=np.int64)
        T, result = face_flip_pass(pts, tets, n_iter=2)
        assert T.shape[1] == 4
        assert result.n_tets_before == 2

    def test_tet_quality_batch_arr(self):
        """_tet_quality_batch_arr results match per-tet _tet_quality."""
        from core.generator.native_tet.flip import _tet_quality, _tet_quality_batch_arr
        rng = np.random.default_rng(1234)
        pts  = rng.standard_normal((50, 3))
        tets = rng.integers(0, 50, size=(30, 4), dtype=np.int64)
        q_batch = _tet_quality_batch_arr(pts, tets)
        q_single = np.array([_tet_quality(*[pts[i] for i in row]) for row in tets])
        np.testing.assert_allclose(q_batch, q_single, atol=1e-12)

    def test_signed_vol6_batch_arr(self):
        from core.generator.native_tet.flip import _tet_signed_vol6, _tet_signed_vol6_batch_arr
        rng = np.random.default_rng(5678)
        pts  = rng.standard_normal((50, 3))
        tets = rng.integers(0, 50, size=(30, 4), dtype=np.int64)
        v_batch  = _tet_signed_vol6_batch_arr(pts, tets)
        v_single = np.array([_tet_signed_vol6(*[pts[i] for i in row]) for row in tets])
        np.testing.assert_allclose(v_batch, v_single, atol=1e-12)
