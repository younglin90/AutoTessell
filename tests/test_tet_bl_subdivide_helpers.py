"""beta58 — tet_bl_subdivide helper 단위 회귀.

`_identify_prism_cells` / `_prism_vertex_pairs` 는 prism wedge → 3 tet 분할의
topology 인식 코어. 기존 test_tet_bl_subdivide.py 는 end-to-end 만 다루므로
helper 의 경계 조건을 별도 고정한다.
"""
from __future__ import annotations

import numpy as np
import pytest

from core.layers.tet_bl_subdivide import (
    TetSubdivResult,
    _identify_prism_cells,
    _prism_vertex_pairs,
)


# ---------------------------------------------------------------------------
# TetSubdivResult defaults
# ---------------------------------------------------------------------------


def test_tet_subdiv_result_defaults() -> None:
    r = TetSubdivResult(success=True, elapsed=0.1)
    assert r.n_prism_before == 0
    assert r.n_tet_added == 0
    assert r.message == ""


# ---------------------------------------------------------------------------
# _identify_prism_cells
# ---------------------------------------------------------------------------


def _mk_prism_faces_for_cell(cid: int, outer_tri: list[int], inner_tri: list[int]):
    """outer + inner tri + 3 side quad 를 cid 가 owner 인 face 로 반환."""
    a0, a1, a2 = outer_tri
    b0, b1, b2 = inner_tri
    return [
        outer_tri,           # tri
        inner_tri,           # tri
        [a0, a1, b1, b0],    # quad 1
        [a1, a2, b2, b1],    # quad 2
        [a2, a0, b0, b2],    # quad 3
    ]


def test_identify_single_prism_cell() -> None:
    """정확히 2 tri + 3 quad 인 cell 하나 → prism 으로 인식."""
    faces_list = _mk_prism_faces_for_cell(0, [0, 1, 2], [3, 4, 5])
    owner = np.array([0] * 5, dtype=np.int64)
    neighbour = np.array([], dtype=np.int64)
    prism_ids, cell_faces = _identify_prism_cells(faces_list, owner, neighbour, 1)
    assert prism_ids == [0]
    assert len(cell_faces[0]) == 5


def test_identify_tet_not_prism() -> None:
    """tet (4 tri face) → prism 아님."""
    faces_list = [[0, 1, 2], [0, 1, 3], [1, 2, 3], [0, 2, 3]]
    owner = np.array([0, 0, 0, 0], dtype=np.int64)
    neighbour = np.array([], dtype=np.int64)
    prism_ids, _ = _identify_prism_cells(faces_list, owner, neighbour, 1)
    assert prism_ids == []


def test_identify_cell_with_wrong_face_count() -> None:
    """face 6 개 → prism 조건 (5 face) 탈락."""
    faces_list = _mk_prism_faces_for_cell(0, [0, 1, 2], [3, 4, 5])
    faces_list.append([0, 1, 2])  # 추가 tri
    owner = np.array([0] * 6, dtype=np.int64)
    prism_ids, _ = _identify_prism_cells(faces_list, owner, np.array([], dtype=np.int64), 1)
    assert prism_ids == []


def test_identify_cell_with_wrong_mix() -> None:
    """5 face 이지만 3 tri + 2 quad (prism 아님)."""
    faces_list = [
        [0, 1, 2], [3, 4, 5], [0, 1, 3],  # 3 tri
        [0, 1, 4, 3], [1, 2, 5, 4],       # 2 quad
    ]
    owner = np.array([0] * 5, dtype=np.int64)
    prism_ids, _ = _identify_prism_cells(faces_list, owner, np.array([], dtype=np.int64), 1)
    assert prism_ids == []


