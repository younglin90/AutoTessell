"""Native C kernels for native_tet hot loops.

Auto-build pattern identical to core/utils/_shewchuk/__init__.py.

Exposed functions (all return None / arrays via ctypes; None on failure):

    tet_quality_batch(pts, tets) -> np.ndarray  shape (n_tets,)
    tet_signed_vol6_batch(pts, tets) -> np.ndarray  shape (n_tets,)
    tet_min_dihedral_deg_batch(pts, tets) -> np.ndarray  shape (n_tets,)
    tet_aspect_ratio_batch(pts, tets) -> np.ndarray  shape (n_tets,)
    tet_radius_edge_ratio_batch(pts, tets) -> np.ndarray  shape (n_tets,)
    tet_min_solid_angle_sr_batch(pts, tets) -> np.ndarray  shape (n_tets,)
    tet_qshape_batch(pts, tets) -> np.ndarray  shape (n_tets,)
    detect_degenerate_tets_stats(pts, tets, zero_tol, sliver_ratio) -> tuple
    tet_shortest_edges_batch(pts, tets) -> (edges, lengths)
    edge_collapse_priority_batch(pts, tets, q, q_threshold, top_k) -> (edges, scores)
    build_tet_face_adjacency_stats(tets) -> (adj, stats)
    screen_flip_candidates_batch(adj, q, q_threshold) -> (pairs, q, n_internal)
    screen_swap_candidates_batch(tets, q, q_threshold) -> (edges, q, stats)
    tet_vertex_valence_batch(tets, n_vertices) -> (valence, stats, floats)
    tet_boundary_vertex_stats_batch(tets, n_surface_vertices) -> (n_boundary_tets, n_interior_tets)
    tet_edge_stats_batch(pts, tets, sliver_aniso) -> (stats, n_sliver)
    tet_volume_stats_batch(pts, tets, n_bins) -> (stats, n_negative_volume, hist)
    tet_inradius_batch(pts, tets) -> (radii, stats, n_zero_radius)
    tet_circumsphere_batch(pts, tets) -> (centers, radii, stats, n_degenerate)
    tet_aniso_tensor_batch(pts, tets) -> (ratio, stats, n_above_5)
    hex_stretch_stats_batch(pts, hexes) -> (stats, n_below_0p1)
    hex_face_area_stats_batch(pts, hexes) -> (stats, n_stretched)
    bl_prism_quality_stats_batch(pts, prisms) -> (stats, n_inverted)
    hex_skew_simple_stats_batch(pts, hexes) -> (stats, n_above_1)
    hex_ortho_stats_batch(pts, hexes) -> (stats, n_above_30deg)
    hex_jacobian_stats_batch(pts, hexes) -> (stats, n_inverted)
    hex_inverted_stats_batch(pts, hexes, max_indices) -> (indices, counts, worst)
    hex_validate_volumes_batch(pts, hexes, degenerate_eps) -> (fixed_hexes, n_flipped, n_degenerate)
    closest_points_on_triangles_candidates_batch(points, tri_a, tri_b, tri_c, candidate_idx) -> (best_points, best_dist2, has)
    poly_volume_stats_batch(pts, cell_face_lists) -> (volumes, stats, n_negative)
    poly_validate_volumes_batch(pts, cells, degenerate_eps) -> (n_negative, n_degenerate)
    poly_aspect_stats_batch(pts, cell_vertices) -> (stats, n_above_5, n_valid)
    poly_convex_stats_batch(pts, cell_vertices, cell_face_planes, tol) -> (n_convex, max_violation)
    native_checker_non_orthogonality_stats_batch(face_normals, cell_centres, owner, neighbour, n_internal, severe_threshold) -> (max, avg, severe)
    native_checker_skewness_stats_batch(face_centres, cell_centres, owner, neighbour, n_internal) -> max_skewness
    native_checker_face_geometry_batch(points, faces) -> (centres, normals, areas)
    native_checker_cell_centres_from_face_centres_batch(face_centres, owner, n_cells, neighbour) -> centres
    surface_boundary_edges_batch(faces) -> edges
    surface_edge_stats_batch(faces) -> (n_unique, n_boundary, n_nonmanifold, max_count)
    surface_vertex_valence_batch(faces, n_vertices) -> (face_val, edge_val, stats, means)
    surface_edge_lengths_stats_batch(verts, faces) -> (lengths, n_unique, aspect_max, aspect_mean)
    surface_unique_edge_length_stats_batch(verts, faces) -> (n_unique, min, max, p01, p99)
    surface_vertex_gaussian_curvature_batch(verts, faces) -> (K, stats)
    surface_vertex_mean_curvature_batch(verts, faces) -> (H, stats)
    surface_feature_edges_stats_batch(verts, faces, cos_threshold) -> stats
    surface_feature_report_stats_batch(verts, faces, cos_threshold) -> (counts, length_stats)
    surface_diag_stats_batch(verts, faces, cos_threshold, sliver_area_tol) -> (counts, stats)
    surface_dihedral_histogram_batch(verts, faces, bin_edges) -> (counts, stats)
    surface_remove_degenerate_faces_mask(verts, faces, area_tol) -> (keep_mask, n_removed)
    surface_dedup_vertices_quantized(verts, faces, tol) -> (new_verts, new_faces, n_merged)
    surface_area_volume_stats_batch(verts, faces) -> (area, signed_volume, bbox_volume)
    surface_face_area_distribution_stats_batch(verts, faces) -> (min, max, mean, std, p01, p99)
    build_face_to_tets(tets) -> (faces, tet_idx, slot)
        faces   : (n_tets*4, 3) int64   sorted triples
        tet_idx : (n_tets*4,)   int64
        slot    : (n_tets*4,)   int64
    build_edge_to_tets(tets) -> (edges, tet_idx)
        edges   : (n_tets*6, 2) int64   sorted pairs
        tet_idx : (n_tets*6,)   int64
    edge_lengths_batch(pts, edges) -> np.ndarray  shape (n_edges,)
    metric_edge_lengths_batch(pts, tets, M) -> np.ndarray  shape (n_tets, 6)

All functions return None on failure; callers must fall back to Python.
"""
from __future__ import annotations

import ctypes
import subprocess
from pathlib import Path
from typing import Optional

import numpy as np

_HERE = Path(__file__).parent.resolve()
_SO_PATH = _HERE / "libtet_kernels.so"
_C_SRC = _HERE / "tet_kernels.c"
_C_INCLUDES = (
    _HERE / "tet_kernels_hex_poly.inc",
    _HERE / "tet_kernels_native_checker.inc",
    _HERE / "tet_kernels_surface.inc",
)

_lib: Optional[ctypes.CDLL] = None
_available: bool = False


def _native_source_mtime() -> float:
    paths = (_C_SRC, *_C_INCLUDES)
    mtimes = [p.stat().st_mtime for p in paths if p.exists()]
    return max(mtimes) if mtimes else 0.0


def _try_compile() -> bool:
    if not _C_SRC.exists():
        return False
    try:
        result = subprocess.run(
            [
                "cc", "-O3", "-march=native", "-fPIC", "-shared",
                "-std=c99",
                str(_C_SRC),
                "-o", str(_SO_PATH),
                "-lm",
            ],
            capture_output=True,
            timeout=60,
        )
        return result.returncode == 0
    except Exception:
        return False


