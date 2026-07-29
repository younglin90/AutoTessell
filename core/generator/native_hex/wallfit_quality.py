"""Report-only wall-fit candidate quality audit.

The audit is intentionally separate from ``_wall_fit_snap`` acceptance logic.
When enabled, it snapshots the incident cells before and after each projected
boundary-vertex candidate and records quality deltas, signed-volume changes,
and the global boundary face/area invariant.  It never accepts, rejects, or
changes a candidate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

from core.generator.native_hex.match_diagnostic import (
    _cell_centroid,
    _quad_skewness,
    face_centroid_normal_area,
)
from core.generator.native_hex.metrics import CellFaces, _cell_volume
from core.generator.native_hex.transition_quality import (
    _boundary_snapshot,
    _cell_face_warpage,
    _signed_cell_volume,
)

QUALITY_ENV = "AUTO_TESSELL_HEX_WALLFIT_CANDIDATE_QUALITY_DIAG"
NORMAL_DISTANCE_DIAGNOSTIC_FLOOR = 1.0e-12


def enabled() -> bool:
    """Return whether candidate-level wall-fit auditing is enabled."""

    import os

    return os.environ.get(QUALITY_ENV, "").strip().lower() in {"1", "true", "yes"}


def _cell_skewness(
    points: np.ndarray, cell: Sequence[Sequence[int]]
) -> tuple[list[float], list[float]]:
    centroid = _cell_centroid(points, cell)
    values: list[float] = []
    normal_distances: list[float] = []
    for face in cell:
        if len(face) != 4 or len(set(int(vertex) for vertex in face)) != 4:
            continue
        skew, _area = _quad_skewness(points, centroid, face)
        if np.isfinite(skew):
            values.append(float(skew))
        face_centroid, normal, _face_area = face_centroid_normal_area(points, face)
        if np.any(normal):
            normal_distances.append(
                abs(float(np.dot(face_centroid - centroid, normal)))
            )
    return values, normal_distances


def _finite_max(values: Sequence[float]) -> float | None:
    finite = [float(value) for value in values if np.isfinite(value)]
    return max(finite) if finite else None


def _finite_min(values: Sequence[float]) -> float | None:
    finite = [float(value) for value in values if np.isfinite(value)]
    return min(finite) if finite else None


def _finite_percentile(values: Sequence[float], percentile: float) -> float | None:
    finite = np.asarray(
        [float(value) for value in values if np.isfinite(value)], dtype=np.float64
    )
    if finite.size == 0:
        return None
    return float(np.percentile(finite, percentile))


@dataclass(frozen=True)
class CandidateSnapshot:
    """Quality values for one candidate's incident cells."""

    cell_indices: tuple[int, ...]
    max_skew: float | None
    p95_skew: float | None
    max_warpage: float | None
    p95_warpage: float | None
    min_abs_normal_distance: float | None
    n_near_zero_normal_distance: int
    min_signed_volume: float | None
    n_negative_signed_volume: int
    total_orientation_free_volume: float
    boundary_keys: frozenset[tuple[int, ...]]
    boundary_area: float


def snapshot(
    points: np.ndarray,
    cell_faces: CellFaces,
    incident_cells: Sequence[int],
) -> CandidateSnapshot:
    """Snapshot local quality plus the global boundary face/area contract."""

    cell_indices = tuple(sorted({int(index) for index in incident_cells}))
    skew: list[float] = []
    normal_distances: list[float] = []
    warpage: list[float] = []
    signed: list[float] = []
    orientation_free = 0.0
    for index in cell_indices:
        cell = cell_faces[index]
        cell_skew, cell_normal_distances = _cell_skewness(points, cell)
        skew.extend(cell_skew)
        normal_distances.extend(cell_normal_distances)
        warpage.extend(_cell_face_warpage(points, cell))
        signed.append(_signed_cell_volume(points, cell))
        orientation_free += _cell_volume(points, cell)
    boundary_keys, boundary_area, _incidence = _boundary_snapshot(points, cell_faces)
    return CandidateSnapshot(
        cell_indices=cell_indices,
        max_skew=_finite_max(skew),
        p95_skew=_finite_percentile(skew, 95.0),
        max_warpage=_finite_max(warpage),
        p95_warpage=_finite_percentile(warpage, 95.0),
        min_abs_normal_distance=_finite_min(normal_distances),
        n_near_zero_normal_distance=sum(
            value <= NORMAL_DISTANCE_DIAGNOSTIC_FLOOR for value in normal_distances
        ),
        min_signed_volume=_finite_min(signed),
        n_negative_signed_volume=sum(value < 0.0 for value in signed),
        total_orientation_free_volume=float(orientation_free),
        boundary_keys=frozenset(boundary_keys),
        boundary_area=float(boundary_area),
    )


