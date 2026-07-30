#!/usr/bin/env python3
"""Reproduce TRI-FLIP-QUALITY-CPP23-1 direct-kernel timing evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
from collections.abc import Callable

import numpy as np

from core.preprocessor.native_tri.operator_loop import (
    _triangle_quality_batch,
    _triangle_quality_batch_python,
)
from core.utils.native_extensions import load_native_metrics


def _fixture(count: int) -> np.ndarray:
    rng = np.random.default_rng(20260731)
    origins = rng.uniform(-10.0, 10.0, size=(count, 1, 3))
    offsets = rng.normal(size=(count, 2, 3))
    return np.ascontiguousarray(np.concatenate((origins, origins + offsets), axis=1))


def _median_seconds(call: Callable[[], np.ndarray], repeats: int) -> tuple[float, np.ndarray]:
    samples: list[float] = []
    output = np.empty(0, dtype=np.float64)
    for _ in range(repeats):
        started = time.perf_counter()
        output = call()
        samples.append(time.perf_counter() - started)
    return statistics.median(samples), output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--triangles", type=int, default=50_000)
    parser.add_argument("--repeats", type=int, default=5)
    arguments = parser.parse_args()
    if arguments.triangles < 1 or arguments.repeats < 1:
        raise SystemExit("triangles and repeats must be positive")
    native = load_native_metrics()
    if native is None or not hasattr(native, "triangle_quality_batch"):
        raise SystemExit("native_metrics.triangle_quality_batch is unavailable")

    triangles = _fixture(arguments.triangles)
    _triangle_quality_batch_python(triangles[:10])
    _triangle_quality_batch(triangles[:10])
    python_seconds, python_output = _median_seconds(
        lambda: _triangle_quality_batch_python(triangles), arguments.repeats
    )
    native_seconds, native_output = _median_seconds(
        lambda: _triangle_quality_batch(triangles), arguments.repeats
    )
    difference = float(np.max(np.abs(python_output - native_output)))
    if not np.allclose(python_output, native_output, rtol=2e-15, atol=2e-15):
        raise SystemExit(f"Python/native mismatch: max_abs={difference}")
    print(
        json.dumps(
            {
                "triangles": len(triangles),
                "python_median_seconds": python_seconds,
                "native_median_seconds": native_seconds,
                "speedup": python_seconds / native_seconds,
                "max_absolute_difference": difference,
                "python_sha256": hashlib.sha256(python_output.tobytes()).hexdigest(),
                "native_sha256": hashlib.sha256(native_output.tobytes()).hexdigest(),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
