"""Deterministic, report-only quality-distribution evidence.

This module deliberately does not import or modify ``NativeMeshChecker``.  It
turns explicitly supplied, labelled face/cell measurements into a canonical
``QualityDistributionReport/v1`` payload for offline inspection.  It never
infers source, patch, feature, physical-group, or boundary-layer provenance.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np


SCHEMA = "QualityDistributionReport"
VERSION = "v1"
PERCENTILE_METHOD = "linear"
METRIC_VOCABULARY = frozenset(("internal_skewness", "boundary_skewness", "internal_non_orthogonality", "boundary_non_orthogonality", "aspect_ratio", "metric_distortion", "quad_scaled_jacobian", "quad_warpage", "surface_angle_deviation", "tri_mean_ratio", "quad_aspect_ratio", "quad_scaled_jacobian", "quad_warpage"))
SURFACE_METRIC_STATUS = frozenset(("measured", "not_measured", "not_applicable", "unverified"))

FacePartition = Literal["internal", "boundary"]
CellPartition = Literal["core", "boundary_layer", "transition"]

_FACE_METRICS: dict[str, tuple[str, ...]] = {
    "internal": ("skewness", "non_orthogonality", "face_weight"),
    "boundary": ("skewness", "non_orthogonality", "face_weight"),
}
_CELL_METRICS: tuple[str, ...] = ("aspect_ratio", "metric_distortion")
_POLARITY: dict[str, str] = {
    "skewness": "lower_is_better",
    "non_orthogonality": "lower_is_better",
    "face_weight": "higher_is_better",
    "aspect_ratio": "lower_is_better",
    "metric_distortion": "lower_is_better",
}
_PROVENANCE_KEYS: tuple[str, ...] = (
    "source_entity_id",
    "patch",
    "feature",
    "physical_group",
    "layer",
    "provenance",
)


@dataclass(frozen=True, slots=True)
class QualitySample:
    """One explicit quality measurement and its declared source lineage.

    ``source_entity_id``, ``layer``, and ``provenance`` must be supplied to
    claim complete provenance.  ``"not_applicable"`` is an explicit known
    value; ``None`` is unknown.  Metric distortion derives its value from the
    optional symmetric positive-definite ``metric_tensor`` rather than trusting
    a caller-provided scalar.
    """

    entity_id: int
    value: float | None = None
    source_entity_id: int | None = None
    patch: str | None = None
    feature: str | None = None
    physical_group: str | None = None
    layer: str | int | None = None
    provenance: str | Mapping[str, Any] | None = None
    metric_tensor: object | None = None


@dataclass(frozen=True, slots=True)
class QualityDistributionReport:
    """Canonical v1 report for supplied face and cell quality populations."""

    face_populations: Mapping[str, Mapping[str, Any]]
    cell_populations: Mapping[str, Mapping[str, Any]]
    provenance_complete: bool
    schema: str = SCHEMA
    version: str = VERSION
    percentile_method: str = PERCENTILE_METHOD

    @classmethod
    def from_populations(
        cls,
        *,
        face_populations: Mapping[str, Mapping[str, object]] | None = None,
        cell_populations: Mapping[str, Mapping[str, object]] | None = None,
    ) -> QualityDistributionReport:
        """Build a report from fixed labelled face and cell partitions.

        Each metric is an iterable of :class:`QualitySample` objects or
        mapping records.  A metric may also be ``{"samples": [...],
        "definition": "..."}``.  Boundary non-orthogonality is measured only
        with that non-empty definition.  ``metric_distortion`` samples must
        carry ``metric_tensor``; their reported values are ``cond(M)``.
        """

        supplied_faces = _validate_partitions(face_populations, _FACE_METRICS, "face")
        supplied_cells = _validate_partitions(
            cell_populations,
            {partition: _CELL_METRICS for partition in ("core", "boundary_layer", "transition")},
            "cell",
        )
        built_faces: dict[str, dict[str, Any]] = {}
        built_cells: dict[str, dict[str, Any]] = {}

        for partition, metrics in _FACE_METRICS.items():
            supplied = supplied_faces.get(partition, {})
            metric_reports: dict[str, Any] = {}
            for metric in metrics:
                samples, definition, present = _metric_input(supplied.get(metric))
                if partition == "boundary" and metric == "non_orthogonality":
                    metric_reports[metric] = _boundary_non_orthogonality_report(
                        samples, definition, present
                    )
                else:
                    metric_reports[metric] = _summarize(metric, samples, present=present)
            built_faces[partition] = {
                "provenance_complete": _metrics_provenance_complete(metric_reports),
                "metrics": metric_reports,
            }

        for partition in ("core", "boundary_layer", "transition"):
            supplied = supplied_cells.get(partition, {})
            metric_reports = {}
            for metric in _CELL_METRICS:
                samples, _definition, present = _metric_input(supplied.get(metric))
                if metric == "metric_distortion":
                    metric_reports[metric] = _metric_distortion_report(samples, present=present)
                else:
                    metric_reports[metric] = _summarize(metric, samples, present=present)
            built_cells[partition] = {
                "provenance_complete": _metrics_provenance_complete(metric_reports),
                "metrics": metric_reports,
            }

        return cls(
            face_populations=built_faces,
            cell_populations=built_cells,
            provenance_complete=all(
                population["provenance_complete"]
                for population in (*built_faces.values(), *built_cells.values())
            ),
        )

    build = from_populations

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe, schema-versioned representation."""

        return {
            "schema": self.schema,
            "version": self.version,
            "percentile_method": self.percentile_method,
            "provenance_complete": self.provenance_complete,
            "face_populations": self.face_populations,
            "cell_populations": self.cell_populations,
        }

    def to_json(self) -> str:
        """Serialize canonical deterministic JSON (no whitespace or NaN)."""

        return json.dumps(
            self.to_dict(), allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True
        )


