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
    build_tet_face_adjacency_stats as _c_build_tet_face_adjacency_stats,
    build_face_to_tets as _c_build_face_to_tets,
    bl_prism_quality_stats_batch as _c_bl_prism_quality_stats_batch,
    closest_points_on_triangles_candidates_batch as _c_closest_points_on_triangles_candidates_batch,
    detect_degenerate_tets_stats as _c_detect_degenerate_tets_stats,
    edge_lengths_batch as _c_edge_lengths_batch,
    hex_face_area_stats_batch as _c_hex_face_area_stats_batch,
    hex_inverted_stats_batch as _c_hex_inverted_stats_batch,
    hex_jacobian_stats_batch as _c_hex_jacobian_stats_batch,
    hex_ortho_stats_batch as _c_hex_ortho_stats_batch,
    hex_skew_simple_stats_batch as _c_hex_skew_simple_stats_batch,
    hex_stretch_stats_batch as _c_hex_stretch_stats_batch,
    hex_validate_volumes_batch as _c_hex_validate_volumes_batch,
    is_available,
    metric_edge_lengths_batch as _c_metric_edge_lengths_batch,
    native_checker_cell_centres_from_face_centres_batch as _c_native_checker_cell_centres_batch,
    native_checker_face_geometry_batch as _c_native_checker_face_geometry_batch,
    native_checker_non_orthogonality_stats_batch as _c_native_checker_non_ortho_stats_batch,
    native_checker_skewness_stats_batch as _c_native_checker_skewness_stats_batch,
    tet_aniso_tensor_batch as _c_tet_aniso_tensor_batch,
    tet_aspect_ratio_batch as _c_aspect_ratio_batch,
    tet_min_dihedral_deg_batch as _c_min_dihedral_deg_batch,
    tet_min_solid_angle_sr_batch as _c_min_solid_angle_sr_batch,
    tet_quality_batch as _c_quality_batch,
    tet_qshape_batch as _c_tet_qshape_batch,
    tet_radius_edge_ratio_batch as _c_radius_edge_ratio_batch,
    tet_boundary_vertex_stats_batch as _c_tet_boundary_vertex_stats_batch,
    tet_circumsphere_batch as _c_tet_circumsphere_batch,
    poly_aspect_stats_batch as _c_poly_aspect_stats_batch,
    poly_convex_stats_batch as _c_poly_convex_stats_batch,
    poly_validate_volumes_batch as _c_poly_validate_volumes_batch,
    poly_volume_stats_batch as _c_poly_volume_stats_batch,
    tet_edge_stats_batch as _c_tet_edge_stats_batch,
    tet_inradius_batch as _c_tet_inradius_batch,
    tet_vertex_valence_batch as _c_tet_vertex_valence_batch,
    tet_volume_stats_batch as _c_tet_volume_stats_batch,
    screen_flip_candidates_batch as _c_screen_flip_candidates_batch,
    screen_swap_candidates_batch as _c_screen_swap_candidates_batch,
    surface_area_volume_stats_batch as _c_surface_area_volume_stats_batch,
    surface_boundary_edges_batch as _c_surface_boundary_edges_batch,
    surface_diag_stats_batch as _c_surface_diag_stats_batch,
    surface_dihedral_histogram_batch as _c_surface_dihedral_histogram_batch,
    surface_edge_lengths_stats_batch as _c_surface_edge_lengths_stats_batch,
    surface_edge_stats_batch as _c_surface_edge_stats_batch,
    surface_face_area_distribution_stats_batch as _c_surface_face_area_distribution_stats_batch,
    surface_feature_edges_stats_batch as _c_surface_feature_edges_stats_batch,
    surface_feature_report_stats_batch as _c_surface_feature_report_stats_batch,
    surface_dedup_vertices_quantized as _c_surface_dedup_vertices_quantized,
    surface_remove_degenerate_faces_mask as _c_surface_remove_degenerate_faces_mask,
    surface_unique_edge_length_stats_batch as _c_surface_unique_edge_length_stats_batch,
    surface_vertex_gaussian_curvature_batch as _c_surface_vertex_gaussian_curvature_batch,
    surface_vertex_mean_curvature_batch as _c_surface_vertex_mean_curvature_batch,
    surface_vertex_valence_batch as _c_surface_vertex_valence_batch,
    tet_shortest_edges_batch as _c_tet_shortest_edges_batch,
    tet_signed_vol6_batch as _c_vol6_batch,
)
from core.analyzer import topology as topology_module
from core.analyzer import aniso_tensor as aniso_tensor_module
from core.analyzer import boundary_stats as boundary_stats_module
from core.analyzer import curvature as curvature_module
from core.analyzer import dihedral_hist as dihedral_hist_module
from core.analyzer import edge_stats as edge_stats_module
from core.analyzer import face_area_var as face_area_var_module
from core.analyzer import feature_edges as feature_edges_module
from core.analyzer import feature_report as feature_report_module
from core.analyzer import tet_face_adj as tet_face_adj_module
from core.analyzer import flip_candidates as flip_candidates_module
from core.analyzer import geometry_kpi as geometry_kpi_module
from core.analyzer import mean_curvature as mean_curvature_module
from core.analyzer import sliver_collapse as sliver_collapse_module
from core.analyzer import surface_diag as surface_diag_module
from core.analyzer import edge_collapse_score as edge_collapse_score_module
from core.analyzer import swap_candidates as swap_candidates_module
from core.analyzer import surface_volume as surface_volume_module
from core.analyzer import tet_circumsphere as tet_circumsphere_module
from core.analyzer import tet_edge_stats as tet_edge_stats_module
from core.analyzer import tet_inradius as tet_inradius_module
from core.analyzer import tet_valence as tet_valence_module
from core.analyzer import vertex_valence as vertex_valence_module
from core.analyzer import volume_stats as volume_stats_module
from core.evaluator import bl_quality as bl_quality_module
from core.evaluator import degenerate_detector as degenerate_detector_module
from core.evaluator import hex_face_area as hex_face_area_module
from core.evaluator import hex_inverted as hex_inverted_module
from core.evaluator import hex_jacobian as hex_jacobian_module
from core.evaluator import hex_ortho as hex_ortho_module
from core.evaluator import hex_skew_simple as hex_skew_simple_module
from core.evaluator import hex_stretch as hex_stretch_module
from core.generator.native_hex import mesher as native_hex_mesher_module
from core.generator.native_hex import snap as native_hex_snap_module
from core.generator.native_poly import voronoi as native_poly_voronoi_module
from core.evaluator import native_checker as native_checker_module
from core.evaluator.native_checker import NativeMeshChecker
from core.evaluator import poly_aspect as poly_aspect_module
from core.evaluator import poly_convex as poly_convex_module
from core.evaluator import poly_volume as poly_volume_module
from core.preprocessor.native_repair import dedup as surface_dedup_module
from core.preprocessor.native_repair import degenerate as surface_degenerate_module
from core.evaluator import tet_qshape as tet_qshape_module
from core.generator.native_tet import quality as tet_quality_module
from core.generator.native_tet.quality import (
    tet_aspect_ratio as _py_aspect_ratio,
    tet_min_dihedral_deg as _py_min_dihedral_deg,
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


def _py_radius_edge_ratio(pts: np.ndarray, tets: np.ndarray) -> np.ndarray:
    tets = np.asarray(tets, dtype=np.int64)
    if tets.size == 0:
        return np.zeros(0)
    v = pts[tets]
    a, b, c, d = v[:, 0], v[:, 1], v[:, 2], v[:, 3]
    e1 = np.linalg.norm(b - a, axis=1)
    e2 = np.linalg.norm(c - a, axis=1)
    e3 = np.linalg.norm(d - a, axis=1)
    e4 = np.linalg.norm(c - b, axis=1)
    e5 = np.linalg.norm(d - b, axis=1)
    e6 = np.linalg.norm(d - c, axis=1)
    emin = np.minimum.reduce([e1, e2, e3, e4, e5, e6])
    emax = np.maximum.reduce([e1, e2, e3, e4, e5, e6])
    return np.where(emin > 1e-30, (emax * 0.5) / emin, 1e6)


def _py_min_solid_angle_sr(pts: np.ndarray, tets: np.ndarray) -> np.ndarray:
    tets = np.asarray(tets, dtype=np.int64)
    if tets.size == 0:
        return np.zeros(0)
    v = pts[tets]

    def _sa(o, p1, p2, p3):
        a = p1 - o
        b = p2 - o
        c = p3 - o
        na = np.linalg.norm(a, axis=1)
        nb = np.linalg.norm(b, axis=1)
        nc = np.linalg.norm(c, axis=1)
        num = np.abs(np.einsum("ij,ij->i", a, np.cross(b, c)))
        ab = np.einsum("ij,ij->i", a, b)
        bc = np.einsum("ij,ij->i", b, c)
        ca = np.einsum("ij,ij->i", c, a)
        denom = na * nb * nc + ab * nc + bc * na + ca * nb
        return 2.0 * np.arctan2(num, np.where(np.abs(denom) > 1e-30, denom, 1e-30))

    sa0 = _sa(v[:, 0], v[:, 1], v[:, 2], v[:, 3])
    sa1 = _sa(v[:, 1], v[:, 0], v[:, 2], v[:, 3])
    sa2 = _sa(v[:, 2], v[:, 0], v[:, 1], v[:, 3])
    sa3 = _sa(v[:, 3], v[:, 0], v[:, 1], v[:, 2])
    return np.minimum.reduce([sa0, sa1, sa2, sa3])


def _py_tet_qshape(pts: np.ndarray, tets: np.ndarray) -> np.ndarray:
    pts = np.asarray(pts, dtype=np.float64)
    tets = np.asarray(tets, dtype=np.int64)
    if tets.size == 0:
        return np.zeros(0, dtype=np.float64)
    a = pts[tets[:, 0]]
    b = pts[tets[:, 1]]
    c = pts[tets[:, 2]]
    d = pts[tets[:, 3]]
    vol = np.einsum("ij,ij->i", np.cross(b - a, c - a), d - a) / 6.0
    abs_vol = np.abs(vol)
    e_idx = tets[:, np.array([[0, 1], [0, 2], [0, 3], [1, 2], [1, 3], [2, 3]])]
    p0 = pts[e_idx[..., 0]]
    p1 = pts[e_idx[..., 1]]
    sum_l_sq = ((p1 - p0) ** 2).sum(axis=-1).sum(axis=1)
    safe = sum_l_sq > 1e-30
    raw = np.zeros(tets.shape[0], dtype=np.float64)
    raw[safe] = (3.0 * abs_vol[safe]) ** (2.0 / 3.0) / sum_l_sq[safe]
    q = np.clip(raw / 0.0857, 0.0, 1.0)
    q[vol <= 0] = 0.0
    return q


def _py_shortest_edges(pts: np.ndarray, tets: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    pairs = np.array([[0, 1], [0, 2], [0, 3], [1, 2], [1, 3], [2, 3]], dtype=np.int64)
    e_idx = tets[:, pairs]
    p0 = pts[e_idx[..., 0]]
    p1 = pts[e_idx[..., 1]]
    lens = np.linalg.norm(p1 - p0, axis=-1)
    local = lens.argmin(axis=1)
    rows = np.arange(tets.shape[0])
    return e_idx[rows, local], lens[rows, local]


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

    def test_tet_shape_quality_native_route_matches_fallback(self, monkeypatch):
        pts, tets = _make_random_mesh(n_pts=320, n_tets=250, seed=1400)
        tets[:4, 1] = tets[:4, 0]
        q_native = tet_quality_module.tet_shape_quality(pts, tets)
        monkeypatch.setattr(tet_quality_module, "_c_quality_batch", None)
        q_python = tet_quality_module.tet_shape_quality(pts, tets)
        np.testing.assert_allclose(q_native, q_python, atol=1e-12)


class TestRadiusEdgeRatio:

    def test_regular_tet_value(self):
        pts, tets = _make_regular_tet()
        ratio_c = _c_radius_edge_ratio_batch(pts, tets)
        ratio_py = _py_radius_edge_ratio(pts, tets)
        assert ratio_c is not None
        np.testing.assert_allclose(ratio_c, ratio_py, atol=1e-12)

    def test_random_meshes_allclose(self):
        for seed in range(100):
            n = 20 + seed * 2
            pts, tets = _make_random_mesh(n_pts=n + 10, n_tets=n, seed=seed + 1700)
            ratio_c = _c_radius_edge_ratio_batch(pts, tets)
            ratio_py = _py_radius_edge_ratio(pts, tets)
            assert ratio_c is not None
            np.testing.assert_allclose(
                ratio_c, ratio_py, atol=1e-12,
                err_msg=f"radius-edge mismatch seed={seed}",
            )

    def test_degenerate_duplicate_vertices(self):
        pts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64)
        tets = np.array([[0, 0, 1, 2]], dtype=np.int64)
        ratio_c = _c_radius_edge_ratio_batch(pts, tets)
        ratio_py = _py_radius_edge_ratio(pts, tets)
        assert ratio_c is not None
        np.testing.assert_allclose(ratio_c, ratio_py, atol=1e-12)

    def test_tet_radius_edge_native_route_matches_fallback(self, monkeypatch):
        pts, tets = _make_random_mesh(n_pts=380, n_tets=280, seed=1700)
        tets[:4, 1] = tets[:4, 0]
        ratio_native = tet_quality_module.tet_radius_edge_ratio(pts, tets)
        monkeypatch.setattr(tet_quality_module, "_c_radius_edge_ratio_batch", None)
        ratio_python = tet_quality_module.tet_radius_edge_ratio(pts, tets)
        np.testing.assert_allclose(ratio_native, ratio_python, atol=1e-12)


class TestMinSolidAngleSr:

    def test_regular_tet_value(self):
        pts, tets = _make_regular_tet()
        solid_c = _c_min_solid_angle_sr_batch(pts, tets)
        solid_py = _py_min_solid_angle_sr(pts, tets)
        assert solid_c is not None
        np.testing.assert_allclose(solid_c, solid_py, atol=1e-12)

    def test_random_meshes_allclose(self):
        for seed in range(100):
            n = 20 + seed * 2
            pts, tets = _make_random_mesh(n_pts=n + 10, n_tets=n, seed=seed + 1800)
            solid_c = _c_min_solid_angle_sr_batch(pts, tets)
            solid_py = _py_min_solid_angle_sr(pts, tets)
            assert solid_c is not None
            np.testing.assert_allclose(
                solid_c, solid_py, atol=1e-12,
                err_msg=f"solid angle mismatch seed={seed}",
            )

    def test_degenerate_duplicate_vertices(self):
        pts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64)
        tets = np.array([[0, 0, 1, 2]], dtype=np.int64)
        solid_c = _c_min_solid_angle_sr_batch(pts, tets)
        solid_py = _py_min_solid_angle_sr(pts, tets)
        assert solid_c is not None
        np.testing.assert_allclose(solid_c, solid_py, atol=1e-12)

    def test_tet_min_solid_angle_native_route_matches_fallback(self, monkeypatch):
        pts, tets = _make_random_mesh(n_pts=400, n_tets=290, seed=1800)
        tets[:4, 1] = tets[:4, 0]
        solid_native = tet_quality_module.tet_min_solid_angle_sr(pts, tets)
        monkeypatch.setattr(tet_quality_module, "_c_min_solid_angle_sr_batch", None)
        solid_python = tet_quality_module.tet_min_solid_angle_sr(pts, tets)
        np.testing.assert_allclose(solid_native, solid_python, atol=1e-12)


