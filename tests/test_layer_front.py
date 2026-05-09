from __future__ import annotations

import numpy as np

from core.layers.layer_front import build_layer_front


def test_layer_front_counts_boundary_and_shared_edges() -> None:
    faces = [
        [0, 1, 2],
        [1, 3, 2],
    ]
    front = build_layer_front(faces, [0, 1])
    assert front.active_faces == (0, 1)
    assert front.ignored_faces == ()
    assert front.vertices == (0, 1, 2, 3)
    assert front.n_boundary_edges == 4
    assert front.n_nonmanifold_edges == 0
    shared = [e for e in front.edges if e.vertices == (1, 2)]
    assert len(shared) == 1
    assert shared[0].faces == (0, 1)


def test_layer_front_strict_ignores_nonmanifold_front_faces() -> None:
    faces = [
        [0, 1, 2],
        [1, 0, 3],
        [0, 1, 4],
    ]
    diagnostic = build_layer_front(faces, [0, 1, 2])
    assert diagnostic.n_nonmanifold_edges == 1
    assert diagnostic.ignored_faces == ()

    strict = build_layer_front(faces, [0, 1, 2], strict_manifold=True)
    assert strict.active_faces == ()
    assert strict.ignored_faces == (0, 1, 2)


def test_layer_front_builds_per_source_vertex_graph() -> None:
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [1.0, 1.0, 0.0],
            [0.0, 1.0, 0.0],
        ],
        dtype=np.float64,
    )
    faces = [
        [0, 1, 2],
        [0, 2, 3],
    ]
    front = build_layer_front(faces, [0, 1], points=points)
    by_vertex = {lv.vertex: lv for lv in front.layer_vertices}

    assert front.n_feature_vertices == 0
    assert front.n_blocked_vertices == 4
    assert by_vertex[0].faces == (0, 1)
    assert by_vertex[0].neighbours == (1, 2, 3)
    assert by_vertex[0].is_boundary
    assert not by_vertex[0].is_feature
    assert by_vertex[0].normal == (0.0, 0.0, 1.0)


def test_layer_front_marks_cube_corners_as_geometric_features() -> None:
    points = np.array(
        [
            [0, 0, 0],
            [1, 0, 0],
            [1, 1, 0],
            [0, 1, 0],
            [0, 0, 1],
            [1, 0, 1],
            [1, 1, 1],
            [0, 1, 1],
        ],
        dtype=np.float64,
    )
    faces = [
        [0, 2, 1], [0, 3, 2],
        [4, 5, 6], [4, 6, 7],
        [0, 1, 5], [0, 5, 4],
        [3, 7, 6], [3, 6, 2],
        [0, 4, 7], [0, 7, 3],
        [1, 2, 6], [1, 6, 5],
    ]
    front = build_layer_front(faces, list(range(12)), points=points)
    by_vertex = {lv.vertex: lv for lv in front.layer_vertices}

    assert front.n_boundary_edges == 0
    assert front.n_feature_vertices == 8
    assert front.n_blocked_vertices == 8
    assert all(lv.is_feature for lv in front.layer_vertices)
    assert by_vertex[0].faces == (0, 1, 4, 5, 8, 9)
    assert by_vertex[0].neighbours == (1, 2, 3, 4, 5, 7)
