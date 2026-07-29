"""Report-only exact-source audit for the triangle-to-quad boundary adapter.

The sparse octree boundary is axis-aligned and fails the input-surface
contract.  This audit instead verifies the separate triangle-derived quad
surface before any volume realization, transition template, or writer can use
it.  It deliberately proves only the surface representation.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from .source_triangle_quadization_l0 import (
    SourceQuadization,
    all_quad_ball_precheck_l1,
    quadize_triangles_exact_l0,
)


@dataclass(frozen=True)
class ExactSourceQuadizationAudit:
    """Exact source-to-quad surface result; never a volume-fill certificate."""

    status: str
    source_face_count: int
    quad_count: int
    source_vertex_prefix_identical: bool
    exact_three_quads_per_source_face: bool
    oriented_closed_quad_surface: bool
    all_quad_sphere_precheck: bool
    euler_characteristic: int
    max_support_distance: float
    max_relative_area_error: float
    source_entities_preserved: bool
    production_mesh_changed: bool
    quadization: SourceQuadization


def _oriented_quad_edge_closed(points: np.ndarray, quads: np.ndarray) -> bool:
    """Require exactly one oppositely directed mate for every quad edge."""
    edges: Counter[tuple[int, int]] = Counter()
    for quad in np.asarray(quads, dtype=np.int64):
        if len(set(int(vertex) for vertex in quad)) != 4:
            return False
        for first, second in zip(quad, np.roll(quad, -1), strict=True):
            edges[(int(first), int(second))] += 1
    return bool(edges) and all(
        count == 1 and edges.get((end, start), 0) == 1 for (start, end), count in edges.items()
    )


def audit_exact_source_quadization_l1(
    vertices: np.ndarray,
    faces: np.ndarray,
    face_entities: Sequence[tuple[str, str]],
    *,
    tolerance: float = 1.0e-12,
) -> ExactSourceQuadizationAudit:
    """Audit source support, area, topology, and entity identity exactly enough for L1."""
    source_points = np.asarray(vertices, dtype=np.float64)
    source_faces = np.asarray(faces, dtype=np.int64)
    entities = tuple(face_entities)
    quadization = quadize_triangles_exact_l0(
        source_points, source_faces, entities, tolerance=tolerance
    )
    if not quadization.accepted:
        return ExactSourceQuadizationAudit(
            f"reject_quadization:{quadization.reason}",
            len(source_faces),
            0,
            False,
            False,
            False,
            False,
            0,
            quadization.max_support_distance,
            quadization.max_relative_area_error,
            False,
            False,
            quadization,
        )
    owner_counts = np.bincount(quadization.source_face_ids, minlength=len(source_faces))
    exact_three = bool(len(owner_counts) == len(source_faces) and np.all(owner_counts == 3))
    prefix_identical = bool(
        len(quadization.points) >= len(source_points)
        and np.array_equal(quadization.points[: len(source_points)], source_points)
    )
    oriented_closed = _oriented_quad_edge_closed(quadization.points, quadization.quads)
    sphere_precheck, characteristic = all_quad_ball_precheck_l1(
        quadization.points, quadization.quads
    )
    entities_preserved = bool(
        quadization.source_entities == entities
        and len(quadization.source_face_ids) == len(quadization.quads)
    )
    accepted = (
        prefix_identical
        and exact_three
        and oriented_closed
        and quadization.max_support_distance <= tolerance
        and quadization.max_relative_area_error <= tolerance
        and entities_preserved
    )
    return ExactSourceQuadizationAudit(
        "pass_exact_source_quadization" if accepted else "reject_exact_source_quadization_contract",
        len(source_faces),
        len(quadization.quads),
        prefix_identical,
        exact_three,
        oriented_closed,
        sphere_precheck,
        characteristic,
        quadization.max_support_distance,
        quadization.max_relative_area_error,
        entities_preserved,
        False,
        quadization,
    )
