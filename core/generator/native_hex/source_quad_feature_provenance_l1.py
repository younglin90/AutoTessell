"""L1 audit that exact triangle-to-quad subdivision preserves entity boundaries.

The source quadizer splits every source edge at its exact midpoint. This audit
proves that a caller-supplied source entity discontinuity becomes exactly two
quad-edge discontinuities, and that no other quad edge is promoted to a
feature. It is report-only and is deliberately disconnected from shell
topology, point motion, and production meshing.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from .source_feature_provenance_l0 import audit_source_entity_boundaries_l0
from .source_triangle_quadization_l0 import SourceQuadization, quadize_triangles_exact_l0


@dataclass(frozen=True)
class ExactQuadFeatureProvenanceAudit:
    """Entity-boundary preservation result for an exact source quad subdivision."""

    status: str
    source_entity_boundary_edge_count: int
    expected_quad_entity_boundary_segment_count: int
    observed_quad_entity_boundary_segment_count: int
    every_source_boundary_split_exactly_twice: bool
    no_spurious_quad_entity_boundaries: bool
    source_vertex_prefix_identical: bool
    production_mesh_changed: bool
    quadization: SourceQuadization


def _quad_edge_owners(quads: np.ndarray) -> dict[tuple[int, int], list[int]]:
    owners: dict[tuple[int, int], list[int]] = defaultdict(list)
    for quad_id, quad in enumerate(np.asarray(quads, dtype=np.int64)):
        for first, second in zip(quad, np.roll(quad, -1), strict=True):
            first_vertex, second_vertex = int(first), int(second)
            edge = (min(first_vertex, second_vertex), max(first_vertex, second_vertex))
            owners[edge].append(quad_id)
    return owners


def audit_quadized_entity_boundaries_l1(
    vertices: np.ndarray,
    faces: np.ndarray,
    face_entities: Sequence[tuple[str, str]],
    *,
    tolerance: float = 1.0e-12,
) -> ExactQuadFeatureProvenanceAudit:
    """Prove exact propagation of supplied source entity boundaries into quads."""
    source_points = np.asarray(vertices, dtype=np.float64)
    source_faces = np.asarray(faces, dtype=np.int64)
    entities = tuple(face_entities)
    source = audit_source_entity_boundaries_l0(source_points, source_faces, entities)
    quadization = quadize_triangles_exact_l0(
        source_points, source_faces, entities, tolerance=tolerance
    )
    if source.status != "pass_authoritative_source_entity_boundaries" or not quadization.accepted:
        return ExactQuadFeatureProvenanceAudit(
            "reject_source_or_quadization_contract",
            0,
            0,
            0,
            False,
            False,
            False,
            False,
            quadization,
        )

    midpoint_ids = {
        (first, second): midpoint
        for first, second, midpoint in quadization.source_edge_midpoint_ids
    }
    expected: set[tuple[int, int]] = set()
    valid_segments = True
    for boundary in source.entity_boundaries:
        midpoint = midpoint_ids.get(boundary.edge)
        if midpoint is None:
            valid_segments = False
            continue
        first, second = boundary.edge
        expected.update(
            (
                (min(first, midpoint), max(first, midpoint)),
                (min(midpoint, second), max(midpoint, second)),
            )
        )

    owners = _quad_edge_owners(quadization.quads)
    observed: set[tuple[int, int]] = set()
    for edge, quad_owners in owners.items():
        if len(quad_owners) != 2:
            valid_segments = False
            continue
        first_quad, second_quad = quad_owners
        first_entity = entities[int(quadization.source_face_ids[first_quad])]
        second_entity = entities[int(quadization.source_face_ids[second_quad])]
        if first_entity != second_entity:
            observed.add(edge)
    prefix_identical = bool(
        len(quadization.points) >= len(source_points)
        and np.array_equal(quadization.points[: len(source_points)], source_points)
    )
    exact_twice = (
        valid_segments
        and len(expected) == 2 * len(source.entity_boundaries)
        and expected <= observed
    )
    no_spurious = observed <= expected
    accepted = exact_twice and no_spurious and prefix_identical
    return ExactQuadFeatureProvenanceAudit(
        (
            "pass_exact_quad_entity_boundary_provenance"
            if accepted
            else "reject_exact_quad_entity_boundary_provenance"
        ),
        len(source.entity_boundaries),
        len(expected),
        len(observed),
        exact_twice,
        no_spurious,
        prefix_identical,
        False,
        quadization,
    )
