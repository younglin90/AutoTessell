#!/usr/bin/env python3
"""Reproduce TRI-CURV-SIZING-CPP23-1 parity and timing evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
from collections.abc import Callable

import numpy as np

from core.preprocessor.native_tri.operator_loop import (
    _estimate_curvature_sizing_python,
    estimate_curvature_sizing,
)
from core.utils.native_extensions import load_native_metrics


def _fixture(size: int) -> tuple[np.ndarray, np.ndarray]:
    axis = np.linspace(0.0, 1.0, size)
    x, y = np.meshgrid(axis, axis, indexing="ij")
    vertices = np.column_stack(
        (x.ravel(), y.ravel(), 0.02 * np.sin(8.0 * x).ravel() * np.sin(8.0 * y).ravel())
    )
    row, column = np.meshgrid(
        np.arange(size - 1, dtype=np.int64),
        np.arange(size - 1, dtype=np.int64),
        indexing="ij",
    )
    first = (row * size + column).ravel()
    second = first + size
    fourth = second + 1
    third = first + 1
    faces = np.empty((2 * len(first), 3), dtype=np.int64)
    faces[0::2] = np.column_stack((first, second, fourth))
    faces[1::2] = np.column_stack((first, fourth, third))
    return np.ascontiguousarray(vertices), faces


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
    parser.add_argument("--size", type=int, default=260)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--epsilon", type=float, default=1e-4)
    arguments = parser.parse_args()
    if arguments.size < 2 or arguments.repeats < 1:
        raise SystemExit("size must be >= 2 and repeats must be >= 1")
    native = load_native_metrics()
    if native is None or not hasattr(native, "estimate_triangle_curvature_sizing"):
        raise SystemExit("native_metrics.estimate_triangle_curvature_sizing is unavailable")

    vertices, faces = _fixture(arguments.size)
    _estimate_curvature_sizing_python(vertices, faces, arguments.epsilon)
    estimate_curvature_sizing(vertices, faces, arguments.epsilon)
    python_seconds, python_output = _median_seconds(
        lambda: _estimate_curvature_sizing_python(vertices, faces, arguments.epsilon),
        arguments.repeats,
    )
    native_seconds, native_output = _median_seconds(
        lambda: estimate_curvature_sizing(vertices, faces, arguments.epsilon),
        arguments.repeats,
    )
    difference = float(np.max(np.abs(python_output - native_output)))
    if not np.allclose(python_output, native_output, rtol=2e-14, atol=2e-14):
        raise SystemExit(f"Python/native mismatch: max_abs={difference}")
    print(
        json.dumps(
            {
                "vertices": len(vertices),
                "faces": len(faces),
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
