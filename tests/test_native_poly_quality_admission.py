"""L0 contract tests for independent Native Poly quality admission."""

from __future__ import annotations

from core.evaluator.native_poly_quality_admission import assess_native_poly_quality


def _metrics(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "cells": 128,
        "negative_volumes": 0,
        "strict_topology_valid": True,
        "max_non_orthogonality": 42.0,
        "max_skewness": 0.31,
        "max_aspect_ratio": 12.0,
    }
    value.update(overrides)
    return value


def test_core_quality_admission_accepts_only_strict_measured_envelope() -> None:
    report = assess_native_poly_quality(_metrics())
    assert report.accepted is True
    assert report.status == "accepted"
    assert report.reason == ""


def test_core_quality_admission_rejects_the_previous_poly_tail() -> None:
    report = assess_native_poly_quality(
        _metrics(max_non_orthogonality=86.73399653940153, max_skewness=3.0654950568643824)
    )
    assert report.accepted is False
    assert report.reason == "max_non_orthogonality_gate_failed"


def test_quality_admission_is_fail_closed_for_missing_distribution_metric() -> None:
    values = _metrics()
    del values["max_aspect_ratio"]
    report = assess_native_poly_quality(values)
    assert report.accepted is False
    assert report.reason == "max_aspect_ratio_missing"


def test_positive_boundary_layer_uses_metric_aspect_not_raw_anisotropic_aspect() -> None:
    report = assess_native_poly_quality(
        {
            "cells": 64,
            "negative_volumes": 0,
            "strict_topology_valid": True,
            "max_non_orthogonality": 61.0,
            "max_skewness": 0.61,
            "max_metric_aspect_ratio": 2.4,
        },
        boundary_layer=True,
    )
    assert report.accepted is True


def test_positive_boundary_layer_rejects_missing_metric_aspect() -> None:
    report = assess_native_poly_quality(
        {
            "cells": 64,
            "negative_volumes": 0,
            "strict_topology_valid": True,
            "max_non_orthogonality": 61.0,
            "max_skewness": 0.61,
        },
        boundary_layer=True,
    )
    assert report.accepted is False
    assert report.reason == "max_metric_aspect_ratio_missing"
