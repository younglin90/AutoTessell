"""Round 32 — 입력 pre-check unit tests."""
from __future__ import annotations

import numpy as np
import pytest


def test_input_check_clean_cube() -> None:
    from core.generator.native_tet.input_check import check_input
    import trimesh

    m = trimesh.creation.box(extents=(1, 1, 1))
    V = np.asarray(m.vertices, dtype=np.float64)
    F = np.asarray(m.faces, dtype=np.int64)

    res = check_input(V, F)
    assert res.n_duplicate_vertices == 0
    assert res.n_zero_area_triangles == 0
    assert res.n_boundary_edges == 0
    assert res.n_nonmanifold_edges == 0
    # self-intersection AABB heuristic 은 cube 처럼 인접 face 많으면 over-count
    # 가능 — 해당 warning 은 허용.
    hard_warnings = [
        w for w in res.warnings
        if "duplicate" in w or "zero-area" in w
        or "non-watertight" in w or "non-manifold" in w
    ]
    assert hard_warnings == []


def test_input_check_detects_duplicates() -> None:
    from core.generator.native_tet.input_check import check_input

    # vertex 0 중복.
    V = np.array(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 0]], dtype=np.float64,
    )
    F = np.array([[0, 1, 2]], dtype=np.int64)
    res = check_input(V, F)
    assert res.n_duplicate_vertices >= 1
    assert any("duplicate" in w for w in res.warnings)


def test_input_check_detects_zero_area() -> None:
    from core.generator.native_tet.input_check import check_input

    V = np.array(
        [[0, 0, 0], [1, 0, 0], [2, 0, 0]],   # collinear
        dtype=np.float64,
    )
    F = np.array([[0, 1, 2]], dtype=np.int64)
    res = check_input(V, F)
    assert res.n_zero_area_triangles == 1
    assert any("zero-area" in w for w in res.warnings)


def test_input_check_detects_boundary() -> None:
    from core.generator.native_tet.input_check import check_input

    # 단일 triangle — 3 boundary edges.
    V = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float64)
    F = np.array([[0, 1, 2]], dtype=np.int64)
    res = check_input(V, F)
    assert res.n_boundary_edges == 3
    assert any("non-watertight" in w for w in res.warnings)


def test_input_check_detects_nonmanifold() -> None:
    from core.generator.native_tet.input_check import check_input

    # 3 triangles 이 edge (0,1) 공유 — non-manifold.
    V = np.array(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1]],
        dtype=np.float64,
    )
    F = np.array(
        [[0, 1, 2], [0, 1, 3], [0, 1, 4]], dtype=np.int64,
    )
    res = check_input(V, F)
    assert res.n_nonmanifold_edges >= 1
    assert any("non-manifold" in w for w in res.warnings)
