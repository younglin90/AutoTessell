"""Unit tests for core.layers.native_bl_vd (vertex duplication BL utilities)."""
from __future__ import annotations

import os
import json
from pathlib import Path

import numpy as np
import pytest

from core.layers.native_bl_vd import (
    build_bulk_preserving_multi_layer_full_bl_polymesh,
    build_full_bl_polymesh,
    build_gap_fill_cells,
    build_multi_layer_bl,
    build_multi_layer_full_bl_polymesh,
    build_multi_layer_gap_fill_cells,
    build_prism_cells,
    cells_to_polymesh,
    compute_face_normals,
    detect_junction_verts,
    generate_per_face_inner_verts,
)


def _single_tet_boundary() -> tuple[list[list[int]], np.ndarray, np.ndarray, np.ndarray]:
    """One tetrahedral bulk cell represented by its four boundary faces."""
    points = np.array([
        [0, 0, 0],
        [1, 0, 0],
        [0, 1, 0],
        [0, 0, 1],
    ], dtype=np.float64)
    # Outward faces for tet (0, 1, 2, 3).
    faces = [
        [1, 2, 3],
        [0, 3, 2],
        [0, 1, 3],
        [0, 2, 1],
    ]
    owner = np.array([0, 0, 0, 0], dtype=np.int64)
    neighbour = np.array([], dtype=np.int64)
    return faces, points, owner, neighbour


def _cube_faces() -> tuple[list[list[int]], np.ndarray]:
    """Unit cube as 12 triangle faces (6 quads × 2 tris each).

    Vertex layout:
      0: (0,0,0)  4: (0,0,1)
      1: (1,0,0)  5: (1,0,1)
      2: (1,1,0)  6: (1,1,1)
      3: (0,1,0)  7: (0,1,1)

    Faces have outward normals (cube interior is +).
    """
    points = np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],  # bottom z=0
        [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],  # top z=1
    ], dtype=np.float64)
    faces = [
        # bottom z=0 (normal -z)
        [0, 2, 1], [0, 3, 2],
        # top z=1 (normal +z)
        [4, 5, 6], [4, 6, 7],
        # front y=0 (normal -y)
        [0, 1, 5], [0, 5, 4],
        # back y=1 (normal +y)
        [3, 7, 6], [3, 6, 2],
        # left x=0 (normal -x)
        [0, 4, 7], [0, 7, 3],
        # right x=1 (normal +x)
        [1, 2, 6], [1, 6, 5],
    ]
    return faces, points


def _flat_strip_faces() -> tuple[list[list[int]], np.ndarray]:
    """Two coplanar triangles sharing an edge — no junction expected.

    Vertices:
      0: (0,0,0)
      1: (1,0,0)
      2: (1,1,0)
      3: (0,1,0)
    Faces:
      [0,1,2], [0,2,3]
    """
    points = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], dtype=np.float64)
    faces = [[0, 1, 2], [0, 2, 3]]
    return faces, points


def test_compute_face_normals_cube():
    faces, points = _cube_faces()
    normals = compute_face_normals(faces, points)
    assert len(normals) == 12
    # bottom faces: normal -z
    assert np.allclose(normals[0], [0, 0, -1])
    assert np.allclose(normals[1], [0, 0, -1])
    # top faces: normal +z
    assert np.allclose(normals[2], [0, 0, 1])
    assert np.allclose(normals[3], [0, 0, 1])
    # front faces (y=0): normal -y
    assert np.allclose(normals[4], [0, -1, 0])


def test_compute_face_normals_degenerate_skipped():
    points = np.array([[0, 0, 0], [1, 0, 0], [2, 0, 0]], dtype=np.float64)  # collinear
    faces = [[0, 1, 2]]
    normals = compute_face_normals(faces, points)
    assert len(normals) == 0


def test_detect_junction_verts_flat_strip_no_junctions():
    """Coplanar faces — no junction verts/edges."""
    faces, points = _flat_strip_faces()
    info = detect_junction_verts([0, 1], faces, points)
    assert info.junction_verts == set()
    assert info.junction_edges == set()
    assert len(info.face_normals) == 2


def test_detect_junction_verts_cube_all_corners_are_junctions():
    """Cube: every corner has 3 adj faces with mutually orthogonal normals.

    cos(adjacent face normals) = 0 < 0.9 threshold → all corners are junction verts.
    """
    faces, points = _cube_faces()
    info = detect_junction_verts(list(range(12)), faces, points, cos_thresh=0.9)
    # All 8 cube vertices are junction verts (3 perpendicular faces meet).
    assert info.junction_verts == set(range(8))
    # Every cube edge is a junction edge (2 perpendicular faces share each edge).
    # Cube has 12 edges; some are shared by 2 of the 12 triangles, some by 1.
    # Edges between perpendicular faces should all be junctions.
    assert len(info.junction_edges) >= 12  # at least cube edges


def test_detect_junction_verts_threshold_relaxed():
    """cos_thresh=-1.0 → no junctions (any cos > -1)."""
    faces, points = _cube_faces()
    info = detect_junction_verts(list(range(12)), faces, points, cos_thresh=-1.0)
    assert info.junction_verts == set()
    assert info.junction_edges == set()


def test_detect_junction_returns_face_normals():
    faces, points = _cube_faces()
    info = detect_junction_verts(list(range(12)), faces, points)
    assert len(info.face_normals) == 12
    # validate keys are face indices
    assert set(info.face_normals.keys()) == set(range(12))


def test_per_face_inner_verts_flat_strip_no_dup():
    """Flat strip — non-junction verts get a single shared inner vert each."""
    faces, points = _flat_strip_faces()
    info = detect_junction_verts([0, 1], faces, points, cos_thresh=0.9)
    res = generate_per_face_inner_verts(
        [0, 1], faces, points, info, thickness=0.1,
    )
    # All 4 verts shared inner: 1 inner per vert = 4 dup verts (no junctions).
    assert res.n_dup_verts == 4
    # Each (face, vert) maps to the shared inner for that vert.
    inner_for_v0 = res.face_inner_vert[(0, 0)]
    assert res.face_inner_vert[(1, 0)] == inner_for_v0  # same vert v=0, both faces share
    inner_for_v2 = res.face_inner_vert[(0, 2)]
    assert res.face_inner_vert[(1, 2)] == inner_for_v2
    # Inner pt = orig + (-z) × thickness = (x, y, -0.1).
    inner_pt_v0 = res.new_points[inner_for_v0]
    assert np.isclose(inner_pt_v0[2], -0.1, atol=1e-6)


def test_per_face_inner_verts_cube_corners_get_3_dup_each():
    """Cube — each corner has 3 perpendicular faces → 3 clusters → 3 dup verts.

    Total dup verts = 8 corners × 3 = 24 (junction case), since cube has no
    non-junction verts (all corners are at 3-face junction).
    """
    faces, points = _cube_faces()
    info = detect_junction_verts(list(range(12)), faces, points, cos_thresh=0.9)
    res = generate_per_face_inner_verts(
        list(range(12)), faces, points, info, thickness=0.1, cluster_cos=0.5,
    )
    # 8 verts × 3 perpendicular face normals → 3 clusters per vert (no merging
    # at cluster_cos=0.5 since perpendicular cos=0 < 0.5).
    assert res.n_dup_verts == 8 * 3
    # Each (face, vert) MUST be in the mapping (every face uses dup for its vert).
    for fi, f in enumerate(faces):
        for v in f:
            assert (fi, v) in res.face_inner_vert
    # Adjacent perpendicular faces at vert 0 (e.g. bottom face 0 and front face 4)
    # should map vert 0 to DIFFERENT inner verts (not shared).
    inner_bottom = res.face_inner_vert[(0, 0)]  # bottom (normal -z)
    inner_front = res.face_inner_vert[(4, 0)]   # front (normal -y)
    assert inner_bottom != inner_front
    # Inner pt for bottom face at vert 0: (0,0,0) - (-z) × 0.1 = (0,0,0.1)?
    # Wait — outward normal -z, so inward is +z, but our convention:
    # inner_pt = points[v] - cmean × thickness, where cmean is face_normal.
    # face_normal for bottom = -z, so inner_pt = (0,0,0) - (-z)×0.1 = (0,0,+0.1)
    inner_pt_bot = res.new_points[inner_bottom]
    assert np.isclose(inner_pt_bot[2], 0.1, atol=1e-6)
    # Front (normal -y) at v=0: inner_pt = (0,0,0) - (-y)×0.1 = (0,+0.1,0)
    inner_pt_front = res.new_points[inner_front]
    assert np.isclose(inner_pt_front[1], 0.1, atol=1e-6)


