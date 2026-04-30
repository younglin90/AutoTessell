"""G2 / beta2603 — mixed_pyramid 회귀."""
from __future__ import annotations

import numpy as np
import pytest

from core.layers.mixed_pyramid import (
    build_pyramid_cells,
    detect_interface_quads,
    pyramid_quality,
    split_quad_to_tri,
)


def test_build_pyramid_cells_unit_square():
    """Unit square → pyramid 1개 cell + 4 tri face + 1 apex 점."""
    pts = np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
    ], dtype=np.float64)
    quads = [[0, 1, 2, 3]]
    new_pts, pyr, new_tris, r = build_pyramid_cells(pts, quads, apex_offset_factor=0.5)
    assert r.success
    assert r.n_pyramid_cells == 1
    assert r.n_new_apex_points == 1
    assert r.n_new_tri_faces == 4
    assert new_pts.shape == (5, 3)
    assert pyr.shape == (1, 5)
    assert pyr[0, 4] == 4  # apex id = 4 (next after 0..3).
    # apex z 는 base 위 (centroid above z=0 plane).
    assert new_pts[4, 2] > 0


def test_build_pyramid_empty_quads():
    pts = np.array([[0, 0, 0]], dtype=np.float64)
    new_pts, pyr, tris, r = build_pyramid_cells(pts, [])
    assert not r.success
    assert pyr.shape == (0, 5)


def test_split_quad_to_tri_diagonal():
    tris = split_quad_to_tri([0, 1, 2, 3])
    assert len(tris) == 2
    assert tris[0] == [0, 1, 2]
    assert tris[1] == [0, 2, 3]


def test_split_quad_to_tri_apex():
    tris = split_quad_to_tri([0, 1, 2, 3], new_apex_id=10)
    assert len(tris) == 4
    assert tris[0] == [0, 1, 10]
    assert tris[3] == [3, 0, 10]


def test_pyramid_quality_unit_square():
    """Unit square base + apex 정중앙 위 → quality > 0."""
    pts = np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        [0.5, 0.5, np.sqrt(2) / 2],  # apex 정상 높이.
    ], dtype=np.float64)
    pyr = np.array([0, 1, 2, 3, 4], dtype=np.int64)
    q = pyramid_quality(pts, pyr)
    assert 0.0 < q <= 1.0


def test_detect_interface_quads_basic():
    """tet cell 이 hex face 의 3+ vertex 공유 → interface."""
    hex_cells = np.array([[0, 1, 2, 3, 4, 5, 6, 7]], dtype=np.int64)
    tet_cells = np.array([[0, 1, 2, 8]], dtype=np.int64)
    hex_face_owner = np.array([0, 0], dtype=np.int64)
    hex_face_verts = [[0, 1, 2, 3], [4, 5, 6, 7]]
    interfaces = detect_interface_quads(
        hex_cells, tet_cells, hex_face_owner, hex_face_verts,
    )
    # face 0 (0,1,2,3) 은 tet (0,1,2,8) 과 3 vertex 공유 → interface.
    # face 1 (4,5,6,7) 은 0 vertex 공유.
    assert 0 in interfaces
    assert 1 not in interfaces


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
