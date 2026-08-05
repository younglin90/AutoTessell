"""Independent, fail-closed quality admission for the Native Poly release route.

The producer may use a permissive diagnostic checker while searching for a
candidate. Release admission is a separate policy: it reads measured metrics
from the staged artifact and refuses a candidate when a required metric is
missing, non-finite, or outside the quality-first envelope. Cell count is not
part of this decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Final


POLY_CORE_LIMITS: Final[dict[str, float]] = {
    "max_non_orthogonality": 50.0,
    "max_skewness": 0.50,
    "max_aspect_ratio": 20.0,
}
POLY_BL_LIMITS: Final[dict[str, float]] = {
    "max_non_orthogonality": 65.0,
    "max_skewness": 0.70,
    "max_metric_aspect_ratio": 3.0,
}


@dataclass(frozen=True, slots=True)
class NativePolyQualityAdmission:
    """Measured release decision for one staged Poly artifact."""

    accepted: bool
    status: str
    reason: str
    metrics: dict[str, float | int | bool]
    limits: dict[str, float]

    def as_dict(self) -> dict[str, object]:
        return {
            "accepted": self.accepted,
            "status": self.status,
            "reason": self.reason,
            "metrics": dict(self.metrics),
            "limits": dict(self.limits),
        }


def assess_native_poly_quality(
    metrics: object,
    *,
    boundary_layer: bool = False,
) -> NativePolyQualityAdmission:
    """Apply strict Poly quality limits to independently measured metrics.

    This deliberately uses the maximum for the current checker contract. A
    future histogram witness may add p95/p99, but missing distribution data must
    not turn a release rejection into a pass.
    """

    limits = dict(POLY_BL_LIMITS if boundary_layer else POLY_CORE_LIMITS)
    if not isinstance(metrics, dict):
        return NativePolyQualityAdmission(
            False, "rejected", "metrics_missing", {}, limits
        )

    required = tuple(limits)
    measured: dict[str, float | int | bool] = dict(metrics)
    for name in required:
        value = metrics.get(name)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return NativePolyQualityAdmission(
                False, "rejected", f"{name}_missing", measured, limits
            )
        if not isfinite(float(value)):
            return NativePolyQualityAdmission(
                False, "rejected", f"{name}_non_finite", measured, limits
            )
        if float(value) > limits[name]:
            return NativePolyQualityAdmission(
                False, "rejected", f"{name}_gate_failed", measured, limits
            )

    if metrics.get("strict_topology_valid") is not True:
        return NativePolyQualityAdmission(
            False, "rejected", "strict_topology_gate_failed", measured, limits
        )
    if metrics.get("negative_volumes") != 0:
        return NativePolyQualityAdmission(
            False, "rejected", "negative_volume_gate_failed", measured, limits
        )
    cells = metrics.get("cells")
    if not isinstance(cells, int) or isinstance(cells, bool) or cells <= 0:
        return NativePolyQualityAdmission(
            False, "rejected", "positive_cell_count_missing", measured, limits
        )
    return NativePolyQualityAdmission(True, "accepted", "", measured, limits)


__all__ = [
    "NativePolyQualityAdmission",
    "POLY_BL_LIMITS",
    "POLY_CORE_LIMITS",
    "assess_native_poly_quality",
]