def test_per_face_inner_verts_cube_relaxed_cluster_merges_all_3():
    """When cluster_cos = -1.0, all face normals at corner merge → 1 cluster."""
    faces, points = _cube_faces()
    info = detect_junction_verts(list(range(12)), faces, points, cos_thresh=0.9)
    res = generate_per_face_inner_verts(
        list(range(12)), faces, points, info, thickness=0.1, cluster_cos=-1.0,
    )
    # 8 verts × 1 cluster = 8 dup (one per corner).
    assert res.n_dup_verts == 8
    # All 3 faces at vert 0 should now share the same inner vert.
    inner_bottom = res.face_inner_vert[(0, 0)]
    inner_front = res.face_inner_vert[(4, 0)]
    inner_left = res.face_inner_vert[(8, 0)]
    assert inner_bottom == inner_front == inner_left


def test_per_face_inner_verts_preserves_original_points():
    """Original points must NOT be modified — only appended."""
    faces, points = _flat_strip_faces()
    info = detect_junction_verts([0, 1], faces, points)
    res = generate_per_face_inner_verts(
        [0, 1], faces, points, info, thickness=0.1,
    )
    # First N rows of new_points must equal original points.
    assert np.allclose(res.new_points[: len(points)], points)
    # Total length = orig + dup.
    assert len(res.new_points) == len(points) + res.n_dup_verts


def test_build_prism_cells_flat_strip():
    """Flat strip — 2 prism cells, 5 faces each, sharing nothing yet."""
    faces, points = _flat_strip_faces()
    info = detect_junction_verts([0, 1], faces, points)
    inner = generate_per_face_inner_verts([0, 1], faces, points, info, thickness=0.1)
    prisms = build_prism_cells([0, 1], faces, inner)
    assert len(prisms.cell_face_verts) == 2
    # Each prism has 5 faces.
    for cf in prisms.cell_face_verts:
        assert len(cf) == 5
        # 2 tris + 3 quads.
        n_tri = sum(1 for f in cf if len(f) == 3)
        n_quad = sum(1 for f in cf if len(f) == 4)
        assert n_tri == 2
        assert n_quad == 3
    # cell_to_wall_face mapping correct
    assert prisms.cell_to_wall_face == [0, 1]


def test_build_prism_cells_cube():
    """Cube — 12 prism cells (one per wall triangle)."""
    faces, points = _cube_faces()
    info = detect_junction_verts(list(range(12)), faces, points, cos_thresh=0.9)
    inner = generate_per_face_inner_verts(
        list(range(12)), faces, points, info, thickness=0.1, cluster_cos=0.5,
    )
    prisms = build_prism_cells(list(range(12)), faces, inner)
    assert len(prisms.cell_face_verts) == 12
    # Each prism: 2 tris + 3 quads.
    for cf in prisms.cell_face_verts:
        n_tri = sum(1 for f in cf if len(f) == 3)
        n_quad = sum(1 for f in cf if len(f) == 4)
        assert n_tri == 2 and n_quad == 3
    # Bottom face (index 0) of prism 0 = original wall face 0 verts.
    bottom_p0 = prisms.cell_face_verts[0][0]
    assert bottom_p0 == faces[0]


def test_build_prism_cells_rejects_non_triangle():
    """Wall face with 4 verts → raises ValueError."""
    points = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], dtype=np.float64)
    faces = [[0, 1, 2, 3]]  # quad wall face
    # We can't run detect_junction_verts on a quad (it expects tri) but
    # build_prism_cells should reject early.
    info = detect_junction_verts([0], faces, points)
    inner = generate_per_face_inner_verts([0], faces, points, info, thickness=0.1)
    try:
        build_prism_cells([0], faces, inner)
        raise AssertionError("Expected ValueError for non-triangle wall face")
    except ValueError as e:
        assert "triangle" in str(e).lower()


def test_cells_to_polymesh_single_prism():
    """Single prism — 5 boundary faces, 0 internal, all patches present."""
    faces, points = _flat_strip_faces()
    info = detect_junction_verts([0], faces, points)
    inner = generate_per_face_inner_verts([0], faces, points, info, thickness=0.1)
    prisms = build_prism_cells([0], faces, inner)
    pm = cells_to_polymesh(prisms.cell_face_verts, inner.new_points)

    assert len(pm.faces) == 5
    assert len(pm.owner) == 5
    assert len(pm.neighbour) == 0  # no internal
    # Owner is always cell 0.
    assert all(o == 0 for o in pm.owner)
    # Patches: wall=1, bl_internal=1, bl_internal_side=3.
    by_name = {p["name"]: p for p in pm.patches}
    assert by_name["wall"]["nFaces"] == 1
    assert by_name["bl_internal"]["nFaces"] == 1
    assert by_name["bl_internal_side"]["nFaces"] == 3
    # Patch ordering wall → bl_internal → bl_internal_side.
    names = [p["name"] for p in pm.patches]
    assert names == ["wall", "bl_internal", "bl_internal_side"]
    # startFace contiguous: wall starts at 0, bl_internal at 1, side at 2.
    assert by_name["wall"]["startFace"] == 0
    assert by_name["bl_internal"]["startFace"] == 1
    assert by_name["bl_internal_side"]["startFace"] == 2


def test_cells_to_polymesh_flat_strip_one_internal():
    """Flat strip (2 prisms, no junctions) — 1 internal side quad shared."""
    faces, points = _flat_strip_faces()
    info = detect_junction_verts([0, 1], faces, points)
    inner = generate_per_face_inner_verts([0, 1], faces, points, info, thickness=0.1)
    prisms = build_prism_cells([0, 1], faces, inner)
    pm = cells_to_polymesh(prisms.cell_face_verts, inner.new_points)

    # Internal face count: 1 (the diagonal side quad shared by both prisms).
    assert len(pm.neighbour) == 1
    # Internal face is a quad (4 verts), not a triangle.
    internal_face = pm.faces[0]
    assert len(internal_face) == 4
    # Owner = cell 0 (lower id), neighbour = cell 1.
    assert pm.owner[0] == 0
    assert pm.neighbour[0] == 1

    # Boundary faces: 2 prisms × 5 - 2 (the shared quad counted twice) = 8.
    n_boundary = len(pm.faces) - 1
    assert n_boundary == 8

    by_name = {p["name"]: p for p in pm.patches}
    assert by_name["wall"]["nFaces"] == 2  # bottom of each prism
    assert by_name["bl_internal"]["nFaces"] == 2  # top of each prism
    # Side quads: 3 per prism × 2 prisms - 2 (the shared one counted twice) = 4.
    assert by_name["bl_internal_side"]["nFaces"] == 4

    # Patch startFace continuous after internal section.
    assert by_name["wall"]["startFace"] == 1
    assert by_name["bl_internal"]["startFace"] == 1 + 2
    assert by_name["bl_internal_side"]["startFace"] == 1 + 2 + 2


