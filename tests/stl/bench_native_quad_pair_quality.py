"""Reproducible benchmark for the bulk native quad-pair selector.

Run from the repository root with ``AUTOTESSELL_EXT_BUILD_DIR`` pointing at a
Release build that contains ``native_metrics.select_quad_pairs``.
"""

from __future__ import annotations

import argparse
import gc
import json
import statistics
import time
import tracemalloc
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any, cast

import numpy as np
from numpy.typing import NDArray

from core.preprocessor.native_remesh.quad_dominant import (
    _select_quad_pairs_python,
    native_quad_dominant_remesh,
)
from core.utils import native_extensions


def _grid(size: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    x: NDArray[np.float64]
    y: NDArray[np.float64]
    x, y = np.meshgrid(
        np.arange(size + 1, dtype=np.float64),
        np.arange(size + 1, dtype=np.float64),
    )
    vertices = np.column_stack((x.ravel(), y.ravel(), np.zeros(x.size)))
    row: NDArray[np.int64] = np.arange(size, dtype=np.int64)[:, None]
    column: NDArray[np.int64] = np.arange(size, dtype=np.int64)[None, :]
    lower_left = row * (size + 1) + column
    triangles: NDArray[np.int64] = np.empty((2 * size * size, 3), dtype=np.int64)
    triangles[0::2] = np.stack(
        (
            lower_left.ravel(),
            (lower_left + 1).ravel(),
            (lower_left + size + 2).ravel(),
        ),
        axis=1,
    )
    triangles[1::2] = np.stack(
        (
            lower_left.ravel(),
            (lower_left + size + 2).ravel(),
            (lower_left + size + 1).ravel(),
        ),
        axis=1,
    )
    edge_faces: dict[tuple[int, int], list[int]] = {}
    for face_index, triangle in enumerate(triangles):
        for local in range(3):
            first = int(triangle[local])
            second = int(triangle[(local + 1) % 3])
            edge = (min(first, second), max(first, second))
            edge_faces.setdefault(edge, []).append(face_index)
    face_pairs = np.asarray(
        [sorted(incident) for incident in edge_faces.values() if len(incident) == 2],
        dtype=np.int64,
    )
    return vertices, triangles, face_pairs


def _timed(function: Callable[[], Any]) -> float:
    start = time.perf_counter()
    function()
    return time.perf_counter() - start


def _measure_alternating(
    first: Callable[[], Any], second: Callable[[], Any], repeats: int
) -> tuple[list[float], list[float]]:
    first()
    second()
    first_samples: list[float] = []
    second_samples: list[float] = []
    for repeat in range(repeats):
        if repeat % 2:
            order = ((second, second_samples), (first, first_samples))
        else:
            order = ((first, first_samples), (second, second_samples))
        for function, samples in order:
            samples.append(_timed(function))
    return first_samples, second_samples


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", type=int, default=60)
    parser.add_argument("--repeats", type=int, default=7)
    parser.add_argument("--trace-memory", action="store_true")
    args = parser.parse_args()

    native = native_extensions.load_native_metrics()
    if native is None or not hasattr(native, "select_quad_pairs"):
        raise SystemExit("native_metrics.select_quad_pairs is unavailable")
    vertices, triangles, face_pairs = _grid(args.size)
    keyword_arguments = {
        "min_scaled_jacobian": 0.2,
        "max_aspect_ratio": 4.0,
        "max_warpage": 0.05,
    }

    def python_kernel() -> tuple[np.ndarray, np.ndarray, np.ndarray, int]:
        return cast(
            tuple[np.ndarray, np.ndarray, np.ndarray, int],
            _select_quad_pairs_python(vertices, triangles, face_pairs, **keyword_arguments),
        )

    def native_kernel() -> dict[str, Any]:
        return cast(
            dict[str, Any],
            native.select_quad_pairs(
                vertices,
                triangles,
                face_pairs,
                keyword_arguments["min_scaled_jacobian"],
                keyword_arguments["max_aspect_ratio"],
                keyword_arguments["max_warpage"],
            ),
        )

    expected = python_kernel()
    observed = native_kernel()
    np.testing.assert_array_equal(observed["accepted_face_pairs"], expected[0])
    np.testing.assert_array_equal(observed["quads"], expected[1])
    np.testing.assert_allclose(observed["quality"], expected[2], rtol=0.0, atol=1e-14)
    assert observed["rejected_quality"] == expected[3]

    python_kernel_times, native_kernel_times = _measure_alternating(
        python_kernel, native_kernel, args.repeats
    )

    original_loader = native_extensions.load_native_metrics
    validation_only_backend = SimpleNamespace(
        validate_triangle_surface_and_build_edge_faces=(
            native.validate_triangle_surface_and_build_edge_faces
        )
    )

    def native_route() -> Any:
        return native_quad_dominant_remesh(vertices, triangles)

    def python_selector_route() -> Any:
        native_extensions.load_native_metrics = lambda: validation_only_backend
        try:
            return native_quad_dominant_remesh(vertices, triangles)
        finally:
            native_extensions.load_native_metrics = original_loader

    python_selector_public_times, native_public_times = _measure_alternating(
        python_selector_route, native_route, args.repeats
    )
    native_result = native_route()
    python_selector_result = python_selector_route()
    np.testing.assert_array_equal(native_result.vertices, python_selector_result.vertices)
    np.testing.assert_array_equal(native_result.triangles, python_selector_result.triangles)
    np.testing.assert_array_equal(native_result.quads, python_selector_result.quads)

    python_kernel_median = statistics.median(python_kernel_times)
    native_kernel_median = statistics.median(native_kernel_times)
    python_selector_public_median = statistics.median(python_selector_public_times)
    native_public_median = statistics.median(native_public_times)
    memory: dict[str, float | int] = {}
    if args.trace_memory:

        def peak_bytes(function: Callable[[], Any]) -> int:
            gc.collect()
            tracemalloc.start()
            function()
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            return peak

        python_peak = peak_bytes(python_kernel)
        native_peak = peak_bytes(native_kernel)
        memory = {
            "python_kernel_peak_bytes": python_peak,
            "native_kernel_peak_bytes": native_peak,
            "python_kernel_peak_bytes_per_pair": python_peak / len(face_pairs),
            "native_kernel_peak_bytes_per_pair": native_peak / len(face_pairs),
            "python_heap_reduction_percent": 100.0 * (1.0 - native_peak / python_peak),
        }
    print(
        json.dumps(
            {
                "vertices": len(vertices),
                "triangles": len(triangles),
                "face_pairs": len(face_pairs),
                "accepted_pairs": len(expected[0]),
                "repeats": args.repeats,
                "python_kernel_seconds": python_kernel_times,
                "native_kernel_seconds": native_kernel_times,
                "python_kernel_median_seconds": python_kernel_median,
                "native_kernel_median_seconds": native_kernel_median,
                "kernel_speedup": python_kernel_median / native_kernel_median,
                "python_selector_public_seconds": python_selector_public_times,
                "native_public_seconds": native_public_times,
                "python_selector_public_median_seconds": python_selector_public_median,
                "native_public_median_seconds": native_public_median,
                "public_speedup": python_selector_public_median / native_public_median,
                **memory,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
