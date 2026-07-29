"""L2 shared-face compatibility measurements for Chen Table-6 S/Z rows."""

from __future__ import annotations

from fractions import Fraction

from core.generator.native_tet.chen_pipel_two_edge_source_match_l1 import (
    certify_two_edge_pipel_source_match_l1,
)
from core.generator.native_tet.chen_staged_state_l0 import _boundary_faces
from core.generator.native_tet.chen_subdivided_staged_state_l3 import (
    ChenSubdividedStagedCommitResult,
    certify_atomic_subdivided_boundary_replacement_l3,
)


_POINTS = (
    (0, 0, 0), (4, 0, 0), (0, 4, 0), (2, 2, 3), (-1, -1, -2),
    (1, 1, -1), (4, 2, 2), (2, Fraction(4, 3), 0),
    (Fraction(5, 4), Fraction(5, 4), 0),
)
_PARENTS = (
    (5, 0, 1, 4), (5, 0, 2, 4), (5, 6, 2, 1), (5, 6, 3, 1),
    (5, 0, 3, 1), (5, 6, 3, 2), (5, 0, 3, 2),
)
_ACTIVE = {3: _PARENTS[3], 5: _PARENTS[5]}
_BOUNDARY = tuple(sorted(_boundary_faces(tuple(_ACTIVE.values()))))


def _candidate(first_scheme: str, second_scheme: str) -> ChenSubdividedStagedCommitResult:
    first = certify_two_edge_pipel_source_match_l1(
        _POINTS, _PARENTS, _POINTS[7], _POINTS[8],
        target_parent_index=3, ordered_parent=(6, 3, 1, 5),
        first_intersection=7, second_intersection=8, scheme=first_scheme,
    )
    second = certify_two_edge_pipel_source_match_l1(
        _POINTS, _PARENTS, _POINTS[7], _POINTS[8],
        target_parent_index=5, ordered_parent=(6, 3, 2, 5),
        first_intersection=7, second_intersection=8, scheme=second_scheme,
    )
    assert first.accepted and first.template is not None
    assert second.accepted and second.template is not None
    return certify_atomic_subdivided_boundary_replacement_l3(
        _POINTS, _ACTIVE, _BOUNDARY,
        {3: first.template.replacement_tets, 5: second.template.replacement_tets},
    )


def test_shared_face_compatibility_depends_on_explicit_parent_orientation_not_letters_alone() -> None:
    same_s = _candidate("NEIGHBOR_S", "NEIGHBOR_S")
    same_z = _candidate("NEIGHBOR_Z", "NEIGHBOR_Z")
    mixed_sz = _candidate("NEIGHBOR_S", "NEIGHBOR_Z")
    mixed_zs = _candidate("NEIGHBOR_Z", "NEIGHBOR_S")

    assert same_s.accepted and same_z.accepted
    assert not mixed_sz.accepted and not mixed_zs.accepted
    assert not mixed_sz.source_boundary_subdivision_preserved
    assert not mixed_zs.source_boundary_subdivision_preserved
