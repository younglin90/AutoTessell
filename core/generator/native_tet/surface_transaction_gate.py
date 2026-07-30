"""Source-surface transaction for the optional metric-tensor sweep.

The metric-tensor sweep already protects its quality and writer-topology
contracts.  This module adds a deliberately separate, default-OFF source
fidelity check at its call site: accepted candidates must not make the source
surface metrics worse than their pre-sweep values.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import numpy as np

from core.generator.native_tet.rescue_gate import SourceTopologyAudit, audit_source_topology

_METRIC_SOURCE_TXN_ENV = "AUTO_TESSELL_TET_METRIC_SOURCE_TXN"
_SOURCE_METRIC_JITTER_EPSILON = 1e-12


@dataclass(frozen=True)
class SourceSurfaceMetrics:
    """Source-fidelity metrics used by the metric-sweep transaction."""

    hausdorff_relative: float
    plane_coverage: float
    area_coverage: float

    @property
    def finite(self) -> bool:
        """Return whether every metric can safely participate in a comparison."""
        return all(
            bool(np.isfinite(value))
            for value in (
                self.hausdorff_relative,
                self.plane_coverage,
                self.area_coverage,
            )
        )


@dataclass(frozen=True)
class MetricSurfaceTransactionReport:
    """Decision and pre/post source metrics for one metric-sweep candidate."""

    accepted: bool
    reason: str
    pre: SourceSurfaceMetrics
    post: SourceSurfaceMetrics


@dataclass(frozen=True)
class MetricTopologyTransactionReport:
    """Source-aware topology decision for one metric-sweep candidate."""

    accepted: bool
    reason: str
    audit: SourceTopologyAudit | None


def metric_source_transaction_enabled() -> bool:
    """Return whether the source-fidelity metric transaction is explicitly enabled."""
    return os.environ.get(_METRIC_SOURCE_TXN_ENV, "0") == "1"


def measure_source_surface_metrics(
    source_vertices: np.ndarray,
    source_faces: np.ndarray,
    points: np.ndarray,
    tets: np.ndarray,
) -> SourceSurfaceMetrics:
    """Measure existing normalized Hausdorff and plane/area source coverage."""
    from core.generator.native_tet.hausdorff import hausdorff_vs_input
    from core.generator.native_tet.plane_coverage import plane_coverage

    source_vertices = np.asarray(source_vertices, dtype=np.float64)
    source_faces = np.asarray(source_faces, dtype=np.int64)
    points = np.asarray(points, dtype=np.float64)
    tets = np.asarray(tets, dtype=np.int64)

    hausdorff = hausdorff_vs_input(
        source_vertices,
        source_faces,
        points,
        tets,
        n_samples_per_tri=2,
    )
    bbox = source_vertices.max(axis=0) - source_vertices.min(axis=0)
    diagonal = float(np.linalg.norm(bbox)) + 1e-30
    coverage = plane_coverage(source_vertices, source_faces, points, tets)
    return SourceSurfaceMetrics(
        hausdorff_relative=float(hausdorff.h_symmetric / diagonal),
        plane_coverage=float(coverage.plane_coverage),
        area_coverage=float(coverage.area_coverage),
    )


def _nonfinite_metrics() -> SourceSurfaceMetrics:
    return SourceSurfaceMetrics(
        hausdorff_relative=float("nan"),
        plane_coverage=float("nan"),
        area_coverage=float("nan"),
    )


def _measure_or_nonfinite(
    source_vertices: np.ndarray,
    source_faces: np.ndarray,
    points: np.ndarray,
    tets: np.ndarray,
) -> tuple[SourceSurfaceMetrics, bool]:
    try:
        return (
            measure_source_surface_metrics(
                source_vertices,
                source_faces,
                points,
                tets,
            ),
            False,
        )
    except Exception:
        # This opt-in gate is fail-closed.  The caller reports the fixed reason
        # alongside the non-finite metric placeholders without exposing a
        # potentially unstable exception string as a runtime contract.
        return _nonfinite_metrics(), True


def audit_metric_surface_candidate(
    source_vertices: np.ndarray,
    source_faces: np.ndarray,
    pre_points: np.ndarray,
    pre_tets: np.ndarray,
    candidate_points: np.ndarray,
    candidate_tets: np.ndarray,
) -> MetricSurfaceTransactionReport:
    """Accept only finite candidates that do not worsen any source metric.

    The normalized symmetric Hausdorff distance is the primary metric.  Plane
    and area coverage are retained as auxiliary axes for planar source meshes.
    A fixed, tiny epsilon admits only numerical measurement jitter.
    """
    pre, pre_error = _measure_or_nonfinite(
        source_vertices,
        source_faces,
        pre_points,
        pre_tets,
    )
    post, post_error = _measure_or_nonfinite(
        source_vertices,
        source_faces,
        candidate_points,
        candidate_tets,
    )

    errors: list[str] = []
    if pre_error:
        errors.append("pre_source_metric_error")
    if post_error:
        errors.append("post_source_metric_error")
    if errors:
        return MetricSurfaceTransactionReport(False, "+".join(errors), pre, post)
    if not pre.finite:
        return MetricSurfaceTransactionReport(False, "pre_source_metrics_nonfinite", pre, post)
    if not post.finite:
        return MetricSurfaceTransactionReport(False, "post_source_metrics_nonfinite", pre, post)

    regressions: list[str] = []
    if post.hausdorff_relative > pre.hausdorff_relative + _SOURCE_METRIC_JITTER_EPSILON:
        regressions.append("hausdorff_relative_worsened")
    if post.plane_coverage < pre.plane_coverage - _SOURCE_METRIC_JITTER_EPSILON:
        regressions.append("plane_coverage_worsened")
    if post.area_coverage < pre.area_coverage - _SOURCE_METRIC_JITTER_EPSILON:
        regressions.append("area_coverage_worsened")
    if regressions:
        return MetricSurfaceTransactionReport(False, "+".join(regressions), pre, post)
    return MetricSurfaceTransactionReport(True, "ok", pre, post)


def apply_metric_surface_transaction(
    source_vertices: np.ndarray,
    source_faces: np.ndarray,
    pre_points: np.ndarray,
    pre_tets: np.ndarray,
    candidate_points: np.ndarray,
    candidate_tets: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, MetricSurfaceTransactionReport]:
    """Return the candidate only when its source audit commits it.

    ``pre_points`` and ``pre_tets`` are snapshots owned by the caller.  On a
    rejection they are returned unchanged, which makes rollback exact without
    a repair, projection, or partial commit.
    """
    report = audit_metric_surface_candidate(
        source_vertices,
        source_faces,
        pre_points,
        pre_tets,
        candidate_points,
        candidate_tets,
    )
    if report.accepted:
        return candidate_points, candidate_tets, report
    return pre_points, pre_tets, report


def apply_metric_topology_transaction(
    source_vertices: np.ndarray,
    source_faces: np.ndarray,
    pre_points: np.ndarray,
    pre_tets: np.ndarray,
    candidate_points: np.ndarray,
    candidate_tets: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, MetricTopologyTransactionReport]:
    """Commit a metric-sweep candidate only with a source-topology certificate.

    The metric sweep owns distinct candidate arrays, so rejection returns the
    caller's exact pre-sweep objects without repairing connectivity or moving a
    source vertex.  Audit failures are deterministic rejections, not silent
    fallbacks.
    """
    try:
        audit = audit_source_topology(
            source_vertices,
            source_faces,
            candidate_points,
            candidate_tets,
        )
    except Exception:
        report = MetricTopologyTransactionReport(
            accepted=False,
            reason="source_topology_audit_error",
            audit=None,
        )
        return pre_points, pre_tets, report

    failures: list[str] = []
    if not audit.boundary.valid:
        failures.append("local_boundary_invalid")
    if not audit.components.bijective:
        failures.append("source_component_bijection_invalid")
    if failures:
        report = MetricTopologyTransactionReport(
            accepted=False,
            reason="+".join(failures),
            audit=audit,
        )
        return pre_points, pre_tets, report

    report = MetricTopologyTransactionReport(
        accepted=True,
        reason="ok",
        audit=audit,
    )
    return candidate_points, candidate_tets, report


__all__ = [
    "MetricTopologyTransactionReport",
    "MetricSurfaceTransactionReport",
    "SourceSurfaceMetrics",
    "apply_metric_topology_transaction",
    "apply_metric_surface_transaction",
    "audit_metric_surface_candidate",
    "measure_source_surface_metrics",
    "metric_source_transaction_enabled",
]