class TestTetQShape:

    def test_regular_tet_value(self):
        pts, tets = _make_regular_tet()
        q_c = _c_tet_qshape_batch(pts, tets)
        q_py = _py_tet_qshape(pts, tets)
        assert q_c is not None
        np.testing.assert_allclose(q_c, q_py, atol=1e-12)

    def test_random_meshes_allclose(self):
        for seed in range(100):
            n = 20 + seed * 2
            pts, tets = _make_random_mesh(n_pts=n + 10, n_tets=n, seed=seed + 1900)
            q_c = _c_tet_qshape_batch(pts, tets)
            q_py = _py_tet_qshape(pts, tets)
            assert q_c is not None
            np.testing.assert_allclose(
                q_c, q_py, atol=1e-12,
                err_msg=f"tet qshape mismatch seed={seed}",
            )

    def test_degenerate_duplicate_vertices(self):
        pts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64)
        tets = np.array([[0, 0, 1, 2]], dtype=np.int64)
        q_c = _c_tet_qshape_batch(pts, tets)
        q_py = _py_tet_qshape(pts, tets)
        assert q_c is not None
        np.testing.assert_allclose(q_c, q_py, atol=1e-12)

    def test_tet_qshape_native_route_matches_fallback(self, monkeypatch):
        pts, tets = _make_random_mesh(n_pts=420, n_tets=300, seed=1900)
        tets[:4, 1] = tets[:4, 0]
        q_native, stats_native = tet_qshape_module.tet_qshape(pts, tets)
        monkeypatch.setattr(tet_qshape_module, "_c_tet_qshape_batch", None)
        q_python, stats_python = tet_qshape_module.tet_qshape(pts, tets)
        np.testing.assert_allclose(q_native, q_python, atol=1e-12)
        assert stats_native.n_tets == stats_python.n_tets
        assert stats_native.q_min == pytest.approx(stats_python.q_min, abs=1e-12)
        assert stats_native.q_max == pytest.approx(stats_python.q_max, abs=1e-12)
        assert stats_native.q_mean == pytest.approx(stats_python.q_mean, abs=1e-12)


class TestDegenerateDetector:

    def test_random_mesh_stats_match_python_fallback(self, monkeypatch):
        pts, tets = _make_random_mesh(n_pts=440, n_tets=320, seed=2000)
        tets[:4, 1] = tets[:4, 0]
        native = _c_detect_degenerate_tets_stats(pts, tets, 1e-12, 0.01)
        assert native is not None
        monkeypatch.setattr(
            degenerate_detector_module,
            "_c_detect_degenerate_tets_stats",
            None,
        )
        py = degenerate_detector_module.detect_degenerate_tets(
            pts, tets, zero_tol=1e-12, sliver_cube_ratio=0.01,
        )
        assert native[:4] == (
            py.n_inverted,
            py.n_zero_vol,
            py.n_sliver,
            py.n_ok,
        )
        assert native[4] == pytest.approx(py.worst_volume, abs=1e-12)
        assert native[5] == pytest.approx(py.smallest_abs_volume, abs=1e-12)

    def test_detect_degenerate_native_route_matches_fallback(self, monkeypatch):
        pts, tets = _make_random_mesh(n_pts=460, n_tets=340, seed=2001)
        tets[:4, 1] = tets[:4, 0]
        native = degenerate_detector_module.detect_degenerate_tets(pts, tets)
        monkeypatch.setattr(
            degenerate_detector_module,
            "_c_detect_degenerate_tets_stats",
            None,
        )
        py = degenerate_detector_module.detect_degenerate_tets(pts, tets)
        assert native.n_tets == py.n_tets
        assert native.n_inverted == py.n_inverted
        assert native.n_zero_vol == py.n_zero_vol
        assert native.n_sliver == py.n_sliver
        assert native.n_ok == py.n_ok
        assert native.worst_volume == pytest.approx(py.worst_volume, abs=1e-12)
        assert native.smallest_abs_volume == pytest.approx(py.smallest_abs_volume, abs=1e-12)


class TestShortestEdges:

    def test_random_meshes_match_python(self):
        for seed in range(50):
            n = 20 + seed * 2
            pts, tets = _make_random_mesh(n_pts=n + 10, n_tets=n, seed=seed + 2100)
            result = _c_tet_shortest_edges_batch(pts, tets)
            assert result is not None
            edges_c, lens_c = result
            edges_py, lens_py = _py_shortest_edges(pts, tets)
            np.testing.assert_array_equal(edges_c, edges_py)
            np.testing.assert_allclose(lens_c, lens_py, atol=1e-12)

    def test_sliver_collapse_native_route_matches_fallback(self, monkeypatch):
        pts, tets = _make_random_mesh(n_pts=480, n_tets=360, seed=2100)
        tets[:4, 1] = tets[:4, 0]
        edges_native, stats_native = sliver_collapse_module.detect_sliver_collapse_edges(
            pts, tets, sliver_q_threshold=0.5,
        )
        monkeypatch.setattr(sliver_collapse_module, "_c_tet_shortest_edges_batch", None)
        edges_python, stats_python = sliver_collapse_module.detect_sliver_collapse_edges(
            pts, tets, sliver_q_threshold=0.5,
        )
        np.testing.assert_array_equal(edges_native, edges_python)
        assert stats_native.n_sliver_tets == stats_python.n_sliver_tets
        assert stats_native.n_collapse_candidates == stats_python.n_collapse_candidates
        assert stats_native.median_short_edge == pytest.approx(
            stats_python.median_short_edge, abs=1e-12,
        )


class TestEdgeCollapsePriority:

    def test_edge_collapse_priority_native_route_matches_fallback(self, monkeypatch):
        rng = np.random.default_rng(2200)
        pts = rng.standard_normal((520, 3))
        tets = np.array(
            [rng.choice(520, size=4, replace=False) for _ in range(380)],
            dtype=np.int64,
        )
        edges_native, scores_native, stats_native = (
            edge_collapse_score_module.edge_collapse_priority(
                pts, tets, q_threshold=0.5, top_k=80,
            )
        )
        monkeypatch.setattr(
            edge_collapse_score_module,
            "_c_edge_collapse_priority_batch",
            None,
        )
        edges_python, scores_python, stats_python = (
            edge_collapse_score_module.edge_collapse_priority(
                pts, tets, q_threshold=0.5, top_k=80,
            )
        )
        np.testing.assert_array_equal(edges_native, edges_python)
        np.testing.assert_allclose(scores_native, scores_python, atol=1e-12)
        assert stats_native.n_candidates == stats_python.n_candidates
        assert stats_native.score_max == pytest.approx(stats_python.score_max, abs=1e-12)
        assert stats_native.score_median == pytest.approx(
            stats_python.score_median, abs=1e-12,
        )


class TestTetFaceAdjacency:

    def test_tet_face_adjacency_native_route_matches_fallback(self, monkeypatch):
        _, tets = _make_random_mesh(n_pts=260, n_tets=180, seed=2300)
        native = _c_build_tet_face_adjacency_stats(tets)
        assert native is not None
        monkeypatch.setattr(tet_face_adj_module, "_c_build_tet_face_adjacency_stats", None)
        adj_python, stats_python = tet_face_adj_module.build_tet_face_adjacency(tets)
        adj_native, stats_native = native
        np.testing.assert_array_equal(adj_native, adj_python)
        assert stats_native == (
            stats_python.n_unique_faces,
            stats_python.n_boundary_faces,
            stats_python.n_interior_faces,
            stats_python.n_nonmanifold,
        )

    def test_build_tet_face_adjacency_public_route_matches_fallback(self, monkeypatch):
        _, tets = _make_random_mesh(n_pts=280, n_tets=200, seed=2301)
        adj_native, stats_native = tet_face_adj_module.build_tet_face_adjacency(tets)
        monkeypatch.setattr(tet_face_adj_module, "_c_build_tet_face_adjacency_stats", None)
        adj_python, stats_python = tet_face_adj_module.build_tet_face_adjacency(tets)
        np.testing.assert_array_equal(adj_native, adj_python)
        assert stats_native.n_unique_faces == stats_python.n_unique_faces
        assert stats_native.n_boundary_faces == stats_python.n_boundary_faces
        assert stats_native.n_interior_faces == stats_python.n_interior_faces
        assert stats_native.n_nonmanifold == stats_python.n_nonmanifold


class TestFlipCandidates:

    def test_screen_flip_candidates_native_route_matches_fallback(self, monkeypatch):
        rng = np.random.default_rng(2400)
        pts = rng.standard_normal((520, 3))
        tets = np.array(
            [rng.choice(520, size=4, replace=False) for _ in range(380)],
            dtype=np.int64,
        )
        pairs_native, q_native, stats_native = flip_candidates_module.screen_flip_candidates(
            pts, tets, q_threshold=0.5,
        )
        monkeypatch.setattr(flip_candidates_module, "_c_screen_flip_candidates_batch", None)
        pairs_python, q_python, stats_python = flip_candidates_module.screen_flip_candidates(
            pts, tets, q_threshold=0.5,
        )
        np.testing.assert_array_equal(pairs_native, pairs_python)
        np.testing.assert_allclose(q_native, q_python, atol=1e-12)
        assert stats_native.n_internal_faces == stats_python.n_internal_faces
        assert stats_native.n_flip_candidates == stats_python.n_flip_candidates

    def test_screen_flip_candidates_batch_direct(self):
        rng = np.random.default_rng(2401)
        pts = rng.standard_normal((540, 3))
        tets = np.array(
            [rng.choice(540, size=4, replace=False) for _ in range(400)],
            dtype=np.int64,
        )
        adj, _ = tet_face_adj_module.build_tet_face_adjacency(tets)
        q, _ = tet_qshape_module.tet_qshape(pts, tets)
        result = _c_screen_flip_candidates_batch(adj, q, 0.5)
        assert result is not None
        pairs, worst_q, n_internal = result
        assert pairs.ndim == 2
        assert pairs.shape[1] == 2
        assert worst_q.shape[0] == pairs.shape[0]
        assert n_internal >= pairs.shape[0]


class TestSwapCandidates:

    def test_screen_swap_candidates_native_route_matches_fallback(self, monkeypatch):
        rng = np.random.default_rng(2500)
        pts = rng.standard_normal((560, 3))
        tets = np.array(
            [rng.choice(560, size=4, replace=False) for _ in range(420)],
            dtype=np.int64,
        )
        edges_native, q_native, stats_native = swap_candidates_module.screen_swap_candidates(
            pts, tets, q_threshold=0.5,
        )
        monkeypatch.setattr(swap_candidates_module, "_c_screen_swap_candidates_batch", None)
        edges_python, q_python, stats_python = swap_candidates_module.screen_swap_candidates(
            pts, tets, q_threshold=0.5,
        )
        np.testing.assert_array_equal(edges_native, edges_python)
        np.testing.assert_allclose(q_native, q_python, atol=1e-12)
        assert stats_native.n_internal_edges == stats_python.n_internal_edges
        assert stats_native.n_swap_candidates == stats_python.n_swap_candidates
        assert stats_native.n_2_3_shell == stats_python.n_2_3_shell
        assert stats_native.n_4_7_shell == stats_python.n_4_7_shell

    def test_screen_swap_candidates_batch_direct(self):
        rng = np.random.default_rng(2501)
        pts = rng.standard_normal((580, 3))
        tets = np.array(
            [rng.choice(580, size=4, replace=False) for _ in range(430)],
            dtype=np.int64,
        )
        q, _ = tet_qshape_module.tet_qshape(pts, tets)
        result = _c_screen_swap_candidates_batch(tets, q, 0.5)
        assert result is not None
        edges, worst_q, stats = result
        assert edges.ndim == 2
        assert edges.shape[1] == 2
        assert worst_q.shape[0] == edges.shape[0]
        assert stats[0] >= edges.shape[0]


class TestSurfaceBoundaryEdges:

    def test_surface_boundary_edges_native_matches_python(self, monkeypatch):
        rng = np.random.default_rng(2600)
        faces = rng.integers(0, 800, size=(600, 3), dtype=np.int64)
        for i in range(0, 80, 2):
            faces[i + 1, 0] = faces[i, 1]
            faces[i + 1, 1] = faces[i, 0]
        native = _c_surface_boundary_edges_batch(faces)
        assert native is not None
        monkeypatch.setattr(topology_module, "_c_surface_boundary_edges_batch", None)
        python = topology_module.boundary_edges(faces)
        np.testing.assert_array_equal(native, python)

    def test_boundary_edges_public_route_matches_fallback(self, monkeypatch):
        rng = np.random.default_rng(2601)
        faces = rng.integers(0, 900, size=(700, 3), dtype=np.int64)
        native = topology_module.boundary_edges(faces)
        monkeypatch.setattr(topology_module, "_c_surface_boundary_edges_batch", None)
        python = topology_module.boundary_edges(faces)
        np.testing.assert_array_equal(native, python)

    def test_surface_edge_stats_native_matches_python(self, monkeypatch):
        rng = np.random.default_rng(2700)
        faces = rng.integers(0, 850, size=(650, 3), dtype=np.int64)
        for i in range(0, 90, 2):
            faces[i + 1, 0] = faces[i, 1]
            faces[i + 1, 1] = faces[i, 0]
        stats = _c_surface_edge_stats_batch(faces)
        assert stats is not None
        monkeypatch.setattr(topology_module, "_c_surface_edge_stats_batch", None)
        boundary = topology_module.boundary_edges(faces)
        edges = topology_module._edges_per_face(faces)
        unique_edges = np.unique(edges, axis=0)
        assert stats[0] == unique_edges.shape[0]
        assert stats[1] == boundary.shape[0]
        assert stats[2] == topology_module.count_non_manifold_edges(faces)

    def test_topology_predicates_native_route_matches_fallback(self, monkeypatch):
        rng = np.random.default_rng(2701)
        faces = rng.integers(0, 900, size=(700, 3), dtype=np.int64)
        native = (
            topology_module.is_watertight(faces),
            topology_module.is_edge_manifold(faces),
            topology_module.count_non_manifold_edges(faces),
            topology_module.compute_euler(900, faces),
        )
        monkeypatch.setattr(topology_module, "_c_surface_edge_stats_batch", None)
        python = (
            topology_module.is_watertight(faces),
            topology_module.is_edge_manifold(faces),
            topology_module.count_non_manifold_edges(faces),
            topology_module.compute_euler(900, faces),
        )
        assert native == python


class TestSurfaceEdgeStats:

    def test_surface_edge_lengths_stats_native_route_matches_fallback(self, monkeypatch):
        rng = np.random.default_rng(2800)
        verts = rng.standard_normal((900, 3))
        faces = rng.integers(0, 900, size=(700, 3), dtype=np.int64)
        native = edge_stats_module.compute_edge_stats(verts, faces)
        assert _c_surface_edge_lengths_stats_batch(verts, faces) is not None
        monkeypatch.setattr(edge_stats_module, "_c_surface_edge_lengths_stats_batch", None)
        python = edge_stats_module.compute_edge_stats(verts, faces)
        assert native.n_edges_total == python.n_edges_total
        assert native.n_edges_unique == python.n_edges_unique
        assert native.edge_min == pytest.approx(python.edge_min, abs=1e-12)
        assert native.edge_max == pytest.approx(python.edge_max, abs=1e-12)
        assert native.edge_mean == pytest.approx(python.edge_mean, abs=1e-12)
        assert native.edge_std == pytest.approx(python.edge_std, abs=1e-12)
        assert native.edge_p5 == pytest.approx(python.edge_p5, abs=1e-12)
        assert native.edge_p50 == pytest.approx(python.edge_p50, abs=1e-12)
        assert native.edge_p95 == pytest.approx(python.edge_p95, abs=1e-12)
        assert native.aspect_ratio_max == pytest.approx(python.aspect_ratio_max, abs=1e-12)
        assert native.aspect_ratio_mean == pytest.approx(python.aspect_ratio_mean, abs=1e-12)


class TestSurfaceCurvature:

    def test_vertex_gaussian_curvature_native_route_matches_fallback(self, monkeypatch):
        rng = np.random.default_rng(2900)
        verts = rng.standard_normal((260, 3))
        faces = np.array(
            [rng.choice(260, size=3, replace=False) for _ in range(220)],
            dtype=np.int64,
        )
        native_k, native_stats = curvature_module.vertex_gaussian_curvature(verts, faces)
        assert _c_surface_vertex_gaussian_curvature_batch(verts, faces) is not None
        monkeypatch.setattr(
            curvature_module,
            "_c_surface_vertex_gaussian_curvature_batch",
            None,
        )
        python_k, python_stats = curvature_module.vertex_gaussian_curvature(verts, faces)
        np.testing.assert_allclose(native_k, python_k, rtol=1e-12, atol=1e-10)
        assert native_stats.n_vertices == python_stats.n_vertices
        assert native_stats.curvature_min == pytest.approx(python_stats.curvature_min, abs=1e-10)
        assert native_stats.curvature_max == pytest.approx(python_stats.curvature_max, abs=1e-10)
        assert native_stats.curvature_mean == pytest.approx(python_stats.curvature_mean, abs=1e-10)
        assert native_stats.curvature_total == pytest.approx(python_stats.curvature_total, abs=1e-10)