def build_quality_distribution_report(
    *,
    face_populations: Mapping[str, Mapping[str, object]] | None = None,
    cell_populations: Mapping[str, Mapping[str, object]] | None = None,
) -> QualityDistributionReport:
    """Convenience factory for :meth:`QualityDistributionReport.from_populations`."""

    return QualityDistributionReport.from_populations(
        face_populations=face_populations, cell_populations=cell_populations
    )


def _validate_partitions(
    populations: Mapping[str, Mapping[str, object]] | None,
    allowed: Mapping[str, tuple[str, ...]],
    kind: str,
) -> Mapping[str, Mapping[str, object]]:
    if populations is None:
        return {}
    unexpected = set(populations) - set(allowed)
    if unexpected:
        raise ValueError(f"unsupported {kind} partition(s): {sorted(unexpected)!r}")
    for partition, metrics in populations.items():
        if not isinstance(metrics, Mapping):
            raise TypeError(f"{kind} partition {partition!r} must map metric names to samples")
        unexpected_metrics = set(metrics) - set(allowed[partition])
        if unexpected_metrics:
            raise ValueError(
                f"unsupported metric(s) for {kind} partition {partition!r}: "
                f"{sorted(unexpected_metrics)!r}"
            )
    return populations


def _metric_input(value: object | None) -> tuple[list[object], str | None, bool]:
    if value is None:
        return [], None, False
    if isinstance(value, Mapping) and ("samples" in value or "definition" in value):
        samples = value.get("samples", ())
        if isinstance(samples, (str, bytes)) or not isinstance(samples, Iterable):
            return [samples], _optional_text(value.get("definition")), True
        return list(samples), _optional_text(value.get("definition")), True
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        return [value], None, True
    return list(value), None, True


def _boundary_non_orthogonality_report(
    samples: list[object], definition: str | None, present: bool
) -> dict[str, Any]:
    if not present:
        return _empty_metric("non_orthogonality", "not_applicable", "definition_not_supplied")
    if not definition:
        return _empty_metric("non_orthogonality", "not_applicable", "definition_required")
    report = _summarize("non_orthogonality", samples, present=True)
    report["definition"] = definition
    return report


def _metric_distortion_report(samples: list[object], *, present: bool) -> dict[str, Any]:
    if not present:
        return _empty_metric("metric_distortion", "not_measured", "spd_metric_not_supplied")

    derived: list[QualitySample] = []
    invalid = 0
    for raw in samples:
        sample = _coerce_sample(raw)
        if sample is None:
            invalid += 1
            continue
        condition = _spd_condition(sample.metric_tensor)
        if condition is None:
            invalid += 1
            continue
        derived.append(
            QualitySample(
                entity_id=sample.entity_id,
                value=condition,
                source_entity_id=sample.source_entity_id,
                patch=sample.patch,
                feature=sample.feature,
                physical_group=sample.physical_group,
                layer=sample.layer,
                provenance=sample.provenance,
                metric_tensor=sample.metric_tensor,
            )
        )
    if invalid:
        report = _empty_metric("metric_distortion", "not_measured", "invalid_spd_metric_data")
        report["count"] = len(samples)
        report["finite_count"] = len(derived)
        report["invalid_metric_tensor_count"] = invalid
        return report
    report = _summarize("metric_distortion", derived, present=True)
    report["invalid_metric_tensor_count"] = 0
    return report


def _spd_condition(tensor: object | None) -> float | None:
    if tensor is None:
        return None
    try:
        matrix = np.asarray(tensor, dtype=np.float64)
    except (TypeError, ValueError):
        return None
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1] or matrix.shape[0] == 0:
        return None
    if not bool(np.isfinite(matrix).all()) or not bool(np.allclose(matrix, matrix.T, rtol=0.0, atol=1e-12)):
        return None
    try:
        eigenvalues = np.linalg.eigvalsh(matrix)
    except np.linalg.LinAlgError:
        return None
    if not bool(np.isfinite(eigenvalues).all()) or bool(np.any(eigenvalues <= 0.0)):
        return None
    return float(eigenvalues[-1] / eigenvalues[0])


