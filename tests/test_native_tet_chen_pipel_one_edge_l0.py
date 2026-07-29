"""L0 certificate for Chen--Zheng 2006 Table-5 one-edge pipel split."""

from __future__ import annotations

from fractions import Fraction

import pytest

from core.generator.native_tet.chen_pipel_one_edge_l0 import (
    certify_one_edge_pipel_template,
)


def _closed_pipe() -> (
    tuple[tuple[tuple[float, float, float], ...], tuple[tuple[int, int, int, int], ...]]
):
    # B-D is interior: its link is the closed three-vertex cycle A-C-E.
    points = (
        (2.0, 0.0, 0.0),  # A
        (0.0, 0.0, -1.0),  # B
        (-1.0, 2.0, 0.0),  # C
        (0.0, 0.0, 1.0),  # D
        (-1.0, -2.0, 0.0),  # E
        (0.0, 0.0, 0.0),  # P on B-D
    )
    return points, ((0, 1, 2, 3), (2, 1, 4, 3), (4, 1, 0, 3))


def test_one_edge_pipel_preserves_closed_pipe_boundary_and_volume() -> None:
    points, parents = _closed_pipe()

    result = certify_one_edge_pipel_template(points, parents, (1, 3), 5)

    assert result.accepted, result.reason
    assert len(result.replacement_tets) == 6
    assert result.parent_volume6 == result.replacement_volume6 == Fraction(24)
    assert result.external_boundary_preserved
    assert result.internal_faces_conforming


def test_endpoint_intersection_rejects_without_replacement() -> None:
    points, parents = _closed_pipe()

    result = certify_one_edge_pipel_template(points, parents, (1, 3), 1)

    assert not result.accepted
    assert result.reason == "intersection_must_be_open_edge_point"
    assert not result.replacement_tets


def test_open_cut_edge_star_rejects_without_replacement() -> None:
    points, parents = _closed_pipe()
    open_points = points + ((-3.0, 0.0, 0.0),)
    open_pipe = parents[:2] + ((4, 1, 6, 3),)

    result = certify_one_edge_pipel_template(open_points, open_pipe, (1, 3), 5)

    with pytest.raises(ValueError, match="closed interior-edge pipe"):
        certify_one_edge_pipel_template(points, parents[:2], (1, 3), 5)
    assert not result.accepted
    assert result.reason == "cut_edge_is_not_interior_closed_pipe"


def test_one_edge_pipel_certificate_is_value_identical_on_repeat() -> None:
    points, parents = _closed_pipe()

    assert certify_one_edge_pipel_template(
        points, parents, (1, 3), 5
    ) == certify_one_edge_pipel_template(points, parents, (1, 3), 5)
