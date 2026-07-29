"""L1 parent-face state ledger for Chen's neighbour-driven S/Z rule.

``Phi`` identifies a neighbouring child after a decomposition.  Chen's p.2035
selection rule needs an earlier datum: ``DType(neighbour, shared_parent_face)``.
This read-only ledger makes that datum explicit and validates it against actual
parent-face topology; it neither chooses a table row nor mutates a mesh.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from core.generator.native_tet.chen_sz_choice_l0 import (
    ChenSzChoiceResult,
    DecompositionType,
    eligible_sz_types_l0,
)

FaceKey = tuple[int, int, int]
IndexTet = tuple[int, int, int, int]


@dataclass(frozen=True)
class ChenSzNeighbourStateResult:
    """Exact parent-face lookup result; rejection carries no eligibility set."""

    accepted: bool
    reason: str
    shared_parent_face: FaceKey | None
    neighbour_tet: int | None
    choice: ChenSzChoiceResult | None
    production_mesh_changed: bool


def _as_tet(tet: Sequence[int]) -> IndexTet | None:
    values = tuple(int(value) for value in tet)
    if len(values) != 4 or len(set(values)) != 4:
        return None
    return values[0], values[1], values[2], values[3]


def _face_key(vertices: Sequence[int]) -> FaceKey:
    values = sorted(int(value) for value in vertices)
    if len(values) != 3 or len(set(values)) != 3:
        raise ValueError("a parent face must have three distinct vertices")
    return values[0], values[1], values[2]


def _parent_face_owners(tets: Sequence[IndexTet]) -> dict[FaceKey, tuple[int, ...]]:
    owners: dict[FaceKey, list[int]] = defaultdict(list)
    for index, tet in enumerate(tets):
        for omitted in range(4):
            owners[_face_key(tuple(tet[item] for item in range(4) if item != omitted))].append(
                index
            )
    return {face: tuple(indices) for face, indices in owners.items()}


def eligible_sz_types_from_parent_state_l1(
    parent_tets: Sequence[Sequence[int]],
    dtype_by_parent_face: Mapping[tuple[int, FaceKey], DecompositionType],
    *,
    tet_index: int,
    opposite_vertex: int,
) -> ChenSzNeighbourStateResult:
    """Apply p.2035 only after validating the DType record's real shared face."""
    raw_tets = tuple(_as_tet(tet) for tet in parent_tets)
    if not raw_tets or any(tet is None for tet in raw_tets):
        return ChenSzNeighbourStateResult(
            False, "invalid_parent_tetrahedron", None, None, None, False
        )
    tets = tuple(tet for tet in raw_tets if tet is not None)
    owners = _parent_face_owners(tets)
    for (owner_index, face), dtype in dtype_by_parent_face.items():
        if owner_index < 0 or owner_index >= len(tets) or dtype not in {"S", "Z"}:
            return ChenSzNeighbourStateResult(
                False, "invalid_dtype_record", None, None, None, False
            )
        if face not in owners or owner_index not in owners[face]:
            return ChenSzNeighbourStateResult(
                False, "dtype_record_not_on_parent_face", None, None, None, False
            )
    if tet_index < 0 or tet_index >= len(tets) or opposite_vertex not in tets[tet_index]:
        return ChenSzNeighbourStateResult(
            False, "invalid_query_parent_or_vertex", None, None, None, False
        )
    face = _face_key(tuple(vertex for vertex in tets[tet_index] if vertex != opposite_vertex))
    face_owners = owners[face]
    if len(face_owners) == 1:
        choice = eligible_sz_types_l0(
            neighbour_exists=False, neighbour_decomposed=False, neighbour_type=None
        )
        return ChenSzNeighbourStateResult(choice.accepted, choice.reason, face, None, choice, False)
    if len(face_owners) != 2:
        return ChenSzNeighbourStateResult(
            False, "parent_face_is_nonmanifold", face, None, None, False
        )
    neighbour = face_owners[0] if face_owners[1] == tet_index else face_owners[1]
    neighbour_type = dtype_by_parent_face.get((neighbour, face))
    choice = eligible_sz_types_l0(
        neighbour_exists=True,
        neighbour_decomposed=neighbour_type is not None,
        neighbour_type=neighbour_type,
    )
    return ChenSzNeighbourStateResult(
        choice.accepted, choice.reason, face, neighbour, choice if choice.accepted else None, False
    )
