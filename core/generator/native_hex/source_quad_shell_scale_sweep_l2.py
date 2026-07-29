"""Report-only thickness sweep for the rejected global-centroid quad shell."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from .source_quad_shell_concavity_l2 import _raw_negative_hex_indices
from .source_triangle_quadization_l0 import extrude_exact_quad_shell_l1
from .source_triangle_quadization_l1 import (
    ExactSourceQuadizationAudit,
    audit_exact_source_quadization_l1,
)


@dataclass(frozen=True)
class CentroidShellScaleSample:
    """Raw orientation count for one inward global-centroid scale."""

    scale: float
    raw_negative_hex_count: int


@dataclass(frozen=True)
class ExactSourceQuadShellScaleSweep:
    """Read-only evidence about whether reducing global thickness can help."""

    status: str
    surface_audit: ExactSourceQuadizationAudit
    samples: tuple[CentroidShellScaleSample, ...]
    all_scales_raw_fold_free: bool
    source_geometry_unchanged: bool
    production_mesh_changed: bool


def audit_exact_source_quad_shell_scale_sweep_l2(
    vertices: np.ndarray,
    faces: np.ndarray,
    face_entities: Sequence[tuple[str, str]],
    *,
    scales: Sequence[float],
) -> ExactSourceQuadShellScaleSweep:
    """Measure raw centroid-shell folds over explicit scales without fixing them."""
    source_points = np.asarray(vertices, dtype=np.float64)
    source_faces = np.asarray(faces, dtype=np.int64)
    points_before, faces_before = source_points.copy(), source_faces.copy()
    surface = audit_exact_source_quadization_l1(source_points, source_faces, face_entities)
    unchanged = bool(np.array_equal(source_points, points_before) and np.array_equal(source_faces, faces_before))
    typed_scales = tuple(float(scale) for scale in scales)
    if not typed_scales or any(not 0.0 < scale < 1.0 for scale in typed_scales):
        return ExactSourceQuadShellScaleSweep(
            "reject_invalid_scale_sweep", surface, (), False, unchanged, False
        )
    if surface.status != "pass_exact_source_quadization":
        return ExactSourceQuadShellScaleSweep(
            "reject_source_quadization", surface, (), False, unchanged, False
        )
    samples: list[CentroidShellScaleSample] = []
    for scale in typed_scales:
        shell_points, shell_hexes = extrude_exact_quad_shell_l1(
            surface.quadization.points, surface.quadization.quads, scale=scale
        )
        samples.append(
            CentroidShellScaleSample(
                scale, len(_raw_negative_hex_indices(shell_points, shell_hexes))
            )
        )
    return ExactSourceQuadShellScaleSweep(
        "pass_centroid_shell_scale_sweep",
        surface,
        tuple(samples),
        all(sample.raw_negative_hex_count == 0 for sample in samples),
        unchanged,
        False,
    )