def test_cells_to_polymesh_internal_sorted_by_owner_neighbour():
    """Internal faces are emitted sorted by (owner, neighbour)."""
    # Construct 3 cells where each pair shares a face.
    # Cell 0: faces {A, B, C, X}; Cell 1: faces {D, E, F, X, Y}; Cell 2: {G, Y, Z, ...}
    # X shared by cells 0&1, Y by cells 1&2 → expected order [(0,1,X),(1,2,Y)].
    cell_face_verts = [
        [
            [0, 1, 2],          # A bottom
            [10, 12, 11],       # B top
            [0, 1, 11, 10],     # C side
            [1, 2, 12, 11],     # X side (shared with cell 1)
        ],
        [
            [2, 5, 4],          # D bottom
            [12, 14, 15],       # E top
            [2, 5, 15, 14],     # F side
            [1, 2, 12, 11],     # X (shared with cell 0; same set as above)
            [5, 4, 16, 15],     # Y side (shared with cell 2)
        ],
        [
            [4, 7, 8],          # G bottom
            [14, 18, 17],       # cap
            [4, 7, 17, 16],     # side
            [5, 4, 16, 15],     # Y (shared with cell 1; same set)
            [7, 8, 18, 17],     # side
        ],
    ]
    points = np.zeros((20, 3), dtype=np.float64)
    pm = cells_to_polymesh(cell_face_verts, points)
    # 2 internal faces (X, Y).
    assert len(pm.neighbour) == 2
    # Order sorted by (owner, neighbour) → [(0,1), (1,2)].
    assert pm.owner[:2] == [0, 1]
    assert pm.neighbour == [1, 2]


def test_cells_to_polymesh_rejects_three_way_share():
    """Face shared by 3+ cells → ValueError (non-manifold)."""
    shared_face = [0, 1, 2]
    cell_face_verts = [
        [shared_face, [3, 4, 5]],
        [shared_face, [6, 7, 8]],
        [shared_face, [9, 10, 11]],
    ]
    points = np.zeros((12, 3), dtype=np.float64)
    try:
        cells_to_polymesh(cell_face_verts, points)
        raise AssertionError("Expected ValueError for 3-way shared face")
    except ValueError as e:
        msg = str(e).lower()
        assert "non-manifold" in msg or "3" in msg


def test_cells_to_polymesh_owner_winding_from_lower_cell():
    """Owner cell winding is preserved; neighbour cell's reversed copy ignored.

    Two cells share a face. Cell 0 has it as [1, 2, 3]; cell 1 has [3, 2, 1].
    Stored face must be [1, 2, 3] (owner=cell 0).
    """
    cell_face_verts = [
        [
            [0, 4, 5],       # padding face (unique)
            [1, 2, 3],       # shared, owner winding
        ],
        [
            [3, 2, 1],       # same face reversed (neighbour winding)
            [6, 7, 8],       # padding (unique)
        ],
    ]
    points = np.zeros((10, 3), dtype=np.float64)
    pm = cells_to_polymesh(cell_face_verts, points)
    assert len(pm.neighbour) == 1
    # First face is internal — verify winding matches owner cell 0.
    assert pm.faces[0] == [1, 2, 3]
    assert pm.owner[0] == 0
    assert pm.neighbour[0] == 1


def test_cells_to_polymesh_cube_internal_diagonals():
    """Cube — 12 prisms.

    With cluster_cos=0.5, two coplanar triangles on each cube face cluster
    together (cos=1 ≥ 0.5), so they share inner verts on the diagonal edge.
    That produces 1 shared side quad per cube face → 6 internal faces total.
    """
    faces, points = _cube_faces()
    info = detect_junction_verts(list(range(12)), faces, points, cos_thresh=0.9)
    inner = generate_per_face_inner_verts(
        list(range(12)), faces, points, info, thickness=0.1, cluster_cos=0.5,
    )
    prisms = build_prism_cells(list(range(12)), faces, inner)
    pm = cells_to_polymesh(prisms.cell_face_verts, inner.new_points)

    # 12 prisms × 5 faces = 60 occurrences. 6 internal pairs → 6 unique internal
    # faces and 60-12=48 boundary faces. Total unique = 54.
    assert len(pm.neighbour) == 6
    assert len(pm.faces) == 54
    by_name = {p["name"]: p for p in pm.patches}
    assert by_name["wall"]["nFaces"] == 12
    assert by_name["bl_internal"]["nFaces"] == 12
    # 12 prisms × 3 sides = 36 side occurrences. 6 internal pairs → 12 of those
    # are internal occurrences. Boundary side faces = 36 - 12 = 24.
    assert by_name["bl_internal_side"]["nFaces"] == 24
    # Owner array length matches faces; neighbour only first 6.
    assert len(pm.owner) == 54
    # All internal faces have owner < neighbour.
    for o, n in zip(pm.owner[:6], pm.neighbour, strict=True):
        assert o < n


def test_build_gap_fill_cells_flat_strip_no_junctions():
    """Flat strip — both face normals coplanar → no junction edges → no gap fill."""
    faces, points = _flat_strip_faces()
    info = detect_junction_verts([0, 1], faces, points)
    inner = generate_per_face_inner_verts([0, 1], faces, points, info, thickness=0.1)
    gap = build_gap_fill_cells([0, 1], faces, points, inner)
    assert gap.cell_face_verts == []
    assert gap.junction_edges == []


def test_build_gap_fill_cells_cube_perpendicular_edges():
    """Cube with cluster_cos=0.5 — 12 cube edges are junctions, 6 face diagonals are not.

    Each junction edge produces 2 tetrahedra → 24 gap-fill cells total.
    The 6 face diagonals connect coplanar tris (same cluster) so vi1==vi2 and
    wi1==wi2, ruling them out as junction edges.
    """
    faces, points = _cube_faces()
    info = detect_junction_verts(list(range(12)), faces, points, cos_thresh=0.9)
    inner = generate_per_face_inner_verts(
        list(range(12)), faces, points, info, thickness=0.1, cluster_cos=0.5,
    )
    gap = build_gap_fill_cells(list(range(12)), faces, points, inner)

    assert len(gap.junction_edges) == 12
    assert len(gap.cell_face_verts) == 24
    # Each gap-fill cell is a tetrahedron: 4 triangle faces.
    for cell in gap.cell_face_verts:
        assert len(cell) == 4
        for face in cell:
            assert len(face) == 3
    # Junction edges are exactly the 12 cube edges (ordered with v < w).
    expected_cube_edges = {
        (0, 1), (0, 3), (0, 4),
        (1, 2), (1, 5),
        (2, 3), (2, 6),
        (3, 7),
        (4, 5), (4, 7),
        (5, 6),
        (6, 7),
    }
    assert set(gap.junction_edges) == expected_cube_edges


def test_build_gap_fill_cells_cube_relaxed_cluster_no_junctions():
    """cluster_cos=-1.0 collapses every corner to one inner vert → no junction edges."""
    faces, points = _cube_faces()
    info = detect_junction_verts(list(range(12)), faces, points, cos_thresh=0.9)
    inner = generate_per_face_inner_verts(
        list(range(12)), faces, points, info, thickness=0.1, cluster_cos=-1.0,
    )
    gap = build_gap_fill_cells(list(range(12)), faces, points, inner)
    assert gap.cell_face_verts == []
    assert gap.junction_edges == []


