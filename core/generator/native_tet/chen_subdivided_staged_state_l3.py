"""Parallel test-only staging certificate for exact boundary subdivisions.

The permanent raw-key staging gate remains intentionally unchanged.  This
adapter is a separate, stricter representation for a whole replacement whose
outer faces subdivide (rather than retain) immutable parent-boundary triangles.
It commits no production state and exposes no candidate on any failed check.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction

from core.generator.native_tet.chen_pipe_cluster_l0 import IndexTet, _orient6, _point
from core.generator.native_tet.chen_source_subdivision_l0 import (
    audit_source_triangle_subdivision_l1,
    oriented_boundary_faces_l1,
)
from core.generator.native_tet.chen_staged_state_l0 import (
    _as_index_tet,
    _boundary_faces,
    _face_key,
)


@dataclass(frozen=True)
class ChenSubdividedStagedCommitResult:
    """Atomic report-only result for a source-boundary-subdividing candidate."""

    accepted: bool
    reason: str
    committed_tets: tuple[tuple[int, IndexTet], ...]
    source_boundary_subdivision_preserved: bool
    volume_preserved: bool
    all_positive: bool
    child_face_incidence_valid: bool
    production_mesh_changed: bool


def certify_atomic_subdivided_boundary_replacement_l3(
    points: Sequence[Sequence[float | int | Fraction]],
    active_parents: Mapping[int, Sequence[int]],
    source_boundary_faces: Sequence[Sequence[int]],
    candidate_children: Mapping[int, Sequence[Sequence[int]]],
) -> ChenSubdividedStagedCommitResult:
    """Require one exact L1 subdivision of the complete original cavity shell."""
    rational = tuple(_point(point) for point in points)
    parents = {identifier: _as_index_tet(tet) for identifier, tet in active_parents.items()}
    if not parents or any(tet is None for tet in parents.values()):
        return ChenSubdividedStagedCommitResult(
            False, "invalid_active_parent", (), False, False, False, False, False
        )
    typed_parents: dict[int, IndexTet] = {
        identifier: tet for identifier, tet in parents.items() if tet is not None
    }
    if any(
        vertex < 0 or vertex >= len(rational) for tet in typed_parents.values() for vertex in tet
    ):
        return ChenSubdividedStagedCommitResult(
            False, "parent_index_out_of_range", (), False, False, False, False, False
        )
    try:
        declared = frozenset(_face_key(face) for face in source_boundary_faces)
    except ValueError:
        return ChenSubdividedStagedCommitResult(
            False, "invalid_source_boundary_face", (), False, False, False, False, False
        )
    before = tuple(typed_parents.values())
    if declared != _boundary_faces(before):
        return ChenSubdividedStagedCommitResult(
            False, "declared_source_boundary_mismatch", (), False, False, False, False, False
        )
    if set(candidate_children) != set(typed_parents):
        return ChenSubdividedStagedCommitResult(
            False,
            "candidate_must_replace_entire_active_cavity",
            (),
            False,
            False,
            False,
            False,
            False,
        )
    staged: list[tuple[int, IndexTet]] = []
    next_identifier = max(typed_parents) + 1
    for identifier in sorted(typed_parents):
        typed_children = tuple(_as_index_tet(child) for child in candidate_children[identifier])
        if not typed_children or any(child is None for child in typed_children):
            return ChenSubdividedStagedCommitResult(
                False, "invalid_candidate_child", (), False, False, False, False, False
            )
        for child in typed_children:
            assert child is not None
            staged.append((next_identifier, child))
            next_identifier += 1
    after = tuple(tet for _identifier, tet in staged)
    if any(vertex < 0 or vertex >= len(rational) for tet in after for vertex in tet):
        return ChenSubdividedStagedCommitResult(
            False, "candidate_index_out_of_range", (), False, False, False, False, False
        )
    before_volume = sum((abs(_orient6(rational, tet)) for tet in before), Fraction(0))
    after_volume = sum((_orient6(rational, tet) for tet in after), Fraction(0))
    all_positive = all(_orient6(rational, tet) > 0 for tet in after)
    face_incidence = Counter(face for tet in after for face in _tet_faces(tet))
    incidence_valid = all(count in (1, 2) for count in face_incidence.values())
    try:
        source_oriented = oriented_boundary_faces_l1(rational, before)
        candidate_oriented = oriented_boundary_faces_l1(rational, after)
        subdivision = audit_source_triangle_subdivision_l1(
            rational, source_oriented, candidate_oriented
        )
    except ValueError:
        return ChenSubdividedStagedCommitResult(
            False, "boundary_orientation_input_invalid", (), False, False, False, False, False
        )
    volume_preserved = before_volume == after_volume
    accepted = bool(all_positive and incidence_valid and subdivision.accepted and volume_preserved)
    return ChenSubdividedStagedCommitResult(
        accepted,
        "accepted" if accepted else "subdivided_staged_contract_failed",
        tuple(staged) if accepted else (),
        subdivision.accepted,
        volume_preserved,
        all_positive,
        incidence_valid,
        False,
    )


def _tet_faces(tet: IndexTet) -> tuple[tuple[int, int, int], ...]:
    return tuple(
        _face_key(tuple(tet[index] for index in range(4) if index != omitted))
        for omitted in range(4)
    )
