"""beta2322 — self-intersection detect-only skeleton tests."""
from __future__ import annotations

import numpy as np

from core.preprocessor.native_repair.self_intersect import (
    SelfIntersectReport,
    detect_self_intersections,
)


def test_two_crossing_triangles_detected() -> None:
    V = np.array([
        [0, 0, 0], [1, 0, 0], [0.5, 1, 0],
        [0.5, 0, -1], [0.5, 0, 1], [0.5, 1, 0.5],
    ], dtype=np.float64)
    F = np.array([[0, 1, 2], [3, 4, 5]], dtype=np.int64)
    r = detect_self_intersections(V, F)
    assert isinstance(r, SelfIntersectReport)
    assert r.has_self_intersection
    assert r.n_intersections >= 1
    assert (0, 1) in r.intersecting_face_pairs


def test_far_apart_triangles_no_intersection() -> None:
    V = np.array([
        [0, 0, 0], [1, 0, 0], [0, 1, 0],
        [10, 0, 0], [11, 0, 0], [10, 1, 0],
    ], dtype=np.float64)
    F = np.array([[0, 1, 2], [3, 4, 5]], dtype=np.int64)
    r = detect_self_intersections(V, F)
    assert not r.has_self_intersection
    assert r.n_intersections == 0


def test_shared_vertex_not_flagged_as_intersection() -> None:
    """Triangles sharing a vertex/edge are not considered self-intersecting."""
    V = np.array([
        [0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1],
    ], dtype=np.float64)
    # Two triangles sharing edge (0, 1).
    F = np.array([[0, 1, 2], [0, 1, 3]], dtype=np.int64)
    r = detect_self_intersections(V, F)
    assert not r.has_self_intersection


def test_large_mesh_short_circuits() -> None:
    """beta2322 — n_faces > max_pairs_for_o_n_squared 일 때 short-circuit
    (다음 카드의 KDTree-based 경로에서 처리)."""
    V = np.random.RandomState(0).rand(200, 3).astype(np.float64)
    F = np.random.RandomState(1).randint(0, 200, size=(6000, 3)).astype(np.int64)
    r = detect_self_intersections(V, F, max_pairs_for_o_n_squared=5000)
    assert r.n_faces == 6000
    assert r.n_pairs_tested == 0  # short-circuit
    assert r.n_intersections == 0


def test_empty_input_returns_zero_report() -> None:
    V = np.zeros((0, 3), dtype=np.float64)
    F = np.zeros((0, 3), dtype=np.int64)
    r = detect_self_intersections(V, F)
    assert r.n_faces == 0
    assert r.n_intersections == 0
