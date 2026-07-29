"""Exact, read-only finite source-triangle cavity census for Chen templates.

An edge ledger cannot explain every Table-5 Phi neighbour: a neighbouring
clusterel can be cut by the *source triangle* without containing the selected
source edge.  This L0 representation classifies the full finite triangle/tet
cavity, records its face-connected components, and fails closed before any
Case-2 or S/Z template is chosen.
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from core.generator.native_tet.chen_clusterel_type_l0 import (
    ChenClusterelTypeResult,
    classify_clusterel_type,
)
from core.generator.native_tet.chen_source_triangle_fragment_l1 import (
    audit_source_triangle_fragment_l1,
)

IndexTet = tuple[int, int, int, int]
FaceKey = tuple[int, int, int]


@dataclass(frozen=True)
class ChenTriangleCavityClusterel:
    """One active finite source-triangle clusterel and its exact type."""

    parent_index: int
    classification: ChenClusterelTypeResult


@dataclass(frozen=True)
class ChenSourceTriangleCavityResult:
    """Fail-closed cavity census; rejected inputs expose no partial cavity."""

    accepted: bool
    reason: str
    clusterels: tuple[ChenTriangleCavityClusterel, ...]
    face_connected_components: tuple[tuple[int, ...], ...]


def _as_tet(tet: Sequence[int]) -> IndexTet | None:
    values = tuple(int(vertex) for vertex in tet)
    if len(values) != 4 or len(set(values)) != 4:
        return None
    return values[0], values[1], values[2], values[3]


def _face_key(vertices: Sequence[int]) -> FaceKey:
    ordered = tuple(sorted(int(vertex) for vertex in vertices))
    if len(ordered) != 3 or len(set(ordered)) != 3:
        raise ValueError("a tetrahedron face must contain three distinct vertices")
    return ordered[0], ordered[1], ordered[2]


def _tet_faces(tet: IndexTet) -> tuple[FaceKey, FaceKey, FaceKey, FaceKey]:
    faces = [
        _face_key(tuple(tet[index] for index in range(4) if index != omitted))
        for omitted in range(4)
    ]
    return faces[0], faces[1], faces[2], faces[3]


def _face_components(
    active_indices: set[int], tets: Sequence[IndexTet]
) -> tuple[tuple[int, ...], ...]:
    owners: dict[FaceKey, list[int]] = defaultdict(list)
    for index in active_indices:
        for face in _tet_faces(tets[index]):
            owners[face].append(index)
    adjacency: dict[int, set[int]] = {index: set() for index in active_indices}
    for face_owners in owners.values():
        if len(face_owners) == 2:
            first, second = face_owners
            adjacency[first].add(second)
            adjacency[second].add(first)
    components: list[tuple[int, ...]] = []
    unseen = set(active_indices)
    while unseen:
        seed = min(unseen)
        component: set[int] = set()
        pending: deque[int] = deque((seed,))
        unseen.remove(seed)
        while pending:
            current = pending.popleft()
            component.add(current)
            for neighbor in sorted(adjacency[current]):
                if neighbor in unseen:
                    unseen.remove(neighbor)
                    pending.append(neighbor)
        components.append(tuple(sorted(component)))
    return tuple(components)


def classify_source_triangle_cavity(
    points: Sequence[Sequence[float | int | Fraction]],
    parent_tets: Sequence[Sequence[int]],
    source_triangle: Sequence[Sequence[float | int | Fraction]],
) -> ChenSourceTriangleCavityResult:
    """Classify the complete finite triangle/tet cavity without mutation."""
    if len(source_triangle) != 3:
        raise ValueError("a source triangle requires exactly three points")
    typed_tets = tuple(_as_tet(tet) for tet in parent_tets)
    if not typed_tets or any(tet is None for tet in typed_tets):
        return ChenSourceTriangleCavityResult(False, "invalid_parent_tetrahedron", (), ())
    tets = tuple(tet for tet in typed_tets if tet is not None)
    if any(vertex < 0 or vertex >= len(points) for tet in tets for vertex in tet):
        return ChenSourceTriangleCavityResult(False, "parent_index_out_of_range", (), ())
    clusterels: list[ChenTriangleCavityClusterel] = []
    for index, tet in enumerate(tets):
        result = classify_clusterel_type(tuple(points[vertex] for vertex in tet), source_triangle)
        # Contact with the source-triangle boundary is ambiguous even when it
        # has zero area.  Preserve the original fail-closed rejection rather
        # than masking it as an unrelated parent.
        if not result.accepted and result.reason == "constraint_boundary_touch":
            return ChenSourceTriangleCavityResult(
                False,
                f"clusterel_rejected:{index}:{result.reason}",
                (),
                (),
            )
        # A whole parent mesh necessarily contains tetrahedra that do not
        # meet this finite source face.  They are outside the cavity, not an
        # unsupported zero-edge clusterel.  Establish that distinction with
        # the exact positive-area fragment predicate before classifying a
        # Chen template type.
        fragment = audit_source_triangle_fragment_l1(
            tuple(points[vertex] for vertex in tet), source_triangle
        )
        if fragment.reason == "source_triangle_has_no_positive_area_inside_parent":
            continue
        if not fragment.accepted:
            return ChenSourceTriangleCavityResult(
                False,
                f"fragment_rejected:{index}:{fragment.reason}",
                (),
                (),
            )
        if not result.accepted:
            return ChenSourceTriangleCavityResult(
                False,
                f"clusterel_rejected:{index}:{result.reason}",
                (),
                (),
            )
        if result.clusterel_type != "CO_PLAN":
            clusterels.append(ChenTriangleCavityClusterel(index, result))
    active_indices = {item.parent_index for item in clusterels}
    return ChenSourceTriangleCavityResult(
        True,
        "accepted",
        tuple(clusterels),
        _face_components(active_indices, tets),
    )