class TestSurfaceFeatureEdges:

    def test_feature_edges_native_route_matches_fallback(self, monkeypatch):
        rng = np.random.default_rng(3000)
        verts = rng.standard_normal((360, 3))
        faces = np.array(
            [rng.choice(360, size=3, replace=False) for _ in range(300)],
            dtype=np.int64,
        )
        for i in range(0, 60, 2):
            faces[i + 1, 0] = faces[i, 1]
            faces[i + 1, 1] = faces[i, 0]
        native = feature_edges_module.extract_feature_edges(
            verts, faces, feature_angle_deg=30.0, return_edges=False,
        )
        cos_thresh = float(np.cos(np.deg2rad(30.0)))
        assert _c_surface_feature_edges_stats_batch(verts, faces, cos_thresh) is not None
        monkeypatch.setattr(feature_edges_module, "_c_surface_feature_edges_stats_batch", None)
        python = feature_edges_module.extract_feature_edges(
            verts, faces, feature_angle_deg=30.0, return_edges=False,
        )
        assert native.n_feature_edges == python.n_feature_edges
        assert native.n_boundary_edges == python.n_boundary_edges
        assert native.n_sharp_dihedral_edges == python.n_sharp_dihedral_edges
        assert native.n_corner_vertices == python.n_corner_vertices
        assert native.edge_pairs is None


class TestSurfaceFeatureReport:

    def test_unique_edge_length_stats_match_numpy_reference(self):
        rng = np.random.default_rng(3100)
        verts = rng.standard_normal((480, 3))
        faces = np.array(
            [rng.choice(480, size=3, replace=False) for _ in range(420)],
            dtype=np.int64,
        )
        for i in range(0, 80, 2):
            faces[i + 1, 0] = faces[i, 1]
            faces[i + 1, 1] = faces[i, 0]

        got = _c_surface_unique_edge_length_stats_batch(verts, faces)
        assert got is not None
        n_unique, edge_min, edge_max, p01, p99 = got

        edges = np.concatenate([
            faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]],
        ], axis=0)
        edges = np.sort(edges, axis=1)
        edges_unique = np.unique(edges, axis=0)
        lens = np.linalg.norm(verts[edges_unique[:, 1]] - verts[edges_unique[:, 0]], axis=1)
        ref_p01, ref_p99 = np.percentile(lens, [1, 99])

        assert n_unique == int(edges_unique.shape[0])
        assert edge_min == pytest.approx(float(lens.min()), abs=1e-12)
        assert edge_max == pytest.approx(float(lens.max()), abs=1e-12)
        assert p01 == pytest.approx(float(ref_p01), abs=1e-12)
        assert p99 == pytest.approx(float(ref_p99), abs=1e-12)

    def test_combined_feature_report_stats_match_reference_paths(self):
        rng = np.random.default_rng(3150)
        verts = rng.standard_normal((500, 3))
        faces = np.array(
            [rng.choice(500, size=3, replace=False) for _ in range(440)],
            dtype=np.int64,
        )
        for i in range(0, 90, 2):
            faces[i + 1, 0] = faces[i, 1]
            faces[i + 1, 1] = faces[i, 0]

        cos_thresh = float(np.cos(np.deg2rad(30.0)))
        combined = _c_surface_feature_report_stats_batch(verts, faces, cos_thresh)
        assert combined is not None
        counts, length_stats = combined
        n_unique, n_feature, n_boundary, n_sharp, n_corners = counts
        edge_min, edge_max, p01, p99 = length_stats

        edge_stats = _c_surface_unique_edge_length_stats_batch(verts, faces)
        feature_stats = _c_surface_feature_edges_stats_batch(verts, faces, cos_thresh)
        assert edge_stats is not None
        assert feature_stats is not None
        ref_n_unique, ref_edge_min, ref_edge_max, ref_p01, ref_p99 = edge_stats
        ref_n_feature, ref_n_boundary, ref_n_sharp, ref_n_corners = feature_stats

        assert n_unique == ref_n_unique
        assert n_feature == ref_n_feature
        assert n_boundary == ref_n_boundary
        assert n_sharp == ref_n_sharp
        assert n_corners == ref_n_corners
        assert edge_min == pytest.approx(ref_edge_min, abs=1e-12)
        assert edge_max == pytest.approx(ref_edge_max, abs=1e-12)
        assert p01 == pytest.approx(ref_p01, abs=1e-12)
        assert p99 == pytest.approx(ref_p99, abs=1e-12)

    def test_feature_report_native_edge_stats_route_matches_fallback(self, monkeypatch):
        rng = np.random.default_rng(3200)
        verts = rng.standard_normal((520, 3))
        faces = np.array(
            [rng.choice(520, size=3, replace=False) for _ in range(460)],
            dtype=np.int64,
        )
        for i in range(0, 100, 2):
            faces[i + 1, 0] = faces[i, 1]
            faces[i + 1, 1] = faces[i, 0]

        native = feature_report_module.feature_report(verts, faces, sharp_angle_deg=30.0)
        assert _c_surface_feature_report_stats_batch(
            verts,
            faces,
            float(np.cos(np.deg2rad(30.0))),
        ) is not None
        monkeypatch.setattr(
            feature_report_module,
            "_c_surface_feature_report_stats_batch",
            None,
        )
        monkeypatch.setattr(
            feature_report_module,
            "_c_surface_unique_edge_length_stats_batch",
            None,
        )
        python = feature_report_module.feature_report(verts, faces, sharp_angle_deg=30.0)

        assert native.n_vertices == python.n_vertices
        assert native.n_triangles == python.n_triangles
        assert native.edge_min == pytest.approx(python.edge_min, abs=1e-12)
        assert native.edge_max == pytest.approx(python.edge_max, abs=1e-12)
        assert native.edge_p99_ratio == pytest.approx(python.edge_p99_ratio, abs=1e-12)
        assert native.n_sharp_edges == python.n_sharp_edges
        assert native.sharp_ratio == pytest.approx(python.sharp_ratio, abs=1e-12)
        assert native.complexity_score == pytest.approx(python.complexity_score, abs=1e-12)


class TestSurfaceDegenerateRepair:

    def test_remove_degenerate_faces_native_route_matches_fallback(self, monkeypatch):
        rng = np.random.default_rng(3300)
        verts = rng.standard_normal((700, 3))
        faces = np.array(
            [rng.choice(700, size=3, replace=False) for _ in range(600)],
            dtype=np.int64,
        )
        faces[10] = faces[0]
        faces[12] = faces[2][::-1]
        faces[20, 2] = faces[20, 1]
        faces[21] = faces[20]

        native = surface_degenerate_module.remove_degenerate_faces(
            verts, faces, area_tol=1e-18,
        )
        assert _c_surface_remove_degenerate_faces_mask(verts, faces, 1e-18) is not None
        monkeypatch.setattr(
            surface_degenerate_module,
            "_c_surface_remove_degenerate_faces_mask",
            None,
        )
        python = surface_degenerate_module.remove_degenerate_faces(
            verts, faces, area_tol=1e-18,
        )
        np.testing.assert_array_equal(native[0], python[0])
        assert native[1] == python[1]

    def test_remove_degenerate_faces_mask_matches_numpy_reference(self):
        rng = np.random.default_rng(3310)
        verts = rng.standard_normal((500, 3))
        faces = np.array(
            [rng.choice(500, size=3, replace=False) for _ in range(420)],
            dtype=np.int64,
        )
        faces[5] = faces[4]
        faces[7] = faces[4][::-1]
        faces[9, 1] = faces[9, 0]

        got = _c_surface_remove_degenerate_faces_mask(verts, faces, 1e-18)
        assert got is not None
        keep, removed = got

        v = verts[faces]
        n = np.cross(v[:, 1] - v[:, 0], v[:, 2] - v[:, 0])
        areas = 0.5 * np.linalg.norm(n, axis=1)
        keep_area = areas >= 1e-18
        sorted_faces = np.sort(faces, axis=1)
        _, first_idx = np.unique(sorted_faces, axis=0, return_index=True)
        keep_ref = np.zeros(faces.shape[0], dtype=bool)
        keep_ref[first_idx] = True
        keep_ref &= keep_area

        np.testing.assert_array_equal(keep, keep_ref)
        assert removed == int(faces.shape[0] - int(keep_ref.sum()))


class TestSurfaceDedupRepair:

    def test_dedup_vertices_native_route_matches_fallback(self, monkeypatch):
        rng = np.random.default_rng(3400)
        verts = rng.standard_normal((700, 3))
        for i in range(0, 80, 2):
            verts[i + 1] = verts[i]
        faces = np.array(
            [rng.choice(700, size=3, replace=False) for _ in range(600)],
            dtype=np.int64,
        )

        native = surface_dedup_module.dedup_vertices(verts, faces, tol=1e-9)
        assert _c_surface_dedup_vertices_quantized(verts, faces, 1e-9) is not None
        monkeypatch.setattr(
            surface_dedup_module,
            "_c_surface_dedup_vertices_quantized",
            None,
        )
        python = surface_dedup_module.dedup_vertices(verts, faces, tol=1e-9)
        np.testing.assert_array_equal(native[0], python[0])
        np.testing.assert_array_equal(native[1], python[1])
        assert native[2] == python[2]

    def test_dedup_vertices_quantized_matches_numpy_reference(self):
        rng = np.random.default_rng(3410)
        verts = rng.standard_normal((500, 3))
        for i in range(0, 60, 2):
            verts[i + 1] = verts[i]
        faces = np.array(
            [rng.choice(500, size=3, replace=False) for _ in range(420)],
            dtype=np.int64,
        )

        got = _c_surface_dedup_vertices_quantized(verts, faces, 1e-9)
        assert got is not None
        new_v, new_f, merged = got

        keys = np.round(verts * 1e9).astype(np.int64)
        _, unique_idx, inverse = np.unique(
            keys, axis=0, return_index=True, return_inverse=True,
        )
        inverse = np.asarray(inverse, dtype=np.int64).reshape(-1)
        ref_v = verts[unique_idx]
        ref_f = inverse[faces].astype(np.int64).reshape(faces.shape)
        np.testing.assert_array_equal(new_v, ref_v)
        np.testing.assert_array_equal(new_f, ref_f)
        assert merged == int(verts.shape[0] - ref_v.shape[0])


class TestSurfaceVolume:

    def test_surface_volume_native_route_matches_fallback(self, monkeypatch):
        rng = np.random.default_rng(3500)
        verts = rng.standard_normal((800, 3))
        faces = np.array(
            [rng.choice(800, size=3, replace=False) for _ in range(700)],
            dtype=np.int64,
        )

        native = surface_volume_module.surface_volume_integral(verts, faces)
        assert _c_surface_area_volume_stats_batch(verts, faces) is not None
        monkeypatch.setattr(
            surface_volume_module,
            "_c_surface_area_volume_stats_batch",
            None,
        )
        python = surface_volume_module.surface_volume_integral(verts, faces)
        assert native.n_triangles == python.n_triangles
        assert native.surface_area == pytest.approx(python.surface_area, rel=1e-12, abs=1e-9)
        assert native.enclosed_volume == pytest.approx(python.enclosed_volume, rel=1e-12, abs=1e-9)
        assert native.bbox_volume == pytest.approx(python.bbox_volume, rel=1e-12, abs=1e-12)
        assert native.fill_ratio == pytest.approx(python.fill_ratio, rel=1e-12, abs=1e-12)

    def test_surface_area_volume_stats_match_numpy_reference(self):
        rng = np.random.default_rng(3510)
        verts = rng.standard_normal((600, 3))
        faces = np.array(
            [rng.choice(600, size=3, replace=False) for _ in range(520)],
            dtype=np.int64,
        )
        got = _c_surface_area_volume_stats_batch(verts, faces)
        assert got is not None
        area, vol, bbox_vol = got

        a = verts[faces[:, 0]]
        b = verts[faces[:, 1]]
        c = verts[faces[:, 2]]
        cross_ab = np.cross(b - a, c - a)
        ref_area = float((0.5 * np.linalg.norm(cross_ab, axis=1)).sum())
        ref_vol = float((np.einsum("ij,ij->i", a, np.cross(b, c)) / 6.0).sum())
        bbox = verts.max(axis=0) - verts.min(axis=0)
        ref_bbox_vol = float(np.prod(np.maximum(bbox, 0.0)))

        assert area == pytest.approx(ref_area, rel=1e-12, abs=1e-9)
        assert vol == pytest.approx(ref_vol, rel=1e-12, abs=1e-9)
        assert bbox_vol == pytest.approx(ref_bbox_vol, rel=1e-12, abs=1e-12)


class TestGeometryKPI:

    def test_geometry_kpi_native_route_matches_fallback(self, monkeypatch):
        rng = np.random.default_rng(3600)
        verts = rng.standard_normal((850, 3))
        faces = np.array(
            [rng.choice(850, size=3, replace=False) for _ in range(760)],
            dtype=np.int64,
        )

        native = geometry_kpi_module.compute_geometry_kpi(verts, faces)
        assert _c_surface_area_volume_stats_batch(verts, faces) is not None
        assert _c_surface_edge_stats_batch(faces) is not None
        monkeypatch.setattr(geometry_kpi_module, "_c_surface_area_volume_stats_batch", None)
        monkeypatch.setattr(geometry_kpi_module, "_c_surface_edge_stats_batch", None)
        python = geometry_kpi_module.compute_geometry_kpi(verts, faces)

        assert native.n_vertices == python.n_vertices
        assert native.n_faces == python.n_faces
        assert native.n_edges == python.n_edges
        assert native.bbox_min == pytest.approx(python.bbox_min, abs=1e-12)
        assert native.bbox_max == pytest.approx(python.bbox_max, abs=1e-12)
        assert native.bbox_diag == pytest.approx(python.bbox_diag, abs=1e-12)
        assert native.bbox_volume == pytest.approx(python.bbox_volume, abs=1e-12)
        assert native.surface_area == pytest.approx(python.surface_area, rel=1e-12, abs=1e-9)
        assert native.enclosed_volume == pytest.approx(python.enclosed_volume, rel=1e-12, abs=1e-9)
        assert native.euler_characteristic == python.euler_characteristic
        assert native.genus_estimate == python.genus_estimate


class TestFaceAreaVariance:

    def test_face_area_variance_native_route_matches_fallback(self, monkeypatch):
        rng = np.random.default_rng(3700)
        verts = rng.standard_normal((760, 3))
        faces = np.array(
            [rng.choice(760, size=3, replace=False) for _ in range(690)],
            dtype=np.int64,
        )

        native = face_area_var_module.face_area_variance(verts, faces)
        assert _c_surface_face_area_distribution_stats_batch(verts, faces) is not None
        monkeypatch.setattr(
            face_area_var_module,
            "_c_surface_face_area_distribution_stats_batch",
            None,
        )
        python = face_area_var_module.face_area_variance(verts, faces)
        assert native.n_triangles == python.n_triangles
        assert native.area_min == pytest.approx(python.area_min, rel=1e-12, abs=1e-12)
        assert native.area_max == pytest.approx(python.area_max, rel=1e-12, abs=1e-12)
        assert native.area_mean == pytest.approx(python.area_mean, rel=1e-12, abs=1e-12)
        assert native.area_std == pytest.approx(python.area_std, rel=1e-12, abs=1e-12)
        assert native.cv == pytest.approx(python.cv, rel=1e-12, abs=1e-12)
        assert native.p99_to_p01 == pytest.approx(python.p99_to_p01, rel=1e-12, abs=1e-12)

    def test_face_area_distribution_stats_match_numpy_reference(self):
        rng = np.random.default_rng(3710)
        verts = rng.standard_normal((620, 3))
        faces = np.array(
            [rng.choice(620, size=3, replace=False) for _ in range(540)],
            dtype=np.int64,
        )
        got = _c_surface_face_area_distribution_stats_batch(verts, faces)
        assert got is not None
        area_min, area_max, mean, std, p01, p99 = got

        a = verts[faces[:, 0]]
        b = verts[faces[:, 1]]
        c = verts[faces[:, 2]]
        areas = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
        ref_p01, ref_p99 = np.percentile(areas, [1, 99])
        assert area_min == pytest.approx(float(areas.min()), rel=1e-12, abs=1e-12)
        assert area_max == pytest.approx(float(areas.max()), rel=1e-12, abs=1e-12)
        assert mean == pytest.approx(float(areas.mean()), rel=1e-12, abs=1e-12)
        assert std == pytest.approx(float(areas.std()), rel=1e-12, abs=1e-12)
        assert p01 == pytest.approx(float(ref_p01), rel=1e-12, abs=1e-12)
        assert p99 == pytest.approx(float(ref_p99), rel=1e-12, abs=1e-12)