def _summarize(metric: str, raw_samples: list[object], *, present: bool) -> dict[str, Any]:
    if not present:
        return _empty_metric(metric, "not_measured", "metric_not_supplied")
    samples = [_coerce_sample(raw) for raw in raw_samples]
    if any(sample is None for sample in samples):
        report = _empty_metric(metric, "measurement_failed", "invalid_sample")
        report["count"] = len(raw_samples)
        return report
    normalized = [sample for sample in samples if sample is not None]
    values = np.asarray([sample.value for sample in normalized], dtype=np.float64)
    finite = np.isfinite(values)
    if not bool(finite.all()):
        report = _empty_metric(metric, "measurement_failed", "nonfinite_value")
        report["count"] = len(normalized)
        report["finite_count"] = int(finite.sum())
        return report
    if not normalized:
        return _empty_metric(metric, "measured", None)

    polarity = _POLARITY[metric]
    worst_value = float(values.min() if polarity == "higher_is_better" else values.max())
    tied = [sample for sample in normalized if float(sample.value) == worst_value]
    worst = min(tied, key=lambda sample: sample.entity_id)
    provenance_complete = _sample_provenance_complete(worst)
    return {
        "status": "measured",
        "reason": None,
        "polarity": polarity,
        "count": len(normalized),
        "finite_count": len(normalized),
        "p95": float(np.percentile(values, 95, method=PERCENTILE_METHOD)),
        "p99": float(np.percentile(values, 99, method=PERCENTILE_METHOD)),
        "worst_value": worst_value,
        "worst_entity_id": worst.entity_id,
        **_sample_provenance(worst),
        "provenance_complete": provenance_complete,
    }


def _empty_metric(metric: str, status: str, reason: str | None) -> dict[str, Any]:
    return {
        "status": status,
        "reason": reason,
        "polarity": _POLARITY[metric],
        "count": 0,
        "finite_count": 0,
        "p95": None,
        "p99": None,
        "worst_value": None,
        "worst_entity_id": None,
        **{key: None for key in _PROVENANCE_KEYS},
        "provenance_complete": False,
    }


def _coerce_sample(raw: object) -> QualitySample | None:
    if isinstance(raw, QualitySample):
        sample = raw
    elif isinstance(raw, Mapping):
        entity_id = raw.get("entity_id")
        if isinstance(entity_id, bool) or not isinstance(entity_id, (int, np.integer)):
            return None
        value = raw.get("value")
        try:
            numeric_value = None if value is None else float(value)
        except (TypeError, ValueError):
            numeric_value = math.nan
        sample = QualitySample(
            entity_id=int(entity_id),
            value=numeric_value,
            source_entity_id=_optional_int(raw.get("source_entity_id", raw.get("source_entity"))),
            patch=_optional_text(raw.get("patch")),
            feature=_optional_text(raw.get("feature")),
            physical_group=_optional_text(raw.get("physical_group")),
            layer=raw.get("layer"),
            provenance=raw.get("provenance"),
            metric_tensor=raw.get("metric_tensor"),
        )
    else:
        return None
    if isinstance(sample.entity_id, bool) or not isinstance(sample.entity_id, (int, np.integer)):
        return None
    if sample.value is None:
        return None
    try:
        value = float(sample.value)
    except (TypeError, ValueError):
        return None
    return QualitySample(
        entity_id=int(sample.entity_id),
        value=value,
        source_entity_id=_optional_int(sample.source_entity_id),
        patch=_optional_text(sample.patch),
        feature=_optional_text(sample.feature),
        physical_group=_optional_text(sample.physical_group),
        layer=sample.layer,
        provenance=sample.provenance,
        metric_tensor=sample.metric_tensor,
    )


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        return None
    return int(value)


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _sample_provenance(sample: QualitySample) -> dict[str, Any]:
    return {
        "source_entity_id": sample.source_entity_id,
        "patch": sample.patch,
        "feature": sample.feature,
        "physical_group": sample.physical_group,
        "layer": sample.layer,
        "provenance": sample.provenance,
    }


def _sample_provenance_complete(sample: QualitySample) -> bool:
    return (
        sample.source_entity_id is not None
        and sample.layer is not None
        and sample.provenance is not None
    )


def _metrics_provenance_complete(metrics: Mapping[str, Mapping[str, Any]]) -> bool:
    measured = [metric for metric in metrics.values() if metric["status"] == "measured"]
    return bool(measured) and all(bool(metric["provenance_complete"]) for metric in measured)
