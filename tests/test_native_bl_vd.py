"""Unit tests for core.layers.native_bl_vd (vertex duplication BL utilities)."""
from __future__ import annotations

import numpy as np

from core.layers.native_bl_vd import (
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