class TestSurfaceDiag:

    def test_surface_diag_native_route_matches_fallback(self, monkeypatch):
        rng = np.random.default_rng(3800)
        verts = rng.standard_normal((820, 3))
        faces = np.array(
            [rng.choice(820, size=3, replace=False) for _ in range(760)],
            dtype=np.int64,
        )
        for i in range(0, 90, 2):
            faces[i + 1, 0] = faces[i, 1]
            faces[i + 1, 1] = faces[i, 0]

        native = surface_diag_module.diagnose_surface(
            verts, faces, feature_angle_deg=30.0, sliver_area_tol=1e-12,
        )
        assert _c_surface_diag_stats_batch(
            verts, faces, float(np.cos(np.deg2rad(30.0))), 1e-12,
        ) is not None
        monkeypatch.setattr(surface_diag_module, "_c_surface_diag_stats_batch", None)
        python = surface_diag_module.diagnose_surface(
            verts, faces, feature_angle_deg=30.0, sliver_area_tol=1e-12,
        )

        assert native.n_vertices == python.n_vertices
        assert native.n_faces == python.n_faces
        assert native.n_inconsistent_normals == python.n_inconsistent_normals
        assert native.n_sliver_faces == python.n_sliver_faces
        assert native.n_dihedral_sharp == python.n_dihedral_sharp
        assert native.dihedral_min_deg == pytest.approx(python.dihedral_min_deg, abs=1e-10)
        assert native.dihedral_max_deg == pytest.approx(python.dihedral_max_deg, abs=1e-10)
        assert native.dihedral_mean_deg == pytest.approx(python.dihedral_mean_deg, abs=1e-10)
        assert native.face_area_min == pytest.approx(python.face_area_min, rel=1e-12, abs=1e-12)
        assert native.face_area_max == pytest.approx(python.face_area_max, rel=1e-12, abs=1e-12)
        assert native.aspect_ratio_max == pytest.approx(python.aspect_ratio_max, rel=1e-12, abs=1e-12)
        assert native.warnings == python.warnings

    def test_surface_diag_stats_match_python_reference(self):
        rng = np.random.default_rng(3810)
        verts = rng.standard_normal((620, 3))
        faces = np.array(
            [rng.choice(620, size=3, replace=False) for _ in range(540)],
            dtype=np.int64,
        )
        for i in range(0, 70, 2):
            faces[i + 1, 0] = faces[i, 1]
            faces[i + 1, 1] = faces[i, 0]

        cos_thresh = float(np.cos(np.deg2rad(30.0)))
        native = _c_surface_diag_stats_batch(verts, faces, cos_thresh, 1e-12)
        assert native is not None
        counts, stats = native
        py = surface_diag_module.diagnose_surface(verts, faces, feature_angle_deg=30.0)
        assert counts[0] == py.n_inconsistent_normals
        assert counts[1] == py.n_sliver_faces
        assert counts[2] == py.n_dihedral_sharp
        assert stats[0] == pytest.approx(py.dihedral_min_deg, abs=1e-10)
        assert stats[1] == pytest.approx(py.dihedral_max_deg, abs=1e-10)
        assert stats[2] == pytest.approx(py.dihedral_mean_deg, abs=1e-10)
        assert stats[3] == pytest.approx(py.face_area_min, rel=1e-12, abs=1e-12)
        assert stats[4] == pytest.approx(py.face_area_max, rel=1e-12, abs=1e-12)
        assert stats[5] == pytest.approx(py.aspect_ratio_max, rel=1e-12, abs=1e-12)


class TestDihedralHistogram:

    def test_dihedral_histogram_native_route_matches_fallback(self, monkeypatch):
        rng = np.random.default_rng(3900)
        verts = rng.standard_normal((820, 3))
        faces = np.array(
            [rng.choice(820, size=3, replace=False) for _ in range(760)],
            dtype=np.int64,
        )
        for i in range(0, 90, 2):
            faces[i + 1, 0] = faces[i, 1]
            faces[i + 1, 1] = faces[i, 0]

        bins = (0, 45, 90, 135, 180)
        native = dihedral_hist_module.dihedral_histogram(verts, faces, bin_edges_deg=bins)
        assert _c_surface_dihedral_histogram_batch(
            verts, faces, np.asarray(bins, dtype=np.float64),
        ) is not None
        monkeypatch.setattr(
            dihedral_hist_module,
            "_c_surface_dihedral_histogram_batch",
            None,
        )
        python = dihedral_hist_module.dihedral_histogram(verts, faces, bin_edges_deg=bins)

        assert native.n_edges == python.n_edges
        assert native.angle_min_deg == pytest.approx(python.angle_min_deg, abs=1e-10)
        assert native.angle_max_deg == pytest.approx(python.angle_max_deg, abs=1e-10)
        assert native.angle_mean_deg == pytest.approx(python.angle_mean_deg, abs=1e-10)
        assert native.bins_deg == python.bins_deg
        assert native.counts == python.counts

    def test_dihedral_histogram_stats_match_python_reference(self):
        rng = np.random.default_rng(3910)
        verts = rng.standard_normal((620, 3))
        faces = np.array(
            [rng.choice(620, size=3, replace=False) for _ in range(540)],
            dtype=np.int64,
        )
        for i in range(0, 70, 2):
            faces[i + 1, 0] = faces[i, 1]
            faces[i + 1, 1] = faces[i, 0]

        bins = np.asarray((0, 30, 60, 90, 120, 150, 180), dtype=np.float64)
        native = _c_surface_dihedral_histogram_batch(verts, faces, bins)
        assert native is not None
        counts, stats = native
        py = dihedral_hist_module.dihedral_histogram(verts, faces)
        assert int(stats[0]) == py.n_edges
        assert stats[1] == pytest.approx(py.angle_min_deg, abs=1e-10)
        assert stats[2] == pytest.approx(py.angle_max_deg, abs=1e-10)
        assert stats[3] == pytest.approx(py.angle_mean_deg, abs=1e-10)
        assert tuple(int(c) for c in counts) == py.counts


class TestMeanCurvature:

    def test_mean_curvature_native_route_matches_fallback(self, monkeypatch):
        rng = np.random.default_rng(4000)
        verts = rng.standard_normal((260, 3))
        faces = np.array(
            [rng.choice(260, size=3, replace=False) for _ in range(220)],
            dtype=np.int64,
        )
        faces[10, 1] = faces[10, 0]

        native_h, native_stats = mean_curvature_module.vertex_mean_curvature(verts, faces)
        assert _c_surface_vertex_mean_curvature_batch(verts, faces) is not None
        monkeypatch.setattr(
            mean_curvature_module,
            "_c_surface_vertex_mean_curvature_batch",
            None,
        )
        python_h, python_stats = mean_curvature_module.vertex_mean_curvature(verts, faces)

        np.testing.assert_allclose(native_h, python_h, rtol=1e-12, atol=1e-10)
        assert native_stats.n_vertices == python_stats.n_vertices
        assert native_stats.h_norm_min == pytest.approx(python_stats.h_norm_min, abs=1e-10)
        assert native_stats.h_norm_max == pytest.approx(python_stats.h_norm_max, abs=1e-10)
        assert native_stats.h_norm_mean == pytest.approx(python_stats.h_norm_mean, abs=1e-10)
        assert native_stats.h_norm_p99 == pytest.approx(python_stats.h_norm_p99, abs=1e-10)

    def test_mean_curvature_batch_matches_python_reference(self):
        rng = np.random.default_rng(4010)
        verts = rng.standard_normal((240, 3))
        faces = np.array(
            [rng.choice(240, size=3, replace=False) for _ in range(200)],
            dtype=np.int64,
        )
        got = _c_surface_vertex_mean_curvature_batch(verts, faces)
        assert got is not None
        h, stats = got
        # Use the Python fallback by temporarily disabling the module-level hook.
        old = mean_curvature_module._c_surface_vertex_mean_curvature_batch
        mean_curvature_module._c_surface_vertex_mean_curvature_batch = None
        try:
            ref_h, ref_stats = mean_curvature_module.vertex_mean_curvature(verts, faces)
        finally:
            mean_curvature_module._c_surface_vertex_mean_curvature_batch = old
        np.testing.assert_allclose(h, ref_h, rtol=1e-12, atol=1e-10)
        assert stats[0] == pytest.approx(ref_stats.h_norm_min, abs=1e-10)
        assert stats[1] == pytest.approx(ref_stats.h_norm_max, abs=1e-10)
        assert stats[2] == pytest.approx(ref_stats.h_norm_mean, abs=1e-10)
        assert stats[3] == pytest.approx(ref_stats.h_norm_p99, abs=1e-10)


class TestVertexValence:

    def test_vertex_valence_native_route_matches_fallback(self, monkeypatch):
        rng = np.random.default_rng(4100)
        n_vertices = 420
        faces = np.array(
            [rng.choice(n_vertices, size=3, replace=False) for _ in range(360)],
            dtype=np.int64,
        )
        faces[10] = faces[0]
        native_fv, native_ev, native_stats = vertex_valence_module.surface_vertex_valence(
            faces, n_vertices=n_vertices,
        )
        assert _c_surface_vertex_valence_batch(faces, n_vertices) is not None
        monkeypatch.setattr(vertex_valence_module, "_c_surface_vertex_valence_batch", None)
        python_fv, python_ev, python_stats = vertex_valence_module.surface_vertex_valence(
            faces, n_vertices=n_vertices,
        )

        np.testing.assert_array_equal(native_fv, python_fv)
        np.testing.assert_array_equal(native_ev, python_ev)
        assert native_stats.n_vertices == python_stats.n_vertices
        assert native_stats.n_used == python_stats.n_used
        assert native_stats.face_valence_min == python_stats.face_valence_min
        assert native_stats.face_valence_max == python_stats.face_valence_max
        assert native_stats.face_valence_mean == pytest.approx(python_stats.face_valence_mean)
        assert native_stats.edge_valence_min == python_stats.edge_valence_min
        assert native_stats.edge_valence_max == python_stats.edge_valence_max
        assert native_stats.edge_valence_mean == pytest.approx(python_stats.edge_valence_mean)
        assert native_stats.n_high_face_valence == python_stats.n_high_face_valence
        assert native_stats.n_isolated == python_stats.n_isolated

    def test_vertex_valence_batch_matches_numpy_reference(self):
        rng = np.random.default_rng(4110)
        n_vertices = 380
        faces = np.array(
            [rng.choice(n_vertices, size=3, replace=False) for _ in range(330)],
            dtype=np.int64,
        )
        got = _c_surface_vertex_valence_batch(faces, n_vertices)
        assert got is not None
        face_val, edge_val, stats, means = got
        old = vertex_valence_module._c_surface_vertex_valence_batch
        vertex_valence_module._c_surface_vertex_valence_batch = None
        try:
            ref_fv, ref_ev, ref_stats = vertex_valence_module.surface_vertex_valence(
                faces, n_vertices=n_vertices,
            )
        finally:
            vertex_valence_module._c_surface_vertex_valence_batch = old

        np.testing.assert_array_equal(face_val, ref_fv)
        np.testing.assert_array_equal(edge_val, ref_ev)
        assert stats[0] == ref_stats.n_used
        assert stats[1] == ref_stats.face_valence_min
        assert stats[2] == ref_stats.face_valence_max
        assert stats[3] == ref_stats.edge_valence_min
        assert stats[4] == ref_stats.edge_valence_max
        assert stats[5] == ref_stats.n_high_face_valence
        assert stats[6] == ref_stats.n_isolated
        assert means[0] == pytest.approx(ref_stats.face_valence_mean)
        assert means[1] == pytest.approx(ref_stats.edge_valence_mean)


class TestTetVertexValence:

    def test_tet_vertex_valence_native_route_matches_fallback(self, monkeypatch):
        rng = np.random.default_rng(4120)
        n_vertices = 640
        tets = rng.integers(0, n_vertices, size=(520, 4), dtype=np.int64)
        tets[7] = np.array([3, 3, 12, 12], dtype=np.int64)

        native_val, native_stats = tet_valence_module.tet_vertex_valence(n_vertices, tets)
        assert _c_tet_vertex_valence_batch(tets, n_vertices) is not None
        monkeypatch.setattr(tet_valence_module, "_c_tet_vertex_valence_batch", None)
        python_val, python_stats = tet_valence_module.tet_vertex_valence(n_vertices, tets)

        np.testing.assert_array_equal(native_val, python_val)
        assert native_stats.n_vertices == python_stats.n_vertices
        assert native_stats.n_used == python_stats.n_used
        assert native_stats.valence_min == python_stats.valence_min
        assert native_stats.valence_max == python_stats.valence_max
        assert native_stats.valence_mean == pytest.approx(python_stats.valence_mean)
        assert native_stats.valence_p99 == pytest.approx(python_stats.valence_p99)
        assert native_stats.n_above_50 == python_stats.n_above_50
        assert native_stats.n_isolated == python_stats.n_isolated

    def test_tet_vertex_valence_batch_matches_numpy_reference(self):
        rng = np.random.default_rng(4130)
        n_vertices = 580
        tets = rng.integers(0, n_vertices, size=(470, 4), dtype=np.int64)
        tets[11] = np.array([5, 5, 5, 5], dtype=np.int64)

        got = _c_tet_vertex_valence_batch(tets, n_vertices)
        assert got is not None
        valence, stats, floats = got

        old = tet_valence_module._c_tet_vertex_valence_batch
        tet_valence_module._c_tet_vertex_valence_batch = None
        try:
            ref_valence, ref_stats = tet_valence_module.tet_vertex_valence(n_vertices, tets)
        finally:
            tet_valence_module._c_tet_vertex_valence_batch = old

        np.testing.assert_array_equal(valence, ref_valence)
        assert stats[0] == ref_stats.n_used
        assert stats[1] == ref_stats.valence_min
        assert stats[2] == ref_stats.valence_max
        assert stats[3] == ref_stats.n_above_50
        assert stats[4] == ref_stats.n_isolated
        assert floats[0] == pytest.approx(ref_stats.valence_mean)
        assert floats[1] == pytest.approx(ref_stats.valence_p99)


class TestBoundaryVertexStats:

    def test_boundary_vertex_stats_native_route_matches_fallback(self, monkeypatch):
        rng = np.random.default_rng(4140)
        n_vertices = 720
        n_surface = 180
        pts = rng.random((n_vertices, 3))
        tets = rng.integers(0, n_vertices, size=(610, 4), dtype=np.int64)
        tets[0] = np.array([n_surface, n_surface + 1, n_surface + 2, n_surface + 3])
        tets[1] = np.array([0, n_surface + 4, n_surface + 5, n_surface + 6])

        native = boundary_stats_module.boundary_vertex_stats(pts, tets, n_surface)
        assert _c_tet_boundary_vertex_stats_batch(tets, n_surface) is not None
        monkeypatch.setattr(boundary_stats_module, "_c_tet_boundary_vertex_stats_batch", None)
        fallback = boundary_stats_module.boundary_vertex_stats(pts, tets, n_surface)

        assert native.n_total_vertices == fallback.n_total_vertices
        assert native.n_surface_vertices == fallback.n_surface_vertices
        assert native.n_interior_vertices == fallback.n_interior_vertices
        assert native.n_boundary_tets == fallback.n_boundary_tets
        assert native.n_interior_tets == fallback.n_interior_tets
        assert native.surface_ratio == pytest.approx(fallback.surface_ratio)

    def test_boundary_vertex_stats_batch_matches_numpy_reference(self):
        rng = np.random.default_rng(4150)
        n_vertices = 500
        n_surface = 125
        tets = rng.integers(0, n_vertices, size=(430, 4), dtype=np.int64)

        got = _c_tet_boundary_vertex_stats_batch(tets, n_surface)
        assert got is not None
        is_boundary = (tets < n_surface).any(axis=1)
        assert got[0] == int(is_boundary.sum())
        assert got[1] == int(tets.shape[0] - is_boundary.sum())

        got_zero = _c_tet_boundary_vertex_stats_batch(tets, 0)
        assert got_zero == (0, int(tets.shape[0]))