def _load_lib() -> Optional[ctypes.CDLL]:
    if not _SO_PATH.exists():
        return None
    try:
        lib = ctypes.CDLL(str(_SO_PATH))
    except OSError:
        return None

    c_double_p = ctypes.POINTER(ctypes.c_double)
    c_long_p   = ctypes.POINTER(ctypes.c_long)

    try:
        # tet_quality_batch
        lib.tet_quality_batch.restype  = None
        lib.tet_quality_batch.argtypes = [
            c_double_p, ctypes.c_int,
            c_long_p,   ctypes.c_int,
            c_double_p,
        ]
        # tet_signed_vol6_batch
        lib.tet_signed_vol6_batch.restype  = None
        lib.tet_signed_vol6_batch.argtypes = [
            c_double_p, ctypes.c_int,
            c_long_p,   ctypes.c_int,
            c_double_p,
        ]
        # tet_min_dihedral_deg_batch
        lib.tet_min_dihedral_deg_batch.restype  = None
        lib.tet_min_dihedral_deg_batch.argtypes = [
            c_double_p, ctypes.c_int,
            c_long_p,   ctypes.c_int,
            c_double_p,
        ]
        # tet_aspect_ratio_batch
        lib.tet_aspect_ratio_batch.restype  = None
        lib.tet_aspect_ratio_batch.argtypes = [
            c_double_p, ctypes.c_int,
            c_long_p,   ctypes.c_int,
            c_double_p,
        ]
        # tet_radius_edge_ratio_batch
        lib.tet_radius_edge_ratio_batch.restype  = None
        lib.tet_radius_edge_ratio_batch.argtypes = [
            c_double_p, ctypes.c_int,
            c_long_p,   ctypes.c_int,
            c_double_p,
        ]
        # tet_min_solid_angle_sr_batch
        lib.tet_min_solid_angle_sr_batch.restype  = None
        lib.tet_min_solid_angle_sr_batch.argtypes = [
            c_double_p, ctypes.c_int,
            c_long_p,   ctypes.c_int,
            c_double_p,
        ]
        # tet_qshape_batch
        lib.tet_qshape_batch.restype  = None
        lib.tet_qshape_batch.argtypes = [
            c_double_p, ctypes.c_int,
            c_long_p,   ctypes.c_int,
            c_double_p,
        ]
        # detect_degenerate_tets_stats
        lib.detect_degenerate_tets_stats.restype  = None
        lib.detect_degenerate_tets_stats.argtypes = [
            c_double_p, ctypes.c_int,
            c_long_p,   ctypes.c_int,
            ctypes.c_double,
            ctypes.c_double,
            c_long_p,
            c_double_p,
        ]
        # tet_shortest_edges_batch
        lib.tet_shortest_edges_batch.restype  = None
        lib.tet_shortest_edges_batch.argtypes = [
            c_double_p, ctypes.c_int,
            c_long_p,   ctypes.c_int,
            c_long_p,
            c_double_p,
        ]
        # edge_collapse_priority_batch
        lib.edge_collapse_priority_batch.restype  = None
        lib.edge_collapse_priority_batch.argtypes = [
            c_double_p, ctypes.c_int,
            c_long_p,   ctypes.c_int,
            c_double_p,
            ctypes.c_double,
            ctypes.c_int,
            c_long_p,
            c_double_p,
            c_long_p,
        ]
        # build_tet_face_adjacency_stats
        lib.build_tet_face_adjacency_stats.restype  = None
        lib.build_tet_face_adjacency_stats.argtypes = [
            c_long_p,
            ctypes.c_int,
            c_long_p,
            c_long_p,
        ]
        # screen_flip_candidates_batch
        lib.screen_flip_candidates_batch.restype  = None
        lib.screen_flip_candidates_batch.argtypes = [
            c_long_p,
            ctypes.c_int,
            c_double_p,
            ctypes.c_double,
            c_long_p,
            c_double_p,
            c_long_p,
        ]
        # screen_swap_candidates_batch
        lib.screen_swap_candidates_batch.restype  = None
        lib.screen_swap_candidates_batch.argtypes = [
            c_long_p,
            ctypes.c_int,
            c_double_p,
            ctypes.c_double,
            c_long_p,
            c_double_p,
            c_long_p,
        ]
        # tet_vertex_valence_batch
        lib.tet_vertex_valence_batch.restype = None
        lib.tet_vertex_valence_batch.argtypes = [
            c_long_p,
            ctypes.c_int,
            ctypes.c_int,
            c_long_p,
            c_long_p,
            c_double_p,
        ]
        # tet_boundary_vertex_stats_batch
        lib.tet_boundary_vertex_stats_batch.restype = None
        lib.tet_boundary_vertex_stats_batch.argtypes = [
            c_long_p,
            ctypes.c_int,
            ctypes.c_int,
            c_long_p,
        ]
        # tet_edge_stats_batch
        lib.tet_edge_stats_batch.restype = None
        lib.tet_edge_stats_batch.argtypes = [
            c_double_p,
            ctypes.c_int,
            c_long_p,
            ctypes.c_int,
            ctypes.c_double,
            c_double_p,
            c_long_p,
        ]
        # tet_volume_stats_batch
        lib.tet_volume_stats_batch.restype = None
        lib.tet_volume_stats_batch.argtypes = [
            c_double_p,
            ctypes.c_int,
            c_long_p,
            ctypes.c_int,
            ctypes.c_int,
            c_double_p,
            c_long_p,
            c_long_p,
        ]
        # tet_inradius_batch
        lib.tet_inradius_batch.restype = None
        lib.tet_inradius_batch.argtypes = [
            c_double_p,
            ctypes.c_int,
            c_long_p,
            ctypes.c_int,
            c_double_p,
            c_double_p,
            c_long_p,
        ]
        # tet_circumsphere_batch
        lib.tet_circumsphere_batch.restype = None
        lib.tet_circumsphere_batch.argtypes = [
            c_double_p,
            ctypes.c_int,
            c_long_p,
            ctypes.c_int,
            c_double_p,
            c_double_p,
            c_double_p,
            c_long_p,
        ]
        # tet_aniso_tensor_batch
        lib.tet_aniso_tensor_batch.restype = None
        lib.tet_aniso_tensor_batch.argtypes = [
            c_double_p,
            ctypes.c_int,
            c_long_p,
            ctypes.c_int,
            c_double_p,
            c_double_p,
            c_long_p,
        ]
        # hex_stretch_stats_batch
        lib.hex_stretch_stats_batch.restype = None
        lib.hex_stretch_stats_batch.argtypes = [
            c_double_p,
            ctypes.c_int,
            c_long_p,
            ctypes.c_int,
            c_double_p,
            c_long_p,
        ]
        # hex_face_area_stats_batch
        lib.hex_face_area_stats_batch.restype = None
        lib.hex_face_area_stats_batch.argtypes = [
            c_double_p,
            ctypes.c_int,
            c_long_p,
            ctypes.c_int,
            c_double_p,
            c_long_p,
        ]
        # bl_prism_quality_stats_batch
        lib.bl_prism_quality_stats_batch.restype = None
        lib.bl_prism_quality_stats_batch.argtypes = [
            c_double_p,
            ctypes.c_int,
            c_long_p,
            ctypes.c_int,
            c_double_p,
            c_long_p,
        ]
        # hex_skew_simple_stats_batch
        lib.hex_skew_simple_stats_batch.restype = None
        lib.hex_skew_simple_stats_batch.argtypes = [
            c_double_p,
            ctypes.c_int,
            c_long_p,
            ctypes.c_int,
            c_double_p,
            c_long_p,
        ]
        # hex_ortho_stats_batch
        lib.hex_ortho_stats_batch.restype = None
        lib.hex_ortho_stats_batch.argtypes = [
            c_double_p,
            ctypes.c_int,
            c_long_p,
            ctypes.c_int,
            c_double_p,
            c_long_p,
        ]
        # hex_jacobian_stats_batch
        lib.hex_jacobian_stats_batch.restype = None
        lib.hex_jacobian_stats_batch.argtypes = [
            c_double_p,
            ctypes.c_int,
            c_long_p,
            ctypes.c_int,
            c_double_p,
            c_long_p,
        ]
        # hex_inverted_stats_batch
        lib.hex_inverted_stats_batch.restype = None
        lib.hex_inverted_stats_batch.argtypes = [
            c_double_p,
            ctypes.c_int,
            c_long_p,
            ctypes.c_int,
            ctypes.c_int,
            c_long_p,
            c_long_p,
            c_double_p,
        ]
        # hex_validate_volumes_batch
        lib.hex_validate_volumes_batch.restype = None
        lib.hex_validate_volumes_batch.argtypes = [
            c_double_p,
            ctypes.c_int,
            c_long_p,
            ctypes.c_int,
            ctypes.c_double,
            c_long_p,
        ]
        # closest_points_on_triangles_candidates_batch
        lib.closest_points_on_triangles_candidates_batch.restype = None
        lib.closest_points_on_triangles_candidates_batch.argtypes = [
            c_double_p,
            ctypes.c_int,
            c_double_p,
            c_double_p,
            c_double_p,
            ctypes.c_int,
            c_long_p,
            ctypes.c_int,
            c_double_p,
            c_double_p,
            c_long_p,
        ]
        # poly_volume_stats_batch
        lib.poly_volume_stats_batch.restype = None
        lib.poly_volume_stats_batch.argtypes = [
            c_double_p,
            ctypes.c_int,
            c_long_p,
            c_long_p,
            ctypes.c_int,
            c_long_p,
            ctypes.c_int,
            c_double_p,
            c_double_p,
            c_long_p,
        ]
        # poly_validate_volumes_batch
        lib.poly_validate_volumes_batch.restype = None
        lib.poly_validate_volumes_batch.argtypes = [
            c_double_p,
            ctypes.c_int,
            c_long_p,
            c_long_p,
            ctypes.c_int,
            c_long_p,
            ctypes.c_int,
            ctypes.c_double,
            c_long_p,
        ]
        # poly_aspect_stats_batch
        lib.poly_aspect_stats_batch.restype = None
        lib.poly_aspect_stats_batch.argtypes = [
            c_double_p,
            ctypes.c_int,
            c_long_p,
            c_long_p,
            ctypes.c_int,
            c_double_p,
            c_long_p,
        ]
        # poly_convex_stats_batch
        lib.poly_convex_stats_batch.restype = None
        lib.poly_convex_stats_batch.argtypes = [
            c_double_p,
            ctypes.c_int,
            c_long_p,
            c_long_p,
            c_double_p,
            c_long_p,
            ctypes.c_int,
            ctypes.c_double,
            c_long_p,
            c_double_p,
        ]
        # native_checker_non_orthogonality_stats_batch
        lib.native_checker_non_orthogonality_stats_batch.restype = None
        lib.native_checker_non_orthogonality_stats_batch.argtypes = [
            c_double_p,
            c_double_p,
            c_long_p,
            c_long_p,
            ctypes.c_int,
            ctypes.c_double,
            c_double_p,
            c_long_p,
        ]
        # native_checker_skewness_stats_batch
        lib.native_checker_skewness_stats_batch.restype = None
        lib.native_checker_skewness_stats_batch.argtypes = [
            c_double_p,
            c_double_p,
            c_long_p,
            c_long_p,
            ctypes.c_int,
            c_double_p,
        ]
        # native_checker_face_geometry_batch
        lib.native_checker_face_geometry_batch.restype = None
        lib.native_checker_face_geometry_batch.argtypes = [
            c_double_p,
            ctypes.c_int,
            c_long_p,
            c_long_p,
            ctypes.c_int,
            c_double_p,
            c_double_p,
            c_double_p,
        ]
        # native_checker_cell_centres_from_face_centres_batch
        lib.native_checker_cell_centres_from_face_centres_batch.restype = None
        lib.native_checker_cell_centres_from_face_centres_batch.argtypes = [
            c_double_p,
            c_long_p,
            ctypes.c_int,
            c_long_p,
            ctypes.c_int,
            ctypes.c_int,
            c_double_p,
        ]
        # surface_boundary_edges_batch
        lib.surface_boundary_edges_batch.restype  = None
        lib.surface_boundary_edges_batch.argtypes = [
            c_long_p,
            ctypes.c_int,
            c_long_p,
            c_long_p,
        ]
        # surface_edge_stats_batch
        lib.surface_edge_stats_batch.restype  = None
        lib.surface_edge_stats_batch.argtypes = [
            c_long_p,
            ctypes.c_int,
            c_long_p,
        ]
        # surface_vertex_valence_batch
        lib.surface_vertex_valence_batch.restype  = None
        lib.surface_vertex_valence_batch.argtypes = [
            c_long_p,
            ctypes.c_int,
            ctypes.c_int,
            c_long_p,
            c_long_p,
            c_long_p,
            c_double_p,
        ]
        # surface_edge_lengths_stats_batch
        lib.surface_edge_lengths_stats_batch.restype  = None
        lib.surface_edge_lengths_stats_batch.argtypes = [
            c_double_p,
            ctypes.c_int,
            c_long_p,
            ctypes.c_int,
            c_double_p,
            c_long_p,
            c_double_p,
        ]
        # surface_unique_edge_length_stats_batch
        lib.surface_unique_edge_length_stats_batch.restype  = None
        lib.surface_unique_edge_length_stats_batch.argtypes = [
            c_double_p,
            ctypes.c_int,
            c_long_p,
            ctypes.c_int,
            c_long_p,
            c_double_p,
        ]
        # surface_vertex_gaussian_curvature_batch
        lib.surface_vertex_gaussian_curvature_batch.restype  = None
        lib.surface_vertex_gaussian_curvature_batch.argtypes = [
            c_double_p,
            ctypes.c_int,
            c_long_p,
            ctypes.c_int,
            c_double_p,
            c_double_p,
        ]
        # surface_vertex_mean_curvature_batch
        lib.surface_vertex_mean_curvature_batch.restype  = None
        lib.surface_vertex_mean_curvature_batch.argtypes = [
            c_double_p,
            ctypes.c_int,
            c_long_p,
            ctypes.c_int,
            c_double_p,
            c_double_p,
        ]
        # surface_feature_edges_stats_batch
        lib.surface_feature_edges_stats_batch.restype  = None
        lib.surface_feature_edges_stats_batch.argtypes = [
            c_double_p,
            ctypes.c_int,
            c_long_p,
            ctypes.c_int,
            ctypes.c_double,
            c_long_p,
        ]
        # surface_feature_report_stats_batch
        lib.surface_feature_report_stats_batch.restype  = None
        lib.surface_feature_report_stats_batch.argtypes = [
            c_double_p,
            ctypes.c_int,
            c_long_p,
            ctypes.c_int,
            ctypes.c_double,
            c_long_p,
            c_double_p,
        ]
        # surface_diag_stats_batch
        lib.surface_diag_stats_batch.restype  = None
        lib.surface_diag_stats_batch.argtypes = [
            c_double_p,
            ctypes.c_int,
            c_long_p,
            ctypes.c_int,
            ctypes.c_double,
            ctypes.c_double,
            c_long_p,
            c_double_p,
        ]
        # surface_dihedral_histogram_batch
        lib.surface_dihedral_histogram_batch.restype  = None
        lib.surface_dihedral_histogram_batch.argtypes = [
            c_double_p,
            ctypes.c_int,
            c_long_p,
            ctypes.c_int,
            c_double_p,
            ctypes.c_int,
            c_long_p,
            c_long_p,
            c_double_p,
        ]
        # surface_remove_degenerate_faces_mask
        lib.surface_remove_degenerate_faces_mask.restype  = None
        lib.surface_remove_degenerate_faces_mask.argtypes = [
            c_double_p,
            ctypes.c_int,
            c_long_p,
            ctypes.c_int,
            ctypes.c_double,
            c_long_p,
            c_long_p,
        ]
        # surface_dedup_vertices_quantized
        lib.surface_dedup_vertices_quantized.restype  = None
        lib.surface_dedup_vertices_quantized.argtypes = [
            c_double_p,
            ctypes.c_int,
            c_long_p,
            ctypes.c_int,
            ctypes.c_double,
            c_double_p,
            c_long_p,
            c_long_p,
        ]
        # surface_area_volume_stats_batch
        lib.surface_area_volume_stats_batch.restype  = None
        lib.surface_area_volume_stats_batch.argtypes = [
            c_double_p,
            ctypes.c_int,
            c_long_p,
            ctypes.c_int,
            c_double_p,
        ]
        # surface_face_area_distribution_stats_batch
        lib.surface_face_area_distribution_stats_batch.restype  = None
        lib.surface_face_area_distribution_stats_batch.argtypes = [
            c_double_p,
            ctypes.c_int,
            c_long_p,
            ctypes.c_int,
            c_double_p,
        ]
        # build_face_to_tets
        lib.build_face_to_tets.restype  = ctypes.c_int
        lib.build_face_to_tets.argtypes = [
            c_long_p, ctypes.c_int,
            c_long_p, c_long_p, c_long_p,
            ctypes.c_int,
        ]
        # build_edge_to_tets
        lib.build_edge_to_tets.restype  = ctypes.c_int
        lib.build_edge_to_tets.argtypes = [
            c_long_p, ctypes.c_int,
            c_long_p, c_long_p,
            ctypes.c_int,
        ]
        # edge_lengths_batch
        lib.edge_lengths_batch.restype  = None
        lib.edge_lengths_batch.argtypes = [
            c_double_p,
            c_long_p, ctypes.c_int,
            c_double_p,
        ]
        # metric_edge_lengths_batch
        lib.metric_edge_lengths_batch.restype  = None
        lib.metric_edge_lengths_batch.argtypes = [
            c_double_p,
            c_long_p, ctypes.c_int,
            c_double_p,
            c_double_p,
        ]
    except Exception:
        return None

    return lib


def _init() -> None:
    global _lib, _available  # noqa: PLW0603
    needs_compile = not _SO_PATH.exists()
    if not needs_compile and _C_SRC.exists():
        try:
            needs_compile = _native_source_mtime() > _SO_PATH.stat().st_mtime
        except OSError:
            needs_compile = False
    if needs_compile:
        _try_compile()
    lib = _load_lib()
    if lib is None and _C_SRC.exists():
        _try_compile()
        lib = _load_lib()
    if lib is None:
        return
    _lib = lib
    _available = True


def is_available() -> bool:
    return _available


# ---------------------------------------------------------------------------
# Public API helpers
# ---------------------------------------------------------------------------

def _c_double_ptr(arr: np.ndarray) -> ctypes.POINTER:
    a = np.ascontiguousarray(arr, dtype=np.float64)
    return a.ctypes.data_as(ctypes.POINTER(ctypes.c_double)), a


def _c_long_ptr(arr: np.ndarray) -> ctypes.POINTER:
    a = np.ascontiguousarray(arr, dtype=np.int64)
    return a.ctypes.data_as(ctypes.POINTER(ctypes.c_long)), a


def tet_quality_batch(
    pts: np.ndarray,
    tets: np.ndarray,
) -> Optional[np.ndarray]:
    """Return quality array shape (n_tets,), or None if C unavailable."""
    if _lib is None:
        return None
    pts  = np.ascontiguousarray(pts,  dtype=np.float64)
    tets = np.ascontiguousarray(tets, dtype=np.int64)
    n_tets = tets.shape[0]
    out = np.empty(n_tets, dtype=np.float64)

    pts_p,  _pts_k  = _c_double_ptr(pts)
    tets_p, _tets_k = _c_long_ptr(tets)
    out_p,  _out_k  = _c_double_ptr(out)

    _lib.tet_quality_batch(
        pts_p,  ctypes.c_int(pts.shape[0]),
        tets_p, ctypes.c_int(n_tets),
        out_p,
    )
    return _out_k


