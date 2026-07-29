"""Test-only star-shaped exact-boundary tet-core witness.

This is deliberately not wired into ``generate_native_tet``.  It proves the
minimal handoff contract on a closed, star-shaped surface before a general CDT
facet-recovery implementation is considered.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from core.utils.predicates_exact import orient3d


@dataclass(frozen=True)
class StarTetCore:
    """A tetra fan whose exterior faces are exactly the supplied triangles."""

    points: np.ndarray
    tets: np.ndarray
    center_index: int


def build_star_tet_core(
    vertices: np.ndarray,
    faces: np.ndarray,
    *,
    center: np.ndarray | None = None,
) -> StarTetCore:
    """Build a positive oriented tetra fan if one point sees every face.

    The input must be a closed two-manifold and all oriented faces must see the
    candidate center from the same strict side.  This is an L0 witness, not a
    general tetrahedralizer for non-star-shaped PLCs.
    """
    points = np.asarray(vertices, dtype=np.float64)
    surface = np.asarray(faces, dtype=np.int64)
    if points.ndim != 2 or points.shape[1] != 3:
        raise ValueError("vertices must have shape (n, 3)")
    if surface.ndim != 2 or surface.shape[1] != 3 or surface.size == 0:
        raise ValueError("faces must have nonzero shape (m, 3)")
    if int(surface.min()) < 0 or int(surface.max()) >= len(points):
        raise ValueError("face index is outside vertices")

    edge_pairs = np.concatenate(
        (surface[:, [0, 1]], surface[:, [1, 2]], surface[:, [2, 0]]), axis=0
    )
    edge_pairs.sort(axis=1)
    _, edge_counts = np.unique(edge_pairs, axis=0, return_counts=True)
    if not np.all(edge_counts == 2):
        raise ValueError("faces must be a closed two-manifold")

    star_center = (
        np.asarray(center, dtype=np.float64) if center is not None else np.mean(points, axis=0)
    )
    if star_center.shape != (3,):
        raise ValueError("center must have shape (3,)")

    signs = np.asarray(
        [orient3d(points[a], points[b], points[c], star_center) for a, b, c in surface],
        dtype=np.int8,
    )
    if np.any(signs == 0) or not np.all(signs == signs[0]):
        raise ValueError("center is not a strict star point for every oriented face")

    center_index = len(points)
    tets = np.column_stack((surface, np.full(len(surface), center_index, dtype=np.int64)))
    if signs[0] < 0:
        tets[:, [1, 2]] = tets[:, [2, 1]]
    return StarTetCore(
        points=np.vstack((points, star_center[None, :])),
        tets=tets,
        center_index=center_index,
    )