def _delta(after: float | None, before: float | None) -> float | None:
    if after is None or before is None:
        return None
    return float(after - before)


def pareto_frontier(
    records: Sequence[dict[str, object]],
) -> tuple[dict[str, object], ...]:
    """Return non-dominated wall-fit candidates for report-only analysis.

    Larger ``distance_reduction`` is better.  Smaller skew/warpage deltas,
    boundary-area change, and negative-volume delta are better.  This helper
    does not encode an acceptance rule: it only exposes the candidates that
    are not dominated on all measured axes.  The diagnostic lane is bounded
    by the number of wall-fit candidates, which is small compared with the
    mesh itself.
    """

    def _values(record: dict[str, object]) -> tuple[float, float, float, float, float]:
        return (
            float(record.get("distance_reduction", 0.0)),
            float(record.get("applied_skew_delta", 0.0) or 0.0),
            float(record.get("applied_warpage_delta", 0.0) or 0.0),
            abs(float(record.get("boundary_area_delta", 0.0) or 0.0)),
            float(record.get("negative_signed_volume_delta", 0.0) or 0.0),
        )

    def _dominates(left: tuple[float, ...], right: tuple[float, ...]) -> bool:
        tolerance = 1.0e-12
        no_worse = (
            left[0] >= right[0] - tolerance
            and left[1] <= right[1] + tolerance
            and left[2] <= right[2] + tolerance
            and left[3] <= right[3] + tolerance
            and left[4] <= right[4] + tolerance
        )
        strictly_better = (
            left[0] > right[0] + tolerance
            or left[1] < right[1] - tolerance
            or left[2] < right[2] - tolerance
            or left[3] < right[3] - tolerance
            or left[4] < right[4] - tolerance
        )
        return bool(no_worse and strictly_better)

    frontier: list[dict[str, object]] = []
    values = [_values(record) for record in records]
    for index, record in enumerate(records):
        if any(
            _dominates(values[other], values[index])
            for other in range(len(records))
            if other != index
        ):
            continue
        frontier.append(dict(record))
    frontier.sort(
        key=lambda record: (
            -float(record.get("distance_reduction", 0.0)),
            float(record.get("applied_skew_delta", 0.0) or 0.0),
            int(record.get("vertex", -1)),
        )
    )
    return tuple(frontier)


