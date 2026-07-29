"""Fail-closed source feature-provenance audit for exact quad boundaries.

Unlike a dihedral census, this module accepts only caller-supplied source-face
entity identities as authoritative. It exposes entity discontinuities along a
closed two-manifold triangular input without inferring CAD semantics from STL
geometry. The result is diagnostic-only: it does not choose a shell topology,
move a point, or alter production meshing.
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

SourceEntity = tuple[str, str]


@dataclass(frozen=True)
class SourceEntityBoundary:
    """An authoritative source edge separating two distinct face entities."""

    edge: tuple[int, int]
    incident_faces: tuple[int, int]
    incident_entities: tuple[SourceEntity, SourceEntity]


@dataclass(frozen=True)
class SourceFeatureProvenanceAudit:
    """Result of a read-only authority and closed-topology audit."""

    status: str
    source_face_count: int
    two_manifold_edge_count: int
    entity_boundaries: tuple[SourceEntityBoundary, ...]
    entity_boundary_components: tuple[tuple[int, ...], ...]
    supplied_entities_are_authoritative: bool
    source_geometry_unchanged: bool
    production_mesh_changed: bool


def _components(boundaries: Sequence[SourceEntityBoundary]) -> tuple[tuple[int, ...], ...]:
    adjacency: dict[int, set[int]] = defaultdict(set)
    for boundary in boundaries:
        first, second = boundary.edge
        adjacency[first].add(second)
        adjacency[second].add(first)
    unseen = set(adjacency)
    components: list[tuple[int, ...]] = []
    while unseen:
        seed = min(unseen)
        unseen.remove(seed)
        component: set[int] = set()
        pending: deque[int] = deque((seed,))
        while pending:
            vertex = pending.popleft()
            component.add(vertex)
            for neighbour in sorted(adjacency[vertex]):
                if neighbour in unseen:
                    unseen.remove(neighbour)
                    pending.append(neighbour)
        components.append(tuple(sorted(component)))
    return tuple(components)


def audit_source_entity_boundaries_l0(
    vertices: np.ndarray,
    faces: np.ndarray,
    face_entities: Sequence[SourceEntity],
) -> SourceFeatureProvenanceAudit:
    """Audit authoritative entity transitions, never infer them from geometry.

    ``face_entities`` is authoritative only because the caller supplies it as
    source metadata. Missing, blank, open, or non-manifold input fails closed;
    an all-one-entity input is accepted with zero entity-boundary edges.
    """
    points = np.asarray(vertices, dtype=np.float64)
    triangles = np.asarray(faces, dtype=np.int64)
    if points.ndim != 2 or points.shape[1] != 3 or triangles.ndim != 2 or triangles.shape[1] != 3:
        return SourceFeatureProvenanceAudit(
            "reject_invalid_input", 0, 0, (), (), False, True, False
        )
    if np.any(triangles < 0) or np.any(triangles >= len(points)):
        return SourceFeatureProvenanceAudit(
            "reject_face_index_out_of_range", len(triangles), 0, (), (), False, True, False
        )
    if len(face_entities) != len(triangles) or any(
        not patch or not entity for patch, entity in face_entities
    ):
        return SourceFeatureProvenanceAudit(
            "reject_missing_authoritative_face_entities",
            len(triangles),
            0,
            (),
            (),
            False,
            True,
            False,
        )

    points_before, triangles_before = points.copy(), triangles.copy()
    owners: dict[tuple[int, int], list[int]] = defaultdict(list)
    for face_index, triangle in enumerate(triangles):
        if len({int(value) for value in triangle}) != 3:
            return SourceFeatureProvenanceAudit(
                "reject_degenerate_source_triangle", len(triangles), 0, (), (), False, True, False
            )
        for first, second in zip(triangle, np.roll(triangle, -1), strict=True):
            first_vertex, second_vertex = int(first), int(second)
            edge = (min(first_vertex, second_vertex), max(first_vertex, second_vertex))
            owners[edge].append(face_index)
    unchanged = bool(
        np.array_equal(points, points_before) and np.array_equal(triangles, triangles_before)
    )
    if any(len(face_owners) != 2 for face_owners in owners.values()):
        return SourceFeatureProvenanceAudit(
            "reject_source_not_closed_two_manifold",
            len(triangles),
            0,
            (),
            (),
            False,
            unchanged,
            False,
        )

    boundaries: list[SourceEntityBoundary] = []
    for edge, face_owners in sorted(owners.items()):
        first_face, second_face = sorted(face_owners)
        first_entity = face_entities[first_face]
        second_entity = face_entities[second_face]
        if first_entity != second_entity:
            boundaries.append(
                SourceEntityBoundary(
                    edge,
                    (first_face, second_face),
                    (first_entity, second_entity),
                )
            )
    return SourceFeatureProvenanceAudit(
        "pass_authoritative_source_entity_boundaries",
        len(triangles),
        len(owners),
        tuple(boundaries),
        _components(boundaries),
        True,
        unchanged,
        False,
    )
