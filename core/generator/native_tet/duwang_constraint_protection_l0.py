"""Read-only direct-source-face protection audit for local tet candidates.

Du--Wang (2004) requires a candidate cavity to preserve every already
recovered constraint.  This minimal L0 ledger deliberately covers only direct
source faces already present in the tet-face census; it does not treat a
source-face subdivision as equivalent, insert points, choose a cavity, or
modify a production mesh.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

FaceKey = tuple[int, int, int]
Tet = tuple[int, int, int, int]


@dataclass(frozen=True)
class DuWangConstraintProtectionResult:
    """Exact before/after constraint-face census; no candidate is applied."""

    accepted: bool
    reason: str
    protected_faces: tuple[FaceKey, ...]
    present_before: tuple[FaceKey, ...]
    missing_before: tuple[FaceKey, ...]
    present_after: tuple[FaceKey, ...]
    would_delete: tuple[FaceKey, ...]
    production_mesh_changed: bool


def _as_tet(tet: Sequence[int]) -> Tet:
    values = tuple(int(vertex) for vertex in tet)
    if len(values) != 4 or len(set(values)) != 4:
        raise ValueError("each tetrahedron must have four distinct vertices")
    return values[0], values[1], values[2], values[3]


def _face_key(face: Sequence[int]) -> FaceKey:
    values = tuple(sorted(int(vertex) for vertex in face))
    if len(values) != 3 or len(set(values)) != 3:
        raise ValueError("each protected face must have three distinct vertices")
    return values[0], values[1], values[2]


def _face_census(tets: Sequence[Tet]) -> Counter[FaceKey]:
    faces: Counter[FaceKey] = Counter()
    for tet in tets:
        for omitted in range(4):
            faces[_face_key(tuple(tet[index] for index in range(4) if index != omitted))] += 1
    return faces


def audit_direct_constraint_face_protection_l0(
    before_tets: Sequence[Sequence[int]],
    after_tets: Sequence[Sequence[int]],
    protected_faces: Sequence[Sequence[int]],
) -> DuWangConstraintProtectionResult:
    """Report whether a candidate removes any previously present direct face.

    A protected face absent before is reported as ``missing_before`` rather
    than silently claimed preserved.  A source subdivision is intentionally
    out of scope for L0 and must use the exact source-subdivision ledger later.
    """
    try:
        before = tuple(_as_tet(tet) for tet in before_tets)
        after = tuple(_as_tet(tet) for tet in after_tets)
        protected = tuple(sorted({_face_key(face) for face in protected_faces}))
    except ValueError:
        return DuWangConstraintProtectionResult(
            False, "invalid_tetrahedron_or_protected_face", (), (), (), (), (), False
        )
    if not protected:
        return DuWangConstraintProtectionResult(
            False, "empty_protected_face_set", (), (), (), (), (), False
        )
    before_faces = _face_census(before)
    after_faces = _face_census(after)
    present_before = tuple(face for face in protected if before_faces[face] > 0)
    missing_before = tuple(face for face in protected if before_faces[face] == 0)
    present_after = tuple(face for face in protected if after_faces[face] > 0)
    would_delete = tuple(face for face in present_before if after_faces[face] == 0)
    accepted = not missing_before and not would_delete
    reason = "preserved" if accepted else "missing_before" if missing_before else "would_delete"
    return DuWangConstraintProtectionResult(
        accepted,
        reason,
        protected,
        present_before,
        missing_before,
        present_after,
        would_delete,
        False,
    )
