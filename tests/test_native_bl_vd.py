"""Unit tests for core.layers.native_bl_vd (vertex duplication BL utilities)."""
from __future__ import annotations

import numpy as np

from core.layers.native_bl_vd import (
    build_prism_cells,
    cells_to_polymesh,
    compute_face_normals,
    detect_junction_verts,
    generate_per_face_inner_verts,
)


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
