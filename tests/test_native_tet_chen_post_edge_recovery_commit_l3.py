"""Atomic L3 Chen missing-facet recovered-face tests."""

from __future__ import annotations

from fractions import Fraction
from itertools import product
from typing import cast

from core.generator.native_tet.chen_clusterel_node_state_l0 import (
    classify_clusterel_node_states_l0,
)
from core.generator.native_tet.chen_pipe_cluster_l0 import _positive_orientation
from core.generator.native_tet.chen_pipel_two_edge_l0 import (
    Case2Scheme,
    certify_two_edge_pipel_template,
)
from core.generator.native_tet.chen_post_edge_recovery_commit_l3 import (
    certify_post_edge_recovery_commit_l3,
)
from core.generator.native_tet.chen_post_edge_recovery_state_l1 import (
    ChenPostEdgeRecoveryClusterelRecord,
)
from core.generator.native_tet.chen_thr_edg_source_match_l1 import (
    certify_thr_edg_source_match_l1,
)


_POINTS = ((0, 0, 0), (4, 0, 0), (0, 4, 0), (2, 2, 3), (-1, -1, -2), (Fraction(1, 5), Fraction(1, 5), 0))
_PARENTS = ((0, 1, 3, 4), (1, 2, 3, 4), (2, 0, 3, 4))
_SOURCE_IDS = (0, 1, 2)
_CHILDREN = {
    0: ((0, 3, 1, 5), (0, 5, 1, 4)),
    1: ((1, 3, 2, 5), (1, 5, 2, 4)),
    2: ((3, 0, 2, 5), (5, 0, 2, 4)),
}


def _records() -> tuple[ChenPostEdgeRecoveryClusterelRecord, ...]:
    source = tuple(_POINTS[index] for index in _SOURCE_IDS)
    return tuple(
        ChenPostEdgeRecoveryClusterelRecord(
            index, classify_clusterel_node_states_l0(tuple(_POINTS[vertex] for vertex in tet), source).nodes
        )
        for index, tet in enumerate(_PARENTS)
    )


def test_table5_closed_one_edge_pipe_recovers_exact_two_owner_source_subfaces() -> None:
    result = certify_post_edge_recovery_commit_l3(_POINTS, _PARENTS, _SOURCE_IDS, _records(), _CHILDREN)

    assert result.accepted, result.reason
    assert result.before_state is not None and result.before_state.accepted
    assert result.staging is not None and result.staging.accepted
    assert result.after_faces is not None and result.after_faces.accepted
    assert result.source_points_unchanged
    assert not result.production_mesh_changed


def test_incomplete_closed_pipe_rejects_before_after_face_claim() -> None:
    result = certify_post_edge_recovery_commit_l3(
        _POINTS, _PARENTS, _SOURCE_IDS, _records(), {0: _CHILDREN[0], 1: _CHILDREN[1]}
    )

    assert not result.accepted
    assert result.reason.startswith("staging_failed:")
    assert result.after_faces is None


def test_post_edge_recovery_commit_is_value_identical_on_repeat() -> None:
    first = certify_post_edge_recovery_commit_l3(_POINTS, _PARENTS, _SOURCE_IDS, _records(), _CHILDREN)
    second = certify_post_edge_recovery_commit_l3(_POINTS, _PARENTS, _SOURCE_IDS, _records(), _CHILDREN)

    assert first == second


def test_mixed_one_two_edge_explicit_plan_recovers_whole_source_face() -> None:
    points = (
        (0, 0, 0), (4, 0, 0), (0, 4, 0), (2, 2, 3), (-1, -1, -2),
        (1, 1, -1), (4, 2, 2), (2, Fraction(4, 3), 0),
        (Fraction(5, 4), Fraction(5, 4), 0),
    )
    parents = (
        (5, 0, 1, 4), (5, 0, 2, 4), (5, 6, 2, 1), (5, 6, 3, 1),
        (5, 0, 3, 1), (5, 6, 3, 2), (5, 0, 3, 2),
    )
    source_ids = (0, 1, 2)
    source = tuple(points[index] for index in source_ids)
    records = tuple(
        ChenPostEdgeRecoveryClusterelRecord(
            index, classify_clusterel_node_states_l0(tuple(points[vertex] for vertex in tet), source).nodes
        )
        for index, tet in enumerate(parents)
        if index in {2, 3, 4, 5, 6}
    )
    # The two Case-2 rows use the shared-face orientation-compatible local
    # S/S choice; the remaining parents use their literal Table-5 children.
    children = {
        2: ((5, 1, 2, 7), (7, 1, 2, 6)),
        3: ((3, 6, 1, 7), (3, 7, 1, 8), (8, 7, 1, 5)),
        4: ((5, 0, 1, 8), (8, 0, 1, 3)),
        5: ((6, 3, 2, 7), (7, 3, 2, 8), (7, 8, 2, 5)),
        6: ((0, 5, 2, 8), (0, 8, 2, 3)),
    }

    result = certify_post_edge_recovery_commit_l3(points, parents, source_ids, records, children)

    assert result.accepted, result.reason
    assert result.before_state is not None and result.before_state.active_parent_types == (
        (2, "ONE_EDG"), (3, "TWO_EDG"), (4, "ONE_EDG"),
        (5, "TWO_EDG"), (6, "ONE_EDG"),
    )
    assert result.staging is not None and result.staging.accepted
    assert result.after_faces is not None and result.after_faces.accepted
    assert {tuple(sorted(face)) for face in result.after_faces.recovered_faces} == {
        (0, 1, 8), (0, 2, 8), (1, 2, 7), (1, 7, 8), (2, 7, 8)
    }


