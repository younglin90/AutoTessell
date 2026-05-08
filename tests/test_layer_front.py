from __future__ import annotations

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