def test_build_gap_fill_cells_three_way_edge_raises():
    """3 wall faces sharing one edge → NotImplementedError."""
    points = np.array([
        [0, 0, 0], [1, 0, 0],         # shared edge endpoints
        [0, 1, 0], [0, 0, 1], [-1, 0, 0],
    ], dtype=np.float64)
    faces = [
        [0, 1, 2],
        [0, 1, 3],
        [0, 1, 4],
    ]
    info = detect_junction_verts([0, 1, 2], faces, points)
    inner = generate_per_face_inner_verts([0, 1, 2], faces, points, info, thickness=0.1)
    try:
        build_gap_fill_cells([0, 1, 2], faces, points, inner)
        raise AssertionError("Expected NotImplementedError for 3-way edge")
    except NotImplementedError as e:
        msg = str(e).lower()
        assert "3+" in msg or "fan" in msg


def test_build_gap_fill_cells_tent_one_junction_edge():
    """Two triangles meeting at 90° along a shared edge → 1 junction edge → 2 tets."""
    # Edge (0, 1) on the x-axis. Tri f0 in xy plane (normal +z),
    # tri f1 in xz plane (normal -y). They share edge (0, 1).
    points = np.array([
        [0, 0, 0],   # 0 — shared endpoint
        [1, 0, 0],   # 1 — shared endpoint
        [0, 1, 0],   # 2 — apex of f0 (+y)
        [0, 0, 1],   # 3 — apex of f1 (+z)
    ], dtype=np.float64)
    faces = [
        [0, 1, 2],   # normal +z
        [1, 0, 3],   # normal +y → wait let's recompute
    ]
    # cross(p1-p0, p2-p0) for f0 = cross((1,0,0), (0,1,0)) = (0,0,1) → +z OK
    # for f1 [1,0,3]: cross((0-1,0,0), (0-1,0,1)) = cross((-1,0,0),(-1,0,1))
    #   = (0*1 - 0*0, 0*(-1) - (-1)*1, (-1)*0 - 0*(-1)) = (0, 1, 0) → +y
    # So normals are +z (f0) and +y (f1), perpendicular → junction edge (0,1).
    info = detect_junction_verts([0, 1], faces, points, cos_thresh=0.9)
    inner = generate_per_face_inner_verts(
        [0, 1], faces, points, info, thickness=0.1, cluster_cos=0.5,
    )
    gap = build_gap_fill_cells([0, 1], faces, points, inner)
    assert gap.junction_edges == [(0, 1)]
    assert len(gap.cell_face_verts) == 2
    # Each tet contains v=0 and w=1 in every cell's vertex set.
    for cell in gap.cell_face_verts:
        cell_verts = set()
        for face in cell:
            cell_verts.update(face)
        assert {0, 1}.issubset(cell_verts)


def test_build_gap_fill_cells_returns_tet_face_verts_consistent():
    """Each gap-fill cell's 4 triangles cover exactly 4 distinct verts (a tet)."""
    faces, points = _cube_faces()
    info = detect_junction_verts(list(range(12)), faces, points, cos_thresh=0.9)
    inner = generate_per_face_inner_verts(
        list(range(12)), faces, points, info, thickness=0.1, cluster_cos=0.5,
    )
    gap = build_gap_fill_cells(list(range(12)), faces, points, inner)
    for cell in gap.cell_face_verts:
        verts = set()
        for face in cell:
            verts.update(face)
        # A tetrahedron has 4 distinct vertices.
        assert len(verts) == 4
        # Each vertex appears in exactly 3 of the 4 triangles.
        for v in verts:
            count = sum(1 for face in cell if v in face)
            assert count == 3


def test_cells_to_polymesh_gap_fill_kind_routes_to_side_patch():
    """cell_kinds='gap_fill' classifies every face as bl_internal_side."""
    # One isolated tet (4 triangle faces) labelled gap_fill.
    cell_face_verts = [[
        [0, 1, 2],
        [0, 2, 3],
        [0, 3, 1],
        [1, 3, 2],
    ]]
    points = np.zeros((4, 3), dtype=np.float64)
    pm = cells_to_polymesh(cell_face_verts, points, cell_kinds=["gap_fill"])
    assert len(pm.faces) == 4
    by_name = {p["name"]: p for p in pm.patches}
    # Even face_idx 0/1 must NOT route to wall/bl_internal for gap_fill cells.
    assert "wall" not in by_name
    assert "bl_internal" not in by_name
    assert by_name["bl_internal_side"]["nFaces"] == 4


def test_cells_to_polymesh_cell_kinds_length_mismatch_raises():
    cell_face_verts = [[[0, 1, 2]]]
    points = np.zeros((3, 3), dtype=np.float64)
    try:
        cells_to_polymesh(cell_face_verts, points, cell_kinds=["prism", "gap_fill"])
        raise AssertionError("Expected ValueError for length mismatch")
    except ValueError as e:
        assert "cell_kinds" in str(e)


def test_build_full_bl_polymesh_flat_strip_no_gap():
    """Flat strip — 2 prisms, no junctions, 0 gap-fill cells.

    After triangulating side quads canonically, the shared diagonal side
    becomes 2 internal triangle pairs (instead of 1 internal quad).
    """
    faces, points = _flat_strip_faces()
    info = detect_junction_verts([0, 1], faces, points)
    inner = generate_per_face_inner_verts([0, 1], faces, points, info, thickness=0.1)
    result = build_full_bl_polymesh([0, 1], faces, points, inner)

    assert result.n_prism_cells == 2
    assert result.n_gap_fill_cells == 0
    assert result.junction_edges == []

    pm = result.polymesh
    # Every face is now a triangle (prism quads triangulated, no quads remain).
    for f in pm.faces:
        assert len(f) == 3
    # 2 internal faces from the canonical split of the shared side quad.
    assert len(pm.neighbour) == 2
    assert pm.owner[:2] == [0, 0]
    assert pm.neighbour == [1, 1]

    by_name = {p["name"]: p for p in pm.patches}
    assert by_name["wall"]["nFaces"] == 2  # bottom of each prism
    assert by_name["bl_internal"]["nFaces"] == 2  # cap of each prism
    # 2 prisms × 6 side triangles = 12; 2×2 internal occurrences => 8 boundary.
    assert by_name["bl_internal_side"]["nFaces"] == 8


def test_build_full_bl_polymesh_tent_one_junction_edge():
    """Tent (2 perpendicular tris share an edge) → 1 junction → 2 gap tets.

    Triangulated prism sides on the junction edge share with the gap-fill
    tet faces — 4 internal faces (2 per (prism, tet) pair).
    """
    points = np.array([
        [0, 0, 0],
        [1, 0, 0],
        [0, 1, 0],
        [0, 0, 1],
    ], dtype=np.float64)
    faces = [[0, 1, 2], [1, 0, 3]]
    info = detect_junction_verts([0, 1], faces, points, cos_thresh=0.9)
    inner = generate_per_face_inner_verts(
        [0, 1], faces, points, info, thickness=0.1, cluster_cos=0.5,
    )
    result = build_full_bl_polymesh([0, 1], faces, points, inner)

    assert result.n_prism_cells == 2
    assert result.n_gap_fill_cells == 2
    assert result.junction_edges == [(0, 1)]

    pm = result.polymesh
    for f in pm.faces:
        assert len(f) == 3
    # Junction edge produces 2 internal pairs per (prism, tet) match → 4 total.
    assert len(pm.neighbour) == 4

    by_name = {p["name"]: p for p in pm.patches}
    assert by_name["wall"]["nFaces"] == 2  # 1 per prism
    assert by_name["bl_internal"]["nFaces"] == 2  # 1 per prism
    # Side patch: 8 prism (non-junction edges, all boundary) + 4 tet (unmatched
    # tet triangles on the planar quad away from prism diagonal).
    assert by_name["bl_internal_side"]["nFaces"] == 12

    # Internal faces have owner < neighbour.
    for o, n in zip(pm.owner[:4], pm.neighbour, strict=True):
        assert o < n
    # Each internal pair links a prism (cell_id < 2) with a gap-fill tet
    # (cell_id ∈ {2, 3}), confirming the triangulation closes the gap.
    for o, n in zip(pm.owner[:4], pm.neighbour, strict=True):
        assert o < 2
        assert n in (2, 3)


