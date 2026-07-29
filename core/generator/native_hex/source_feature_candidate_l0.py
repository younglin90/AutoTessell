"""Geometry-only feature-candidate audit for exact-quad shell prerequisites.

An STL has triangles but normally no authoritative CAD ridge/corner entities.
This module may measure dihedral candidates for diagnostics; it deliberately
never upgrades them to feature provenance or uses them to choose shell
topology.  Invalid/non-manifold source topology fails closed.
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class SourceFeatureCandidate:
    """One geometry-only sharp-edge candidate from two source triangles."""

    edge: tuple[int, int]
    incident_faces: tuple[int, int]
    unsigned_dihedral_degrees: float


@dataclass(frozen=True)
class SourceFeatureCandidateAudit:
    """Fail-closed source audit; candidates are explicitly non-authoritative."""

    status: str
    source_face_count: int
    manifold_edge_count: int
    candidate_edges: tuple[SourceFeatureCandidate, ...]
    candidate_components: tuple[tuple[int, ...], ...]
    candidates_are_authoritative: bool
    source_geometry_unchanged: bool
    production_mesh_changed: bool


def _candidate_components(
    candidates: Sequence[SourceFeatureCandidate],
) -> tuple[tuple[int, ...], ...]:
    adjacency: dict[int, set[int]] = defaultdict(set)
    for candidate in candidates:
        first, second = candidate.edge
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
            for neighbor in sorted(adjacency[vertex]):
                if neighbor in unseen:
                    unseen.remove(neighbor)
                    pending.append(neighbor)
        components.append(tuple(sorted(component)))
    return tuple(components)


def audit_geometric_feature_candidates_l0(
    vertices: np.ndarray,
    faces: np.ndarray,
    *,
    dihedral_threshold_degrees: float = 30.0,
) -> SourceFeatureCandidateAudit:
    """Measure sharp dihedral candidates without inferring CAD features."""
    points = np.asarray(vertices, dtype=np.float64)
    triangles = np.asarray(faces, dtype=np.int64)
    if (
        points.ndim != 2
        or points.shape[1] != 3
        or triangles.ndim != 2
        or triangles.shape[1] != 3
        or not 0.0 < dihedral_threshold_degrees < 180.0
    ):
        return SourceFeatureCandidateAudit("reject_invalid_input", 0, 0, (), (), False, True, False)
    if np.any(triangles < 0) or np.any(triangles >= len(points)):
        return SourceFeatureCandidateAudit(
            "reject_face_index_out_of_range", len(triangles), 0, (), (), False, True, False
        )
    points_before, faces_before = points.copy(), triangles.copy()
    normals = np.cross(
        points[triangles[:, 1]] - points[triangles[:, 0]],
        points[triangles[:, 2]] - points[triangles[:, 0]],
    )
    lengths = np.linalg.norm(normals, axis=1)
    if np.any(lengths <= np.finfo(float).tiny):
        return SourceFeatureCandidateAudit(
            "reject_degenerate_source_triangle", len(triangles), 0, (), (), False, True, False
        )
    unit_normals = normals / lengths[:, None]
    owners: dict[tuple[int, int], list[int]] = defaultdict(list)
    for face_index, triangle in enumerate(triangles):
        for first, second in zip(triangle, np.roll(triangle, -1), strict=True):
            first_vertex, second_vertex = int(first), int(second)
            edge = (
                (first_vertex, second_vertex)
                if first_vertex < second_vertex
                else (second_vertex, first_vertex)
            )
            owners[edge].append(face_index)
    if any(len(face_owners) != 2 for face_owners in owners.values()):
        return SourceFeatureCandidateAudit(
            "reject_source_not_closed_two_manifold",
            len(triangles),
            0,
            (),
            (),
            False,
            bool(np.array_equal(points, points_before) and np.array_equal(triangles, faces_before)),
            False,
        )
    candidates: list[SourceFeatureCandidate] = []
    for edge, face_owners in sorted(owners.items()):
        first_face, second_face = face_owners
        # Absolute cosine makes the diagnostic insensitive to an accidental
        # local orientation reversal; this is not a signed CAD concavity test.
        cosine = float(
            np.clip(abs(np.dot(unit_normals[first_face], unit_normals[second_face])), 0.0, 1.0)
        )
        angle = float(np.degrees(np.arccos(cosine)))
        if angle >= dihedral_threshold_degrees:
            candidates.append(SourceFeatureCandidate(edge, (first_face, second_face), angle))
    unchanged = bool(
        np.array_equal(points, points_before) and np.array_equal(triangles, faces_before)
    )
    return SourceFeatureCandidateAudit(
        "pass_geometric_candidates_not_authoritative",
        len(triangles),
        len(owners),
        tuple(candidates),
        _candidate_components(candidates),
        False,
        unchanged,
        False,
    )