class TestTetEdgeStats:

    def test_tet_edge_stats_native_route_matches_fallback(self, monkeypatch):
        rng = np.random.default_rng(4160)
        pts = rng.random((760, 3))
        tets = rng.integers(0, pts.shape[0], size=(540, 4), dtype=np.int64)
        tets[3] = np.array([8, 8, 9, 10], dtype=np.int64)

        native = tet_edge_stats_module.tet_edge_stats(pts, tets, sliver_aniso=6.5)
        assert _c_tet_edge_stats_batch(pts, tets, 6.5) is not None
        monkeypatch.setattr(tet_edge_stats_module, "_c_tet_edge_stats_batch", None)
        fallback = tet_edge_stats_module.tet_edge_stats(pts, tets, sliver_aniso=6.5)

        assert native.n_tets == fallback.n_tets
        assert native.edge_min == pytest.approx(fallback.edge_min, abs=1e-12)
        assert native.edge_max == pytest.approx(fallback.edge_max, abs=1e-12)
        assert native.edge_mean == pytest.approx(fallback.edge_mean, abs=1e-12)
        assert native.edge_p99 == pytest.approx(fallback.edge_p99, abs=1e-12)
        assert native.aniso_max == pytest.approx(fallback.aniso_max, abs=1e-12)
        assert native.aniso_mean == pytest.approx(fallback.aniso_mean, abs=1e-12)
        assert native.n_sliver == fallback.n_sliver

    def test_tet_edge_stats_batch_matches_numpy_reference(self):
        rng = np.random.default_rng(4170)
        pts = rng.random((620, 3))
        tets = rng.integers(0, pts.shape[0], size=(490, 4), dtype=np.int64)
        tets[5] = np.array([2, 2, 2, 3], dtype=np.int64)

        got = _c_tet_edge_stats_batch(pts, tets, 4.0)
        assert got is not None
        stats, n_sliver = got

        old = tet_edge_stats_module._c_tet_edge_stats_batch
        tet_edge_stats_module._c_tet_edge_stats_batch = None
        try:
            ref = tet_edge_stats_module.tet_edge_stats(pts, tets, sliver_aniso=4.0)
        finally:
            tet_edge_stats_module._c_tet_edge_stats_batch = old

        assert stats[0] == pytest.approx(ref.edge_min, abs=1e-12)
        assert stats[1] == pytest.approx(ref.edge_max, abs=1e-12)
        assert stats[2] == pytest.approx(ref.edge_mean, abs=1e-12)
        assert stats[3] == pytest.approx(ref.edge_p99, abs=1e-12)
        assert stats[4] == pytest.approx(ref.aniso_max, abs=1e-12)
        assert stats[5] == pytest.approx(ref.aniso_mean, abs=1e-12)
        assert n_sliver == ref.n_sliver


class TestVolumeStats:

    def test_volume_stats_native_route_matches_fallback(self, monkeypatch):
        rng = np.random.default_rng(4180)
        pts = rng.random((780, 3))
        tets = rng.integers(0, pts.shape[0], size=(560, 4), dtype=np.int64)
        tets[0] = np.array([0, 1, 2, 3], dtype=np.int64)
        tets[1] = np.array([0, 2, 1, 3], dtype=np.int64)

        native = volume_stats_module.compute_tet_stats(pts, tets, n_bins=16)
        assert _c_tet_volume_stats_batch(pts, tets, 16) is not None
        monkeypatch.setattr(volume_stats_module, "_c_tet_volume_stats_batch", None)
        fallback = volume_stats_module.compute_tet_stats(pts, tets, n_bins=16)

        assert native.n_cells == fallback.n_cells
        assert native.n_tet == fallback.n_tet
        assert native.quality_min == pytest.approx(fallback.quality_min, abs=1e-12)
        assert native.quality_max == pytest.approx(fallback.quality_max, abs=1e-12)
        assert native.quality_mean == pytest.approx(fallback.quality_mean, abs=1e-12)
        assert native.quality_p5 == pytest.approx(fallback.quality_p5, abs=1e-12)
        assert native.quality_p50 == pytest.approx(fallback.quality_p50, abs=1e-12)
        assert native.quality_p95 == pytest.approx(fallback.quality_p95, abs=1e-12)
        assert native.volume_min == pytest.approx(fallback.volume_min, abs=1e-12)
        assert native.volume_max == pytest.approx(fallback.volume_max, abs=1e-12)
        assert native.volume_total == pytest.approx(fallback.volume_total, abs=1e-12)
        assert native.n_negative_volume == fallback.n_negative_volume
        assert native.histogram_bins == fallback.histogram_bins

    def test_volume_stats_batch_matches_numpy_reference(self):
        rng = np.random.default_rng(4190)
        pts = rng.random((620, 3))
        tets = rng.integers(0, pts.shape[0], size=(480, 4), dtype=np.int64)

        got = _c_tet_volume_stats_batch(pts, tets, 12)
        assert got is not None
        stats, n_neg, hist = got

        old = volume_stats_module._c_tet_volume_stats_batch
        volume_stats_module._c_tet_volume_stats_batch = None
        try:
            ref = volume_stats_module.compute_tet_stats(pts, tets, n_bins=12)
        finally:
            volume_stats_module._c_tet_volume_stats_batch = old

        assert stats[0] == pytest.approx(ref.quality_min, abs=1e-12)
        assert stats[1] == pytest.approx(ref.quality_max, abs=1e-12)
        assert stats[2] == pytest.approx(ref.quality_mean, abs=1e-12)
        assert stats[3] == pytest.approx(ref.quality_p5, abs=1e-12)
        assert stats[4] == pytest.approx(ref.quality_p50, abs=1e-12)
        assert stats[5] == pytest.approx(ref.quality_p95, abs=1e-12)
        assert stats[6] == pytest.approx(ref.volume_min, abs=1e-12)
        assert stats[7] == pytest.approx(ref.volume_max, abs=1e-12)
        assert stats[8] == pytest.approx(ref.volume_total, abs=1e-12)
        assert n_neg == ref.n_negative_volume
        np.testing.assert_array_equal(hist, np.array([b[2] for b in ref.histogram_bins], dtype=np.int64))


class TestTetInradius:

    def test_tet_inradius_native_route_matches_fallback(self, monkeypatch):
        rng = np.random.default_rng(4200)
        pts = rng.random((720, 3))
        tets = rng.integers(0, pts.shape[0], size=(510, 4), dtype=np.int64)
        tets[4] = np.array([1, 1, 2, 3], dtype=np.int64)

        native_r, native = tet_inradius_module.tet_inradii(pts, tets)
        assert _c_tet_inradius_batch(pts, tets) is not None
        monkeypatch.setattr(tet_inradius_module, "_c_tet_inradius_batch", None)
        fallback_r, fallback = tet_inradius_module.tet_inradii(pts, tets)

        np.testing.assert_allclose(native_r, fallback_r, rtol=1e-12, atol=1e-12)
        assert native.n_tets == fallback.n_tets
        assert native.r_min == pytest.approx(fallback.r_min, abs=1e-12)
        assert native.r_max == pytest.approx(fallback.r_max, abs=1e-12)
        assert native.r_mean == pytest.approx(fallback.r_mean, abs=1e-12)
        assert native.n_zero_radius == fallback.n_zero_radius

    def test_tet_inradius_batch_matches_numpy_reference(self):
        rng = np.random.default_rng(4210)
        pts = rng.random((640, 3))
        tets = rng.integers(0, pts.shape[0], size=(470, 4), dtype=np.int64)

        got = _c_tet_inradius_batch(pts, tets)
        assert got is not None
        radii, stats, n_zero = got

        old = tet_inradius_module._c_tet_inradius_batch
        tet_inradius_module._c_tet_inradius_batch = None
        try:
            ref_radii, ref = tet_inradius_module.tet_inradii(pts, tets)
        finally:
            tet_inradius_module._c_tet_inradius_batch = old

        np.testing.assert_allclose(radii, ref_radii, rtol=1e-12, atol=1e-12)
        assert stats[0] == pytest.approx(ref.r_min, abs=1e-12)
        assert stats[1] == pytest.approx(ref.r_max, abs=1e-12)
        assert stats[2] == pytest.approx(ref.r_mean, abs=1e-12)
        assert n_zero == ref.n_zero_radius


class TestTetCircumsphere:

    def test_tet_circumsphere_native_route_matches_fallback(self, monkeypatch):
        rng = np.random.default_rng(4220)
        pts = rng.random((720, 3))
        tets = np.array(
            [rng.choice(pts.shape[0], size=4, replace=False) for _ in range(420)],
            dtype=np.int64,
        )
        tets[6] = np.array([4, 4, 8, 9], dtype=np.int64)

        native_centers, native_radii, native = tet_circumsphere_module.tet_circumspheres(pts, tets)
        assert _c_tet_circumsphere_batch(pts, tets) is not None
        monkeypatch.setattr(tet_circumsphere_module, "_c_tet_circumsphere_batch", None)
        fallback_centers, fallback_radii, fallback = tet_circumsphere_module.tet_circumspheres(pts, tets)

        np.testing.assert_allclose(native_centers, fallback_centers, rtol=1e-9, atol=1e-9)
        np.testing.assert_allclose(native_radii, fallback_radii, rtol=1e-9, atol=1e-9)
        assert native.n_tets == fallback.n_tets
        assert native.radius_min == pytest.approx(fallback.radius_min, abs=1e-9)
        assert native.radius_max == pytest.approx(fallback.radius_max, abs=1e-9)
        assert native.radius_mean == pytest.approx(fallback.radius_mean, abs=1e-9)
        assert native.n_degenerate == fallback.n_degenerate

    def test_tet_circumsphere_batch_matches_numpy_reference(self):
        rng = np.random.default_rng(4230)
        pts = rng.random((640, 3))
        tets = np.array(
            [rng.choice(pts.shape[0], size=4, replace=False) for _ in range(370)],
            dtype=np.int64,
        )

        got = _c_tet_circumsphere_batch(pts, tets)
        assert got is not None
        centers, radii, stats, n_deg = got

        old = tet_circumsphere_module._c_tet_circumsphere_batch
        tet_circumsphere_module._c_tet_circumsphere_batch = None
        try:
            ref_centers, ref_radii, ref = tet_circumsphere_module.tet_circumspheres(pts, tets)
        finally:
            tet_circumsphere_module._c_tet_circumsphere_batch = old

        np.testing.assert_allclose(centers, ref_centers, rtol=1e-9, atol=1e-9)
        np.testing.assert_allclose(radii, ref_radii, rtol=1e-9, atol=1e-9)
        assert stats[0] == pytest.approx(ref.radius_min, abs=1e-9)
        assert stats[1] == pytest.approx(ref.radius_max, abs=1e-9)
        assert stats[2] == pytest.approx(ref.radius_mean, abs=1e-9)
        assert n_deg == ref.n_degenerate


class TestAnisoTensor:

    def test_aniso_tensor_native_route_matches_fallback(self, monkeypatch):
        rng = np.random.default_rng(4240)
        pts = rng.random((720, 3))
        tets = np.array(
            [rng.choice(pts.shape[0], size=4, replace=False) for _ in range(430)],
            dtype=np.int64,
        )

        native_ratio, native = aniso_tensor_module.tet_aniso_tensor(pts, tets)
        assert _c_tet_aniso_tensor_batch(pts, tets) is not None
        monkeypatch.setattr(aniso_tensor_module, "_c_tet_aniso_tensor_batch", None)
        fallback_ratio, fallback = aniso_tensor_module.tet_aniso_tensor(pts, tets)

        np.testing.assert_allclose(native_ratio, fallback_ratio, rtol=1e-8, atol=1e-8)
        assert native.n_tets == fallback.n_tets
        assert native.aniso_min == pytest.approx(fallback.aniso_min, rel=1e-8, abs=1e-8)
        assert native.aniso_max == pytest.approx(fallback.aniso_max, rel=1e-8, abs=1e-8)
        assert native.aniso_mean == pytest.approx(fallback.aniso_mean, rel=1e-8, abs=1e-8)
        assert native.aniso_p99 == pytest.approx(fallback.aniso_p99, rel=1e-8, abs=1e-8)
        assert native.n_above_5 == fallback.n_above_5

    def test_aniso_tensor_batch_matches_numpy_reference(self):
        rng = np.random.default_rng(4250)
        pts = rng.random((640, 3))
        tets = np.array(
            [rng.choice(pts.shape[0], size=4, replace=False) for _ in range(380)],
            dtype=np.int64,
        )

        got = _c_tet_aniso_tensor_batch(pts, tets)
        assert got is not None
        ratio, stats, n_above_5 = got

        old = aniso_tensor_module._c_tet_aniso_tensor_batch
        aniso_tensor_module._c_tet_aniso_tensor_batch = None
        try:
            ref_ratio, ref = aniso_tensor_module.tet_aniso_tensor(pts, tets)
        finally:
            aniso_tensor_module._c_tet_aniso_tensor_batch = old

        np.testing.assert_allclose(ratio, ref_ratio, rtol=1e-8, atol=1e-8)
        assert stats[0] == pytest.approx(ref.aniso_min, rel=1e-8, abs=1e-8)
        assert stats[1] == pytest.approx(ref.aniso_max, rel=1e-8, abs=1e-8)
        assert stats[2] == pytest.approx(ref.aniso_mean, rel=1e-8, abs=1e-8)
        assert stats[3] == pytest.approx(ref.aniso_p99, rel=1e-8, abs=1e-8)
        assert n_above_5 == ref.n_above_5


class TestHexStretch:

    def test_hex_stretch_native_route_matches_fallback(self, monkeypatch):
        rng = np.random.default_rng(4260)
        pts = rng.random((840, 3))
        hexes = rng.integers(0, pts.shape[0], size=(520, 8), dtype=np.int64)
        hexes[0] = np.array([0, 1, 2, 3, 4, 5, 6, 7], dtype=np.int64)

        native = hex_stretch_module.hex_stretch_stats(pts, hexes)
        assert _c_hex_stretch_stats_batch(pts, hexes) is not None
        monkeypatch.setattr(hex_stretch_module, "_c_hex_stretch_stats_batch", None)
        fallback = hex_stretch_module.hex_stretch_stats(pts, hexes)

        assert native.n_hexes == fallback.n_hexes
        assert native.stretch_min == pytest.approx(fallback.stretch_min, abs=1e-12)
        assert native.stretch_max == pytest.approx(fallback.stretch_max, abs=1e-12)
        assert native.stretch_mean == pytest.approx(fallback.stretch_mean, abs=1e-12)
        assert native.n_below_0p1 == fallback.n_below_0p1

    def test_hex_stretch_stats_batch_matches_numpy_reference(self):
        rng = np.random.default_rng(4270)
        pts = rng.random((760, 3))
        hexes = rng.integers(0, pts.shape[0], size=(470, 8), dtype=np.int64)

        got = _c_hex_stretch_stats_batch(pts, hexes)
        assert got is not None
        stats, n_below = got

        old = hex_stretch_module._c_hex_stretch_stats_batch
        hex_stretch_module._c_hex_stretch_stats_batch = None
        try:
            ref = hex_stretch_module.hex_stretch_stats(pts, hexes)
        finally:
            hex_stretch_module._c_hex_stretch_stats_batch = old

        assert stats[0] == pytest.approx(ref.stretch_min, abs=1e-12)
        assert stats[1] == pytest.approx(ref.stretch_max, abs=1e-12)
        assert stats[2] == pytest.approx(ref.stretch_mean, abs=1e-12)
        assert n_below == ref.n_below_0p1