def test_build_full_bl_polymesh_cube_no_open_prism_sides():
    """Cube — every prism side face is paired (face-diag with sibling, junction
    edge with gap-fill tet). Only boundary faces are wall, cap, and unmatched
    tet faces forming the gap-fill closure on cube edges.
    """
    faces, points = _cube_faces()
    info = detect_junction_verts(list(range(12)), faces, points, cos_thresh=0.9)
    inner = generate_per_face_inner_verts(
        list(range(12)), faces, points, info, thickness=0.1, cluster_cos=0.5,
    )
    result = build_full_bl_polymesh(list(range(12)), faces, points, inner)

    assert result.n_prism_cells == 12
    assert result.n_gap_fill_cells == 24
    assert len(result.junction_edges) == 12

    pm = result.polymesh
    for f in pm.faces:
        assert len(f) == 3

    by_name = {p["name"]: p for p in pm.patches}
    assert by_name["wall"]["nFaces"] == 12
    assert by_name["bl_internal"]["nFaces"] == 12
    # Internal: 6 face-diagonals × 2 internal triangle pairs = 12, plus 12
    # cube edges × 4 prism↔tet pairs = 48. Total 60 internal faces.
    assert len(pm.neighbour) == 60
    # Side boundary: 24 gap-fill tets × 2 unmatched faces each = 48.
    assert by_name["bl_internal_side"]["nFaces"] == 48
    assert len(pm.faces) == 132  # 60 internal + 12 wall + 12 cap + 48 side

    # Every internal face is shared between either two prisms or a prism and
    # a gap-fill tet. The latter requires owner < 12 (prism) and neighbour
    # in [12, 36) (gap-fill).
    n_prism_prism = 0
    n_prism_tet = 0
    for o, n in zip(pm.owner[:60], pm.neighbour, strict=True):
        assert o < n
        if o < 12 and n < 12:
            n_prism_prism += 1
        elif o < 12 and n >= 12:
            n_prism_tet += 1
        else:
            raise AssertionError(f"Unexpected internal owner/neighbour pair ({o}, {n})")
    assert n_prism_prism == 12
    assert n_prism_tet == 48


def test_build_full_bl_polymesh_owner_lt_neighbour_invariant():
    """All internal faces in the merged polyMesh satisfy owner < neighbour."""
    faces, points = _cube_faces()
    info = detect_junction_verts(list(range(12)), faces, points, cos_thresh=0.9)
    inner = generate_per_face_inner_verts(
        list(range(12)), faces, points, info, thickness=0.1, cluster_cos=0.5,
    )
    result = build_full_bl_polymesh(list(range(12)), faces, points, inner)
    pm = result.polymesh
    for o, n in zip(pm.owner[: len(pm.neighbour)], pm.neighbour, strict=True):
        assert o < n
    # Owner array length matches faces; neighbour only the internal section.
    assert len(pm.owner) == len(pm.faces)
    assert len(pm.neighbour) <= len(pm.owner)


def test_build_full_bl_polymesh_relaxed_cluster_no_junction_no_gap():
    """cluster_cos=-1.0 collapses every junction → no gap-fill cells, no
    junction edges; result is identical in cell count to the prism-only case
    (with triangulated side quads)."""
    faces, points = _cube_faces()
    info = detect_junction_verts(list(range(12)), faces, points, cos_thresh=0.9)
    inner = generate_per_face_inner_verts(
        list(range(12)), faces, points, info, thickness=0.1, cluster_cos=-1.0,
    )
    result = build_full_bl_polymesh(list(range(12)), faces, points, inner)

    assert result.n_prism_cells == 12
    assert result.n_gap_fill_cells == 0
    assert result.junction_edges == []
    pm = result.polymesh
    for f in pm.faces:
        assert len(f) == 3


def test_build_multi_layer_bl_n1_matches_build_prism_cells():
    """num_layers=1 must produce cells identical to build_prism_cells."""
    faces, points = _flat_strip_faces()
    info = detect_junction_verts([0, 1], faces, points)
    inner = generate_per_face_inner_verts(
        [0, 1], faces, points, info, thickness=0.1
    )
    prisms = build_prism_cells([0, 1], faces, inner)

    multi = build_multi_layer_bl(
        [0, 1], faces, points, info,
        num_layers=1, first_layer_thickness=0.1,
    )
    assert multi.num_layers == 1
    assert multi.layer_thicknesses == [0.1]
    assert multi.cell_to_wall_face == prisms.cell_to_wall_face
    assert multi.cell_to_layer == [0, 0]
    assert len(multi.cell_face_verts) == len(prisms.cell_face_verts)
    for c1, c2 in zip(multi.cell_face_verts, prisms.cell_face_verts, strict=True):
        assert c1 == c2
    # Inner vert positions match too — same thickness, same junction info.
    assert np.allclose(multi.new_points, inner.new_points)


def test_build_multi_layer_bl_layer_thicknesses_geometric():
    """Cumulative layer thicknesses follow the geometric progression."""
    faces, points = _flat_strip_faces()
    info = detect_junction_verts([0, 1], faces, points)
    result = build_multi_layer_bl(
        [0, 1], faces, points, info,
        num_layers=4, first_layer_thickness=0.1, growth_ratio=2.0,
    )
    expected = [0.1, 0.3, 0.7, 1.5]
    assert len(result.layer_thicknesses) == 4
    for got, exp in zip(result.layer_thicknesses, expected, strict=True):
        assert abs(got - exp) < 1e-12


def test_build_multi_layer_bl_inner_pt_positions_match_thickness():
    """Each layer's inner verts sit at -cumulative_thickness × face_normal."""
    points = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float64)
    faces = [[0, 1, 2]]  # outward normal +z
    info = detect_junction_verts([0], faces, points)
    result = build_multi_layer_bl(
        [0], faces, points, info,
        num_layers=3, first_layer_thickness=0.1, growth_ratio=2.0,
    )
    # 3 cells, one per layer; cell k's top tri is cell_face_verts[k][1].
    pts = result.new_points
    expected_z = [-0.1, -0.3, -0.7]
    for k, ez in enumerate(expected_z):
        top = result.cell_face_verts[k][1]
        for vid in top:
            assert np.isclose(pts[vid][2], ez, atol=1e-9)


def test_build_multi_layer_bl_cap_sharing_flat_strip():
    """Layer K top must share canonical face with layer K+1 bottom."""
    faces, points = _flat_strip_faces()
    info = detect_junction_verts([0, 1], faces, points)
    result = build_multi_layer_bl(
        [0, 1], faces, points, info,
        num_layers=3, first_layer_thickness=0.1, growth_ratio=1.5,
    )
    cells = result.cell_face_verts
    # 6 cells = 3 layers × 2 wall faces. Layer k cells = [2k, 2k+1].
    for k in range(2):
        for w in range(2):
            top_k = cells[k * 2 + w][1]
            bot_kp1 = cells[(k + 1) * 2 + w][0]
            assert sorted(top_k) == sorted(bot_kp1)