def test_identify_multiple_prisms() -> None:
    """두 prism cell 이 서로 다른 owner → 둘 다 인식."""
    f0 = _mk_prism_faces_for_cell(0, [0, 1, 2], [3, 4, 5])
    f1 = _mk_prism_faces_for_cell(1, [6, 7, 8], [9, 10, 11])
    faces_all = f0 + f1
    owner = np.array([0] * 5 + [1] * 5, dtype=np.int64)
    prism_ids, _ = _identify_prism_cells(faces_all, owner, np.array([], dtype=np.int64), 2)
    assert sorted(prism_ids) == [0, 1]


def test_identify_respects_neighbour_faces() -> None:
    """face 가 cell 두 개에 공유되면 양쪽 cell 의 face list 에 들어감."""
    # cell 0 = prism (owner), cell 1 = shares one quad as neighbour
    f_prism = _mk_prism_faces_for_cell(0, [0, 1, 2], [3, 4, 5])
    # cell 1 에 더 많은 face 추가해서 5 개로 맞추되 prism 조건 만족시키기
    f_prism_2 = _mk_prism_faces_for_cell(1, [6, 7, 8], [9, 10, 11])
    faces_all = f_prism + f_prism_2
    # 마지막 prism quad 를 shared internal face 로 (cell 0, cell 1 소속)
    owner = np.array([0, 0, 0, 0, 0, 1, 1, 1, 1, 1], dtype=np.int64)
    neighbour = np.array([], dtype=np.int64)
    prism_ids, _ = _identify_prism_cells(faces_all, owner, neighbour, 2)
    assert sorted(prism_ids) == [0, 1]


# ---------------------------------------------------------------------------
# _prism_vertex_pairs
# ---------------------------------------------------------------------------


def test_prism_vertex_pairs_standard_wedge() -> None:
    """표준 wedge: outer [0,1,2] + inner [3,4,5] 에서 pair (0→3)(1→4)(2→5)."""
    face_verts = _mk_prism_faces_for_cell(0, [0, 1, 2], [3, 4, 5])
    outer, inner = _prism_vertex_pairs(face_verts)
    assert outer == [0, 1, 2]
    # pair_map: 0 shares quads with 3, 1 with 4, 2 with 5
    assert inner == [3, 4, 5]


def test_prism_vertex_pairs_shuffled_outer() -> None:
    """outer triangle 순서가 달라도 같은 pair 가 유지됨."""
    face_verts = _mk_prism_faces_for_cell(0, [2, 0, 1], [5, 3, 4])
    outer, inner = _prism_vertex_pairs(face_verts)
    assert set(outer) == {0, 1, 2}
    assert set(inner) == {3, 4, 5}
    # order matching: outer[i] ↔ inner[i]
    # outer = [2,0,1] → inner should be [5,3,4]
    assert outer == [2, 0, 1]
    assert inner == [5, 3, 4]


def test_prism_vertex_pairs_rejects_wrong_face_count() -> None:
    """tri 1 개 + quad 3 개 → None."""
    face_verts = [
        [0, 1, 2],
        [0, 1, 4, 3], [1, 2, 5, 4], [2, 0, 3, 5],
    ]
    assert _prism_vertex_pairs(face_verts) is None


def test_prism_vertex_pairs_rejects_shared_tri_vertex() -> None:
    """outer / inner 가 vertex 공유 → prism 아님, None."""
    face_verts = [
        [0, 1, 2], [2, 3, 4],
        [0, 1, 3, 2], [1, 2, 4, 3], [2, 0, 2, 4],  # 의도적 engineered
    ]
    # outer{0,1,2} inner{2,3,4} → intersection {2} → None
    assert _prism_vertex_pairs(face_verts) is None


def test_prism_vertex_pairs_rejects_bad_quad_topology() -> None:
    """outer vertex 가 quads 2 개에 정확히 포함되지 않으면 None."""
    face_verts = [
        [0, 1, 2], [3, 4, 5],
        [0, 1, 4, 3], [0, 1, 4, 3], [0, 1, 4, 3],  # 같은 quad 3번 (degenerate)
    ]
    assert _prism_vertex_pairs(face_verts) is None
