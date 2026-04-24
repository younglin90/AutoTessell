"""R124 — insphere_staged tests."""
from __future__ import annotations


def test_insphere_regular_tet_center_is_inside() -> None:
    from core.utils.predicates_staged import insphere_staged

    pts = [(1, 1, 1), (1, -1, -1), (-1, 1, -1), (-1, -1, 1)]
    assert insphere_staged(*pts, (0, 0, 0)) == 1


def test_insphere_far_point_is_outside() -> None:
    from core.utils.predicates_staged import insphere_staged

    pts = [(1, 1, 1), (1, -1, -1), (-1, 1, -1), (-1, -1, 1)]
    assert insphere_staged(*pts, (10, 10, 10)) == -1


def test_insphere_vertex_on_circumsphere() -> None:
    """tet 의 한 vertex 는 circumsphere 위 → boundary (0) 이어야."""
    from core.utils.predicates_staged import insphere_staged

    pts = [(1, 1, 1), (1, -1, -1), (-1, 1, -1), (-1, -1, 1)]
    r = insphere_staged(*pts, (1, 1, 1))
    assert r == 0
