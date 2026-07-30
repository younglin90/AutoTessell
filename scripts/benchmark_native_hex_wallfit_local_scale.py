#!/usr/bin/env python3
"""Benchmark C++ wall-fit local scales against the exact Python oracle."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
import tracemalloc
from collections import defaultdict
from collections.abc import Callable
from typing import Any, cast

import numpy as np

from core.generator.native_hex import quality
from core.generator.native_hex.mesher import _wall_fit_snap
from scripts.benchmark_native_hex_wallfit_initial_projection import _fixture


class _OracleProxy:
    def __init__(self, module: Any, oracle: Callable[..., np.ndarray]) -> None:
        self._module = module
        self._oracle = oracle

    def boundary_vertex_local_scales(self, *args: Any) -> np.ndarray:
        return self._oracle(*args)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._module, name)


def _boundary_context(
    cell_faces: list[list[list[int]]],
) -> tuple[np.ndarray, dict[int, set[int]]]:
    face_cells: dict[tuple[int, ...], list[int]] = defaultdict(list)
    for cell_index, cell in enumerate(cell_faces):
        for face in cell:
            face_cells[tuple(sorted(int(vertex) for vertex in face))].append(cell_index)
    boundary_vertices: set[int] = set()
    for face_key, owners in face_cells.items():
        if len(owners) == 1:
            boundary_vertices.update(face_key)
    incident: dict[int, set[int]] = {
        vertex: set() for vertex in boundary_vertices
    }
    for cell_index, cell in enumerate(cell_faces):
        cell_vertices = {int(vertex) for face in cell for vertex in face}
        for vertex in cell_vertices & boundary_vertices:
            incident[vertex].add(cell_index)
    return np.asarray(sorted(boundary_vertices), dtype=np.int64), incident


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--grid", type=int, default=16)
    parser.add_argument("--repeats", type=int, default=12)
    parser.add_argument("--memory-repeats", type=int, default=5)
    parser.add_argument("--kernel-repeats", type=int, default=11)
    args = parser.parse_args()
    if (
        args.grid <= 0
        or args.repeats <= 0
        or args.memory_repeats <= 0
        or args.kernel_repeats <= 0
    ):
        parser.error("grid and repeat counts must be positive")

    native_module = quality._load_native_hex_quality()
    if native_module is None or not hasattr(
        native_module, "boundary_vertex_local_scales"
    ):
        raise RuntimeError(
            "updated native_hex_quality is required; set AUTOTESSELL_EXT_BUILD_DIR"
        )
    points, cell_faces, surface_points, surface_faces = _fixture(args.grid)
    expected_boundary, incident = _boundary_context(cell_faces)

    def python_oracle(
        query_points: np.ndarray,
        query_cells: list[list[list[int]]],
        boundary: np.ndarray,
    ) -> np.ndarray:
        if query_cells is not cell_faces or not np.array_equal(boundary, expected_boundary):
            raise RuntimeError("benchmark oracle received unexpected topology")
        values = np.zeros(boundary.shape[0], dtype=np.float64)
        for output_index, vertex in enumerate(boundary.tolist()):
            for cell_index in incident[vertex]:
                for face in query_cells[cell_index]:
                    for edge in range(len(face)):
                        values[output_index] = max(
                            values[output_index],
                            float(
                                np.linalg.norm(
                                    query_points[face[edge]]
                                    - query_points[face[(edge + 1) % len(face)]]
                                )
                            ),
                        )
        return cast(np.ndarray, values)

    oracle_module = _OracleProxy(native_module, python_oracle)
    python_oracle(points, cell_faces, expected_boundary)
    native_module.boundary_vertex_local_scales(
        points, cell_faces, expected_boundary
    )
    python_kernel_times: list[float] = []
    native_kernel_times: list[float] = []
    for repeat in range(args.kernel_repeats):
        kernel_order = [
            (python_oracle, python_kernel_times),
            (native_module.boundary_vertex_local_scales, native_kernel_times),
        ]
        if repeat % 2:
            kernel_order.reverse()
        for kernel, samples in kernel_order:
            started = time.perf_counter()
            kernel(points, cell_faces, expected_boundary)
            samples.append(time.perf_counter() - started)

    def run(module: Any) -> tuple[np.ndarray, dict[str, object]]:
        quality._NATIVE_HEX_QUALITY = module
        quality._NATIVE_HEX_QUALITY_IMPORT_ATTEMPTED = True
        return cast(
            tuple[np.ndarray, dict[str, object]],
            _wall_fit_snap(
                points,
                cell_faces,
                surface_points,
                surface_faces,
                1.0 / args.grid,
                tol=1.0e-12,
                ratio=0.5,
                iters=1,
            ),
        )

    for _ in range(2):
        run(oracle_module)
        run(native_module)

    baseline_times: list[float] = []
    native_times: list[float] = []
    snapshots: list[tuple[str, dict[str, object]]] = []
    for repeat in range(args.repeats):
        order = [(oracle_module, baseline_times), (native_module, native_times)]
        if repeat % 2:
            order.reverse()
        for module, samples in order:
            started = time.perf_counter()
            output, stats = run(module)
            samples.append(time.perf_counter() - started)
            snapshots.append((hashlib.sha256(output.tobytes()).hexdigest(), stats))

    def memory_peaks(module: Any) -> list[int]:
        peaks: list[int] = []
        for _ in range(args.memory_repeats):
            tracemalloc.start()
            run(module)
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            peaks.append(peak)
        return peaks

    baseline_peak = memory_peaks(oracle_module)
    native_peak = memory_peaks(native_module)
    baseline_median = statistics.median(baseline_times)
    native_median = statistics.median(native_times)
    python_kernel_median = statistics.median(python_kernel_times)
    native_kernel_median = statistics.median(native_kernel_times)
    print(
        json.dumps(
            {
                "absolute_budget_pass": native_median <= 0.30,
                "baseline_median_s": baseline_median,
                "baseline_peak_bytes_median": statistics.median(baseline_peak),
                "baseline_samples_s": baseline_times,
                "exact_hashes": len({digest for digest, _ in snapshots}) == 1,
                "exact_stats": all(stats == snapshots[0][1] for _, stats in snapshots),
                "fixture_cells": len(cell_faces),
                "fixture_points": len(points),
                "kernel_gate_pass": python_kernel_median / native_kernel_median
                >= 20.0,
                "kernel_native_median_s": native_kernel_median,
                "kernel_python_median_s": python_kernel_median,
                "kernel_speedup": python_kernel_median / native_kernel_median,
                "memory_gate_pass": statistics.median(native_peak)
                <= statistics.median(baseline_peak),
                "native_median_s": native_median,
                "native_peak_bytes_median": statistics.median(native_peak),
                "native_samples_s": native_times,
                "output_sha256": snapshots[0][0],
                "relative_gate_pass": baseline_median / native_median >= 1.70,
                "speedup": baseline_median / native_median,
                "stats": snapshots[0][1],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