def test_thr_with_three_case2_neighbours_has_a_literal_surface_preserving_plan() -> None:
    """Enumerate only Table 5/6/11 rows; this is not an automatic selector."""
    points = (
        (0, 0, 0), (4, 0, 0), (0, 4, 0), (2, 2, 3), (-1, -1, -2),
        (4, 1, 2), (1, 0, -1), (3, -1, 4), (4, 4, 4), (2, 1, 3),
        (Fraction(5, 4), Fraction(1, 4), 0),
        (Fraction(5, 4), Fraction(1, 2), 0),
        (2, Fraction(1, 3), 0),
    )
    parents = (
        (6, 0, 2, 4), (6, 7, 1, 4), (6, 0, 7, 4), (6, 0, 7, 1),
        (5, 8, 2, 1), (5, 6, 2, 1), (3, 5, 8, 2), (3, 6, 0, 2),
        (3, 5, 6, 2), (9, 0, 7, 1), (9, 5, 7, 1), (9, 5, 8, 7),
        (9, 3, 8, 7), (9, 3, 5, 8), (9, 3, 6, 0), (9, 3, 5, 6),
        (9, 6, 0, 1), (9, 5, 6, 1),
    )
    source_ids = (0, 1, 2)
    source = tuple(points[index] for index in source_ids)
    active = {5, 7, 8, 14, 15, 16, 17}
    records = tuple(
        ChenPostEdgeRecoveryClusterelRecord(
            index,
            classify_clusterel_node_states_l0(tuple(points[vertex] for vertex in tet), source).nodes,
        )
        for index, tet in enumerate(parents)
        if index in active
    )

    def split_one_edge(parent: tuple[int, int, int, int], edge: tuple[int, int], point: int) -> tuple[tuple[int, int, int, int], ...]:
        other = tuple(vertex for vertex in parent if vertex not in edge)
        raw = ((edge[0], point, other[0], other[1]), (point, edge[1], other[0], other[1]))
        oriented = tuple(_positive_orientation(points, tet) for tet in raw)
        assert all(tet is not None for tet in oriented)
        return tuple(tet for tet in oriented if tet is not None)

    fixed = {
        5: split_one_edge(parents[5], (5, 6), 12),
        7: split_one_edge(parents[7], (3, 6), 11),
        16: split_one_edge(parents[16], (9, 6), 10),
    }
    two_specs = (
        (8, (3, 5, 2, 6), 11, 12),
        (14, (9, 3, 0, 6), 10, 11),
        (17, (9, 5, 1, 6), 10, 12),
    )
    thr_parent = (9, 3, 5, 6)
    thr_labels = {"A": 9, "B": 3, "C": 5, "D": 6, "P1": 10, "P2": 11, "P3": 12}
    survivors: list[tuple[tuple[str, str, str], str]] = []
    for two_choices in product(("NEIGHBOR_S", "NEIGHBOR_Z"), repeat=3):
        two_children = {}
        for (parent_index, ordered, first, second), scheme in zip(two_specs, two_choices, strict=True):
            template = certify_two_edge_pipel_template(
                points, ordered, first, second, cast(Case2Scheme, scheme)
            )
            assert template.accepted, template.reason
            two_children[parent_index] = template.replacement_tets
        for thr_scheme in ("S2/Z1", "S1/Z2"):
            thr = certify_thr_edg_source_match_l1(
                tuple(points[index] for index in thr_parent), source, subcase=thr_scheme
            )
            assert thr.accepted and thr.candidate is not None
            candidates = {
                **fixed,
                **two_children,
                15: tuple(tuple(thr_labels[label] for label in tet) for tet in thr.candidate.oriented_children),
            }
            result = certify_post_edge_recovery_commit_l3(points, parents, source_ids, records, candidates)
            if result.accepted:
                survivors.append(((two_choices[0], two_choices[1], two_choices[2]), thr_scheme))

    assert survivors == [
        (("NEIGHBOR_S", "NEIGHBOR_S", "NEIGHBOR_S"), "S2/Z1"),
        (("NEIGHBOR_Z", "NEIGHBOR_Z", "NEIGHBOR_Z"), "S1/Z2"),
    ]