def tet_signed_vol6_batch(
    pts: np.ndarray,
    tets: np.ndarray,
) -> Optional[np.ndarray]:
    """Return signed vol*6 array shape (n_tets,), or None if C unavailable."""
    if _lib is None:
        return None
    pts  = np.ascontiguousarray(pts,  dtype=np.float64)
    tets = np.ascontiguousarray(tets, dtype=np.int64)
    n_tets = tets.shape[0]
    out = np.empty(n_tets, dtype=np.float64)

    pts_p,  _pts_k  = _c_double_ptr(pts)
    tets_p, _tets_k = _c_long_ptr(tets)
    out_p,  _out_k  = _c_double_ptr(out)

    _lib.tet_signed_vol6_batch(
        pts_p,  ctypes.c_int(pts.shape[0]),
        tets_p, ctypes.c_int(n_tets),
        out_p,
    )
    return _out_k


def tet_min_dihedral_deg_batch(
    pts: np.ndarray,
    tets: np.ndarray,
) -> Optional[np.ndarray]:
    """Return minimum dihedral angle array shape (n_tets,), or None."""
    if _lib is None:
        return None
    pts  = np.ascontiguousarray(pts,  dtype=np.float64)
    tets = np.ascontiguousarray(tets, dtype=np.int64)
    n_tets = tets.shape[0]
    out = np.empty(n_tets, dtype=np.float64)

    pts_p,  _pts_k  = _c_double_ptr(pts)
    tets_p, _tets_k = _c_long_ptr(tets)
    out_p,  _out_k  = _c_double_ptr(out)

    _lib.tet_min_dihedral_deg_batch(
        pts_p,  ctypes.c_int(pts.shape[0]),
        tets_p, ctypes.c_int(n_tets),
        out_p,
    )
    dup = (
        (tets[:, 0] == tets[:, 1]) | (tets[:, 0] == tets[:, 2])
        | (tets[:, 0] == tets[:, 3]) | (tets[:, 1] == tets[:, 2])
        | (tets[:, 1] == tets[:, 3]) | (tets[:, 2] == tets[:, 3])
    )
    if bool(np.any(dup)):
        v = pts[tets[dup]]
        a, b, c, d = v[:, 0], v[:, 1], v[:, 2], v[:, 3]

        def _unit_n(p: np.ndarray, q: np.ndarray, r: np.ndarray) -> np.ndarray:
            n = np.cross(q - p, r - p)
            nrm = np.linalg.norm(n, axis=1, keepdims=True)
            return n / np.where(nrm > 1e-30, nrm, 1.0)

        n_abc = _unit_n(a, b, c)
        n_abd = _unit_n(a, b, d)
        n_acd = _unit_n(a, c, d)
        n_bcd = _unit_n(b, c, d)

        def _dih(n1: np.ndarray, n2: np.ndarray) -> np.ndarray:
            dot = np.clip(np.einsum("ij,ij->i", n1, n2), -1.0, 1.0)
            return np.rad2deg(np.arccos(dot))

        dh1 = 180.0 - _dih(n_abc, n_abd)
        dh2 = 180.0 - _dih(n_abc, n_acd)
        dh3 = 180.0 - _dih(n_abd, n_acd)
        dh4 = 180.0 - _dih(n_abc, n_bcd)
        dh5 = 180.0 - _dih(n_abd, n_bcd)
        dh6 = 180.0 - _dih(n_acd, n_bcd)
        _out_k[dup] = np.minimum.reduce([dh1, dh2, dh3, dh4, dh5, dh6])
    return _out_k


def _duplicate_tet_rows(tets: np.ndarray) -> np.ndarray:
    return (
        (tets[:, 0] == tets[:, 1]) | (tets[:, 0] == tets[:, 2])
        | (tets[:, 0] == tets[:, 3]) | (tets[:, 1] == tets[:, 2])
        | (tets[:, 1] == tets[:, 3]) | (tets[:, 2] == tets[:, 3])
    )


def tet_aspect_ratio_batch(
    pts: np.ndarray,
    tets: np.ndarray,
) -> Optional[np.ndarray]:
    """Return aspect ratio array shape (n_tets,), or None if C unavailable."""
    if _lib is None:
        return None
    pts  = np.ascontiguousarray(pts,  dtype=np.float64)
    tets = np.ascontiguousarray(tets, dtype=np.int64)
    n_tets = tets.shape[0]
    out = np.empty(n_tets, dtype=np.float64)

    pts_p,  _pts_k  = _c_double_ptr(pts)
    tets_p, _tets_k = _c_long_ptr(tets)
    out_p,  _out_k  = _c_double_ptr(out)

    _lib.tet_aspect_ratio_batch(
        pts_p,  ctypes.c_int(pts.shape[0]),
        tets_p, ctypes.c_int(n_tets),
        out_p,
    )
    dup = _duplicate_tet_rows(tets)
    if bool(np.any(dup)):
        v = pts[tets[dup]]
        a, b, c, d = v[:, 0], v[:, 1], v[:, 2], v[:, 3]
        vol6 = np.abs(np.einsum("ij,ij->i", b - a, np.cross(c - a, d - a)))
        vol = vol6 / 6.0

        def _area(p: np.ndarray, q: np.ndarray, r: np.ndarray) -> np.ndarray:
            return 0.5 * np.linalg.norm(np.cross(q - p, r - p), axis=1)

        surf_sum = _area(a, b, c) + _area(a, b, d) + _area(a, c, d) + _area(b, c, d)
        inrad = np.where(surf_sum > 1e-30, 3.0 * vol / surf_sum, 0.0)
        e1 = np.linalg.norm(b - a, axis=1)
        e2 = np.linalg.norm(c - a, axis=1)
        e3 = np.linalg.norm(d - a, axis=1)
        e4 = np.linalg.norm(c - b, axis=1)
        e5 = np.linalg.norm(d - b, axis=1)
        e6 = np.linalg.norm(d - c, axis=1)
        rmax = np.maximum.reduce([e1, e2, e3, e4, e5, e6]) / 2.0
        safe_inrad = np.where(inrad > 1e-30, inrad, 1.0)
        _out_k[dup] = np.where(inrad > 1e-30, rmax / safe_inrad, 1e6)
    return _out_k


def tet_radius_edge_ratio_batch(
    pts: np.ndarray,
    tets: np.ndarray,
) -> Optional[np.ndarray]:
    """Return radius-edge proxy array shape (n_tets,), or None if unavailable."""
    if _lib is None:
        return None
    pts = np.ascontiguousarray(pts, dtype=np.float64)
    tets = np.ascontiguousarray(tets, dtype=np.int64)
    n_tets = tets.shape[0]
    out = np.empty(n_tets, dtype=np.float64)

    pts_p, _pts_k = _c_double_ptr(pts)
    tets_p, _tets_k = _c_long_ptr(tets)
    out_p, _out_k = _c_double_ptr(out)

    _lib.tet_radius_edge_ratio_batch(
        pts_p, ctypes.c_int(pts.shape[0]),
        tets_p, ctypes.c_int(n_tets),
        out_p,
    )
    return _out_k


def tet_min_solid_angle_sr_batch(
    pts: np.ndarray,
    tets: np.ndarray,
) -> Optional[np.ndarray]:
    """Return minimum solid angle array shape (n_tets,), or None if unavailable."""
    if _lib is None:
        return None
    pts = np.ascontiguousarray(pts, dtype=np.float64)
    tets = np.ascontiguousarray(tets, dtype=np.int64)
    n_tets = tets.shape[0]
    out = np.empty(n_tets, dtype=np.float64)

    pts_p, _pts_k = _c_double_ptr(pts)
    tets_p, _tets_k = _c_long_ptr(tets)
    out_p, _out_k = _c_double_ptr(out)

    _lib.tet_min_solid_angle_sr_batch(
        pts_p, ctypes.c_int(pts.shape[0]),
        tets_p, ctypes.c_int(n_tets),
        out_p,
    )
    return _out_k


def tet_qshape_batch(
    pts: np.ndarray,
    tets: np.ndarray,
) -> Optional[np.ndarray]:
    """Return evaluator Q-shape array shape (n_tets,), or None if unavailable."""
    if _lib is None:
        return None
    pts = np.ascontiguousarray(pts, dtype=np.float64)
    tets = np.ascontiguousarray(tets, dtype=np.int64)
    n_tets = tets.shape[0]
    out = np.empty(n_tets, dtype=np.float64)

    pts_p, _pts_k = _c_double_ptr(pts)
    tets_p, _tets_k = _c_long_ptr(tets)
    out_p, _out_k = _c_double_ptr(out)

    _lib.tet_qshape_batch(
        pts_p, ctypes.c_int(pts.shape[0]),
        tets_p, ctypes.c_int(n_tets),
        out_p,
    )
    v = pts[tets]
    vol = np.einsum("ij,ij->i", np.cross(v[:, 1] - v[:, 0], v[:, 2] - v[:, 0]), v[:, 3] - v[:, 0]) / 6.0
    near_zero = np.abs(vol) <= 1e-12
    if bool(np.any(near_zero)):
        vv = v[near_zero]
        vol_nz = vol[near_zero]
        e01 = ((vv[:, 1] - vv[:, 0]) ** 2).sum(axis=1)
        e02 = ((vv[:, 2] - vv[:, 0]) ** 2).sum(axis=1)
        e03 = ((vv[:, 3] - vv[:, 0]) ** 2).sum(axis=1)
        e12 = ((vv[:, 2] - vv[:, 1]) ** 2).sum(axis=1)
        e13 = ((vv[:, 3] - vv[:, 1]) ** 2).sum(axis=1)
        e23 = ((vv[:, 3] - vv[:, 2]) ** 2).sum(axis=1)
        sum_l_sq = e01 + e02 + e03 + e12 + e13 + e23
        raw = np.zeros_like(sum_l_sq)
        safe = sum_l_sq > 1e-30
        raw[safe] = (3.0 * np.abs(vol_nz[safe])) ** (2.0 / 3.0) / sum_l_sq[safe]
        q = np.clip(raw / 0.0857, 0.0, 1.0)
        q[vol_nz <= 0] = 0.0
        _out_k[near_zero] = q
    return _out_k


def detect_degenerate_tets_stats(
    pts: np.ndarray,
    tets: np.ndarray,
    zero_tol: float,
    sliver_cube_ratio: float,
) -> Optional[tuple[int, int, int, int, float, float]]:
    """Return degenerate tet counts and volume extrema, or None if unavailable."""
    if _lib is None:
        return None
    pts = np.ascontiguousarray(pts, dtype=np.float64)
    tets = np.ascontiguousarray(tets, dtype=np.int64)
    n_tets = tets.shape[0]
    counts = np.zeros(4, dtype=np.int64)
    stats = np.zeros(2, dtype=np.float64)

    pts_p, _pts_k = _c_double_ptr(pts)
    tets_p, _tets_k = _c_long_ptr(tets)
    counts_p, _counts_k = _c_long_ptr(counts)
    stats_p, _stats_k = _c_double_ptr(stats)

    _lib.detect_degenerate_tets_stats(
        pts_p, ctypes.c_int(pts.shape[0]),
        tets_p, ctypes.c_int(n_tets),
        ctypes.c_double(float(zero_tol)),
        ctypes.c_double(float(sliver_cube_ratio)),
        counts_p,
        stats_p,
    )
    return (
        int(_counts_k[0]),
        int(_counts_k[1]),
        int(_counts_k[2]),
        int(_counts_k[3]),
        float(_stats_k[0]),
        float(_stats_k[1]),
    )


def tet_shortest_edges_batch(
    pts: np.ndarray,
    tets: np.ndarray,
) -> Optional[tuple[np.ndarray, np.ndarray]]:
    """Return shortest edge ids (n_tets, 2) and lengths (n_tets,), or None."""
    if _lib is None:
        return None
    pts = np.ascontiguousarray(pts, dtype=np.float64)
    tets = np.ascontiguousarray(tets, dtype=np.int64)
    n_tets = tets.shape[0]
    edges = np.empty((n_tets, 2), dtype=np.int64)
    lengths = np.empty(n_tets, dtype=np.float64)

    pts_p, _pts_k = _c_double_ptr(pts)
    tets_p, _tets_k = _c_long_ptr(tets)
    edges_p, _edges_k = _c_long_ptr(edges)
    lengths_p, _lengths_k = _c_double_ptr(lengths)

    _lib.tet_shortest_edges_batch(
        pts_p, ctypes.c_int(pts.shape[0]),
        tets_p, ctypes.c_int(n_tets),
        edges_p,
        lengths_p,
    )
    return _edges_k.reshape(n_tets, 2), _lengths_k