def test_build_multi_layer_bl_cube_3_layers_36_cells():
    """Cube with 3 layers: 12 wall faces × 3 = 36 prism cells."""
    faces, points = _cube_faces()
    info = detect_junction_verts(list(range(12)), faces, points, cos_thresh=0.9)
    result = build_multi_layer_bl(
        list(range(12)), faces, points, info,
        num_layers=3, first_layer_thickness=0.05, growth_ratio=1.2,
        cluster_cos=0.5,
    )
    assert result.num_layers == 3
    assert len(result.cell_face_verts) == 36
    assert len(result.cell_to_wall_face) == 36
    assert len(result.cell_to_layer) == 36
    assert result.cell_to_layer == [0] * 12 + [1] * 12 + [2] * 12
    # Each layer's wall-face mapping matches the input order.
    for k in range(3):
        assert result.cell_to_wall_face[k * 12 : (k + 1) * 12] == list(range(12))
    # Each prism has 2 tris + 3 quads.
    for cf in result.cell_face_verts:
        n_tri = sum(1 for f in cf if len(f) == 3)
        n_quad = sum(1 for f in cf if len(f) == 4)
        assert n_tri == 2 and n_quad == 3


def test_build_multi_layer_bl_cube_3_layers_polymesh_caps_internal():
    """Cube 3-layer polymesh: intermediate caps internal, only outer wall/cap boundary.

    Counts (cluster_cos=0.5):
      Internal faces:
        - 6 face-diagonal side quads per layer × 3 layers = 18
        - 12 cap faces × 2 layer-to-layer transitions = 24
        Total internal = 42
      Boundary faces:
        - wall: 12 (layer 0 bottom)
        - bl_internal: 12 (layer 2 top)
        - bl_internal_side: 24 boundary side quads per layer × 3 = 72
    """
    faces, points = _cube_faces()
    info = detect_junction_verts(list(range(12)), faces, points, cos_thresh=0.9)
    result = build_multi_layer_bl(
        list(range(12)), faces, points, info,
        num_layers=3, first_layer_thickness=0.05, growth_ratio=1.2,
        cluster_cos=0.5,
    )
    pm = cells_to_polymesh(result.cell_face_verts, result.new_points)

    assert len(pm.neighbour) == 42
    by_name = {p["name"]: p for p in pm.patches}
    assert by_name["wall"]["nFaces"] == 12
    assert by_name["bl_internal"]["nFaces"] == 12
    assert by_name["bl_internal_side"]["nFaces"] == 72
    assert len(pm.faces) == 138

    # Owner < neighbour invariant on internal faces.
    for o, n in zip(pm.owner[:42], pm.neighbour, strict=True):
        assert o < n

    # Wall faces (layer 0 bottoms) all have owner in layer 0 cells [0, 12).
    wall_patch = by_name["wall"]
    for o in pm.owner[wall_patch["startFace"] : wall_patch["startFace"] + wall_patch["nFaces"]]:
        assert 0 <= o < 12
    # bl_internal faces (layer 2 tops) all have owner in layer 2 cells [24, 36).
    cap_patch = by_name["bl_internal"]
    for o in pm.owner[cap_patch["startFace"] : cap_patch["startFace"] + cap_patch["nFaces"]]:
        assert 24 <= o < 36


def test_build_multi_layer_gap_fill_cube_3_layers_closes_each_layer():
    """Cube 3-layer VD: each cube edge gets 2 gap tets per layer."""
    faces, points = _cube_faces()
    info = detect_junction_verts(list(range(12)), faces, points, cos_thresh=0.9)
    multi = build_multi_layer_bl(
        list(range(12)), faces, points, info,
        num_layers=3, first_layer_thickness=0.05, growth_ratio=1.2,
        cluster_cos=0.5,
    )
    gap = build_multi_layer_gap_fill_cells(list(range(12)), faces, multi)

    assert len(gap.cell_face_verts) == 12 * 3 * 2
    assert len(gap.junction_edges) == 12 * 3
    for cell in gap.cell_face_verts:
        assert len(cell) == 4
        assert all(len(face) == 3 for face in cell)


def test_build_multi_layer_full_bl_polymesh_cube_3_layers_reduces_side_open_faces():
    """Combined multi-layer VD has prism/gap internal matches on each layer."""
    faces, points = _cube_faces()
    info = detect_junction_verts(list(range(12)), faces, points, cos_thresh=0.9)
    result = build_multi_layer_full_bl_polymesh(
        list(range(12)), faces, points, info,
        num_layers=3, first_layer_thickness=0.05, growth_ratio=1.2,
        cluster_cos=0.5,
    )

    assert result.n_prism_cells == 36
    assert result.n_gap_fill_cells == 72
    by_name = {p["name"]: p for p in result.polymesh.patches}
    assert by_name["wall"]["nFaces"] == 12
    assert by_name["bl_internal"]["nFaces"] == 12
    # Previously multi-layer VD left 72 prism side quads open.  With per-layer
    # gap-fill, those side quads are triangulated and paired to closure tets;
    # only the closure tets' outer triangles remain on the side patch.
    assert by_name["bl_internal_side"]["nFaces"] == 72 * 2
    # 42 prism/prism internal faces from the no-gap multi-layer stack, plus
    # prism/gap matches and a small number of gap/gap matches across layer
    # transitions.
    assert len(result.polymesh.neighbour) == 204


def test_build_bulk_preserving_multi_layer_full_bl_keeps_original_tet_cell():
    """Bulk-preserving VD replaces wall faces with inner caps, not the bulk."""
    faces, points, owner, neighbour = _single_tet_boundary()
    wall_faces = list(range(4))
    info = detect_junction_verts(wall_faces, faces, points, cos_thresh=0.9)

    result = build_bulk_preserving_multi_layer_full_bl_polymesh(
        wall_faces,
        faces,
        owner,
        neighbour,
        points,
        info,
        num_layers=1,
        first_layer_thickness=0.05,
        growth_ratio=1.2,
        cluster_cos=0.5,
    )

    assert result.n_bulk_cells == 1
    assert result.n_prism_cells == 4
    assert result.n_gap_fill_cells == 6
    n_total_cells = max(result.polymesh.owner + result.polymesh.neighbour) + 1
    assert n_total_cells == 1 + 4 + 6

    by_name = {p["name"]: p for p in result.polymesh.patches}
    assert by_name["wall"]["nFaces"] == 4
    # The innermost BL caps are shared with the original bulk cell, so they
    # must be internal faces rather than an exposed bl_internal boundary.
    assert "bl_internal" not in by_name
    assert "bl_internal_side" in by_name

    # Four bulk-to-prism cap faces: owner is the preserved bulk cell 0 and
    # neighbours are the four appended prism cells [1, 4].
    cap_neighbours = {
        n for o, n in zip(
            result.polymesh.owner[: len(result.polymesh.neighbour)],
            result.polymesh.neighbour,
            strict=True,
        )
        if o == 0
    }
    assert cap_neighbours == {1, 2, 3, 4}


def test_build_bulk_preserving_multi_layer_full_bl_rejects_polygon_wall_face():
    """The first bulk-preserving VD step is intentionally tri-wall only."""
    points = np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
    ], dtype=np.float64)
    faces = [[0, 1, 2, 3]]
    owner = np.array([0], dtype=np.int64)
    neighbour = np.array([], dtype=np.int64)
    info = detect_junction_verts([0], faces, points, cos_thresh=0.9)

    with pytest.raises(ValueError, match="triangle wall faces"):
        build_bulk_preserving_multi_layer_full_bl_polymesh(
            [0],
            faces,
            owner,
            neighbour,
            points,
            info,
            num_layers=1,
            first_layer_thickness=0.05,
        )


