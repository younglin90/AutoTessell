"""Measure native_metrics AABB binding coercion without changing mesh output."""

from __future__ import annotations

import json
import statistics
import sys
import time
import tracemalloc
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))


@dataclass(frozen=True)
class BindingMeasurement:
    layout: str
    repetitions: int
    median_seconds: float
    traced_peak_bytes: int
    output_pair_count: int


def _native_metrics_or_raise() -> Any:
    from core.evaluator import native_checker

    module = native_checker._load_native_metrics()
    if module is None:
        raise RuntimeError("native_metrics extension is not built")
    return module


def _disjoint_aabbs(count: int) -> tuple[np.ndarray, np.ndarray]:
    coordinates = np.arange(count, dtype=np.float64) * 4.0
    minimum = np.zeros((count, 3), dtype=np.float64)
    minimum[:, 0] = coordinates
    maximum = minimum + 1.0
    return minimum, maximum


def _layout_inputs(count: int, layout: str) -> tuple[np.ndarray, np.ndarray]:
    minimum, maximum = _disjoint_aabbs(count)
    if layout == "contiguous_float64":
        return minimum, maximum
    if layout == "strided_float64":
        minimum_base = np.empty((2 * count, 3), dtype=np.float64)
        maximum_base = np.empty((2 * count, 3), dtype=np.float64)
        minimum_base[::2] = minimum
        maximum_base[::2] = maximum
        return minimum_base[::2], maximum_base[::2]
    if layout == "contiguous_float32":
        return minimum.astype(np.float32), maximum.astype(np.float32)
    raise ValueError(f"unknown layout: {layout}")


def measure_aabb_binding(
    module: Any,
    *,
    layout: str,
    count: int,
    repetitions: int,
) -> BindingMeasurement:
    """Measure traced Python allocation and elapsed time for one input layout."""
    minimum, maximum = _layout_inputs(count, layout)
    before = (minimum.copy(), maximum.copy())
    module.aabb_overlap_pairs(minimum, maximum, 0.0)
    samples: list[float] = []
    output_pair_count = 0
    tracemalloc.start()
    for _ in range(repetitions):
        started = time.perf_counter()
        result = module.aabb_overlap_pairs(minimum, maximum, 0.0)
        samples.append(time.perf_counter() - started)
        output_pair_count = int(len(result))
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    np.testing.assert_array_equal(minimum, before[0])
    np.testing.assert_array_equal(maximum, before[1])
    if output_pair_count != 0:
        raise AssertionError("disjoint benchmark inputs must produce no overlap pairs")
    return BindingMeasurement(
        layout,
        repetitions,
        statistics.median(samples),
        peak,
        output_pair_count,
    )


def main() -> None:
    module = _native_metrics_or_raise()
    results = [
        measure_aabb_binding(
            module,
            layout=layout,
            count=100_000,
            repetitions=9,
        )
        for layout in (
            "contiguous_float64",
            "strided_float64",
            "contiguous_float32",
        )
    ]
    print(json.dumps([asdict(result) for result in results], sort_keys=True))


if __name__ == "__main__":
    main()