class TestHexFaceArea:

    def test_hex_face_area_native_route_matches_fallback(self, monkeypatch):
        rng = np.random.default_rng(4280)
        pts = rng.random((840, 3))
        hexes = rng.integers(0, pts.shape[0], size=(520, 8), dtype=np.int64)
        hexes[0] = np.array([0, 1, 2, 3, 4, 5, 6, 7], dtype=np.int64)

        native = hex_face_area_module.hex_face_area_stats(pts, hexes)
        assert _c_hex_face_area_stats_batch(pts, hexes) is not None
        monkeypatch.setattr(hex_face_area_module, "_c_hex_face_area_stats_batch", None)
        fallback = hex_face_area_module.hex_face_area_stats(pts, hexes)

        assert native.n_hexes == fallback.n_hexes
        assert native.area_min == pytest.approx(fallback.area_min, abs=1e-12)
        assert native.area_max == pytest.approx(fallback.area_max, abs=1e-12)
        assert native.area_mean == pytest.approx(fallback.area_mean, abs=1e-12)
        assert native.ratio_max == pytest.approx(fallback.ratio_max, abs=1e-12)
        assert native.ratio_mean == pytest.approx(fallback.ratio_mean, abs=1e-12)
        assert native.n_stretched == fallback.n_stretched

    def test_hex_face_area_stats_batch_matches_numpy_reference(self):
        rng = np.random.default_rng(4290)
        pts = rng.random((760, 3))
        hexes = rng.integers(0, pts.shape[0], size=(470, 8), dtype=np.int64)

        got = _c_hex_face_area_stats_batch(pts, hexes)
        assert got is not None
        stats, n_stretched = got

        old = hex_face_area_module._c_hex_face_area_stats_batch
        hex_face_area_module._c_hex_face_area_stats_batch = None
        try:
            ref = hex_face_area_module.hex_face_area_stats(pts, hexes)
        finally:
            hex_face_area_module._c_hex_face_area_stats_batch = old

        assert stats[0] == pytest.approx(ref.area_min, abs=1e-12)
        assert stats[1] == pytest.approx(ref.area_max, abs=1e-12)
        assert stats[2] == pytest.approx(ref.area_mean, abs=1e-12)
        assert stats[3] == pytest.approx(ref.ratio_max, abs=1e-12)
        assert stats[4] == pytest.approx(ref.ratio_mean, abs=1e-12)
        assert n_stretched == ref.n_stretched


class TestBLQuality:

    def test_bl_quality_native_route_matches_fallback(self, monkeypatch):
        rng = np.random.default_rng(4300)
        pts = rng.random((840, 3))
        prisms = rng.integers(0, pts.shape[0], size=(520, 6), dtype=np.int64)
        prisms[0] = np.array([0, 1, 2, 3, 4, 5], dtype=np.int64)

        native = bl_quality_module.bl_prism_quality(pts, prisms)
        assert _c_bl_prism_quality_stats_batch(pts, prisms) is not None
        monkeypatch.setattr(bl_quality_module, "_c_bl_prism_quality_stats_batch", None)
        fallback = bl_quality_module.bl_prism_quality(pts, prisms)

        assert native.n_prisms == fallback.n_prisms
        assert native.aspect_min == pytest.approx(fallback.aspect_min, abs=1e-12)
        assert native.aspect_max == pytest.approx(fallback.aspect_max, abs=1e-12)
        assert native.aspect_mean == pytest.approx(fallback.aspect_mean, abs=1e-12)
        assert native.thickness_uniformity_mean == pytest.approx(
            fallback.thickness_uniformity_mean, abs=1e-12,
        )
        assert native.skew_max == pytest.approx(fallback.skew_max, abs=1e-12)
        assert native.skew_mean == pytest.approx(fallback.skew_mean, abs=1e-12)
        assert native.n_inverted == fallback.n_inverted

    def test_bl_quality_stats_batch_matches_numpy_reference(self):
        rng = np.random.default_rng(4310)
        pts = rng.random((760, 3))
        prisms = rng.integers(0, pts.shape[0], size=(470, 6), dtype=np.int64)

        got = _c_bl_prism_quality_stats_batch(pts, prisms)
        assert got is not None
        stats, n_inv = got

        old = bl_quality_module._c_bl_prism_quality_stats_batch
        bl_quality_module._c_bl_prism_quality_stats_batch = None
        try:
            ref = bl_quality_module.bl_prism_quality(pts, prisms)
        finally:
            bl_quality_module._c_bl_prism_quality_stats_batch = old

        assert stats[0] == pytest.approx(ref.aspect_min, abs=1e-12)
        assert stats[1] == pytest.approx(ref.aspect_max, abs=1e-12)
        assert stats[2] == pytest.approx(ref.aspect_mean, abs=1e-12)
        assert stats[3] == pytest.approx(ref.thickness_uniformity_mean, abs=1e-12)
        assert stats[4] == pytest.approx(ref.skew_max, abs=1e-12)
        assert stats[5] == pytest.approx(ref.skew_mean, abs=1e-12)
        assert n_inv == ref.n_inverted


class TestHexSkewSimple:

    def test_hex_skew_simple_native_route_matches_fallback(self, monkeypatch):
        rng = np.random.default_rng(4320)
        pts = rng.random((840, 3))
        hexes = rng.integers(0, pts.shape[0], size=(520, 8), dtype=np.int64)
        hexes[0] = np.array([0, 1, 2, 3, 4, 5, 6, 7], dtype=np.int64)

        native = hex_skew_simple_module.hex_skew_simple(pts, hexes)
        assert _c_hex_skew_simple_stats_batch(pts, hexes) is not None
        monkeypatch.setattr(hex_skew_simple_module, "_c_hex_skew_simple_stats_batch", None)
        fallback = hex_skew_simple_module.hex_skew_simple(pts, hexes)

        assert native.n_hexes == fallback.n_hexes
        assert native.skew_min == pytest.approx(fallback.skew_min, abs=1e-12)
        assert native.skew_max == pytest.approx(fallback.skew_max, abs=1e-12)
        assert native.skew_mean == pytest.approx(fallback.skew_mean, abs=1e-12)
        assert native.n_above_1 == fallback.n_above_1

    def test_hex_skew_simple_stats_batch_matches_numpy_reference(self):
        rng = np.random.default_rng(4330)
        pts = rng.random((760, 3))
        hexes = rng.integers(0, pts.shape[0], size=(470, 8), dtype=np.int64)

        got = _c_hex_skew_simple_stats_batch(pts, hexes)
        assert got is not None
        stats, n_above = got

        old = hex_skew_simple_module._c_hex_skew_simple_stats_batch
        hex_skew_simple_module._c_hex_skew_simple_stats_batch = None
        try:
            ref = hex_skew_simple_module.hex_skew_simple(pts, hexes)
        finally:
            hex_skew_simple_module._c_hex_skew_simple_stats_batch = old

        assert stats[0] == pytest.approx(ref.skew_min, abs=1e-12)
        assert stats[1] == pytest.approx(ref.skew_max, abs=1e-12)
        assert stats[2] == pytest.approx(ref.skew_mean, abs=1e-12)
        assert n_above == ref.n_above_1


class TestHexOrtho:

    def test_hex_ortho_native_route_matches_fallback(self, monkeypatch):
        rng = np.random.default_rng(4340)
        pts = rng.random((840, 3))
        hexes = rng.integers(0, pts.shape[0], size=(520, 8), dtype=np.int64)
        hexes[0] = np.array([0, 1, 2, 3, 4, 5, 6, 7], dtype=np.int64)

        native = hex_ortho_module.hex_ortho_stats(pts, hexes)
        assert _c_hex_ortho_stats_batch(pts, hexes) is not None
        monkeypatch.setattr(hex_ortho_module, "_c_hex_ortho_stats_batch", None)
        fallback = hex_ortho_module.hex_ortho_stats(pts, hexes)

        assert native.n_hexes == fallback.n_hexes
        assert native.ortho_min_deg == pytest.approx(fallback.ortho_min_deg, abs=1e-12)
        assert native.ortho_max_deg == pytest.approx(fallback.ortho_max_deg, abs=1e-12)
        assert native.ortho_mean_deg == pytest.approx(fallback.ortho_mean_deg, abs=1e-12)
        assert native.n_above_30deg == fallback.n_above_30deg

    def test_hex_ortho_stats_batch_matches_numpy_reference(self):
        rng = np.random.default_rng(4350)
        pts = rng.random((760, 3))
        hexes = rng.integers(0, pts.shape[0], size=(470, 8), dtype=np.int64)

        got = _c_hex_ortho_stats_batch(pts, hexes)
        assert got is not None
        stats, n_above = got

        old = hex_ortho_module._c_hex_ortho_stats_batch
        hex_ortho_module._c_hex_ortho_stats_batch = None
        try:
            ref = hex_ortho_module.hex_ortho_stats(pts, hexes)
        finally:
            hex_ortho_module._c_hex_ortho_stats_batch = old

        assert stats[0] == pytest.approx(ref.ortho_min_deg, abs=1e-12)
        assert stats[1] == pytest.approx(ref.ortho_max_deg, abs=1e-12)
        assert stats[2] == pytest.approx(ref.ortho_mean_deg, abs=1e-12)
        assert n_above == ref.n_above_30deg


class TestHexJacobian:

    def test_hex_jacobian_native_route_matches_fallback(self, monkeypatch):
        rng = np.random.default_rng(4360)
        pts = rng.random((840, 3))
        hexes = rng.integers(0, pts.shape[0], size=(520, 8), dtype=np.int64)
        hexes[0] = np.array([0, 1, 2, 3, 4, 5, 6, 7], dtype=np.int64)

        native = hex_jacobian_module.hex_jacobian_stats(pts, hexes)
        assert _c_hex_jacobian_stats_batch(pts, hexes) is not None
        monkeypatch.setattr(hex_jacobian_module, "_c_hex_jacobian_stats_batch", None)
        fallback = hex_jacobian_module.hex_jacobian_stats(pts, hexes)

        assert native.n_hexes == fallback.n_hexes
        assert native.j_min == pytest.approx(fallback.j_min, abs=1e-12)
        assert native.j_max == pytest.approx(fallback.j_max, abs=1e-12)
        assert native.j_mean == pytest.approx(fallback.j_mean, abs=1e-12)
        assert native.n_inverted == fallback.n_inverted
        assert native.scaled_j_min == pytest.approx(fallback.scaled_j_min, abs=1e-11)
        assert native.scaled_j_mean == pytest.approx(fallback.scaled_j_mean, abs=1e-11)

    def test_hex_jacobian_stats_batch_matches_numpy_reference(self):
        rng = np.random.default_rng(4370)
        pts = rng.random((760, 3))
        hexes = rng.integers(0, pts.shape[0], size=(470, 8), dtype=np.int64)

        got = _c_hex_jacobian_stats_batch(pts, hexes)
        assert got is not None
        stats, n_inv = got

        old = hex_jacobian_module._c_hex_jacobian_stats_batch
        hex_jacobian_module._c_hex_jacobian_stats_batch = None
        try:
            ref = hex_jacobian_module.hex_jacobian_stats(pts, hexes)
        finally:
            hex_jacobian_module._c_hex_jacobian_stats_batch = old

        assert stats[0] == pytest.approx(ref.j_min, abs=1e-12)
        assert stats[1] == pytest.approx(ref.j_max, abs=1e-12)
        assert stats[2] == pytest.approx(ref.j_mean, abs=1e-12)
        assert stats[3] == pytest.approx(ref.scaled_j_min, abs=1e-11)
        assert stats[4] == pytest.approx(ref.scaled_j_mean, abs=1e-11)
        assert n_inv == ref.n_inverted


class TestHexInverted:

    def test_hex_inverted_native_route_matches_fallback(self, monkeypatch):
        rng = np.random.default_rng(4380)
        pts = rng.random((840, 3))
        hexes = rng.integers(0, pts.shape[0], size=(520, 8), dtype=np.int64)
        hexes[0] = np.array([0, 1, 2, 3, 4, 5, 6, 7], dtype=np.int64)

        native = hex_inverted_module.detect_inverted_hexes(pts, hexes)
        assert _c_hex_inverted_stats_batch(pts, hexes, 100) is not None
        monkeypatch.setattr(hex_inverted_module, "_c_hex_inverted_stats_batch", None)
        fallback = hex_inverted_module.detect_inverted_hexes(pts, hexes)

        assert native.n_hexes == fallback.n_hexes
        assert native.n_inverted == fallback.n_inverted
        assert native.inverted_indices == fallback.inverted_indices
        assert native.worst_j_min == pytest.approx(fallback.worst_j_min, abs=1e-12)
        assert native.worst_hex_idx == fallback.worst_hex_idx

    def test_hex_inverted_stats_batch_matches_numpy_reference(self):
        rng = np.random.default_rng(4390)
        pts = rng.random((760, 3))
        hexes = rng.integers(0, pts.shape[0], size=(470, 8), dtype=np.int64)

        got = _c_hex_inverted_stats_batch(pts, hexes, 100)
        assert got is not None
        indices, counts, worst = got

        old = hex_inverted_module._c_hex_inverted_stats_batch
        hex_inverted_module._c_hex_inverted_stats_batch = None
        try:
            ref = hex_inverted_module.detect_inverted_hexes(pts, hexes)
        finally:
            hex_inverted_module._c_hex_inverted_stats_batch = old

        np.testing.assert_array_equal(indices, np.array(ref.inverted_indices, dtype=np.int64))
        assert counts[0] == ref.n_inverted
        assert counts[1] == ref.worst_hex_idx
        assert counts[2] == len(ref.inverted_indices)
        assert worst == pytest.approx(ref.worst_j_min, abs=1e-12)


def _axis_aligned_hex_batch(n_hex: int) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(4540 + n_hex)
    base = rng.random((n_hex, 3))
    d = 0.01
    offsets = np.array(
        [
            [0.0, 0.0, 0.0],
            [d, 0.0, 0.0],
            [d, d, 0.0],
            [0.0, d, 0.0],
            [0.0, 0.0, d],
            [d, 0.0, d],
            [d, d, d],
            [0.0, d, d],
        ],
        dtype=np.float64,
    )
    pts = (base[:, None, :] + offsets[None, :, :]).reshape(-1, 3)
    hexes = np.arange(n_hex * 8, dtype=np.int64).reshape(n_hex, 8)
    hexes[::7] = hexes[::7][:, [4, 5, 6, 7, 0, 1, 2, 3]]
    return pts, hexes


class TestNativeHexValidateVolumes:

    def test_hex_validate_volumes_native_route_matches_fallback(self, monkeypatch):
        pts, hexes = _axis_aligned_hex_batch(96)

        native = native_hex_mesher_module.validate_hex_cell_volumes(pts, hexes)
        assert _c_hex_validate_volumes_batch(pts, hexes, 1e-20) is not None
        monkeypatch.setattr(native_hex_mesher_module, "_c_hex_validate_volumes_batch", None)
        fallback = native_hex_mesher_module.validate_hex_cell_volumes(pts, hexes)

        np.testing.assert_array_equal(native[0], fallback[0])
        assert native[1] == fallback[1]
        assert native[2] == fallback[2]

    def test_hex_validate_volumes_batch_matches_python_reference(self):
        pts, hexes = _axis_aligned_hex_batch(128)

        got = _c_hex_validate_volumes_batch(pts, hexes, 1e-20)
        assert got is not None

        old_c = native_hex_mesher_module._c_hex_validate_volumes_batch
        try:
            native_hex_mesher_module._c_hex_validate_volumes_batch = None
            ref = native_hex_mesher_module.validate_hex_cell_volumes(pts, hexes)
        finally:
            native_hex_mesher_module._c_hex_validate_volumes_batch = old_c

        np.testing.assert_array_equal(got[0], ref[0])
        assert got[1] == ref[1]
        assert got[2] == ref[2]


class TestNativeHexSnapClosestPoint:

    def test_closest_points_candidates_batch_matches_python_reference(self):
        rng = np.random.default_rng(4550)
        n_points = 240
        n_tri = 90
        points = rng.random((n_points, 3))
        tri_a = rng.random((n_tri, 3))
        tri_b = rng.random((n_tri, 3))
        tri_c = rng.random((n_tri, 3))
        candidates = rng.integers(0, n_tri, size=(n_points, 4), dtype=np.int64)
        candidates[::11, 2:] = n_tri + 3

        got = _c_closest_points_on_triangles_candidates_batch(
            points, tri_a, tri_b, tri_c, candidates
        )
        assert got is not None
        best_pts, best_dist2, has = got

        ref_pts = np.empty_like(points)
        ref_dist2 = np.empty(n_points, dtype=np.float64)
        ref_has = np.zeros(n_points, dtype=bool)
        for i, point in enumerate(points):
            best_pt = point
            best_d2 = np.inf
            for cand in candidates[i]:
                if cand < 0 or cand >= n_tri:
                    continue
                pt = native_hex_snap_module._closest_point_on_triangle(
                    point, tri_a[cand], tri_b[cand], tri_c[cand]
                )
                d2 = float(((pt - point) ** 2).sum())
                if not ref_has[i] or d2 < best_d2:
                    best_d2 = d2
                    best_pt = pt
                    ref_has[i] = True
            ref_pts[i] = best_pt
            ref_dist2[i] = best_d2

        np.testing.assert_array_equal(has, ref_has)
        np.testing.assert_allclose(best_pts, ref_pts, rtol=1e-12, atol=1e-12)
        np.testing.assert_allclose(best_dist2, ref_dist2, rtol=1e-12, atol=1e-12)

    def test_snap_hex_boundary_native_route_matches_fallback(self, monkeypatch):
        rng = np.random.default_rng(4560)
        n_tri = 120
        n_pts = 400
        surface_v = rng.random((n_tri * 3, 3))
        surface_f = np.arange(n_tri * 3, dtype=np.int64).reshape(n_tri, 3)
        tri_centroids = surface_v[surface_f].mean(axis=1)
        base_idx = rng.integers(0, n_tri, size=n_pts, dtype=np.int64)
        hex_vertices = tri_centroids[base_idx] + rng.normal(scale=0.01, size=(n_pts, 3))

        native = native_hex_snap_module.snap_hex_boundary_to_surface(
            hex_vertices,
            surface_v,
            surface_f,
            0.05,
            max_snap_ratio=1.0,
            search_radius_ratio=3.0,
            preserve_features=False,
        )
        monkeypatch.setattr(native_hex_snap_module, "_c_closest_points_batch", None)
        fallback = native_hex_snap_module.snap_hex_boundary_to_surface(
            hex_vertices,
            surface_v,
            surface_f,
            0.05,
            max_snap_ratio=1.0,
            search_radius_ratio=3.0,
            preserve_features=False,
        )

        np.testing.assert_allclose(native[0], fallback[0], rtol=1e-12, atol=1e-12)
        assert native[1] == fallback[1]


