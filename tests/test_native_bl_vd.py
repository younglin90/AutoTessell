"""Unit tests for core.layers.native_bl_vd (vertex duplication BL utilities)."""
from __future__ import annotations

import numpy as np

from core.layers.native_bl_vd import (
    build_full_bl_polymesh,
    build_gap_fill_cells,
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
