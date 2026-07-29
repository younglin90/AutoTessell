"""Immutable, test-only staging state for Chen boundary-recovery candidates.

The dense production CDT path cannot represent a decomposed neighbour beside an
unsplit parent safely.  This adapter instead validates a *whole candidate
replacement* off-mesh, then reports either the complete replacement state or
no state at all.  Its hard contract is exact exterior-face identity, positive
orientation, and exact total six-volume conservation.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction

from core.generator.native_tet.chen_pipe_cluster_l0 import IndexTet, _orient6, _point

FaceKey = tuple[int, int, int]


@dataclass(frozen=True)
class ChenStagedCommitResult:
    """Atomic candidate result; rejection exposes no staged connectivity."""

    accepted: bool
    reason: str
    committed_tets: tuple[tuple[int, IndexTet], ...]
    boundary_preserved: bool
    volume_preserved: bool
    all_positive: bool
    required_source_edge_recovered: bool


def _face_key(vertices: Sequence[int]) -> FaceKey:
    ordered = sorted(int(vertex) for vertex in vertices)
    if len(ordered) != 3 or len(set(ordered)) != 3:
        raise ValueError("a face must contain three distinct vertices")
    return ordered[0], ordered[1], ordered[2]


def _tet_faces(tet: IndexTet) -> tuple[FaceKey, FaceKey, FaceKey, FaceKey]:
    faces = [
        _face_key(tuple(tet[index] for index in range(4) if index != omitted))
        for omitted in range(4)
    ]
    return faces[0], faces[1], faces[2], faces[3]


def _as_index_tet(tet: Sequence[int]) -> IndexTet | None:
    values = tuple(int(vertex) for vertex in tet)
    if len(values) != 4 or len(set(values)) != 4:
        return None
    return values[0], values[1], values[2], values[3]


def _boundary_faces(tets: Sequence[IndexTet]) -> frozenset[FaceKey]:
    counts: Counter[FaceKey] = Counter()
    for tet in tets:
        counts.update(_tet_faces(tet))
    return frozenset(face for face, count in counts.items() if count == 1)


def _all_positive(
    points: Sequence[tuple[Fraction, Fraction, Fraction]], tets: Sequence[IndexTet]
) -> bool:
    return all(_orient6(points, tet) > 0 for tet in tets)


def _contains_edge(tets: Sequence[IndexTet], edge: tuple[int, int] | None) -> bool:
    if edge is None:
        return True
    first, second = edge
    return any(first in tet and second in tet for tet in tets)


def certify_atomic_staged_replacement(
    points: Sequence[Sequence[float | int | Fraction]],
    active_parents: Mapping[int, Sequence[int]],
    source_boundary_faces: Sequence[Sequence[int]],
    candidate_children: Mapping[int, Sequence[Sequence[int]]],
    *,
    required_source_edge: tuple[int, int] | None = None,
) -> ChenStagedCommitResult:
    """Validate an all-or-nothing replacement against the original boundary."""
    rational_points = tuple(_point(point) for point in points)
    parents = {int(identifier): _as_index_tet(tet) for identifier, tet in active_parents.items()}
    if not parents or any(tet is None for tet in parents.values()):
        return ChenStagedCommitResult(
            False, "invalid_active_parent", (), False, False, False, False
        )
    typed_parents: dict[int, IndexTet] = {
        identifier: tet for identifier, tet in parents.items() if tet is not None
    }
    if any(
        vertex < 0 or vertex >= len(rational_points)
        for tet in typed_parents.values()
        for vertex in tet
    ):
        return ChenStagedCommitResult(
            False, "parent_index_out_of_range", (), False, False, False, False
        )
    try:
        declared_boundary = frozenset(_face_key(face) for face in source_boundary_faces)
    except ValueError:
        return ChenStagedCommitResult(
            False, "invalid_source_boundary_face", (), False, False, False, False
        )
    before_tets = tuple(typed_parents.values())
    actual_before_boundary = _boundary_faces(before_tets)
    if declared_boundary != actual_before_boundary:
        return ChenStagedCommitResult(
            False, "declared_source_boundary_mismatch", (), False, False, False, False
        )
    if not candidate_children:
        return ChenStagedCommitResult(
            False, "empty_candidate_replacement", (), True, False, False, False
        )
    if any(identifier not in typed_parents for identifier in candidate_children):
        return ChenStagedCommitResult(
            False, "candidate_parent_not_active", (), False, False, False, False
        )

    staged: list[tuple[int, IndexTet]] = []
    next_identifier = max(typed_parents) + 1
    for identifier in sorted(typed_parents):
        raw_children = candidate_children.get(identifier)
        if raw_children is None:
            staged.append((identifier, typed_parents[identifier]))
            continue
        typed_children = tuple(_as_index_tet(child) for child in raw_children)
        if not typed_children or any(child is None for child in typed_children):
            return ChenStagedCommitResult(
                False, "invalid_candidate_child", (), False, False, False, False
            )
        for child in typed_children:
            assert child is not None
            staged.append((next_identifier, child))
            next_identifier += 1
    after_tets = tuple(tet for _identifier, tet in staged)
    if any(vertex < 0 or vertex >= len(rational_points) for tet in after_tets for vertex in tet):
        return ChenStagedCommitResult(
            False, "candidate_index_out_of_range", (), False, False, False, False
        )

    before_volume = sum((abs(_orient6(rational_points, tet)) for tet in before_tets), Fraction(0))
    after_volume = sum((abs(_orient6(rational_points, tet)) for tet in after_tets), Fraction(0))
    all_positive = _all_positive(rational_points, after_tets)
    boundary_preserved = _boundary_faces(after_tets) == declared_boundary
    recovered = _contains_edge(after_tets, required_source_edge)
    volume_preserved = before_volume == after_volume
    accepted = all_positive and boundary_preserved and volume_preserved and recovered
    return ChenStagedCommitResult(
        accepted,
        "accepted" if accepted else "staged_contract_failed",
        tuple(staged) if accepted else (),
        boundary_preserved,
        volume_preserved,
        all_positive,
        recovered,
    )