def _poly_cube_cells(n_cells: int) -> tuple[np.ndarray, list[list[list[int]]]]:
    rng = np.random.default_rng(4570 + n_cells)
    base = rng.random((n_cells, 3))
    d = 0.01
    offsets = np.array(
        [
            [0.0, 0.0, 0.0],
            [d, 0.0, 0.0],
            [d, d, 0.0],
            [0.0, d, 0.0],
            [0.0, 0.0, d],
            [d, 0.0, d],
            [d, d, d],
            [0.0, d, d],
        ],
        dtype=np.float64,
    )
    points = (base[:, None, :] + offsets[None, :, :]).reshape(-1, 3)
    local_faces = [
        [0, 3, 2, 1],
        [4, 5, 6, 7],
        [0, 1, 5, 4],
        [3, 7, 6, 2],
        [0, 4, 7, 3],
        [1, 2, 6, 5],
    ]
    cells = []
    for ci in range(n_cells):
        offset = ci * 8
        faces = [[offset + v for v in face] for face in local_faces]
        if ci % 9 == 0:
            faces = [list(reversed(face)) for face in faces]
        cells.append(faces)
    return points, cells


class TestNativePolyValidateVolumes:

    def test_poly_validate_volumes_native_route_matches_fallback(self, monkeypatch):
        points, cells = _poly_cube_cells(96)

        native = native_poly_voronoi_module.validate_poly_cell_volumes(cells, points)
        assert _c_poly_validate_volumes_batch(points, cells, 1e-20) is not None
        monkeypatch.setattr(native_poly_voronoi_module, "_c_poly_validate_volumes_batch", None)
        fallback = native_poly_voronoi_module.validate_poly_cell_volumes(cells, points)

        assert native == fallback

    def test_poly_validate_volumes_batch_matches_python_reference(self):
        points, cells = _poly_cube_cells(128)

        got = _c_poly_validate_volumes_batch(points, cells, 1e-20)
        assert got is not None

        old_c = native_poly_voronoi_module._c_poly_validate_volumes_batch
        try:
            native_poly_voronoi_module._c_poly_validate_volumes_batch = None
            ref = native_poly_voronoi_module.validate_poly_cell_volumes(cells, points)
        finally:
            native_poly_voronoi_module._c_poly_validate_volumes_batch = old_c

        assert got == ref


class TestPolyVolume:

    def test_poly_volume_native_route_matches_fallback(self, monkeypatch):
        rng = np.random.default_rng(4400)
        pts = rng.random((900, 3))
        cell_face_lists = []
        for _ in range(80):
            faces = []
            base = rng.integers(0, pts.shape[0], size=24, dtype=np.int64)
            for j in range(6):
                faces.append(base[j * 4:(j + 1) * 4].copy())
            cell_face_lists.append(faces)

        native_vols, native = poly_volume_module.poly_cell_volumes(pts, cell_face_lists)
        assert _c_poly_volume_stats_batch(pts, cell_face_lists) is not None
        monkeypatch.setattr(poly_volume_module, "_c_poly_volume_stats_batch", None)
        fallback_vols, fallback = poly_volume_module.poly_cell_volumes(pts, cell_face_lists)

        np.testing.assert_allclose(native_vols, fallback_vols, rtol=1e-12, atol=1e-12)
        assert native.n_cells == fallback.n_cells
        assert native.volume_min == pytest.approx(fallback.volume_min, abs=1e-12)
        assert native.volume_max == pytest.approx(fallback.volume_max, abs=1e-12)
        assert native.volume_mean == pytest.approx(fallback.volume_mean, abs=1e-12)
        assert native.total_volume == pytest.approx(fallback.total_volume, abs=1e-12)
        assert native.n_negative == fallback.n_negative

    def test_poly_volume_stats_batch_matches_python_reference(self):
        rng = np.random.default_rng(4410)
        pts = rng.random((760, 3))
        cell_face_lists = []
        for _ in range(60):
            faces = []
            base = rng.integers(0, pts.shape[0], size=20, dtype=np.int64)
            for j in range(5):
                faces.append(base[j * 4:(j + 1) * 4].copy())
            cell_face_lists.append(faces)

        got = _c_poly_volume_stats_batch(pts, cell_face_lists)
        assert got is not None
        vols, stats, n_neg = got

        old = poly_volume_module._c_poly_volume_stats_batch
        poly_volume_module._c_poly_volume_stats_batch = None
        try:
            ref_vols, ref = poly_volume_module.poly_cell_volumes(pts, cell_face_lists)
        finally:
            poly_volume_module._c_poly_volume_stats_batch = old

        np.testing.assert_allclose(vols, ref_vols, rtol=1e-12, atol=1e-12)
        assert stats[0] == pytest.approx(ref.volume_min, abs=1e-12)
        assert stats[1] == pytest.approx(ref.volume_max, abs=1e-12)
        assert stats[2] == pytest.approx(ref.volume_mean, abs=1e-12)
        assert stats[3] == pytest.approx(ref.total_volume, abs=1e-12)
        assert n_neg == ref.n_negative


class TestPolyAspect:

    def test_poly_aspect_native_route_matches_fallback(self, monkeypatch):
        rng = np.random.default_rng(4420)
        pts = rng.random((900, 3))
        cell_vertices = []
        for i in range(120):
            n_v = 3 if i % 17 == 0 else 8
            cell_vertices.append(rng.integers(0, pts.shape[0], size=n_v, dtype=np.int64))

        native = poly_aspect_module.poly_cell_aspect(pts, cell_vertices)
        assert _c_poly_aspect_stats_batch(pts, cell_vertices) is not None
        monkeypatch.setattr(poly_aspect_module, "_c_poly_aspect_stats_batch", None)
        fallback = poly_aspect_module.poly_cell_aspect(pts, cell_vertices)

        assert native.n_cells == fallback.n_cells
        assert native.aspect_min == pytest.approx(fallback.aspect_min, abs=1e-12)
        assert native.aspect_max == pytest.approx(fallback.aspect_max, abs=1e-12)
        assert native.aspect_mean == pytest.approx(fallback.aspect_mean, abs=1e-12)
        assert native.n_above_5 == fallback.n_above_5

    def test_poly_aspect_stats_batch_matches_python_reference(self):
        rng = np.random.default_rng(4430)
        pts = rng.random((760, 3))
        cell_vertices = [
            rng.integers(0, pts.shape[0], size=3, dtype=np.int64),
            np.array([0, 1, 2, 3], dtype=np.int64),
        ]
        for _ in range(90):
            cell_vertices.append(
                rng.integers(0, pts.shape[0], size=8, dtype=np.int64)
            )

        got = _c_poly_aspect_stats_batch(pts, cell_vertices)
        assert got is not None
        stats, n_above_5, n_valid = got

        old = poly_aspect_module._c_poly_aspect_stats_batch
        poly_aspect_module._c_poly_aspect_stats_batch = None
        try:
            ref = poly_aspect_module.poly_cell_aspect(pts, cell_vertices)
        finally:
            poly_aspect_module._c_poly_aspect_stats_batch = old

        assert n_valid == sum(len(cv) >= 4 for cv in cell_vertices)
        assert stats[0] == pytest.approx(ref.aspect_min, abs=1e-12)
        assert stats[1] == pytest.approx(ref.aspect_max, abs=1e-12)
        assert stats[2] == pytest.approx(ref.aspect_mean, abs=1e-12)
        assert n_above_5 == ref.n_above_5


class TestPolyConvex:

    def test_poly_convex_native_route_matches_fallback(self, monkeypatch):
        rng = np.random.default_rng(4440)
        pts = rng.random((640, 3))
        cell_vertices = [np.array([], dtype=np.int64)]
        cell_face_planes = [np.zeros((0, 4), dtype=np.float64)]
        for i in range(90):
            cell_vertices.append(rng.integers(0, pts.shape[0], size=8, dtype=np.int64))
            if i % 13 == 0:
                cell_face_planes.append(np.zeros((0, 4), dtype=np.float64))
            else:
                normals = rng.normal(size=(6, 3))
                offsets = rng.normal(loc=-1.0, scale=0.3, size=(6, 1))
                cell_face_planes.append(np.hstack([normals, offsets]))

        native = poly_convex_module.poly_cell_convex(pts, cell_vertices, cell_face_planes)
        assert _c_poly_convex_stats_batch(pts, cell_vertices, cell_face_planes, 1e-9) is not None
        monkeypatch.setattr(poly_convex_module, "_c_poly_convex_stats_batch", None)
        fallback = poly_convex_module.poly_cell_convex(pts, cell_vertices, cell_face_planes)

        assert native.n_cells == fallback.n_cells
        assert native.n_convex == fallback.n_convex
        assert native.n_non_convex == fallback.n_non_convex
        assert native.convex_ratio == pytest.approx(fallback.convex_ratio, abs=1e-12)
        assert native.max_violation == pytest.approx(fallback.max_violation, abs=1e-12)

    def test_poly_convex_stats_batch_matches_python_reference(self):
        rng = np.random.default_rng(4450)
        pts = rng.random((720, 3))
        cell_vertices = [np.array([], dtype=np.int64)]
        cell_face_planes = [np.zeros((4, 4), dtype=np.float64)]
        for i in range(70):
            cell_vertices.append(rng.integers(0, pts.shape[0], size=8, dtype=np.int64))
            if i % 11 == 0:
                cell_face_planes.append(np.zeros((0, 4), dtype=np.float64))
            else:
                normals = rng.normal(size=(5, 3))
                offsets = rng.normal(loc=-1.0, scale=0.4, size=(5, 1))
                cell_face_planes.append(np.hstack([normals, offsets]))

        got = _c_poly_convex_stats_batch(pts, cell_vertices, cell_face_planes, 1e-9)
        assert got is not None
        n_convex, max_violation = got

        old = poly_convex_module._c_poly_convex_stats_batch
        poly_convex_module._c_poly_convex_stats_batch = None
        try:
            ref = poly_convex_module.poly_cell_convex(pts, cell_vertices, cell_face_planes)
        finally:
            poly_convex_module._c_poly_convex_stats_batch = old

        assert n_convex == ref.n_convex
        assert max_violation == pytest.approx(ref.max_violation, abs=1e-12)


class TestNativeCheckerNonOrthogonality:

    def test_non_orthogonality_native_route_matches_fallback(self, monkeypatch):
        rng = np.random.default_rng(4460)
        n_cells = 240
        n_internal = 900
        face_centres = rng.random((n_internal, 3))
        face_normals = rng.normal(size=(n_internal, 3))
        cell_centres = rng.random((n_cells, 3))
        owner = rng.integers(0, n_cells, size=n_internal, dtype=np.int64)
        neighbour = rng.integers(0, n_cells, size=n_internal, dtype=np.int64)
        same = neighbour == owner
        neighbour[same] = (neighbour[same] + 1) % n_cells
        checker = NativeMeshChecker()

        monkeypatch.setattr(native_checker_module, "_NATIVE_METRICS", None)
        monkeypatch.setattr(native_checker_module, "_NATIVE_METRICS_IMPORT_ATTEMPTED", True)
        native = checker._compute_non_orthogonality(
            face_centres, face_normals, cell_centres, owner, neighbour, n_internal
        )
        assert _c_native_checker_non_ortho_stats_batch(
            face_normals,
            cell_centres,
            owner,
            neighbour,
            n_internal,
            checker.SEVERE_NON_ORTHO_THRESHOLD,
        ) is not None
        monkeypatch.setattr(native_checker_module, "_c_non_ortho_stats_batch", None)
        fallback = checker._compute_non_orthogonality(
            face_centres, face_normals, cell_centres, owner, neighbour, n_internal
        )

        np.testing.assert_allclose(native, fallback, rtol=1e-12, atol=1e-12)

    def test_non_orthogonality_stats_batch_matches_python_reference(self):
        rng = np.random.default_rng(4470)
        n_cells = 180
        n_internal = 640
        face_centres = rng.random((n_internal, 3))
        face_normals = rng.normal(size=(n_internal, 3))
        cell_centres = rng.random((n_cells, 3))
        owner = rng.integers(0, n_cells, size=n_internal, dtype=np.int64)
        neighbour = rng.integers(0, n_cells, size=n_internal, dtype=np.int64)
        same = neighbour == owner
        neighbour[same] = (neighbour[same] + 1) % n_cells
        checker = NativeMeshChecker()

        got = _c_native_checker_non_ortho_stats_batch(
            face_normals,
            cell_centres,
            owner,
            neighbour,
            n_internal,
            checker.SEVERE_NON_ORTHO_THRESHOLD,
        )
        assert got is not None

        old_c = native_checker_module._c_non_ortho_stats_batch
        old_module = native_checker_module._NATIVE_METRICS
        old_attempted = native_checker_module._NATIVE_METRICS_IMPORT_ATTEMPTED
        try:
            native_checker_module._c_non_ortho_stats_batch = None
            native_checker_module._NATIVE_METRICS = None
            native_checker_module._NATIVE_METRICS_IMPORT_ATTEMPTED = True
            ref = checker._compute_non_orthogonality(
                face_centres,
                face_normals,
                cell_centres,
                owner,
                neighbour,
                n_internal,
            )
        finally:
            native_checker_module._c_non_ortho_stats_batch = old_c
            native_checker_module._NATIVE_METRICS = old_module
            native_checker_module._NATIVE_METRICS_IMPORT_ATTEMPTED = old_attempted

        np.testing.assert_allclose(got, ref, rtol=1e-12, atol=1e-12)