def test_build_multi_layer_bl_invalid_args():
    faces, points = _flat_strip_faces()
    info = detect_junction_verts([0, 1], faces, points)
    bad_kwargs = [
        dict(num_layers=0, first_layer_thickness=0.1, growth_ratio=1.0),
        dict(num_layers=-1, first_layer_thickness=0.1, growth_ratio=1.0),
        dict(num_layers=2, first_layer_thickness=0.0, growth_ratio=1.0),
        dict(num_layers=2, first_layer_thickness=-0.1, growth_ratio=1.0),
        dict(num_layers=2, first_layer_thickness=0.1, growth_ratio=0.0),
        dict(num_layers=2, first_layer_thickness=0.1, growth_ratio=-1.0),
    ]
    for kw in bad_kwargs:
        try:
            build_multi_layer_bl([0, 1], faces, points, info, **kw)
        except ValueError:
            continue
        raise AssertionError(f"Expected ValueError for kwargs={kw}")


def test_build_multi_layer_bl_rejects_non_triangle():
    points = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], dtype=np.float64)
    faces = [[0, 1, 2, 3]]
    info = detect_junction_verts([0], faces, points)
    try:
        build_multi_layer_bl(
            [0], faces, points, info,
            num_layers=2, first_layer_thickness=0.1,
        )
    except ValueError as e:
        assert "triangle" in str(e).lower()
    else:
        raise AssertionError("Expected ValueError for non-triangle wall face")


def test_build_multi_layer_bl_disjoint_layer_vert_ids():
    """Inner verts of different layers must occupy disjoint id ranges."""
    faces, points = _cube_faces()
    info = detect_junction_verts(list(range(12)), faces, points, cos_thresh=0.9)
    result = build_multi_layer_bl(
        list(range(12)), faces, points, info,
        num_layers=3, first_layer_thickness=0.05, growth_ratio=1.2,
        cluster_cos=0.5,
    )
    n_orig = len(points)
    layer_inner_ids: list[set[int]] = [set(), set(), set()]
    for cell_idx, cell in enumerate(result.cell_face_verts):
        layer = result.cell_to_layer[cell_idx]
        # face_idx 1 = top; collects this layer's inner ids.
        for vid in cell[1]:
            assert vid >= n_orig  # all inner verts are appended
            layer_inner_ids[layer].add(int(vid))
    # Pairwise disjoint.
    assert layer_inner_ids[0].isdisjoint(layer_inner_ids[1])
    assert layer_inner_ids[1].isdisjoint(layer_inner_ids[2])
    assert layer_inner_ids[0].isdisjoint(layer_inner_ids[2])
    # Layer 1 outer (= layer 0 inner) ids appear in layer 1 cells' bottom faces.
    layer1_outer_ids: set[int] = set()
    for cell_idx, cell in enumerate(result.cell_face_verts):
        if result.cell_to_layer[cell_idx] != 1:
            continue
        for vid in cell[0]:  # bottom = previous layer's inner
            layer1_outer_ids.add(int(vid))
    assert layer1_outer_ids == layer_inner_ids[0]


# ---------------------------------------------------------------------------
# VD-8a — env-gated wiring through generate_native_bl
# ---------------------------------------------------------------------------


def _write_single_hex_polymesh(case_dir: Path) -> None:
    """Write a single-hex polyMesh whose only patch is `wall` (all 6 faces)."""
    from core.generator.polymesh_writer import write_generic_polymesh

    V = np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
    ], dtype=np.float64)
    cell_faces = [[
        [0, 3, 2, 1],  # z-
        [4, 5, 6, 7],  # z+
        [0, 1, 5, 4],  # y-
        [1, 2, 6, 5],  # x+
        [2, 3, 7, 6],  # y+
        [3, 0, 4, 7],  # x-
    ]]
    write_generic_polymesh(
        V, cell_faces, case_dir,
        patch_name="wall", patch_type="wall",
    )


def _write_single_tet_polymesh(case_dir: Path) -> None:
    """Write a single tetrahedral polyMesh whose four faces are wall patch."""
    from core.generator.polymesh_writer import write_generic_polymesh

    faces, points, _owner, _neighbour = _single_tet_boundary()
    write_generic_polymesh(
        points,
        [faces],
        case_dir,
        patch_name="wall",
        patch_type="wall",
    )


def test_generate_native_bl_vd_env_gated_replaces_polymesh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AUTO_TESSELL_BL_VD_ENABLE=1 routes generate_native_bl through the VD writer.

    Setup:
      single-hex polyMesh whose only patch is `wall` (6 quads → 12 wall
      triangles after native_bl's fan-triangulation).
    Expectation:
      * res.success is True
      * VD message tag is present
      * n_prism_cells == num_layers × 12 (no bulk cells; VD path drops the bulk)
      * polyMesh on disk has wall + bl_internal + bl_internal_side patches
    """
    from core.layers.native_bl import BLConfig, generate_native_bl
    from core.utils.polymesh_reader import parse_foam_boundary

    _write_single_hex_polymesh(tmp_path)

    monkeypatch.setenv("AUTO_TESSELL_BL_VD_ENABLE", "1")

    res = generate_native_bl(
        tmp_path,
        BLConfig(
            num_layers=2,
            growth_ratio=1.2,
            first_thickness=0.05,
            collision_safety=False,
            backup_original=False,
        ),
    )
    assert res.success, res.message
    assert "VD-8a" in res.message
    assert res.n_wall_faces == 12
    assert res.n_prism_cells == 2 * 12

    boundary = parse_foam_boundary(tmp_path / "constant" / "polyMesh" / "boundary")
    patch_names = {p["name"] for p in boundary}
    assert "wall" in patch_names
    assert "bl_internal" in patch_names
    assert "bl_internal_side" in patch_names


def test_generate_native_bl_vd_preserve_bulk_env_keeps_bulk_cell(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AUTO_TESSELL_BL_VD_PRESERVE_BULK=1 uses the bulk-preserving writer."""
    from core.evaluator.native_checker import NativeMeshChecker
    from core.layers.native_bl import BLConfig, generate_native_bl

    _write_single_tet_polymesh(tmp_path)

    monkeypatch.setenv("AUTO_TESSELL_BL_VD_ENABLE", "1")
    monkeypatch.setenv("AUTO_TESSELL_BL_VD_PRESERVE_BULK", "1")

    res = generate_native_bl(
        tmp_path,
        BLConfig(
            num_layers=1,
            growth_ratio=1.2,
            first_thickness=0.03,
            collision_safety=False,
            backup_original=False,
        ),
    )
    assert res.success, res.message
    assert "VD-8a" in res.message
    assert "bulk preserved" in res.message
    assert res.n_prism_cells == 1 + 4 + 6

    checker = NativeMeshChecker().run(tmp_path)
    assert checker.mesh_ok
    assert checker.negative_volumes == 0
    assert checker.min_cell_volume > 0.0
    assert checker.min_determinant > 0.0

    quality = json.loads((tmp_path / "native_bl_quality.json").read_text())
    assert quality["requested_layers"] == 1
    assert quality["used_layers"] == 1
    assert quality["lcr"]["min_layers_used"] == 1
    assert quality["wall_preserve"]["within_envelope"] is True
    assert quality["wall_preserve"]["max_diff_rel"] == 0.0


def test_generate_native_bl_vd_env_default_off_keeps_existing_path(
    tmp_path: Path,
) -> None:
    """Default-off env: existing per-vertex extrusion path runs (no VD tag in message).

    This guards Task 5's bench-parity requirement at the unit-test level — VD
    code must not affect the production pipeline when the env flag is unset.
    """
    from core.layers.native_bl import BLConfig, generate_native_bl

    _write_single_hex_polymesh(tmp_path)

    # Be explicit: neither set nor "1". Pop in case the pytest worker inherits
    # an env from an earlier monkeypatch'd test.
    os.environ.pop("AUTO_TESSELL_BL_VD_ENABLE", None)

    res = generate_native_bl(
        tmp_path,
        BLConfig(
            num_layers=1,
            first_thickness=0.05,
            collision_safety=False,
            backup_original=False,
        ),
    )
    assert res.success, res.message
    assert "VD-8a" not in res.message
    # Existing path message format includes "Phase 2 OK" + "bl_side_faces=".
    assert "Phase 2 OK" in res.message


# ---------------------------------------------------------------------------
# VD-8b — AUTO_TESSELL_BL_VD_FOR per-STL allow-list filter
# ---------------------------------------------------------------------------


def _write_geometry_report(case_dir: Path, input_path: str) -> None:
    """Write a minimal ``geometry_report.json`` so VD-8b can read the STL name."""
    import json

    case_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "file_info": {
            "path": input_path,
            "format": "STL",
            "file_size_bytes": 0,
            "detected_encoding": "binary",
            "is_cad_brep": False,
            "is_surface_mesh": True,
            "is_volume_mesh": False,
        }
    }
    (case_dir / "geometry_report.json").write_text(json.dumps(payload))


