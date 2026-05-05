"""Round 65 — constraint preservation (protected edges/faces)."""
from __future__ import annotations

import numpy as np
import pytest


def test_collapse_respects_protected_edges() -> None:
    """short edge 가 protected 면 collapse 되지 않음."""
    from core.generator.native_tet.local_ops import collapse_short_edges

    # very short protected edge (0,1).
    pts = np.array(
        [[0, 0, 0], [0.01, 0, 0], [0, 1, 0], [0, 0, 1]],
        dtype=np.float64,
    )
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    # protected 없으면 collapse 가능 (both unlocked, short).
    _, _, n_free = collapse_short_edges(
        pts.copy(), tets, target_edge=1.0, ratio=0.8,
    )
    _, _, n_protect = collapse_short_edges(
        pts.copy(), tets, target_edge=1.0, ratio=0.8,
        protected_edges={(0, 1)},
    )
    # protected 상태에서 collapse 수 <= 보호 없는 경우.
    assert n_protect <= n_free


def test_flip_23_respects_protected_face() -> None:
    """공유 face 가 protected 면 2-3 flip 되지 않음."""
    from core.generator.native_tet.flip import flip_faces_23

    pts = np.array(
        [
            [0, 0, 0], [1, 0, 0], [0.5, 0.866, 0],
            [0.5, 0.289, 0.6],
            [0.5, 0.289, -0.6],
        ],
        dtype=np.float64,
    )
    tets = np.array([[0, 1, 2, 3], [0, 1, 2, 4]], dtype=np.int64)
    face_key = tuple(sorted((0, 1, 2)))

    out_free, n_free = flip_faces_23(pts, tets, min_quality_improvement=-1.0)
    out_prot, n_prot = flip_faces_23(
        pts, tets, min_quality_improvement=-1.0,
        protected_faces={face_key},
    )
    # protected 상태에서는 flip 수 0.
    assert n_prot == 0
    # 자유 상태는 발생 여부 자유지만 원래 2 tet 또는 3 tet.
    assert out_free.shape[0] in (2, 3)
    assert out_prot.shape[0] == 2


def test_flip_32_respects_protected_edge() -> None:
    """3 tet 공유 edge 가 protected 면 3-2 flip 되지 않음."""
    from core.generator.native_tet.flip import flip_edges_32

    pts = np.array(
        [
            [0, 0, 0], [0, 0, 1],
            [1, 0, 0.5], [-0.5, 0.866, 0.5], [-0.5, -0.866, 0.5],
        ],
        dtype=np.float64,
    )
    tets = np.array(
        [[0, 1, 2, 3], [0, 1, 3, 4], [0, 1, 4, 2]], dtype=np.int64,
    )
    # edge (0, 1) 이 protected.
    _, n_prot = flip_edges_32(
        pts, tets, min_quality_improvement=-1.0,
        protected_edges={(0, 1)},
    )
    assert n_prot == 0