class TestNativeCheckerSkewness:

    def test_skewness_native_route_matches_fallback(self, monkeypatch):
        rng = np.random.default_rng(4480)
        n_cells = 240
        n_internal = 900
        face_centres = rng.random((n_internal, 3))
        cell_centres = rng.random((n_cells, 3))
        owner = rng.integers(0, n_cells, size=n_internal, dtype=np.int64)
        neighbour = rng.integers(0, n_cells, size=n_internal, dtype=np.int64)
        same = neighbour == owner
        neighbour[same] = (neighbour[same] + 1) % n_cells
        checker = NativeMeshChecker()

        monkeypatch.setattr(native_checker_module, "_NATIVE_METRICS", None)
        monkeypatch.setattr(native_checker_module, "_NATIVE_METRICS_IMPORT_ATTEMPTED", True)
        native = checker._compute_skewness(
            face_centres, cell_centres, owner, neighbour, n_internal
        )
        assert _c_native_checker_skewness_stats_batch(
            face_centres,
            cell_centres,
            owner,
            neighbour,
            n_internal,
        ) is not None
        monkeypatch.setattr(native_checker_module, "_c_skewness_stats_batch", None)
        fallback = checker._compute_skewness(
            face_centres, cell_centres, owner, neighbour, n_internal
        )

        assert native == pytest.approx(fallback, rel=1e-12, abs=1e-12)

    def test_skewness_stats_batch_matches_python_reference(self):
        rng = np.random.default_rng(4490)
        n_cells = 180
        n_internal = 640
        face_centres = rng.random((n_internal, 3))
        cell_centres = rng.random((n_cells, 3))
        owner = rng.integers(0, n_cells, size=n_internal, dtype=np.int64)
        neighbour = rng.integers(0, n_cells, size=n_internal, dtype=np.int64)
        same = neighbour == owner
        neighbour[same] = (neighbour[same] + 1) % n_cells
        checker = NativeMeshChecker()

        got = _c_native_checker_skewness_stats_batch(
            face_centres,
            cell_centres,
            owner,
            neighbour,
            n_internal,
        )
        assert got is not None

        old_c = native_checker_module._c_skewness_stats_batch
        old_module = native_checker_module._NATIVE_METRICS
        old_attempted = native_checker_module._NATIVE_METRICS_IMPORT_ATTEMPTED
        try:
            native_checker_module._c_skewness_stats_batch = None
            native_checker_module._NATIVE_METRICS = None
            native_checker_module._NATIVE_METRICS_IMPORT_ATTEMPTED = True
            ref = checker._compute_skewness(
                face_centres,
                cell_centres,
                owner,
                neighbour,
                n_internal,
            )
        finally:
            native_checker_module._c_skewness_stats_batch = old_c
            native_checker_module._NATIVE_METRICS = old_module
            native_checker_module._NATIVE_METRICS_IMPORT_ATTEMPTED = old_attempted

        assert got == pytest.approx(ref, rel=1e-12, abs=1e-12)


class TestNativeCheckerFaceGeometry:

    def test_face_geometry_native_route_matches_fallback(self, monkeypatch):
        rng = np.random.default_rng(4500)
        points = rng.random((640, 3))
        faces = []
        for i in range(220):
            n_v = 3 + (i % 3)
            faces.append(rng.integers(0, points.shape[0], size=n_v, dtype=np.int64))

        monkeypatch.setattr(native_checker_module, "_NATIVE_METRICS", None)
        monkeypatch.setattr(native_checker_module, "_NATIVE_METRICS_IMPORT_ATTEMPTED", True)
        native = NativeMeshChecker._compute_face_geometry(points, faces)
        assert native is not None
        assert _c_native_checker_face_geometry_batch(points, faces) is not None
        monkeypatch.setattr(native_checker_module, "_c_face_geometry_batch", None)
        centres = NativeMeshChecker._compute_face_centres(points, faces)
        normals, areas = NativeMeshChecker._compute_face_normals_areas(points, faces)

        np.testing.assert_allclose(native[0], centres, rtol=0.0, atol=1e-15)
        np.testing.assert_allclose(native[1], normals, rtol=0.0, atol=1e-15)
        np.testing.assert_allclose(native[2], areas, rtol=0.0, atol=1e-15)

    def test_face_geometry_batch_matches_python_reference(self):
        rng = np.random.default_rng(4510)
        points = rng.random((720, 3))
        faces = []
        for i in range(260):
            n_v = 3 + (i % 4)
            faces.append(rng.integers(0, points.shape[0], size=n_v, dtype=np.int64))

        got = _c_native_checker_face_geometry_batch(points, faces)
        assert got is not None
        centres = NativeMeshChecker._compute_face_centres(points, faces)
        normals, areas = NativeMeshChecker._compute_face_normals_areas(points, faces)

        np.testing.assert_allclose(got[0], centres, rtol=0.0, atol=1e-15)
        np.testing.assert_allclose(got[1], normals, rtol=0.0, atol=1e-15)
        np.testing.assert_allclose(got[2], areas, rtol=0.0, atol=1e-15)


class TestNativeCheckerCellCentres:

    def test_cell_centres_native_route_matches_fallback(self, monkeypatch):
        rng = np.random.default_rng(4520)
        n_cells = 120
        n_faces = 500
        n_internal = 300
        face_centres = rng.random((n_faces, 3))
        owner = rng.integers(0, n_cells, size=n_faces, dtype=np.int64)
        neighbour = rng.integers(0, n_cells, size=n_internal, dtype=np.int64)

        native = NativeMeshChecker._compute_cell_centres(
            face_centres, owner, n_cells, neighbour
        )
        assert _c_native_checker_cell_centres_batch(
            face_centres, owner, n_cells, neighbour
        ) is not None
        monkeypatch.setattr(native_checker_module, "_c_cell_centres_batch", None)
        fallback = NativeMeshChecker._compute_cell_centres(
            face_centres, owner, n_cells, neighbour
        )

        np.testing.assert_allclose(native, fallback, rtol=0.0, atol=1e-15)

    def test_cell_centres_batch_matches_python_reference(self):
        rng = np.random.default_rng(4530)
        n_cells = 140
        n_faces = 640
        n_internal = 420
        face_centres = rng.random((n_faces, 3))
        owner = rng.integers(0, n_cells, size=n_faces, dtype=np.int64)
        neighbour = rng.integers(0, n_cells, size=n_internal, dtype=np.int64)

        got = _c_native_checker_cell_centres_batch(
            face_centres, owner, n_cells, neighbour
        )
        assert got is not None

        old_c = native_checker_module._c_cell_centres_batch
        try:
            native_checker_module._c_cell_centres_batch = None
            ref = NativeMeshChecker._compute_cell_centres(
                face_centres, owner, n_cells, neighbour
            )
        finally:
            native_checker_module._c_cell_centres_batch = old_c

        np.testing.assert_allclose(got, ref, rtol=0.0, atol=1e-15)


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
# Tests — minimum dihedral angle
# ---------------------------------------------------------------------------

class TestMinDihedralDeg:

    def test_regular_tet_value(self):
        pts, tets = _make_regular_tet()
        dih_c = _c_min_dihedral_deg_batch(pts, tets)
        dih_py = _py_min_dihedral_deg(pts, tets)
        assert dih_c is not None
        np.testing.assert_allclose(dih_c, dih_py, atol=1e-12)

    def test_random_meshes_allclose(self):
        for seed in range(100):
            n = 20 + seed * 2
            pts, tets = _make_random_mesh(n_pts=n + 10, n_tets=n, seed=seed + 300)
            dih_c = _c_min_dihedral_deg_batch(pts, tets)
            dih_py = _py_min_dihedral_deg(pts, tets)
            assert dih_c is not None
            np.testing.assert_allclose(
                dih_c, dih_py, atol=1e-12,
                err_msg=f"min dihedral mismatch seed={seed}",
            )

    def test_degenerate_zero_normals(self):
        pts = np.zeros((4, 3), dtype=np.float64)
        tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
        dih_c = _c_min_dihedral_deg_batch(pts, tets)
        dih_py = _py_min_dihedral_deg(pts, tets)
        assert dih_c is not None
        np.testing.assert_allclose(dih_c, dih_py, atol=1e-12)

    def test_tet_min_dihedral_native_route_matches_fallback(self, monkeypatch):
        pts, tets = _make_random_mesh(n_pts=360, n_tets=270, seed=1600)
        tets[:4, 1] = tets[:4, 0]
        dih_native = tet_quality_module.tet_min_dihedral_deg(pts, tets)
        monkeypatch.setattr(tet_quality_module, "_c_min_dihedral_deg_batch", None)
        dih_python = tet_quality_module.tet_min_dihedral_deg(pts, tets)
        np.testing.assert_allclose(dih_native, dih_python, atol=1e-12)


class TestAspectRatio:

    def test_regular_tet_value(self):
        pts, tets = _make_regular_tet()
        aspect_c = _c_aspect_ratio_batch(pts, tets)
        aspect_py = _py_aspect_ratio(pts, tets)
        assert aspect_c is not None
        np.testing.assert_allclose(aspect_c, aspect_py, atol=1e-12)

    def test_random_meshes_allclose(self):
        for seed in range(100):
            n = 20 + seed * 2
            pts, tets = _make_random_mesh(n_pts=n + 10, n_tets=n, seed=seed + 400)
            aspect_c = _c_aspect_ratio_batch(pts, tets)
            aspect_py = _py_aspect_ratio(pts, tets)
            assert aspect_c is not None
            np.testing.assert_allclose(
                aspect_c, aspect_py, rtol=1e-12, atol=1e-9,
                err_msg=f"aspect mismatch seed={seed}",
            )

    def test_degenerate_zero_normals(self):
        pts = np.zeros((4, 3), dtype=np.float64)
        tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
        aspect_c = _c_aspect_ratio_batch(pts, tets)
        aspect_py = _py_aspect_ratio(pts, tets)
        assert aspect_c is not None
        np.testing.assert_allclose(aspect_c, aspect_py, atol=1e-12)

    def test_tet_aspect_ratio_native_route_matches_fallback(self, monkeypatch):
        pts, tets = _make_random_mesh(n_pts=340, n_tets=260, seed=1500)
        tets[:4, 1] = tets[:4, 0]
        aspect_native = tet_quality_module.tet_aspect_ratio(pts, tets)
        monkeypatch.setattr(tet_quality_module, "_c_aspect_ratio_batch", None)
        aspect_python = tet_quality_module.tet_aspect_ratio(pts, tets)
        np.testing.assert_allclose(aspect_native, aspect_python, atol=1e-12)


class TestQualitySnapshot:

    def test_snapshot_matches_python_dihedral_fallback(self, monkeypatch):
        pts, tets = _make_random_mesh(n_pts=128, n_tets=96, seed=991)
        snap_c = tet_quality_module.snapshot(pts, tets)
        monkeypatch.setattr(tet_quality_module, "_c_quality_batch", None)
        monkeypatch.setattr(tet_quality_module, "_c_signed_vol6_batch", None)
        monkeypatch.setattr(tet_quality_module, "_c_aspect_ratio_batch", None)
        monkeypatch.setattr(tet_quality_module, "_c_min_dihedral_deg_batch", None)
        snap_py = tet_quality_module.snapshot(pts, tets)
        assert snap_c.n_tets == snap_py.n_tets
        assert snap_c.min_q == pytest.approx(snap_py.min_q, rel=1e-12, abs=1e-12)
        assert snap_c.mean_q == pytest.approx(snap_py.mean_q, rel=1e-12, abs=1e-12)
        assert snap_c.median_q == pytest.approx(snap_py.median_q, rel=1e-12, abs=1e-12)
        assert snap_c.max_aspect == pytest.approx(snap_py.max_aspect, rel=1e-12, abs=1e-9)
        assert snap_c.mean_aspect == pytest.approx(snap_py.mean_aspect, rel=1e-12, abs=1e-9)
        assert snap_c.min_dihedral_deg == pytest.approx(snap_py.min_dihedral_deg, abs=1e-12)
        assert snap_c.median_dihedral_deg == pytest.approx(
            snap_py.median_dihedral_deg, abs=1e-12,
        )
        assert snap_c.vol_weighted_mean_q == pytest.approx(
            snap_py.vol_weighted_mean_q, rel=1e-12, abs=1e-12,
        )
        assert snap_c.p10_q == pytest.approx(snap_py.p10_q, rel=1e-12, abs=1e-12)
        assert snap_c.p10_dihedral_deg == pytest.approx(snap_py.p10_dihedral_deg, abs=1e-12)


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


class TestFlipFaceMap:

    def test_flip_face_map_matches_reference(self):
        from core.generator.native_tet.flip import _face_map_vectorized

        for seed in range(40):
            n = 20 + seed * 3
            _, tets = _make_random_mesh(n_pts=n + 10, n_tets=n, seed=seed + 1000)
            got = _face_map_vectorized(tets)
            exp = _py_face_map(tets)
            assert set(got) == set(exp)
            for k in exp:
                assert got[k] == exp[k]

    def test_flip_face_map_keeps_duplicate_owner_lists(self):
        from core.generator.native_tet.flip import _face_map_vectorized

        tets = np.array([
            [0, 1, 2, 3],
            [0, 1, 2, 4],
            [0, 1, 2, 5],
        ], dtype=np.int64)
        got = _face_map_vectorized(tets)
        exp = _py_face_map(tets)
        assert set(got) == set(exp)
        for k in exp:
            assert got[k] == exp[k]


class TestBoundaryEdgesFromFaceMap:

    def test_boundary_edges_match_reference(self):
        from core.generator.native_tet.flip import (
            _boundary_edges_from_fmap,
            _face_map_vectorized,
        )

        for seed in range(40):
            n = 20 + seed * 3
            _, tets = _make_random_mesh(n_pts=n + 10, n_tets=n, seed=seed + 1200)
            fmap = _face_map_vectorized(tets)
            got = _boundary_edges_from_fmap(fmap)
            exp: set[tuple[int, int]] = set()
            for (a, b, c), owners in fmap.items():
                if len(owners) == 1:
                    exp.update(((a, b), (a, c), (b, c)))
            assert got == exp


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


class TestFlipEdgeMap:

    def test_flip_edge_map_matches_reference(self):
        from core.generator.native_tet.flip import _edge_to_tets_map

        for seed in range(40):
            n = 20 + seed * 3
            _, tets = _make_random_mesh(n_pts=n + 10, n_tets=n, seed=seed + 1100)
            got = _edge_to_tets_map(tets)
            exp = _py_edge_map(tets)
            assert set(got) == set(exp)
            for k in exp:
                assert got[k] == exp[k]

    def test_flip_edge_map_keeps_duplicate_owner_lists(self):
        from core.generator.native_tet.flip import _edge_to_tets_map

        tets = np.array([
            [0, 1, 2, 3],
            [0, 1, 2, 4],
            [0, 1, 2, 5],
        ], dtype=np.int64)
        got = _edge_to_tets_map(tets)
        exp = _py_edge_map(tets)
        assert set(got) == set(exp)
        for k in exp:
            assert got[k] == exp[k]


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


class TestLocalOpsEdgeLengths:

    def test_local_ops_edge_lengths_matches_reference(self):
        from core.generator.native_tet.local_ops import _edge_lengths

        for seed in range(40):
            n = 20 + seed * 3
            pts, tets = _make_random_mesh(n_pts=n + 10, n_tets=n, seed=seed + 900)
            got = _edge_lengths(pts, tets)
            exp = _py_edge_lengths(pts, tets)
            assert set(got) == set(exp)
            for k in exp:
                assert got[k] == pytest.approx(exp[k], abs=1e-12)

    def test_local_ops_edge_lengths_handles_duplicate_edges(self):
        from core.generator.native_tet.local_ops import _edge_lengths

        pts = np.array([
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [1.0, 1.0, 1.0],
        ], dtype=np.float64)
        tets = np.array([
            [0, 1, 2, 3],
            [0, 1, 2, 4],
            [0, 0, 1, 2],
        ], dtype=np.int64)
        got = _edge_lengths(pts, tets)
        exp = _py_edge_lengths(pts, tets)
        assert set(got) == set(exp)
        for k in exp:
            assert got[k] == pytest.approx(exp[k], abs=1e-12)


class TestMetricEdgeLengths:

    def test_metric_edge_lengths_match_python_formula(self):
        from core.generator.native_tet.local_ops import _edge_lengths_with_metric

        rng = np.random.default_rng(1300)
        for n in (1, 8, 64):
            pts = rng.standard_normal((n + 12, 3))
            tets = rng.integers(0, n + 12, size=(n, 4), dtype=np.int64)
            A = rng.standard_normal((n + 12, 3, 3))
            M = np.einsum("nij,nkj->nik", A, A) + np.eye(3)[None, :, :] * 1e-3

            c_result = _c_metric_edge_lengths_batch(pts, tets, M)
            assert c_result is not None

            # Force the numpy fallback by reimplementing the reference formula.
            pair_idx = np.array(
                [[0, 1], [0, 2], [0, 3], [1, 2], [1, 3], [2, 3]],
                dtype=np.int64,
            )
            vpts = pts[tets]
            vM = M[tets]
            p = vpts[:, pair_idx[:, 0]]
            q = vpts[:, pair_idx[:, 1]]
            Mp = vM[:, pair_idx[:, 0]]
            Mq = vM[:, pair_idx[:, 1]]
            d = p - q
            Mavg = 0.5 * (Mp + Mq)
            l2 = np.einsum("tij,tijk,tik->ti", d, Mavg, d)
            ref = np.sqrt(np.maximum(l2, 0.0))
            np.testing.assert_allclose(c_result, ref, rtol=1e-12, atol=1e-12)

            routed = _edge_lengths_with_metric(pts, tets, M)
            np.testing.assert_allclose(routed, ref, rtol=1e-12, atol=1e-12)


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