def edge_collapse_priority_batch(
    pts: np.ndarray,
    tets: np.ndarray,
    q: np.ndarray,
    q_threshold: float,
    top_k: int,
) -> Optional[tuple[np.ndarray, np.ndarray]]:
    """Return top collapse edges and scores, or None if native path fails."""
    if _lib is None:
        return None
    if top_k <= 0:
        return np.zeros((0, 2), dtype=np.int64), np.zeros(0, dtype=np.float64)
    pts = np.ascontiguousarray(pts, dtype=np.float64)
    tets = np.ascontiguousarray(tets, dtype=np.int64)
    q = np.ascontiguousarray(q, dtype=np.float64)
    n_tets = tets.shape[0]
    edges = np.empty((int(top_k), 2), dtype=np.int64)
    scores = np.empty(int(top_k), dtype=np.float64)
    n_out = np.zeros(1, dtype=np.int64)

    pts_p, _pts_k = _c_double_ptr(pts)
    tets_p, _tets_k = _c_long_ptr(tets)
    q_p, _q_k = _c_double_ptr(q)
    edges_p, _edges_k = _c_long_ptr(edges)
    scores_p, _scores_k = _c_double_ptr(scores)
    n_p, _n_k = _c_long_ptr(n_out)

    _lib.edge_collapse_priority_batch(
        pts_p, ctypes.c_int(pts.shape[0]),
        tets_p, ctypes.c_int(n_tets),
        q_p,
        ctypes.c_double(float(q_threshold)),
        ctypes.c_int(int(top_k)),
        edges_p,
        scores_p,
        n_p,
    )
    n_keep = int(_n_k[0])
    if n_keep < 0:
        return None
    return _edges_k.reshape(int(top_k), 2)[:n_keep].copy(), _scores_k[:n_keep].copy()


def build_tet_face_adjacency_stats(
    tets: np.ndarray,
) -> Optional[tuple[np.ndarray, tuple[int, int, int, int]]]:
    """Return tet face adjacency and counts, or None if native path fails."""
    if _lib is None:
        return None
    tets = np.ascontiguousarray(tets, dtype=np.int64)
    n_tets = tets.shape[0]
    adj = np.empty((n_tets, 4), dtype=np.int64)
    stats = np.zeros(4, dtype=np.int64)

    tets_p, _tets_k = _c_long_ptr(tets)
    adj_p, _adj_k = _c_long_ptr(adj)
    stats_p, _stats_k = _c_long_ptr(stats)

    _lib.build_tet_face_adjacency_stats(
        tets_p,
        ctypes.c_int(n_tets),
        adj_p,
        stats_p,
    )
    if int(_stats_k[0]) < 0:
        return None
    return _adj_k.reshape(n_tets, 4), (
        int(_stats_k[0]),
        int(_stats_k[1]),
        int(_stats_k[2]),
        int(_stats_k[3]),
    )


def screen_flip_candidates_batch(
    adj: np.ndarray,
    q: np.ndarray,
    q_threshold: float,
) -> Optional[tuple[np.ndarray, np.ndarray, int]]:
    """Return flip candidate pairs, worst-q values, and internal face count."""
    if _lib is None:
        return None
    adj = np.ascontiguousarray(adj, dtype=np.int64)
    q = np.ascontiguousarray(q, dtype=np.float64)
    n_tets = adj.shape[0]
    cap = n_tets * 4
    pairs = np.empty((cap, 2), dtype=np.int64)
    q_out = np.empty(cap, dtype=np.float64)
    counts = np.zeros(2, dtype=np.int64)

    adj_p, _adj_k = _c_long_ptr(adj)
    q_p, _q_k = _c_double_ptr(q)
    pairs_p, _pairs_k = _c_long_ptr(pairs)
    q_out_p, _q_out_k = _c_double_ptr(q_out)
    counts_p, _counts_k = _c_long_ptr(counts)

    _lib.screen_flip_candidates_batch(
        adj_p,
        ctypes.c_int(n_tets),
        q_p,
        ctypes.c_double(float(q_threshold)),
        pairs_p,
        q_out_p,
        counts_p,
    )
    if int(_counts_k[0]) < 0:
        return None
    n_candidates = int(_counts_k[1])
    return (
        _pairs_k.reshape(cap, 2)[:n_candidates].copy(),
        _q_out_k[:n_candidates].copy(),
        int(_counts_k[0]),
    )


def screen_swap_candidates_batch(
    tets: np.ndarray,
    q: np.ndarray,
    q_threshold: float,
) -> Optional[tuple[np.ndarray, np.ndarray, tuple[int, int, int]]]:
    """Return swap candidate edges, worst-q values, and aggregate counts."""
    if _lib is None:
        return None
    tets = np.ascontiguousarray(tets, dtype=np.int64)
    q = np.ascontiguousarray(q, dtype=np.float64)
    n_tets = tets.shape[0]
    cap = n_tets * 6
    edges = np.empty((cap, 2), dtype=np.int64)
    q_out = np.empty(cap, dtype=np.float64)
    counts = np.zeros(4, dtype=np.int64)

    tets_p, _tets_k = _c_long_ptr(tets)
    q_p, _q_k = _c_double_ptr(q)
    edges_p, _edges_k = _c_long_ptr(edges)
    q_out_p, _q_out_k = _c_double_ptr(q_out)
    counts_p, _counts_k = _c_long_ptr(counts)

    _lib.screen_swap_candidates_batch(
        tets_p,
        ctypes.c_int(n_tets),
        q_p,
        ctypes.c_double(float(q_threshold)),
        edges_p,
        q_out_p,
        counts_p,
    )
    if int(_counts_k[0]) < 0:
        return None
    n_candidates = int(_counts_k[1])
    edges_out = _edges_k.reshape(cap, 2)[:n_candidates].copy()
    q_values = _q_out_k[:n_candidates].copy()
    order = np.argsort(q_values)
    return (
        edges_out[order],
        q_values[order],
        (int(_counts_k[0]), int(_counts_k[2]), int(_counts_k[3])),
    )


def tet_vertex_valence_batch(
    tets: np.ndarray,
    n_vertices: int,
) -> Optional[tuple[np.ndarray, tuple[int, int, int, int, int], tuple[float, float]]]:
    """Return per-vertex incident tet counts plus aggregate stats."""
    if _lib is None:
        return None
    tets = np.ascontiguousarray(tets, dtype=np.int64)
    n_vertices = int(n_vertices)
    if n_vertices < 0:
        return None
    valence = np.empty(n_vertices, dtype=np.int64)
    stats = np.zeros(5, dtype=np.int64)
    floats = np.zeros(2, dtype=np.float64)

    tets_p, _tets_k = _c_long_ptr(tets)
    valence_p, _valence_k = _c_long_ptr(valence)
    stats_p, _stats_k = _c_long_ptr(stats)
    floats_p, _floats_k = _c_double_ptr(floats)

    _lib.tet_vertex_valence_batch(
        tets_p,
        ctypes.c_int(tets.shape[0]),
        ctypes.c_int(n_vertices),
        valence_p,
        stats_p,
        floats_p,
    )
    if int(_stats_k[0]) < 0:
        return None
    return (
        _valence_k.copy(),
        (
            int(_stats_k[0]),
            int(_stats_k[1]),
            int(_stats_k[2]),
            int(_stats_k[3]),
            int(_stats_k[4]),
        ),
        (float(_floats_k[0]), float(_floats_k[1])),
    )


def tet_boundary_vertex_stats_batch(
    tets: np.ndarray,
    n_surface_vertices: int,
) -> Optional[tuple[int, int]]:
    """Return boundary/interior tet counts based on surface vertex id cutoff."""
    if _lib is None:
        return None
    tets = np.ascontiguousarray(tets, dtype=np.int64)
    counts = np.zeros(2, dtype=np.int64)

    tets_p, _tets_k = _c_long_ptr(tets)
    counts_p, _counts_k = _c_long_ptr(counts)
    _lib.tet_boundary_vertex_stats_batch(
        tets_p,
        ctypes.c_int(tets.shape[0]),
        ctypes.c_int(int(n_surface_vertices)),
        counts_p,
    )
    return int(_counts_k[0]), int(_counts_k[1])


def tet_edge_stats_batch(
    pts: np.ndarray,
    tets: np.ndarray,
    sliver_aniso: float = 10.0,
) -> Optional[tuple[tuple[float, float, float, float, float, float], int]]:
    """Return tet edge length/aniso aggregate stats."""
    if _lib is None:
        return None
    pts = np.ascontiguousarray(pts, dtype=np.float64)
    tets = np.ascontiguousarray(tets, dtype=np.int64)
    stats = np.zeros(6, dtype=np.float64)
    counts = np.zeros(1, dtype=np.int64)

    pts_p, _pts_k = _c_double_ptr(pts)
    tets_p, _tets_k = _c_long_ptr(tets)
    stats_p, _stats_k = _c_double_ptr(stats)
    counts_p, _counts_k = _c_long_ptr(counts)
    _lib.tet_edge_stats_batch(
        pts_p,
        ctypes.c_int(pts.shape[0]),
        tets_p,
        ctypes.c_int(tets.shape[0]),
        ctypes.c_double(float(sliver_aniso)),
        stats_p,
        counts_p,
    )
    if int(_counts_k[0]) < 0:
        return None
    return (
        (
            float(_stats_k[0]),
            float(_stats_k[1]),
            float(_stats_k[2]),
            float(_stats_k[3]),
            float(_stats_k[4]),
            float(_stats_k[5]),
        ),
        int(_counts_k[0]),
    )


def tet_volume_stats_batch(
    pts: np.ndarray,
    tets: np.ndarray,
    n_bins: int = 20,
) -> Optional[tuple[tuple[float, float, float, float, float, float, float, float, float], int, np.ndarray]]:
    """Return tet quality/volume aggregate stats and quality histogram counts."""
    if _lib is None:
        return None
    pts = np.ascontiguousarray(pts, dtype=np.float64)
    tets = np.ascontiguousarray(tets, dtype=np.int64)
    n_bins = int(n_bins)
    if n_bins <= 0:
        return None
    stats = np.zeros(9, dtype=np.float64)
    counts = np.zeros(1, dtype=np.int64)
    hist = np.zeros(n_bins, dtype=np.int64)

    pts_p, _pts_k = _c_double_ptr(pts)
    tets_p, _tets_k = _c_long_ptr(tets)
    stats_p, _stats_k = _c_double_ptr(stats)
    counts_p, _counts_k = _c_long_ptr(counts)
    hist_p, _hist_k = _c_long_ptr(hist)
    _lib.tet_volume_stats_batch(
        pts_p,
        ctypes.c_int(pts.shape[0]),
        tets_p,
        ctypes.c_int(tets.shape[0]),
        ctypes.c_int(n_bins),
        stats_p,
        counts_p,
        hist_p,
    )
    if int(_counts_k[0]) < 0:
        return None
    return (
        (
            float(_stats_k[0]),
            float(_stats_k[1]),
            float(_stats_k[2]),
            float(_stats_k[3]),
            float(_stats_k[4]),
            float(_stats_k[5]),
            float(_stats_k[6]),
            float(_stats_k[7]),
            float(_stats_k[8]),
        ),
        int(_counts_k[0]),
        _hist_k.copy(),
    )


def tet_inradius_batch(
    pts: np.ndarray,
    tets: np.ndarray,
) -> Optional[tuple[np.ndarray, tuple[float, float, float], int]]:
    """Return tet inradius array plus aggregate stats."""
    if _lib is None:
        return None
    pts = np.ascontiguousarray(pts, dtype=np.float64)
    tets = np.ascontiguousarray(tets, dtype=np.int64)
    n_tets = tets.shape[0]
    radii = np.empty(n_tets, dtype=np.float64)
    stats = np.zeros(3, dtype=np.float64)
    counts = np.zeros(1, dtype=np.int64)

    pts_p, _pts_k = _c_double_ptr(pts)
    tets_p, _tets_k = _c_long_ptr(tets)
    radii_p, _radii_k = _c_double_ptr(radii)
    stats_p, _stats_k = _c_double_ptr(stats)
    counts_p, _counts_k = _c_long_ptr(counts)
    _lib.tet_inradius_batch(
        pts_p,
        ctypes.c_int(pts.shape[0]),
        tets_p,
        ctypes.c_int(n_tets),
        radii_p,
        stats_p,
        counts_p,
    )
    return (
        _radii_k.copy(),
        (float(_stats_k[0]), float(_stats_k[1]), float(_stats_k[2])),
        int(_counts_k[0]),
    )


def tet_circumsphere_batch(
    pts: np.ndarray,
    tets: np.ndarray,
) -> Optional[tuple[np.ndarray, np.ndarray, tuple[float, float, float], int]]:
    """Return tet circumcenters, radii, and aggregate radius stats."""
    if _lib is None:
        return None
    pts = np.ascontiguousarray(pts, dtype=np.float64)
    tets = np.ascontiguousarray(tets, dtype=np.int64)
    n_tets = tets.shape[0]
    centers = np.empty((n_tets, 3), dtype=np.float64)
    radii = np.empty(n_tets, dtype=np.float64)
    stats = np.zeros(3, dtype=np.float64)
    counts = np.zeros(1, dtype=np.int64)

    pts_p, _pts_k = _c_double_ptr(pts)
    tets_p, _tets_k = _c_long_ptr(tets)
    centers_p, _centers_k = _c_double_ptr(centers)
    radii_p, _radii_k = _c_double_ptr(radii)
    stats_p, _stats_k = _c_double_ptr(stats)
    counts_p, _counts_k = _c_long_ptr(counts)
    _lib.tet_circumsphere_batch(
        pts_p,
        ctypes.c_int(pts.shape[0]),
        tets_p,
        ctypes.c_int(n_tets),
        centers_p,
        radii_p,
        stats_p,
        counts_p,
    )
    return (
        _centers_k.reshape(n_tets, 3).copy(),
        _radii_k.copy(),
        (float(_stats_k[0]), float(_stats_k[1]), float(_stats_k[2])),
        int(_counts_k[0]),
    )