@dataclass
class CandidateQualityAudit:
    """Accumulate bounded report-only candidate measurements."""

    n_candidates: int = 0
    n_full: int = 0
    n_partial: int = 0
    n_rejected: int = 0
    n_trial_regression: int = 0
    n_applied_regression: int = 0
    n_boundary_key_change: int = 0
    n_boundary_area_change: int = 0
    max_trial_skew_delta: float = 0.0
    max_applied_skew_delta: float = 0.0
    max_trial_warpage_delta: float = 0.0
    max_applied_warpage_delta: float = 0.0
    max_abs_boundary_area_delta: float = 0.0
    max_relative_boundary_area_delta: float = 0.0
    strict_quality_nonregressing: int = 0
    p95_quality_nonregressing: int = 0
    combined_quality_nonregressing: int = 0
    n_applied_distance_improved: int = 0
    n_distance_improved_quality_regression: int = 0
    n_distance_improved_strict_nonregressing: int = 0
    n_distance_improved_p95_nonregressing: int = 0
    n_distance_improved_combined_nonregressing: int = 0
    total_applied_distance_reduction: float = 0.0
    max_applied_distance_reduction: float = 0.0
    n_trial_near_zero_normal_distance: int = 0
    n_applied_near_zero_normal_distance: int = 0
    min_trial_normal_distance: float | None = None
    min_applied_normal_distance: float | None = None
    samples: list[dict[str, object]] = field(default_factory=list)
    frontier_records: list[dict[str, object]] = field(default_factory=list)

    @staticmethod
    def _regressed(before: CandidateSnapshot, after: CandidateSnapshot) -> bool:
        skew_delta = _delta(after.max_skew, before.max_skew)
        warpage_delta = _delta(after.max_warpage, before.max_warpage)
        new_negative = after.n_negative_signed_volume > before.n_negative_signed_volume
        return bool(
            (skew_delta is not None and skew_delta > 1.0e-12)
            or (warpage_delta is not None and warpage_delta > 1.0e-12)
            or new_negative
        )

    @staticmethod
    def _quality_nonregressing(
        before: CandidateSnapshot, after: CandidateSnapshot, *, use_p95: bool
    ) -> bool:
        before_skew = before.p95_skew if use_p95 else before.max_skew
        after_skew = after.p95_skew if use_p95 else after.max_skew
        before_warpage = before.p95_warpage if use_p95 else before.max_warpage
        after_warpage = after.p95_warpage if use_p95 else after.max_warpage
        if before_skew is None or after_skew is None:
            skew_ok = True
        else:
            skew_ok = after_skew <= before_skew + 1.0e-12
        if before_warpage is None or after_warpage is None:
            warpage_ok = True
        else:
            warpage_ok = after_warpage <= before_warpage + 1.0e-12
        return bool(skew_ok and warpage_ok)

    def record(
        self,
        *,
        vertex: int,
        outcome: str,
        before: CandidateSnapshot,
        trial: CandidateSnapshot,
        after: CandidateSnapshot,
        distance_before: float,
        distance_after: float,
    ) -> None:
        """Record one candidate without affecting the mesh decision."""

        self.n_candidates += 1
        if outcome == "full":
            self.n_full += 1
        elif outcome == "partial":
            self.n_partial += 1
        else:
            self.n_rejected += 1

        trial_skew_delta = _delta(trial.max_skew, before.max_skew)
        trial_warpage_delta = _delta(trial.max_warpage, before.max_warpage)
        applied_skew_delta = _delta(after.max_skew, before.max_skew)
        applied_warpage_delta = _delta(after.max_warpage, before.max_warpage)
        if trial_skew_delta is not None:
            self.max_trial_skew_delta = max(self.max_trial_skew_delta, trial_skew_delta)
        if applied_skew_delta is not None:
            self.max_applied_skew_delta = max(self.max_applied_skew_delta, applied_skew_delta)
        if trial_warpage_delta is not None:
            self.max_trial_warpage_delta = max(
                self.max_trial_warpage_delta, trial_warpage_delta
            )
        if applied_warpage_delta is not None:
            self.max_applied_warpage_delta = max(
                self.max_applied_warpage_delta, applied_warpage_delta
            )

        trial_regression = self._regressed(before, trial)
        applied_regression = self._regressed(before, after)
        self.n_trial_regression += int(trial_regression)
        self.n_applied_regression += int(applied_regression)
        key_changed = before.boundary_keys != after.boundary_keys
        area_delta = float(after.boundary_area - before.boundary_area)
        self.n_boundary_key_change += int(key_changed)
        self.n_boundary_area_change += int(abs(area_delta) > 1.0e-12)
        self.max_abs_boundary_area_delta = max(
            self.max_abs_boundary_area_delta, abs(area_delta)
        )
        relative_area_delta = abs(area_delta) / max(abs(before.boundary_area), 1.0e-30)
        self.max_relative_boundary_area_delta = max(
            self.max_relative_boundary_area_delta, relative_area_delta
        )
        strict_quality_ok = self._quality_nonregressing(before, after, use_p95=False)
        p95_quality_ok = self._quality_nonregressing(before, after, use_p95=True)
        self.strict_quality_nonregressing += int(strict_quality_ok)
        self.p95_quality_nonregressing += int(p95_quality_ok)
        self.combined_quality_nonregressing += int(strict_quality_ok and p95_quality_ok)
        distance_reduction = max(float(distance_before) - float(distance_after), 0.0)
        distance_improved = distance_reduction > 1.0e-15
        self.n_applied_distance_improved += int(distance_improved)
        self.total_applied_distance_reduction += distance_reduction
        self.max_applied_distance_reduction = max(
            self.max_applied_distance_reduction, distance_reduction
        )
        self.n_distance_improved_quality_regression += int(
            distance_improved and applied_regression
        )
        self.n_distance_improved_strict_nonregressing += int(
            distance_improved and strict_quality_ok
        )
        self.n_distance_improved_p95_nonregressing += int(
            distance_improved and p95_quality_ok
        )
        self.n_distance_improved_combined_nonregressing += int(
            distance_improved and strict_quality_ok and p95_quality_ok
        )
        self.frontier_records.append(
            {
                "vertex": int(vertex),
                "outcome": outcome,
                "distance_reduction": distance_reduction,
                "applied_skew_delta": applied_skew_delta or 0.0,
                "applied_warpage_delta": applied_warpage_delta or 0.0,
                "boundary_area_delta": area_delta,
                "negative_signed_volume_delta": float(
                    after.n_negative_signed_volume - before.n_negative_signed_volume
                ),
            }
        )
        self.n_trial_near_zero_normal_distance += int(
            trial.n_near_zero_normal_distance > 0
        )
        self.n_applied_near_zero_normal_distance += int(
            after.n_near_zero_normal_distance > 0
        )
        if trial.min_abs_normal_distance is not None:
            self.min_trial_normal_distance = (
                trial.min_abs_normal_distance
                if self.min_trial_normal_distance is None
                else min(self.min_trial_normal_distance, trial.min_abs_normal_distance)
            )
        if after.min_abs_normal_distance is not None:
            self.min_applied_normal_distance = (
                after.min_abs_normal_distance
                if self.min_applied_normal_distance is None
                else min(self.min_applied_normal_distance, after.min_abs_normal_distance)
            )

        if (trial_regression or applied_regression or key_changed or abs(area_delta) > 1.0e-12) and len(self.samples) < 12:
            self.samples.append(
                {
                    "vertex": int(vertex),
                    "cells": before.cell_indices,
                    "outcome": outcome,
                    "trial_skew_delta": trial_skew_delta,
                    "applied_skew_delta": applied_skew_delta,
                    "before_p95_skew": before.p95_skew,
                    "trial_p95_skew": trial.p95_skew,
                    "after_p95_skew": after.p95_skew,
                    "trial_warpage_delta": trial_warpage_delta,
                    "applied_warpage_delta": applied_warpage_delta,
                    "before_min_abs_normal_distance": before.min_abs_normal_distance,
                    "trial_min_abs_normal_distance": trial.min_abs_normal_distance,
                    "after_min_abs_normal_distance": after.min_abs_normal_distance,
                    "before_near_zero_normal_distance": before.n_near_zero_normal_distance,
                    "trial_near_zero_normal_distance": trial.n_near_zero_normal_distance,
                    "after_near_zero_normal_distance": after.n_near_zero_normal_distance,
                    "before_min_signed_volume": before.min_signed_volume,
                    "trial_min_signed_volume": trial.min_signed_volume,
                    "after_min_signed_volume": after.min_signed_volume,
                    "before_negative_signed_volume": before.n_negative_signed_volume,
                    "trial_negative_signed_volume": trial.n_negative_signed_volume,
                    "after_negative_signed_volume": after.n_negative_signed_volume,
                    "boundary_keys_changed": key_changed,
                    "boundary_area_delta": area_delta,
                    "boundary_area_relative_delta": relative_area_delta,
                    "distance_before": float(distance_before),
                    "distance_after": float(distance_after),
                    "distance_reduction": distance_reduction,
                }
            )

    def to_dict(self) -> dict[str, object]:
        """Return a compact JSON/log-friendly report."""

        frontier = pareto_frontier(self.frontier_records)

        return {
            "n_candidates": self.n_candidates,
            "n_full": self.n_full,
            "n_partial": self.n_partial,
            "n_rejected": self.n_rejected,
            "n_trial_regression": self.n_trial_regression,
            "n_applied_regression": self.n_applied_regression,
            "n_boundary_key_change": self.n_boundary_key_change,
            "n_boundary_area_change": self.n_boundary_area_change,
            "max_trial_skew_delta": self.max_trial_skew_delta,
            "max_applied_skew_delta": self.max_applied_skew_delta,
            "max_trial_warpage_delta": self.max_trial_warpage_delta,
            "max_applied_warpage_delta": self.max_applied_warpage_delta,
            "max_abs_boundary_area_delta": self.max_abs_boundary_area_delta,
            "max_relative_boundary_area_delta": self.max_relative_boundary_area_delta,
            "strict_quality_nonregressing": self.strict_quality_nonregressing,
            "p95_quality_nonregressing": self.p95_quality_nonregressing,
            "combined_quality_nonregressing": self.combined_quality_nonregressing,
            "n_applied_distance_improved": self.n_applied_distance_improved,
            "n_distance_improved_quality_regression": self.n_distance_improved_quality_regression,
            "n_distance_improved_strict_nonregressing": self.n_distance_improved_strict_nonregressing,
            "n_distance_improved_p95_nonregressing": self.n_distance_improved_p95_nonregressing,
            "n_distance_improved_combined_nonregressing": self.n_distance_improved_combined_nonregressing,
            "total_applied_distance_reduction": self.total_applied_distance_reduction,
            "max_applied_distance_reduction": self.max_applied_distance_reduction,
            "n_trial_near_zero_normal_distance": self.n_trial_near_zero_normal_distance,
            "n_applied_near_zero_normal_distance": self.n_applied_near_zero_normal_distance,
            "min_trial_normal_distance": self.min_trial_normal_distance,
            "min_applied_normal_distance": self.min_applied_normal_distance,
            "pareto_frontier_size": len(frontier),
            "pareto_frontier": frontier,
            "samples": tuple(self.samples),
        }
