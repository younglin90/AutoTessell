"""Diagnostic boundary-preservation checks for native-tet stage boundaries.

The checker is deliberately log-only by default.  It shares the canonical
orientation-free ``boundary_face_keys`` implementation from ``near_wall`` so
local-operation guards and pipeline diagnostics use the same definition.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from core.utils.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class BoundaryInvariantReport:
    """Measured before/after boundary comparison."""

    stage_name: str
    keys_equal: bool
    area_equal: bool
    before_face_count: int
    after_face_count: int
    before_area: float
    after_area: float
    added_faces: int
    removed_faces: int

    @property
    def preserved(self) -> bool:
        return self.keys_equal and self.area_equal


def _boundary_area(points: np.ndarray, keys: set[tuple[int, int, int]]) -> float:
    if not keys:
        return 0.0
    faces = np.asarray(sorted(keys), dtype=np.int64)
    pts = np.asarray(points, dtype=np.float64)
    if faces.ndim != 2 or faces.shape[1] != 3:
        return 0.0
    tri = pts[faces]
    return float(
        0.5
        * np.linalg.norm(
            np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]),
            axis=1,
        ).sum()
    )


def check_boundary_invariant(
    pts_before: np.ndarray,
    tets_before: np.ndarray,
    pts_after: np.ndarray,
    tets_after: np.ndarray,
    stage_name: str,
    *,
    log_only: bool = True,
) -> BoundaryInvariantReport:
    """Compare boundary face keys and total area, without changing a mesh.

    ``log_only=True`` records violations and never raises or rejects.  The
    non-log-only branch exists only for future callers and is intentionally not
    used by the pipeline diagnostic harness.
    """
    from core.generator.native_tet.near_wall import boundary_face_keys

    before_keys = boundary_face_keys(np.asarray(tets_before, dtype=np.int64))
    after_keys = boundary_face_keys(np.asarray(tets_after, dtype=np.int64))
    before_area = _boundary_area(np.asarray(pts_before), before_keys)
    after_area = _boundary_area(np.asarray(pts_after), after_keys)
    area_tol = 1e-10 * max(abs(before_area), 1e-30)
    keys_equal = before_keys == after_keys
    area_equal = abs(after_area - before_area) <= area_tol
    report = BoundaryInvariantReport(
        stage_name=str(stage_name),
        keys_equal=keys_equal,
        area_equal=area_equal,
        before_face_count=len(before_keys),
        after_face_count=len(after_keys),
        before_area=before_area,
        after_area=after_area,
        added_faces=len(after_keys - before_keys),
        removed_faces=len(before_keys - after_keys),
    )
    log.info(
        "native_tet_boundary_invariant",
        stage=report.stage_name,
        preserved=report.preserved,
        keys_equal=report.keys_equal,
        area_equal=report.area_equal,
        before_boundary_faces=report.before_face_count,
        after_boundary_faces=report.after_face_count,
        before_boundary_area=round(report.before_area, 12),
        after_boundary_area=round(report.after_area, 12),
        added_faces=report.added_faces,
        removed_faces=report.removed_faces,
        log_only=bool(log_only),
    )
    if not log_only and not report.preserved:
        raise AssertionError(f"boundary invariant failed at {report.stage_name}")
    return report