def tet_aniso_tensor_batch(
    pts: np.ndarray,
    tets: np.ndarray,
) -> Optional[tuple[np.ndarray, tuple[float, float, float, float], int]]:
    """Return tet anisotropy ratio array and aggregate stats."""
    if _lib is None:
        return None
    pts = np.ascontiguousarray(pts, dtype=np.float64)
    tets = np.ascontiguousarray(tets, dtype=np.int64)
    n_tets = tets.shape[0]
    ratio = np.empty(n_tets, dtype=np.float64)
    stats = np.zeros(4, dtype=np.float64)
    counts = np.zeros(1, dtype=np.int64)

    pts_p, _pts_k = _c_double_ptr(pts)
    tets_p, _tets_k = _c_long_ptr(tets)
    ratio_p, _ratio_k = _c_double_ptr(ratio)
    stats_p, _stats_k = _c_double_ptr(stats)
    counts_p, _counts_k = _c_long_ptr(counts)
    _lib.tet_aniso_tensor_batch(
        pts_p,
        ctypes.c_int(pts.shape[0]),
        tets_p,
        ctypes.c_int(n_tets),
        ratio_p,
        stats_p,
        counts_p,
    )
    if int(_counts_k[0]) < 0:
        return None
    return (
        _ratio_k.copy(),
        (
            float(_stats_k[0]),
            float(_stats_k[1]),
            float(_stats_k[2]),
            float(_stats_k[3]),
        ),
        int(_counts_k[0]),
    )


def hex_stretch_stats_batch(
    pts: np.ndarray,
    hexes: np.ndarray,
) -> Optional[tuple[tuple[float, float, float], int]]:
    """Return hex edge stretch aggregate stats."""
    if _lib is None:
        return None
    pts = np.ascontiguousarray(pts, dtype=np.float64)
    hexes = np.ascontiguousarray(hexes, dtype=np.int64)
    stats = np.zeros(3, dtype=np.float64)
    counts = np.zeros(1, dtype=np.int64)

    pts_p, _pts_k = _c_double_ptr(pts)
    hexes_p, _hexes_k = _c_long_ptr(hexes)
    stats_p, _stats_k = _c_double_ptr(stats)
    counts_p, _counts_k = _c_long_ptr(counts)
    _lib.hex_stretch_stats_batch(
        pts_p,
        ctypes.c_int(pts.shape[0]),
        hexes_p,
        ctypes.c_int(hexes.shape[0]),
        stats_p,
        counts_p,
    )
    return (
        (float(_stats_k[0]), float(_stats_k[1]), float(_stats_k[2])),
        int(_counts_k[0]),
    )


def hex_face_area_stats_batch(
    pts: np.ndarray,
    hexes: np.ndarray,
) -> Optional[tuple[tuple[float, float, float, float, float], int]]:
    """Return hex face area and per-hex area ratio aggregate stats."""
    if _lib is None:
        return None
    pts = np.ascontiguousarray(pts, dtype=np.float64)
    hexes = np.ascontiguousarray(hexes, dtype=np.int64)
    stats = np.zeros(5, dtype=np.float64)
    counts = np.zeros(1, dtype=np.int64)

    pts_p, _pts_k = _c_double_ptr(pts)
    hexes_p, _hexes_k = _c_long_ptr(hexes)
    stats_p, _stats_k = _c_double_ptr(stats)
    counts_p, _counts_k = _c_long_ptr(counts)
    _lib.hex_face_area_stats_batch(
        pts_p,
        ctypes.c_int(pts.shape[0]),
        hexes_p,
        ctypes.c_int(hexes.shape[0]),
        stats_p,
        counts_p,
    )
    return (
        (
            float(_stats_k[0]),
            float(_stats_k[1]),
            float(_stats_k[2]),
            float(_stats_k[3]),
            float(_stats_k[4]),
        ),
        int(_counts_k[0]),
    )


def bl_prism_quality_stats_batch(
    pts: np.ndarray,
    prisms: np.ndarray,
) -> Optional[tuple[tuple[float, float, float, float, float, float], int]]:
    """Return boundary-layer prism quality aggregate stats."""
    if _lib is None:
        return None
    pts = np.ascontiguousarray(pts, dtype=np.float64)
    prisms = np.ascontiguousarray(prisms, dtype=np.int64)
    stats = np.zeros(6, dtype=np.float64)
    counts = np.zeros(1, dtype=np.int64)

    pts_p, _pts_k = _c_double_ptr(pts)
    prisms_p, _prisms_k = _c_long_ptr(prisms)
    stats_p, _stats_k = _c_double_ptr(stats)
    counts_p, _counts_k = _c_long_ptr(counts)
    _lib.bl_prism_quality_stats_batch(
        pts_p,
        ctypes.c_int(pts.shape[0]),
        prisms_p,
        ctypes.c_int(prisms.shape[0]),
        stats_p,
        counts_p,
    )
    return (
        (
            float(_stats_k[0]),
            float(_stats_k[1]),
            float(_stats_k[2]),
            float(_stats_k[3]),
            float(_stats_k[4]),
            float(_stats_k[5]),
        ),
        int(_counts_k[0]),
    )


def hex_skew_simple_stats_batch(
    pts: np.ndarray,
    hexes: np.ndarray,
) -> Optional[tuple[tuple[float, float, float], int]]:
    """Return simple hex skew aggregate stats."""
    if _lib is None:
        return None
    pts = np.ascontiguousarray(pts, dtype=np.float64)
    hexes = np.ascontiguousarray(hexes, dtype=np.int64)
    stats = np.zeros(3, dtype=np.float64)
    counts = np.zeros(1, dtype=np.int64)

    pts_p, _pts_k = _c_double_ptr(pts)
    hexes_p, _hexes_k = _c_long_ptr(hexes)
    stats_p, _stats_k = _c_double_ptr(stats)
    counts_p, _counts_k = _c_long_ptr(counts)
    _lib.hex_skew_simple_stats_batch(
        pts_p,
        ctypes.c_int(pts.shape[0]),
        hexes_p,
        ctypes.c_int(hexes.shape[0]),
        stats_p,
        counts_p,
    )
    return (
        (float(_stats_k[0]), float(_stats_k[1]), float(_stats_k[2])),
        int(_counts_k[0]),
    )


def hex_ortho_stats_batch(
    pts: np.ndarray,
    hexes: np.ndarray,
) -> Optional[tuple[tuple[float, float, float], int]]:
    """Return simple hex orthogonality aggregate stats."""
    if _lib is None:
        return None
    pts = np.ascontiguousarray(pts, dtype=np.float64)
    hexes = np.ascontiguousarray(hexes, dtype=np.int64)
    stats = np.zeros(3, dtype=np.float64)
    counts = np.zeros(1, dtype=np.int64)

    pts_p, _pts_k = _c_double_ptr(pts)
    hexes_p, _hexes_k = _c_long_ptr(hexes)
    stats_p, _stats_k = _c_double_ptr(stats)
    counts_p, _counts_k = _c_long_ptr(counts)
    _lib.hex_ortho_stats_batch(
        pts_p,
        ctypes.c_int(pts.shape[0]),
        hexes_p,
        ctypes.c_int(hexes.shape[0]),
        stats_p,
        counts_p,
    )
    return (
        (float(_stats_k[0]), float(_stats_k[1]), float(_stats_k[2])),
        int(_counts_k[0]),
    )


def hex_jacobian_stats_batch(
    pts: np.ndarray,
    hexes: np.ndarray,
) -> Optional[tuple[tuple[float, float, float, float, float], int]]:
    """Return hex corner Jacobian aggregate stats."""
    if _lib is None:
        return None
    pts = np.ascontiguousarray(pts, dtype=np.float64)
    hexes = np.ascontiguousarray(hexes, dtype=np.int64)
    stats = np.zeros(5, dtype=np.float64)
    counts = np.zeros(1, dtype=np.int64)

    pts_p, _pts_k = _c_double_ptr(pts)
    hexes_p, _hexes_k = _c_long_ptr(hexes)
    stats_p, _stats_k = _c_double_ptr(stats)
    counts_p, _counts_k = _c_long_ptr(counts)
    _lib.hex_jacobian_stats_batch(
        pts_p,
        ctypes.c_int(pts.shape[0]),
        hexes_p,
        ctypes.c_int(hexes.shape[0]),
        stats_p,
        counts_p,
    )
    return (
        (
            float(_stats_k[0]),
            float(_stats_k[1]),
            float(_stats_k[2]),
            float(_stats_k[3]),
            float(_stats_k[4]),
        ),
        int(_counts_k[0]),
    )


def hex_inverted_stats_batch(
    pts: np.ndarray,
    hexes: np.ndarray,
    max_indices: int = 100,
) -> Optional[tuple[np.ndarray, tuple[int, int, int], float]]:
    """Return inverted hex index sample, counts, and worst minimum Jacobian."""
    if _lib is None:
        return None
    pts = np.ascontiguousarray(pts, dtype=np.float64)
    hexes = np.ascontiguousarray(hexes, dtype=np.int64)
    max_indices = int(max_indices)
    if max_indices < 0:
        return None
    indices = np.zeros(max_indices, dtype=np.int64)
    counts = np.zeros(3, dtype=np.int64)
    worst = np.zeros(1, dtype=np.float64)

    pts_p, _pts_k = _c_double_ptr(pts)
    hexes_p, _hexes_k = _c_long_ptr(hexes)
    indices_p, _indices_k = _c_long_ptr(indices)
    counts_p, _counts_k = _c_long_ptr(counts)
    worst_p, _worst_k = _c_double_ptr(worst)
    _lib.hex_inverted_stats_batch(
        pts_p,
        ctypes.c_int(pts.shape[0]),
        hexes_p,
        ctypes.c_int(hexes.shape[0]),
        ctypes.c_int(max_indices),
        indices_p,
        counts_p,
        worst_p,
    )
    n_written = int(_counts_k[2])
    return (
        _indices_k[:n_written].copy(),
        (int(_counts_k[0]), int(_counts_k[1]), n_written),
        float(_worst_k[0]),
    )


def hex_validate_volumes_batch(
    pts: np.ndarray,
    hexes: np.ndarray,
    degenerate_eps: float,
) -> Optional[tuple[np.ndarray, int, int]]:
    """Return fixed hexes plus flip/degenerate counts from native volume validation."""
    if _lib is None:
        return None
    pts = np.ascontiguousarray(pts, dtype=np.float64)
    hexes = np.ascontiguousarray(hexes, dtype=np.int64).copy()
    if hexes.ndim != 2 or hexes.shape[1] != 8:
        return None
    n_hexes = int(hexes.shape[0])
    counts = np.zeros(2, dtype=np.int64)

    pts_p, _pts_k = _c_double_ptr(pts)
    hexes_p, _hexes_k = _c_long_ptr(hexes)
    counts_p, _counts_k = _c_long_ptr(counts)
    _lib.hex_validate_volumes_batch(
        pts_p,
        ctypes.c_int(pts.shape[0]),
        hexes_p,
        ctypes.c_int(n_hexes),
        ctypes.c_double(float(degenerate_eps)),
        counts_p,
    )
    return (
        _hexes_k.reshape(n_hexes, 8).copy(),
        int(_counts_k[0]),
        int(_counts_k[1]),
    )