def test_vd_should_activate_default_off(tmp_path, monkeypatch):
    """No env vars set → VD inactive (preserves bench parity at default)."""
    from core.layers.native_bl import _vd_should_activate

    monkeypatch.delenv("AUTO_TESSELL_BL_VD_ENABLE", raising=False)
    monkeypatch.delenv("AUTO_TESSELL_BL_VD_FOR", raising=False)
    assert _vd_should_activate(tmp_path) is False


def test_vd_should_activate_enable_only(tmp_path, monkeypatch):
    """VD_ENABLE=1, VD_FOR unset → VD active (existing VD-8a behavior)."""
    from core.layers.native_bl import _vd_should_activate

    monkeypatch.setenv("AUTO_TESSELL_BL_VD_ENABLE", "1")
    monkeypatch.delenv("AUTO_TESSELL_BL_VD_FOR", raising=False)
    assert _vd_should_activate(tmp_path) is True


def test_vd_should_activate_for_matches_stl_name(tmp_path, monkeypatch):
    """VD_FOR with matching token + valid geometry_report.json → VD active."""
    from core.layers.native_bl import _vd_should_activate

    _write_geometry_report(tmp_path, "/inputs/hard_100029.stl")
    monkeypatch.setenv("AUTO_TESSELL_BL_VD_FOR", "hard_100029,extreme_1017013")
    monkeypatch.delenv("AUTO_TESSELL_BL_VD_ENABLE", raising=False)
    assert _vd_should_activate(tmp_path) is True


def test_vd_should_activate_for_no_match_stays_off(tmp_path, monkeypatch):
    """VD_FOR set but STL name does not match any token → VD inactive."""
    from core.layers.native_bl import _vd_should_activate

    _write_geometry_report(tmp_path, "/inputs/test_cube.stl")
    monkeypatch.setenv("AUTO_TESSELL_BL_VD_FOR", "hard_100029,extreme_1017013")
    # Even if VD_ENABLE=1 is set, VD_FOR is the stricter mode → still off.
    monkeypatch.setenv("AUTO_TESSELL_BL_VD_ENABLE", "1")
    assert _vd_should_activate(tmp_path) is False


def test_vd_should_activate_for_substring_match(tmp_path, monkeypatch):
    """Tokens are substring-matched against the STL basename."""
    from core.layers.native_bl import _vd_should_activate

    _write_geometry_report(tmp_path, "/data/extreme_1017014_decimated.stl")
    monkeypatch.setenv("AUTO_TESSELL_BL_VD_FOR", "extreme_1017014")
    monkeypatch.delenv("AUTO_TESSELL_BL_VD_ENABLE", raising=False)
    assert _vd_should_activate(tmp_path) is True


def test_vd_should_activate_for_missing_geometry_report_off(tmp_path, monkeypatch):
    """VD_FOR set but case_dir has no geometry_report.json → VD inactive."""
    from core.layers.native_bl import _vd_should_activate

    monkeypatch.setenv("AUTO_TESSELL_BL_VD_FOR", "hard_100029")
    monkeypatch.delenv("AUTO_TESSELL_BL_VD_ENABLE", raising=False)
    assert _vd_should_activate(tmp_path) is False


def test_vd_should_activate_for_empty_string_falls_back_to_enable(tmp_path, monkeypatch):
    """Empty VD_FOR is treated as unset (fall through to VD_ENABLE)."""
    from core.layers.native_bl import _vd_should_activate

    monkeypatch.setenv("AUTO_TESSELL_BL_VD_FOR", "")
    monkeypatch.setenv("AUTO_TESSELL_BL_VD_ENABLE", "1")
    assert _vd_should_activate(tmp_path) is True


def test_vd_should_activate_for_whitespace_only_falls_back(tmp_path, monkeypatch):
    """A VD_FOR value of only whitespace/commas is treated as empty."""
    from core.layers.native_bl import _vd_should_activate

    monkeypatch.setenv("AUTO_TESSELL_BL_VD_FOR", " ,  , ")
    monkeypatch.setenv("AUTO_TESSELL_BL_VD_ENABLE", "1")
    assert _vd_should_activate(tmp_path) is True


def test_vd_for_filter_routes_through_generate_native_bl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end: VD_FOR with matching STL name routes generate_native_bl
    through the VD writer (sanity check that the filter wires into the
    public entry point, not just the helper)."""
    from core.layers.native_bl import BLConfig, generate_native_bl

    _write_single_hex_polymesh(tmp_path)
    _write_geometry_report(tmp_path, "/inputs/hard_100029.stl")

    monkeypatch.setenv("AUTO_TESSELL_BL_VD_FOR", "hard_100029")
    monkeypatch.delenv("AUTO_TESSELL_BL_VD_ENABLE", raising=False)

    res = generate_native_bl(
        tmp_path,
        BLConfig(
            num_layers=2, growth_ratio=1.2, first_thickness=0.05,
            collision_safety=False, backup_original=False,
        ),
    )
    assert res.success, res.message
    assert "VD-8a" in res.message  # VD path was taken


def test_vd_for_no_match_keeps_existing_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end: VD_FOR with no matching STL name leaves the per-vertex path
    untouched, even if VD_ENABLE=1 (VD_FOR is the stricter gate)."""
    from core.layers.native_bl import BLConfig, generate_native_bl

    _write_single_hex_polymesh(tmp_path)
    _write_geometry_report(tmp_path, "/inputs/test_cube.stl")

    monkeypatch.setenv("AUTO_TESSELL_BL_VD_FOR", "hard_100029")
    monkeypatch.setenv("AUTO_TESSELL_BL_VD_ENABLE", "1")

    res = generate_native_bl(
        tmp_path,
        BLConfig(
            num_layers=1, first_thickness=0.05,
            collision_safety=False, backup_original=False,
        ),
    )
    assert res.success, res.message
    assert "VD-8a" not in res.message
    assert "Phase 2 OK" in res.message
