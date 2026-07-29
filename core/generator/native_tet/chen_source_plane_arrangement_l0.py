"""Read-only exact source-plane arrangement for a Chen source-facet cavity.

One missing source face can cut many tetrahedra.  Before a local Chen S/Z
template is selected, the finite source-triangle fragments must form one
owner-consistent planar arrangement.  This module builds that arrangement from
the existing exact fragment oracle.  It never creates a point, changes a tet,
or chooses a template.
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from core.generator.native_tet.chen_clusterel_node_state_l0 import (
    ChenClusterelNodeStateResult,
    classify_clusterel_node_states_l0,
)
from core.generator.native_tet.chen_clusterel_type_l0 import (
    ClusterelType,
    classify_clusterel_type,
)
from core.generator.native_tet.chen_penetration_l0 import RationalPoint, _point
from core.generator.native_tet.chen_source_triangle_coverage_l2 import (
    ChenSourceTriangleCoverageResult,
    certify_source_triangle_coverage_l2,
)
from core.generator.native_tet.chen_source_triangle_fragment_l1 import (
    ParameterPoint,
    audit_source_triangle_fragment_l1,
)

IndexTet = tuple[int, int, int, int]
SegmentKey = tuple[ParameterPoint, ParameterPoint]


@dataclass(frozen=True)
class ChenSourcePlaneFragment:
    """One positive-area source-plane fragment, retaining its local status."""

    parent_index: int
    parameter_vertices: tuple[ParameterPoint, ...]
    clusterel_type: ClusterelType | None
    classification_reason: str
    node_reason: str


@dataclass(frozen=True)
class ChenSourcePlaneArrangementResult:
    """Fail-closed multi-tet prerequisite for a later atomic cavity plan."""

    accepted: bool
    reason: str
    fragments: tuple[ChenSourcePlaneFragment, ...]
    components: tuple[tuple[int, ...], ...]
    boundary_segment_count: int
    internal_segment_count: int
    boundary_contact_parent_indices: tuple[int, ...]
    unresolved_parent_indices: tuple[int, ...]
    literal_template_ready: bool
    coverage: ChenSourceTriangleCoverageResult | None
    source_points_unchanged: bool
    production_mesh_changed: bool


def _as_tet(tet: Sequence[int]) -> IndexTet | None:
    values = tuple(int(value) for value in tet)
    if len(values) != 4 or len(set(values)) != 4:
        return None
    return values[0], values[1], values[2], values[3]


def _segment_key(first: ParameterPoint, second: ParameterPoint) -> SegmentKey:
    return (first, second) if first <= second else (second, first)


def _fragment_segments(vertices: Sequence[ParameterPoint]) -> tuple[SegmentKey, ...]:
    return tuple(
        _segment_key(first, second)
        for first, second in zip(vertices, (*vertices[1:], vertices[0]), strict=True)
        if first != second
    )


def _on_source_boundary(segment: SegmentKey) -> bool:
    """Whether a parameter segment lies on one edge of ``u,v >= 0, u+v <= 1``."""
    first, second = segment
    return bool(
        (first[0] == 0 and second[0] == 0)
        or (first[1] == 0 and second[1] == 0)
        or (first[0] + first[1] == 1 and second[0] + second[1] == 1)
    )


def _components(
    parent_indices: Sequence[int], internal_segments: dict[SegmentKey, tuple[int, ...]]
) -> tuple[tuple[int, ...], ...]:
    adjacency: dict[int, set[int]] = {index: set() for index in parent_indices}
    for owners in internal_segments.values():
        if len(owners) == 2:
            first, second = owners
            adjacency[first].add(second)
            adjacency[second].add(first)
    unseen = set(parent_indices)
    result: list[tuple[int, ...]] = []
    while unseen:
        seed = min(unseen)
        pending: deque[int] = deque((seed,))
        unseen.remove(seed)
        component: set[int] = set()
        while pending:
            current = pending.popleft()
            component.add(current)
            for neighbour in sorted(adjacency[current]):
                if neighbour in unseen:
                    unseen.remove(neighbour)
                    pending.append(neighbour)
        result.append(tuple(sorted(component)))
    return tuple(result)


def _boundary_contact_clusterel_type(
    node_state: ChenClusterelNodeStateResult,
) -> ClusterelType | None:
    """Resolve only a source-boundary contact represented by strict tet edges.

    ``classify_clusterel_type`` intentionally rejects every source-boundary
    contact.  Once the planar segment ledger has established that the contact
    is on the source boundary, a set of distinct ``NOD_MID`` intersections is
    the same local cut count as the strict case.  Endpoint/extension nodes or
    duplicate points remain unresolved: they need an explicit degeneracy row,
    not a guessed S/Z template.
    """
    if not node_state.accepted:
        return None
    middle_nodes = tuple(node for node in node_state.nodes if node.node_type == "NOD_MID")
    if any(node.node_type not in {"NOD_NUL", "NOD_MID"} for node in node_state.nodes):
        return None
    points = tuple(node.point for node in middle_nodes)
    if any(point is None for point in points) or len(set(points)) != len(points):
        return None
    return {
        1: "ONE_EDG",
        2: "TWO_EDG",
        3: "THR_EDG",
        4: "FOU_EDG",
    }.get(len(middle_nodes))


def build_source_plane_arrangement_l0(
    points: Sequence[Sequence[float | int | Fraction]],
    parent_tets: Sequence[Sequence[int]],
    source_triangle: Sequence[Sequence[float | int | Fraction]],
) -> ChenSourcePlaneArrangementResult:
    """Audit a complete source-facet cavity without selecting a Chen template.

    A valid arrangement has an exact source-triangle partition, one connected
    set of positive-area fragments, one owner for every source-boundary
    segment, and two distinct owners for every internal arrangement segment.
    Endpoint contacts on the *source* boundary are reported, not guessed into
    a strict template.  Coplanar/touch ambiguity remains fail-closed.
    """
    before = tuple(_point(point) for point in points)
    source = tuple(_point(point) for point in source_triangle)
    if len(source) != 3:
        raise ValueError("a source triangle requires exactly three points")
    typed = tuple(_as_tet(tet) for tet in parent_tets)
    if not typed or any(tet is None for tet in typed):
        return ChenSourcePlaneArrangementResult(
            False, "invalid_parent_tetrahedron", (), (), 0, 0, (), (), False, None, True, False
        )
    tets = tuple(tet for tet in typed if tet is not None)
    if any(vertex < 0 or vertex >= len(before) for tet in tets for vertex in tet):
        return ChenSourcePlaneArrangementResult(
            False, "parent_index_out_of_range", (), (), 0, 0, (), (), False, None, True, False
        )

    fragments: list[ChenSourcePlaneFragment] = []
    segment_owners: dict[SegmentKey, list[int]] = defaultdict(list)
    boundary_contacts: list[int] = []
    unresolved: set[int] = set()
    for parent_index, tet in enumerate(tets):
        local_points = tuple(before[index] for index in tet)
        fragment = audit_source_triangle_fragment_l1(local_points, source)
        if fragment.reason == "source_triangle_has_no_positive_area_inside_parent":
            continue
        if not fragment.accepted:
            return ChenSourcePlaneArrangementResult(
                False,
                f"fragment_failed:{parent_index}:{fragment.reason}",
                (), (), 0, 0, (), (), False, None, before == tuple(_point(point) for point in points), False,
            )
        classification = classify_clusterel_type(local_points, source)
        node_state: ChenClusterelNodeStateResult = classify_clusterel_node_states_l0(local_points, source)
        clusterel_type = classification.clusterel_type if classification.accepted else None
        if classification.reason == "constraint_boundary_touch":
            clusterel_type = _boundary_contact_clusterel_type(node_state)
        fragments.append(ChenSourcePlaneFragment(
            parent_index,
            fragment.parameter_vertices,
            clusterel_type,
            classification.reason,
            node_state.reason,
        ))
        for segment in _fragment_segments(fragment.parameter_vertices):
            segment_owners[segment].append(parent_index)
        if classification.reason == "constraint_boundary_touch":
            boundary_contacts.append(parent_index)
            if clusterel_type is None:
                unresolved.add(parent_index)
        elif not classification.accepted:
            unresolved.add(parent_index)
        if not node_state.accepted:
            unresolved.add(parent_index)

    coverage = certify_source_triangle_coverage_l2(before, tets, source)
    if not coverage.accepted:
        return ChenSourcePlaneArrangementResult(
            False,
            f"source_coverage_failed:{coverage.reason}",
            tuple(fragments), (), 0, 0, tuple(sorted(boundary_contacts)), tuple(sorted(unresolved)), False,
            coverage, before == tuple(_point(point) for point in points), False,
        )

    boundary_segments: dict[SegmentKey, tuple[int, ...]] = {}
    internal_segments: dict[SegmentKey, tuple[int, ...]] = {}
    for segment, raw_owners in segment_owners.items():
        owners = tuple(sorted(set(raw_owners)))
        if _on_source_boundary(segment):
            boundary_segments[segment] = owners
            if len(owners) != 1:
                unresolved.update(owners)
        else:
            internal_segments[segment] = owners
            if len(owners) != 2:
                unresolved.update(owners)
    component_values = _components(
        tuple(fragment.parent_index for fragment in fragments), internal_segments
    )
    if len(component_values) != 1:
        for component in component_values:
            unresolved.update(component)
    literal_ready = bool(fragments) and all(
        fragment.clusterel_type in {"THR_EDG", "FOU_EDG"} for fragment in fragments
    ) and not unresolved and len(component_values) == 1
    unchanged = before == tuple(_point(point) for point in points)
    accepted = bool(fragments) and not unresolved and len(component_values) == 1 and unchanged
    reason = "accepted_literal_template_arrangement" if literal_ready else (
        "accepted_nonliteral_or_boundary_contact_arrangement" if accepted else "unresolved_source_plane_arrangement"
    )
    return ChenSourcePlaneArrangementResult(
        accepted,
        reason,
        tuple(fragments),
        component_values,
        len(boundary_segments),
        len(internal_segments),
        tuple(sorted(boundary_contacts)),
        tuple(sorted(unresolved)),
        literal_ready,
        coverage,
        unchanged,
        False,
    )
