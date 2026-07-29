"""Report-only exact-outer-surface quad shell audit.

This isolates the first volume step after exact triangle-to-quad conversion.
The outer surface stays byte-identical in the quadized representation; only a
test-only centroid-scaled inner shell is examined.  It never fills the cavity,
changes the sparse candidate, or writes a mesh.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from .mesher import validate_hex_cell_volumes
from .source_triangle_quadization_l0 import _HEX_FACES, extrude_exact_quad_shell_l1
from .source_triangle_quadization_l1 import (
    ExactSourceQuadizationAudit,
    audit_exact_source_quadization_l1,
)

QuadKey = tuple[int, int, int, int]


@dataclass(frozen=True)
class ExactSourceQuadShellAudit:
    """Test-only shell result; a passing shell still has an intentionally open core."""

    status: str
    surface_audit: ExactSourceQuadizationAudit
    hex_count: int
    flipped_cell_count: int
    degenerate_cell_count: int
    outer_quad_set_preserved: bool
    source_vertex_prefix_identical: bool
    cavity_unfilled: bool
    production_mesh_changed: bool


def _quad_key(vertices: Sequence[int]) -> QuadKey:
    ordered = tuple(sorted(int(vertex) for vertex in vertices))
    if len(ordered) != 4 or len(set(ordered)) != 4:
        raise ValueError("a quad requires four distinct vertices")
    return ordered[0], ordered[1], ordered[2], ordered[3]


def _outer_quad_keys(hexes: np.ndarray) -> tuple[QuadKey, ...]:
    # The shell builder puts the source-derived outer quad in positions 0..3.
    return tuple(sorted(_quad_key(cell[:4]) for cell in np.asarray(hexes, dtype=np.int64)))


def _all_hex_face_counts(hexes: np.ndarray) -> Counter[QuadKey]:
    counts: Counter[QuadKey] = Counter()
    for cell in np.asarray(hexes, dtype=np.int64):
        for face in _HEX_FACES:
            counts[_quad_key(cell[list(face)])] += 1
    return counts


def audit_exact_source_quad_shell_l1(
    vertices: np.ndarray,
    faces: np.ndarray,
    face_entities: Sequence[tuple[str, str]],
    *,
    scale: float = 0.8,
    tolerance: float = 1.0e-12,
) -> ExactSourceQuadShellAudit:
    """Audit a temporary shell while keeping the exact outer source quads fixed."""
    surface = audit_exact_source_quadization_l1(vertices, faces, face_entities, tolerance=tolerance)
    if surface.status != "pass_exact_source_quadization":
        return ExactSourceQuadShellAudit(
            "reject_source_quadization",
            surface,
            0,
            0,
            0,
            False,
            False,
            True,
            False,
        )
    points, hexes = extrude_exact_quad_shell_l1(
        surface.quadization.points, surface.quadization.quads, scale=scale
    )
    _checked, flipped, degenerate = validate_hex_cell_volumes(points, hexes)
    expected_outer = tuple(sorted(_quad_key(quad) for quad in surface.quadization.quads))
    outer_preserved = _outer_quad_keys(hexes) == expected_outer
    prefix = bool(
        np.array_equal(points[: len(surface.quadization.points)], surface.quadization.points)
    )
    face_counts = _all_hex_face_counts(hexes)
    # A shell has exactly two boundary sheets; every other quad is internal.
    cavity_unfilled = bool(
        len(face_counts) > len(expected_outer)
        and all(count in {1, 2} for count in face_counts.values())
        and sum(count == 1 for count in face_counts.values()) == 2 * len(expected_outer)
    )
    accepted = flipped == 0 and degenerate == 0 and outer_preserved and prefix and cavity_unfilled
    return ExactSourceQuadShellAudit(
        "pass_exact_outer_shell_open_core" if accepted else "reject_shell_validity_or_contract",
        surface,
        len(hexes),
        int(flipped),
        int(degenerate),
        outer_preserved,
        prefix,
        cavity_unfilled,
        False,
    )
