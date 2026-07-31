"""Focused validity checks for the native_metrics binding-allocation benchmark."""

from __future__ import annotations

import pytest

from tests.bench_native_metrics_binding_allocation import (
    _layout_inputs,
    measure_aabb_binding,
)


def _native_metrics_or_skip():
    from core.evaluator import native_checker

    module = native_checker._load_native_metrics()
    if module is None:
        pytest.skip("native_metrics extension is not built")
    return module


def test_aabb_binding_measurement_accepts_all_representative_layouts() -> None:
    module = _native_metrics_or_skip()
    results = [
        measure_aabb_binding(module, layout=layout, count=256, repetitions=3)
        for layout in (
            "contiguous_float64",
            "strided_float64",
            "contiguous_float32",
        )
    ]

    assert [result.layout for result in results] == [
        "contiguous_float64",
        "strided_float64",
        "contiguous_float32",
    ]
    assert all(result.output_pair_count == 0 for result in results)
    assert all(result.median_seconds >= 0.0 for result in results)
    assert all(result.traced_peak_bytes >= 0 for result in results)


def test_layout_fixture_has_declared_dtype_and_contiguity() -> None:
    contiguous, _ = _layout_inputs(8, "contiguous_float64")
    strided, _ = _layout_inputs(8, "strided_float64")
    single_precision, _ = _layout_inputs(8, "contiguous_float32")

    assert contiguous.dtype.name == "float64" and contiguous.flags.c_contiguous
    assert strided.dtype.name == "float64" and not strided.flags.c_contiguous
    assert single_precision.dtype.name == "float32" and single_precision.flags.c_contiguous