def closest_points_on_triangles_candidates_batch(
    points: np.ndarray,
    tri_a: np.ndarray,
    tri_b: np.ndarray,
    tri_c: np.ndarray,
    candidate_idx: np.ndarray,
) -> Optional[tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """Return best closest triangle point per query point over candidate triangles."""
    if _lib is None:
        return None
    points = np.ascontiguousarray(points, dtype=np.float64)
    tri_a = np.ascontiguousarray(tri_a, dtype=np.float64)
    tri_b = np.ascontiguousarray(tri_b, dtype=np.float64)
    tri_c = np.ascontiguousarray(tri_c, dtype=np.float64)
    candidate_idx = np.ascontiguousarray(candidate_idx, dtype=np.int64)
    if points.ndim != 2 or points.shape[1] != 3:
        return None
    if candidate_idx.ndim == 1:
        candidate_idx = candidate_idx.reshape(-1, 1)
    if candidate_idx.shape[0] != points.shape[0]:
        return None
    n_points = int(points.shape[0])
    k = int(candidate_idx.shape[1])
    n_tri = int(min(tri_a.shape[0], tri_b.shape[0], tri_c.shape[0]))
    best_points = np.empty((n_points, 3), dtype=np.float64)
    best_dist2 = np.empty(n_points, dtype=np.float64)
    has = np.zeros(n_points, dtype=np.int64)

    points_p, _points_k = _c_double_ptr(points)
    tri_a_p, _tri_a_k = _c_double_ptr(tri_a)
    tri_b_p, _tri_b_k = _c_double_ptr(tri_b)
    tri_c_p, _tri_c_k = _c_double_ptr(tri_c)
    cand_p, _cand_k = _c_long_ptr(candidate_idx)
    best_points_p, _best_points_k = _c_double_ptr(best_points)
    best_dist2_p, _best_dist2_k = _c_double_ptr(best_dist2)
    has_p, _has_k = _c_long_ptr(has)
    _lib.closest_points_on_triangles_candidates_batch(
        points_p,
        ctypes.c_int(n_points),
        tri_a_p,
        tri_b_p,
        tri_c_p,
        ctypes.c_int(n_tri),
        cand_p,
        ctypes.c_int(k),
        best_points_p,
        best_dist2_p,
        has_p,
    )
    return (
        _best_points_k.reshape(n_points, 3).copy(),
        _best_dist2_k.copy(),
        _has_k.astype(bool).copy(),
    )


def poly_volume_stats_batch(
    pts: np.ndarray,
    cell_face_lists: list,
) -> Optional[tuple[np.ndarray, tuple[float, float, float, float], int]]:
    """Return poly cell volume array and aggregate stats for face-list cells."""
    if _lib is None:
        return None
    pts = np.ascontiguousarray(pts, dtype=np.float64)
    n_cells = len(cell_face_lists)
    if n_cells == 0:
        return (
            np.zeros(0, dtype=np.float64),
            (0.0, 0.0, 0.0, 0.0),
            0,
        )

    face_arrays: list[np.ndarray] = []
    face_offsets = [0]
    cell_offsets = [0]
    for faces in cell_face_lists:
        for face in faces:
            arr = np.asarray(face, dtype=np.int64).ravel()
            face_arrays.append(arr)
            face_offsets.append(face_offsets[-1] + int(arr.size))
        cell_offsets.append(len(face_arrays))

    if face_arrays:
        face_indices = np.ascontiguousarray(np.concatenate(face_arrays), dtype=np.int64)
    else:
        face_indices = np.zeros(0, dtype=np.int64)
    face_offsets_arr = np.ascontiguousarray(face_offsets, dtype=np.int64)
    cell_offsets_arr = np.ascontiguousarray(cell_offsets, dtype=np.int64)
    volumes = np.empty(n_cells, dtype=np.float64)
    stats = np.zeros(4, dtype=np.float64)
    counts = np.zeros(1, dtype=np.int64)

    pts_p, _pts_k = _c_double_ptr(pts)
    face_indices_p, _face_indices_k = _c_long_ptr(face_indices)
    face_offsets_p, _face_offsets_k = _c_long_ptr(face_offsets_arr)
    cell_offsets_p, _cell_offsets_k = _c_long_ptr(cell_offsets_arr)
    volumes_p, _volumes_k = _c_double_ptr(volumes)
    stats_p, _stats_k = _c_double_ptr(stats)
    counts_p, _counts_k = _c_long_ptr(counts)
    _lib.poly_volume_stats_batch(
        pts_p,
        ctypes.c_int(pts.shape[0]),
        face_indices_p,
        face_offsets_p,
        ctypes.c_int(len(face_arrays)),
        cell_offsets_p,
        ctypes.c_int(n_cells),
        volumes_p,
        stats_p,
        counts_p,
    )
    return (
        _volumes_k.copy(),
        (
            float(_stats_k[0]),
            float(_stats_k[1]),
            float(_stats_k[2]),
            float(_stats_k[3]),
        ),
        int(_counts_k[0]),
    )


def poly_validate_volumes_batch(
    pts: np.ndarray,
    cells: list,
    degenerate_eps: float,
) -> Optional[tuple[int, int]]:
    """Return negative and degenerate poly cell counts using centroid fan volumes."""
    if _lib is None:
        return None
    pts = np.ascontiguousarray(pts, dtype=np.float64)
    n_cells = len(cells)
    if n_cells == 0:
        return (0, 0)

    face_arrays: list[np.ndarray] = []
    face_offsets = [0]
    cell_offsets = [0]
    for cell_faces in cells:
        for face in cell_faces:
            arr = np.asarray(face, dtype=np.int64).ravel()
            face_arrays.append(arr)
            face_offsets.append(face_offsets[-1] + int(arr.size))
        cell_offsets.append(len(face_arrays))

    if face_arrays:
        face_indices = np.ascontiguousarray(np.concatenate(face_arrays), dtype=np.int64)
    else:
        face_indices = np.zeros(0, dtype=np.int64)
    face_offsets_arr = np.ascontiguousarray(face_offsets, dtype=np.int64)
    cell_offsets_arr = np.ascontiguousarray(cell_offsets, dtype=np.int64)
    counts = np.zeros(2, dtype=np.int64)

    pts_p, _pts_k = _c_double_ptr(pts)
    face_indices_p, _face_indices_k = _c_long_ptr(face_indices)
    face_offsets_p, _face_offsets_k = _c_long_ptr(face_offsets_arr)
    cell_offsets_p, _cell_offsets_k = _c_long_ptr(cell_offsets_arr)
    counts_p, _counts_k = _c_long_ptr(counts)
    _lib.poly_validate_volumes_batch(
        pts_p,
        ctypes.c_int(pts.shape[0]),
        face_indices_p,
        face_offsets_p,
        ctypes.c_int(len(face_arrays)),
        cell_offsets_p,
        ctypes.c_int(n_cells),
        ctypes.c_double(float(degenerate_eps)),
        counts_p,
    )
    return (int(_counts_k[0]), int(_counts_k[1]))


def poly_aspect_stats_batch(
    pts: np.ndarray,
    cell_vertices: list,
) -> Optional[tuple[tuple[float, float, float], int, int]]:
    """Return bbox aspect aggregate stats for poly cells."""
    if _lib is None:
        return None
    pts = np.ascontiguousarray(pts, dtype=np.float64)
    n_cells = len(cell_vertices)
    if n_cells == 0:
        return ((0.0, 0.0, 0.0), 0, 0)

    cell_arrays: list[np.ndarray] = []
    cell_offsets = [0]
    for cv in cell_vertices:
        arr = np.asarray(cv, dtype=np.int64).ravel()
        cell_arrays.append(arr)
        cell_offsets.append(cell_offsets[-1] + int(arr.size))

    if cell_arrays:
        cell_indices = np.ascontiguousarray(np.concatenate(cell_arrays), dtype=np.int64)
    else:
        cell_indices = np.zeros(0, dtype=np.int64)
    cell_offsets_arr = np.ascontiguousarray(cell_offsets, dtype=np.int64)
    stats = np.zeros(3, dtype=np.float64)
    counts = np.zeros(2, dtype=np.int64)

    pts_p, _pts_k = _c_double_ptr(pts)
    cell_indices_p, _cell_indices_k = _c_long_ptr(cell_indices)
    cell_offsets_p, _cell_offsets_k = _c_long_ptr(cell_offsets_arr)
    stats_p, _stats_k = _c_double_ptr(stats)
    counts_p, _counts_k = _c_long_ptr(counts)
    _lib.poly_aspect_stats_batch(
        pts_p,
        ctypes.c_int(pts.shape[0]),
        cell_indices_p,
        cell_offsets_p,
        ctypes.c_int(n_cells),
        stats_p,
        counts_p,
    )
    return (
        (
            float(_stats_k[0]),
            float(_stats_k[1]),
            float(_stats_k[2]),
        ),
        int(_counts_k[0]),
        int(_counts_k[1]),
    )


def poly_convex_stats_batch(
    pts: np.ndarray,
    cell_vertices: list,
    cell_face_planes: list,
    tol: float,
) -> Optional[tuple[int, float]]:
    """Return convex cell count and max violation for poly cells."""
    if _lib is None:
        return None
    pts = np.ascontiguousarray(pts, dtype=np.float64)
    n_cells = len(cell_vertices)
    if n_cells == 0:
        return (0, 0.0)

    cell_arrays: list[np.ndarray] = []
    cell_offsets = [0]
    plane_arrays: list[np.ndarray] = []
    plane_offsets = [0]
    for ci in range(n_cells):
        cell_arr = np.asarray(cell_vertices[ci], dtype=np.int64).ravel()
        cell_arrays.append(cell_arr)
        cell_offsets.append(cell_offsets[-1] + int(cell_arr.size))

        planes_arr = np.asarray(cell_face_planes[ci], dtype=np.float64)
        if planes_arr.size == 0:
            planes_arr = np.zeros((0, 4), dtype=np.float64)
        else:
            planes_arr = np.ascontiguousarray(planes_arr.reshape(-1, 4), dtype=np.float64)
        plane_arrays.append(planes_arr)
        plane_offsets.append(plane_offsets[-1] + int(planes_arr.shape[0]))

    if cell_arrays:
        cell_indices = np.ascontiguousarray(np.concatenate(cell_arrays), dtype=np.int64)
    else:
        cell_indices = np.zeros(0, dtype=np.int64)
    if plane_arrays:
        planes = np.ascontiguousarray(np.vstack(plane_arrays), dtype=np.float64)
    else:
        planes = np.zeros((0, 4), dtype=np.float64)
    cell_offsets_arr = np.ascontiguousarray(cell_offsets, dtype=np.int64)
    plane_offsets_arr = np.ascontiguousarray(plane_offsets, dtype=np.int64)
    counts = np.zeros(1, dtype=np.int64)
    stats = np.zeros(1, dtype=np.float64)

    pts_p, _pts_k = _c_double_ptr(pts)
    cell_indices_p, _cell_indices_k = _c_long_ptr(cell_indices)
    cell_offsets_p, _cell_offsets_k = _c_long_ptr(cell_offsets_arr)
    planes_p, _planes_k = _c_double_ptr(planes)
    plane_offsets_p, _plane_offsets_k = _c_long_ptr(plane_offsets_arr)
    counts_p, _counts_k = _c_long_ptr(counts)
    stats_p, _stats_k = _c_double_ptr(stats)
    _lib.poly_convex_stats_batch(
        pts_p,
        ctypes.c_int(pts.shape[0]),
        cell_indices_p,
        cell_offsets_p,
        planes_p,
        plane_offsets_p,
        ctypes.c_int(n_cells),
        ctypes.c_double(float(tol)),
        counts_p,
        stats_p,
    )
    return (int(_counts_k[0]), float(_stats_k[0]))


def native_checker_non_orthogonality_stats_batch(
    face_normals: np.ndarray,
    cell_centres: np.ndarray,
    owner: np.ndarray,
    neighbour: np.ndarray,
    n_internal: int,
    severe_threshold: float,
) -> Optional[tuple[float, float, int]]:
    """Return native_checker non-orthogonality max/avg/severe stats."""
    if _lib is None:
        return None
    n_internal = int(n_internal)
    if n_internal <= 0:
        return (0.0, 0.0, 0)
    face_normals = np.ascontiguousarray(face_normals, dtype=np.float64)
    cell_centres = np.ascontiguousarray(cell_centres, dtype=np.float64)
    owner = np.ascontiguousarray(owner, dtype=np.int64)
    neighbour = np.ascontiguousarray(neighbour, dtype=np.int64)
    if (
        face_normals.shape[0] < n_internal
        or owner.shape[0] < n_internal
        or neighbour.shape[0] < n_internal
    ):
        return None

    stats = np.zeros(2, dtype=np.float64)
    counts = np.zeros(2, dtype=np.int64)
    face_normals_p, _face_normals_k = _c_double_ptr(face_normals)
    cell_centres_p, _cell_centres_k = _c_double_ptr(cell_centres)
    owner_p, _owner_k = _c_long_ptr(owner)
    neighbour_p, _neighbour_k = _c_long_ptr(neighbour)
    stats_p, _stats_k = _c_double_ptr(stats)
    counts_p, _counts_k = _c_long_ptr(counts)

    _lib.native_checker_non_orthogonality_stats_batch(
        face_normals_p,
        cell_centres_p,
        owner_p,
        neighbour_p,
        ctypes.c_int(n_internal),
        ctypes.c_double(float(severe_threshold)),
        stats_p,
        counts_p,
    )
    return (
        float(_stats_k[0]),
        float(_stats_k[1]),
        int(_counts_k[0]),
    )


def native_checker_skewness_stats_batch(
    face_centres: np.ndarray,
    cell_centres: np.ndarray,
    owner: np.ndarray,
    neighbour: np.ndarray,
    n_internal: int,
) -> Optional[float]:
    """Return native_checker internal face skewness max."""
    if _lib is None:
        return None
    n_internal = int(n_internal)
    if n_internal <= 0:
        return 0.0
    face_centres = np.ascontiguousarray(face_centres, dtype=np.float64)
    cell_centres = np.ascontiguousarray(cell_centres, dtype=np.float64)
    owner = np.ascontiguousarray(owner, dtype=np.int64)
    neighbour = np.ascontiguousarray(neighbour, dtype=np.int64)
    if (
        face_centres.shape[0] < n_internal
        or owner.shape[0] < n_internal
        or neighbour.shape[0] < n_internal
    ):
        return None

    stats = np.zeros(1, dtype=np.float64)
    face_centres_p, _face_centres_k = _c_double_ptr(face_centres)
    cell_centres_p, _cell_centres_k = _c_double_ptr(cell_centres)
    owner_p, _owner_k = _c_long_ptr(owner)
    neighbour_p, _neighbour_k = _c_long_ptr(neighbour)
    stats_p, _stats_k = _c_double_ptr(stats)
    _lib.native_checker_skewness_stats_batch(
        face_centres_p,
        cell_centres_p,
        owner_p,
        neighbour_p,
        ctypes.c_int(n_internal),
        stats_p,
    )
    return float(_stats_k[0])


def native_checker_face_geometry_batch(
    points: np.ndarray,
    faces: list,
) -> Optional[tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """Return face centres, unit normals, and areas for NativeMeshChecker."""
    if _lib is None:
        return None
    points = np.ascontiguousarray(points, dtype=np.float64)
    n_faces = len(faces)
    if n_faces == 0:
        return (
            np.zeros((0, 3), dtype=np.float64),
            np.zeros((0, 3), dtype=np.float64),
            np.zeros(0, dtype=np.float64),
        )

    face_arrays: list[np.ndarray] = []
    face_offsets = [0]
    for face in faces:
        arr = np.asarray(face, dtype=np.int64).ravel()
        face_arrays.append(arr)
        face_offsets.append(face_offsets[-1] + int(arr.size))

    if face_arrays:
        face_indices = np.ascontiguousarray(np.concatenate(face_arrays), dtype=np.int64)
    else:
        face_indices = np.zeros(0, dtype=np.int64)
    face_offsets_arr = np.ascontiguousarray(face_offsets, dtype=np.int64)
    centres = np.empty((n_faces, 3), dtype=np.float64)
    normals = np.empty((n_faces, 3), dtype=np.float64)
    areas = np.empty(n_faces, dtype=np.float64)

    points_p, _points_k = _c_double_ptr(points)
    face_indices_p, _face_indices_k = _c_long_ptr(face_indices)
    face_offsets_p, _face_offsets_k = _c_long_ptr(face_offsets_arr)
    centres_p, _centres_k = _c_double_ptr(centres)
    normals_p, _normals_k = _c_double_ptr(normals)
    areas_p, _areas_k = _c_double_ptr(areas)
    _lib.native_checker_face_geometry_batch(
        points_p,
        ctypes.c_int(points.shape[0]),
        face_indices_p,
        face_offsets_p,
        ctypes.c_int(n_faces),
        centres_p,
        normals_p,
        areas_p,
    )
    return (
        _centres_k.reshape(n_faces, 3).copy(),
        _normals_k.reshape(n_faces, 3).copy(),
        _areas_k.copy(),
    )


def native_checker_cell_centres_from_face_centres_batch(
    face_centres: np.ndarray,
    owner: np.ndarray,
    n_cells: int,
    neighbour: np.ndarray | None = None,
) -> Optional[np.ndarray]:
    """Return cell centres as mean of owner/neighbour face centres."""
    if _lib is None:
        return None
    n_cells = int(n_cells)
    if n_cells <= 0:
        return np.zeros((0, 3), dtype=np.float64)
    face_centres = np.ascontiguousarray(face_centres, dtype=np.float64)
    owner = np.ascontiguousarray(owner, dtype=np.int64)
    if neighbour is None:
        neighbour_arr = np.zeros(0, dtype=np.int64)
    else:
        neighbour_arr = np.ascontiguousarray(neighbour, dtype=np.int64)
    n_faces = int(min(face_centres.shape[0], owner.shape[0]))
    n_internal = int(min(neighbour_arr.shape[0], n_faces))
    centres = np.empty((n_cells, 3), dtype=np.float64)

    face_centres_p, _face_centres_k = _c_double_ptr(face_centres)
    owner_p, _owner_k = _c_long_ptr(owner)
    neighbour_p, _neighbour_k = _c_long_ptr(neighbour_arr)
    centres_p, _centres_k = _c_double_ptr(centres)
    _lib.native_checker_cell_centres_from_face_centres_batch(
        face_centres_p,
        owner_p,
        ctypes.c_int(n_faces),
        neighbour_p,
        ctypes.c_int(n_internal),
        ctypes.c_int(n_cells),
        centres_p,
    )
    return _centres_k.reshape(n_cells, 3).copy()


def surface_boundary_edges_batch(
    faces: np.ndarray,
) -> Optional[np.ndarray]:
    """Return boundary edges for triangular faces, or None if native path fails."""
    if _lib is None:
        return None
    faces = np.ascontiguousarray(faces, dtype=np.int64)
    n_faces = faces.shape[0]
    edges = np.empty((n_faces * 3, 2), dtype=np.int64)
    n_out = np.zeros(1, dtype=np.int64)

    faces_p, _faces_k = _c_long_ptr(faces)
    edges_p, _edges_k = _c_long_ptr(edges)
    n_p, _n_k = _c_long_ptr(n_out)

    _lib.surface_boundary_edges_batch(
        faces_p,
        ctypes.c_int(n_faces),
        edges_p,
        n_p,
    )
    n_boundary = int(_n_k[0])
    if n_boundary < 0:
        return None
    return _edges_k.reshape(n_faces * 3, 2)[:n_boundary].copy()


def surface_edge_stats_batch(
    faces: np.ndarray,
) -> Optional[tuple[int, int, int, int]]:
    """Return surface edge-count stats, or None if native path fails."""
    if _lib is None:
        return None
    faces = np.ascontiguousarray(faces, dtype=np.int64)
    stats = np.zeros(4, dtype=np.int64)

    faces_p, _faces_k = _c_long_ptr(faces)
    stats_p, _stats_k = _c_long_ptr(stats)
    _lib.surface_edge_stats_batch(
        faces_p,
        ctypes.c_int(faces.shape[0]),
        stats_p,
    )
    if int(_stats_k[0]) < 0:
        return None
    return (
        int(_stats_k[0]),
        int(_stats_k[1]),
        int(_stats_k[2]),
        int(_stats_k[3]),
    )


def surface_vertex_valence_batch(
    faces: np.ndarray,
    n_vertices: int,
) -> Optional[tuple[np.ndarray, np.ndarray, tuple[int, int, int, int, int, int, int], tuple[float, float]]]:
    """Return per-vertex face/edge valence arrays plus aggregate stats."""
    if _lib is None:
        return None
    faces = np.ascontiguousarray(faces, dtype=np.int64)
    n_vertices = int(n_vertices)
    face_val = np.empty(n_vertices, dtype=np.int64)
    edge_val = np.empty(n_vertices, dtype=np.int64)
    stats = np.zeros(7, dtype=np.int64)
    means = np.zeros(2, dtype=np.float64)

    faces_p, _faces_k = _c_long_ptr(faces)
    face_val_p, _face_val_k = _c_long_ptr(face_val)
    edge_val_p, _edge_val_k = _c_long_ptr(edge_val)
    stats_p, _stats_k = _c_long_ptr(stats)
    means_p, _means_k = _c_double_ptr(means)

    _lib.surface_vertex_valence_batch(
        faces_p,
        ctypes.c_int(faces.shape[0]),
        ctypes.c_int(n_vertices),
        face_val_p,
        edge_val_p,
        stats_p,
        means_p,
    )
    if int(_stats_k[0]) < 0:
        return None
    return (
        _face_val_k.copy(),
        _edge_val_k.copy(),
        (
            int(_stats_k[0]),
            int(_stats_k[1]),
            int(_stats_k[2]),
            int(_stats_k[3]),
            int(_stats_k[4]),
            int(_stats_k[5]),
            int(_stats_k[6]),
        ),
        (float(_means_k[0]), float(_means_k[1])),
    )


def surface_edge_lengths_stats_batch(
    verts: np.ndarray,
    faces: np.ndarray,
) -> Optional[tuple[np.ndarray, int, float, float]]:
    """Return all triangle edge lengths plus unique/aspect stats."""
    if _lib is None:
        return None
    verts = np.ascontiguousarray(verts, dtype=np.float64)
    faces = np.ascontiguousarray(faces, dtype=np.int64)
    n_faces = faces.shape[0]
    lengths = np.empty(n_faces * 3, dtype=np.float64)
    counts = np.zeros(1, dtype=np.int64)
    aspect = np.zeros(2, dtype=np.float64)

    verts_p, _verts_k = _c_double_ptr(verts)
    faces_p, _faces_k = _c_long_ptr(faces)
    lengths_p, _lengths_k = _c_double_ptr(lengths)
    counts_p, _counts_k = _c_long_ptr(counts)
    aspect_p, _aspect_k = _c_double_ptr(aspect)

    _lib.surface_edge_lengths_stats_batch(
        verts_p,
        ctypes.c_int(verts.shape[0]),
        faces_p,
        ctypes.c_int(n_faces),
        lengths_p,
        counts_p,
        aspect_p,
    )
    n_unique = int(_counts_k[0])
    if n_unique < 0:
        return None
    return _lengths_k, n_unique, float(_aspect_k[0]), float(_aspect_k[1])


def surface_unique_edge_length_stats_batch(
    verts: np.ndarray,
    faces: np.ndarray,
) -> Optional[tuple[int, float, float, float, float]]:
    """Return unique surface edge count and length min/max/p01/p99."""
    if _lib is None:
        return None
    verts = np.ascontiguousarray(verts, dtype=np.float64)
    faces = np.ascontiguousarray(faces, dtype=np.int64)
    counts = np.zeros(1, dtype=np.int64)
    stats = np.zeros(4, dtype=np.float64)

    verts_p, _verts_k = _c_double_ptr(verts)
    faces_p, _faces_k = _c_long_ptr(faces)
    counts_p, _counts_k = _c_long_ptr(counts)
    stats_p, _stats_k = _c_double_ptr(stats)

    _lib.surface_unique_edge_length_stats_batch(
        verts_p,
        ctypes.c_int(verts.shape[0]),
        faces_p,
        ctypes.c_int(faces.shape[0]),
        counts_p,
        stats_p,
    )
    n_unique = int(_counts_k[0])
    if n_unique < 0:
        return None
    return (
        n_unique,
        float(_stats_k[0]),
        float(_stats_k[1]),
        float(_stats_k[2]),
        float(_stats_k[3]),
    )


def surface_vertex_gaussian_curvature_batch(
    verts: np.ndarray,
    faces: np.ndarray,
) -> Optional[tuple[np.ndarray, tuple[float, float, float, float]]]:
    """Return vertex Gaussian curvature and aggregate stats."""
    if _lib is None:
        return None
    verts = np.ascontiguousarray(verts, dtype=np.float64)
    faces = np.ascontiguousarray(faces, dtype=np.int64)
    k = np.empty(verts.shape[0], dtype=np.float64)
    stats = np.zeros(4, dtype=np.float64)

    verts_p, _verts_k = _c_double_ptr(verts)
    faces_p, _faces_k = _c_long_ptr(faces)
    k_p, _k_k = _c_double_ptr(k)
    stats_p, _stats_k = _c_double_ptr(stats)

    _lib.surface_vertex_gaussian_curvature_batch(
        verts_p,
        ctypes.c_int(verts.shape[0]),
        faces_p,
        ctypes.c_int(faces.shape[0]),
        k_p,
        stats_p,
    )
    return _k_k, (
        float(_stats_k[0]),
        float(_stats_k[1]),
        float(_stats_k[2]),
        float(_stats_k[3]),
    )


def surface_vertex_mean_curvature_batch(
    verts: np.ndarray,
    faces: np.ndarray,
) -> Optional[tuple[np.ndarray, tuple[float, float, float, float]]]:
    """Return vertex mean curvature vectors and aggregate norm stats."""
    if _lib is None:
        return None
    verts = np.ascontiguousarray(verts, dtype=np.float64)
    faces = np.ascontiguousarray(faces, dtype=np.int64)
    h = np.empty((verts.shape[0], 3), dtype=np.float64)
    stats = np.zeros(4, dtype=np.float64)

    verts_p, _verts_k = _c_double_ptr(verts)
    faces_p, _faces_k = _c_long_ptr(faces)
    h_p, _h_k = _c_double_ptr(h)
    stats_p, _stats_k = _c_double_ptr(stats)

    _lib.surface_vertex_mean_curvature_batch(
        verts_p,
        ctypes.c_int(verts.shape[0]),
        faces_p,
        ctypes.c_int(faces.shape[0]),
        h_p,
        stats_p,
    )
    if float(_stats_k[0]) < 0.0:
        return None
    return _h_k.reshape(verts.shape[0], 3), (
        float(_stats_k[0]),
        float(_stats_k[1]),
        float(_stats_k[2]),
        float(_stats_k[3]),
    )


def surface_feature_edges_stats_batch(
    verts: np.ndarray,
    faces: np.ndarray,
    cos_threshold: float,
) -> Optional[tuple[int, int, int, int]]:
    """Return feature edge aggregate counts, or None if native path fails."""
    if _lib is None:
        return None
    verts = np.ascontiguousarray(verts, dtype=np.float64)
    faces = np.ascontiguousarray(faces, dtype=np.int64)
    stats = np.zeros(4, dtype=np.int64)

    verts_p, _verts_k = _c_double_ptr(verts)
    faces_p, _faces_k = _c_long_ptr(faces)
    stats_p, _stats_k = _c_long_ptr(stats)

    _lib.surface_feature_edges_stats_batch(
        verts_p,
        ctypes.c_int(verts.shape[0]),
        faces_p,
        ctypes.c_int(faces.shape[0]),
        ctypes.c_double(float(cos_threshold)),
        stats_p,
    )
    if int(_stats_k[0]) < 0:
        return None
    return (
        int(_stats_k[0]),
        int(_stats_k[1]),
        int(_stats_k[2]),
        int(_stats_k[3]),
    )


def surface_feature_report_stats_batch(
    verts: np.ndarray,
    faces: np.ndarray,
    cos_threshold: float,
) -> Optional[tuple[tuple[int, int, int, int, int], tuple[float, float, float, float]]]:
    """Return fused feature_report edge counts and length statistics."""
    if _lib is None:
        return None
    verts = np.ascontiguousarray(verts, dtype=np.float64)
    faces = np.ascontiguousarray(faces, dtype=np.int64)
    counts = np.zeros(5, dtype=np.int64)
    length_stats = np.zeros(4, dtype=np.float64)

    verts_p, _verts_k = _c_double_ptr(verts)
    faces_p, _faces_k = _c_long_ptr(faces)
    counts_p, _counts_k = _c_long_ptr(counts)
    length_stats_p, _length_stats_k = _c_double_ptr(length_stats)

    _lib.surface_feature_report_stats_batch(
        verts_p,
        ctypes.c_int(verts.shape[0]),
        faces_p,
        ctypes.c_int(faces.shape[0]),
        ctypes.c_double(float(cos_threshold)),
        counts_p,
        length_stats_p,
    )
    if int(_counts_k[0]) < 0:
        return None
    return (
        (
            int(_counts_k[0]),
            int(_counts_k[1]),
            int(_counts_k[2]),
            int(_counts_k[3]),
            int(_counts_k[4]),
        ),
        (
            float(_length_stats_k[0]),
            float(_length_stats_k[1]),
            float(_length_stats_k[2]),
            float(_length_stats_k[3]),
        ),
    )


def surface_diag_stats_batch(
    verts: np.ndarray,
    faces: np.ndarray,
    cos_threshold: float,
    sliver_area_tol: float,
) -> Optional[tuple[tuple[int, int, int, int], tuple[float, float, float, float, float, float]]]:
    """Return fused surface diagnostic counts and aggregate stats."""
    if _lib is None:
        return None
    verts = np.ascontiguousarray(verts, dtype=np.float64)
    faces = np.ascontiguousarray(faces, dtype=np.int64)
    counts = np.zeros(4, dtype=np.int64)
    stats = np.zeros(6, dtype=np.float64)

    verts_p, _verts_k = _c_double_ptr(verts)
    faces_p, _faces_k = _c_long_ptr(faces)
    counts_p, _counts_k = _c_long_ptr(counts)
    stats_p, _stats_k = _c_double_ptr(stats)

    _lib.surface_diag_stats_batch(
        verts_p,
        ctypes.c_int(verts.shape[0]),
        faces_p,
        ctypes.c_int(faces.shape[0]),
        ctypes.c_double(float(cos_threshold)),
        ctypes.c_double(float(sliver_area_tol)),
        counts_p,
        stats_p,
    )
    if int(_counts_k[0]) < 0:
        return None
    return (
        (
            int(_counts_k[0]),
            int(_counts_k[1]),
            int(_counts_k[2]),
            int(_counts_k[3]),
        ),
        (
            float(_stats_k[0]),
            float(_stats_k[1]),
            float(_stats_k[2]),
            float(_stats_k[3]),
            float(_stats_k[4]),
            float(_stats_k[5]),
        ),
    )


def surface_dihedral_histogram_batch(
    verts: np.ndarray,
    faces: np.ndarray,
    bin_edges_deg: np.ndarray,
) -> Optional[tuple[np.ndarray, tuple[int, float, float, float]]]:
    """Return histogram counts and angle aggregate stats for internal edges."""
    if _lib is None:
        return None
    verts = np.ascontiguousarray(verts, dtype=np.float64)
    faces = np.ascontiguousarray(faces, dtype=np.int64)
    bins = np.ascontiguousarray(bin_edges_deg, dtype=np.float64)
    if bins.size < 2:
        return None
    counts = np.zeros(bins.size - 1, dtype=np.int64)
    meta = np.zeros(1, dtype=np.int64)
    stats = np.zeros(3, dtype=np.float64)

    verts_p, _verts_k = _c_double_ptr(verts)
    faces_p, _faces_k = _c_long_ptr(faces)
    bins_p, _bins_k = _c_double_ptr(bins)
    counts_p, _counts_k = _c_long_ptr(counts)
    meta_p, _meta_k = _c_long_ptr(meta)
    stats_p, _stats_k = _c_double_ptr(stats)

    _lib.surface_dihedral_histogram_batch(
        verts_p,
        ctypes.c_int(verts.shape[0]),
        faces_p,
        ctypes.c_int(faces.shape[0]),
        bins_p,
        ctypes.c_int(bins.size),
        counts_p,
        meta_p,
        stats_p,
    )
    n_internal = int(_meta_k[0])
    if n_internal < 0:
        return None
    return _counts_k.copy(), (
        n_internal,
        float(_stats_k[0]),
        float(_stats_k[1]),
        float(_stats_k[2]),
    )


def surface_remove_degenerate_faces_mask(
    verts: np.ndarray,
    faces: np.ndarray,
    area_tol: float,
) -> Optional[tuple[np.ndarray, int]]:
    """Return keep mask and removed count for degenerate/duplicate faces."""
    if _lib is None:
        return None
    verts = np.ascontiguousarray(verts, dtype=np.float64)
    faces = np.ascontiguousarray(faces, dtype=np.int64)
    n_faces = faces.shape[0]
    keep = np.empty(n_faces, dtype=np.int64)
    counts = np.zeros(1, dtype=np.int64)

    verts_p, _verts_k = _c_double_ptr(verts)
    faces_p, _faces_k = _c_long_ptr(faces)
    keep_p, _keep_k = _c_long_ptr(keep)
    counts_p, _counts_k = _c_long_ptr(counts)

    _lib.surface_remove_degenerate_faces_mask(
        verts_p,
        ctypes.c_int(verts.shape[0]),
        faces_p,
        ctypes.c_int(n_faces),
        ctypes.c_double(float(area_tol)),
        keep_p,
        counts_p,
    )
    n_removed = int(_counts_k[0])
    if n_removed < 0:
        return None
    return _keep_k.astype(bool, copy=False), n_removed


def surface_dedup_vertices_quantized(
    verts: np.ndarray,
    faces: np.ndarray,
    tol: float,
) -> Optional[tuple[np.ndarray, np.ndarray, int]]:
    """Return quantized unique vertices, remapped faces, and merge count."""
    if _lib is None:
        return None
    verts = np.ascontiguousarray(verts, dtype=np.float64)
    faces = np.ascontiguousarray(faces, dtype=np.int64)
    new_verts = np.empty_like(verts)
    new_faces = np.empty_like(faces)
    counts = np.zeros(2, dtype=np.int64)

    verts_p, _verts_k = _c_double_ptr(verts)
    faces_p, _faces_k = _c_long_ptr(faces)
    new_verts_p, _new_verts_k = _c_double_ptr(new_verts)
    new_faces_p, _new_faces_k = _c_long_ptr(new_faces)
    counts_p, _counts_k = _c_long_ptr(counts)

    _lib.surface_dedup_vertices_quantized(
        verts_p,
        ctypes.c_int(verts.shape[0]),
        faces_p,
        ctypes.c_int(faces.shape[0]),
        ctypes.c_double(float(tol)),
        new_verts_p,
        new_faces_p,
        counts_p,
    )
    n_unique = int(_counts_k[0])
    if n_unique < 0:
        return None
    return (
        _new_verts_k.reshape(verts.shape)[:n_unique].copy(),
        _new_faces_k.reshape(faces.shape).copy(),
        int(_counts_k[1]),
    )


def surface_area_volume_stats_batch(
    verts: np.ndarray,
    faces: np.ndarray,
) -> Optional[tuple[float, float, float]]:
    """Return surface area, signed volume, and bbox volume."""
    if _lib is None:
        return None
    verts = np.ascontiguousarray(verts, dtype=np.float64)
    faces = np.ascontiguousarray(faces, dtype=np.int64)
    stats = np.zeros(3, dtype=np.float64)

    verts_p, _verts_k = _c_double_ptr(verts)
    faces_p, _faces_k = _c_long_ptr(faces)
    stats_p, _stats_k = _c_double_ptr(stats)

    _lib.surface_area_volume_stats_batch(
        verts_p,
        ctypes.c_int(verts.shape[0]),
        faces_p,
        ctypes.c_int(faces.shape[0]),
        stats_p,
    )
    return float(_stats_k[0]), float(_stats_k[1]), float(_stats_k[2])


def surface_face_area_distribution_stats_batch(
    verts: np.ndarray,
    faces: np.ndarray,
) -> Optional[tuple[float, float, float, float, float, float]]:
    """Return triangle area min/max/mean/std/p01/p99."""
    if _lib is None:
        return None
    verts = np.ascontiguousarray(verts, dtype=np.float64)
    faces = np.ascontiguousarray(faces, dtype=np.int64)
    stats = np.zeros(6, dtype=np.float64)

    verts_p, _verts_k = _c_double_ptr(verts)
    faces_p, _faces_k = _c_long_ptr(faces)
    stats_p, _stats_k = _c_double_ptr(stats)

    _lib.surface_face_area_distribution_stats_batch(
        verts_p,
        ctypes.c_int(verts.shape[0]),
        faces_p,
        ctypes.c_int(faces.shape[0]),
        stats_p,
    )
    if float(_stats_k[0]) < 0.0:
        return None
    return (
        float(_stats_k[0]),
        float(_stats_k[1]),
        float(_stats_k[2]),
        float(_stats_k[3]),
        float(_stats_k[4]),
        float(_stats_k[5]),
    )


def build_face_to_tets(
    tets: np.ndarray,
) -> Optional[tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """Return (faces, tet_idx, slot) arrays, each length n_tets*4, or None."""
    if _lib is None:
        return None
    tets = np.ascontiguousarray(tets, dtype=np.int64)
    n_tets  = tets.shape[0]
    n_faces = n_tets * 4

    faces   = np.empty((n_faces, 3), dtype=np.int64)
    tet_idx = np.empty(n_faces,      dtype=np.int64)
    slot    = np.empty(n_faces,      dtype=np.int64)

    tets_p, _tets_k = _c_long_ptr(tets)
    f_p,    _f_k    = _c_long_ptr(faces)
    ti_p,   _ti_k   = _c_long_ptr(tet_idx)
    sl_p,   _sl_k   = _c_long_ptr(slot)

    ret = _lib.build_face_to_tets(
        tets_p, ctypes.c_int(n_tets),
        f_p, ti_p, sl_p,
        ctypes.c_int(n_faces),
    )
    if ret < 0:
        return None
    return _f_k[:ret], _ti_k[:ret], _sl_k[:ret]


def build_edge_to_tets(
    tets: np.ndarray,
) -> Optional[tuple[np.ndarray, np.ndarray]]:
    """Return (edges, tet_idx) arrays, each length n_tets*6, or None."""
    if _lib is None:
        return None
    tets = np.ascontiguousarray(tets, dtype=np.int64)
    n_tets  = tets.shape[0]
    n_edges = n_tets * 6

    edges   = np.empty((n_edges, 2), dtype=np.int64)
    tet_idx = np.empty(n_edges,      dtype=np.int64)

    tets_p, _tets_k = _c_long_ptr(tets)
    e_p,    _e_k    = _c_long_ptr(edges)
    ti_p,   _ti_k   = _c_long_ptr(tet_idx)

    ret = _lib.build_edge_to_tets(
        tets_p, ctypes.c_int(n_tets),
        e_p, ti_p,
        ctypes.c_int(n_edges),
    )
    if ret < 0:
        return None
    return _e_k[:ret], _ti_k[:ret]


def edge_lengths_batch(
    pts: np.ndarray,
    edges: np.ndarray,
) -> Optional[np.ndarray]:
    """Return length array shape (n_edges,), or None if C unavailable."""
    if _lib is None:
        return None
    pts   = np.ascontiguousarray(pts,   dtype=np.float64)
    edges = np.ascontiguousarray(edges, dtype=np.int64)
    n_edges = edges.shape[0]
    out = np.empty(n_edges, dtype=np.float64)

    pts_p,  _pts_k  = _c_double_ptr(pts)
    e_p,    _e_k    = _c_long_ptr(edges)
    out_p,  _out_k  = _c_double_ptr(out)

    _lib.edge_lengths_batch(
        pts_p,
        e_p, ctypes.c_int(n_edges),
        out_p,
    )
    return _out_k


def metric_edge_lengths_batch(
    pts: np.ndarray,
    tets: np.ndarray,
    M: np.ndarray,
) -> Optional[np.ndarray]:
    """Return metric-aware edge lengths shape (n_tets, 6), or None."""
    if _lib is None:
        return None
    pts = np.ascontiguousarray(pts, dtype=np.float64)
    tets = np.ascontiguousarray(tets, dtype=np.int64)
    M = np.ascontiguousarray(M, dtype=np.float64)
    n_tets = tets.shape[0]
    out = np.empty((n_tets, 6), dtype=np.float64)

    pts_p, _pts_k = _c_double_ptr(pts)
    tets_p, _tets_k = _c_long_ptr(tets)
    M_p, _M_k = _c_double_ptr(M)
    out_p, _out_k = _c_double_ptr(out)

    _lib.metric_edge_lengths_batch(
        pts_p,
        tets_p, ctypes.c_int(n_tets),
        M_p,
        out_p,
    )
    return _out_k


# Run at import time
_init()
