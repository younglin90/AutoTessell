"""Read-only diagnosis of centroid-shell folds on concave exact source faces.

The exact quad shell audit deliberately rejects any raw orientation reversal.
This L2 diagnostic determines whether those reversals are explained by the
test-only global-centroid extrusion itself: it maps every raw-negative hex back
to its immutable source triangle and measures its oriented normal relative to
the global source centroid.  Geometric sharp candidates are reported only as
non-authoritative correlation, never as CAD feature provenance.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from .source_feature_candidate_l0 import audit_geometric_feature_candidates_l0
from .source_quad_shell_l1 import ExactSourceQuadShellAudit, audit_exact_source_quad_shell_l1
from .source_triangle_quadization_l0 import extrude_exact_quad_shell_l1


@dataclass(frozen=True)
class ExactSourceQuadShellConcavityAudit:
    """Report-only raw-fold attribution for the immutable exact outer surface."""

    status: str
    shell: ExactSourceQuadShellAudit
    raw_negative_hex_count: int
    raw_negative_source_face_count: int
    centroid_concave_source_face_count: int
    raw_negative_faces_all_centroid_concave: bool
    raw_negative_faces_candidate_adjacent_count: int
    feature_candidates_authoritative: bool
    source_geometry_unchanged: bool
    production_mesh_changed: bool


_FIVE_TET_FAN = np.array(
    [[0, 1, 3, 4], [1, 2, 3, 6], [3, 4, 6, 7], [1, 4, 5, 6], [1, 3, 4, 6]],
    dtype=np.int64,
)


def _raw_negative_hex_indices(points: np.ndarray, hexes: np.ndarray) -> np.ndarray:
    """Return raw five-tet signed-volume failures without orientation correction."""
    vertices = np.asarray(points, dtype=np.float64)[np.asarray(hexes, dtype=np.int64)[:, _FIVE_TET_FAN]]
    origin = vertices[:, :, 0, :]
    volumes = (
        (vertices[:, :, 1, :] - origin)
        * np.cross(vertices[:, :, 2, :] - origin, vertices[:, :, 3, :] - origin)
    ).sum(axis=2).sum(axis=1)
    return np.flatnonzero(volumes < -1.0e-20)


def audit_exact_source_quad_shell_concavity_l2(
    vertices: np.ndarray,
    faces: np.ndarray,
    face_entities: Sequence[tuple[str, str]],
    *,
    scale: float = 0.8,
) -> ExactSourceQuadShellConcavityAudit:
    """Attribute raw centroid-shell folds while keeping all source data immutable."""
    source_points = np.asarray(vertices, dtype=np.float64)
    source_faces = np.asarray(faces, dtype=np.int64)
    points_before, faces_before = source_points.copy(), source_faces.copy()
    shell = audit_exact_source_quad_shell_l1(
        source_points, source_faces, face_entities, scale=scale
    )
    if shell.surface_audit.status != "pass_exact_source_quadization":
        unchanged = bool(
            np.array_equal(source_points, points_before) and np.array_equal(source_faces, faces_before)
        )
        return ExactSourceQuadShellConcavityAudit(
            "reject_source_quadization",
            shell,
            0,
            0,
            0,
            False,
            0,
            False,
            unchanged,
            False,
        )
    quadization = shell.surface_audit.quadization
    shell_points, shell_hexes = extrude_exact_quad_shell_l1(
        quadization.points, quadization.quads, scale=scale
    )
    raw_negative = _raw_negative_hex_indices(shell_points, shell_hexes)
    raw_source_faces = frozenset(int(quadization.source_face_ids[index]) for index in raw_negative)
    normals = np.cross(
        source_points[source_faces[:, 1]] - source_points[source_faces[:, 0]],
        source_points[source_faces[:, 2]] - source_points[source_faces[:, 0]],
    )
    face_centers = np.mean(source_points[source_faces], axis=1)
    global_center = np.mean(source_points, axis=0)
    centroid_concave = frozenset(
        int(index)
        for index, value in enumerate(np.einsum("ij,ij->i", normals, face_centers - global_center))
        if value < 0.0
    )
    candidates = audit_geometric_feature_candidates_l0(source_points, source_faces)
    candidate_faces = frozenset(
        face for candidate in candidates.candidate_edges for face in candidate.incident_faces
    )
    unchanged = bool(
        np.array_equal(source_points, points_before) and np.array_equal(source_faces, faces_before)
    )
    all_concave = bool(raw_source_faces) and raw_source_faces <= centroid_concave
    return ExactSourceQuadShellConcavityAudit(
        "pass_centroid_shell_concavity_diagnosis",
        shell,
        len(raw_negative),
        len(raw_source_faces),
        len(centroid_concave),
        all_concave,
        len(raw_source_faces & candidate_faces),
        candidates.candidates_are_authoritative,
        unchanged,
        False,
    )
