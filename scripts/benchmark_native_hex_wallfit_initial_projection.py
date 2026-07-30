#!/usr/bin/env python3
"""Benchmark exact native batching of wall-fit's initial projections."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
import tracemalloc
from typing import Any, cast

import numpy as np

from core.generator.native_hex import snap
from core.generator.native_hex.mesher import _wall_fit_snap


def _fixture(
    grid: int,
) -> tuple[np.ndarray, list[list[list[int]]], np.ndarray, np.ndarray]:
    coords = np.linspace(0.0, 1.0, grid + 1)
    points = np.asarray(
        [[x, y, z] for z in coords for y in coords for x in coords],
        dtype=np.float64,
    )

    def vertex(i: int, j: int, k: int) -> int:
        return k * (grid + 1) ** 2 + j * (grid + 1) + i

    cell_faces: list[list[list[int]]] = []
    for k in range(grid):
        for j in range(grid):
            for i in range(grid):
                a, b = vertex(i, j, k), vertex(i + 1, j, k)
                c, d = vertex(i + 1, j + 1, k), vertex(i, j + 1, k)
                e, f = vertex(i, j, k + 1), vertex(i + 1, j, k + 1)
                g, h = vertex(i + 1, j + 1, k + 1), vertex(i, j + 1, k + 1)
                cell_faces.append(
                    [
                        [a, d, c, b],
                        [e, f, g, h],
                        [a, e, h, d],
                        [b, c, g, f],
                        [a, b, f, e],
                        [d, h, g, c],
                    ]
                )
    low, high = -0.02, 1.02
    surface_points = np.asarray(
        [
            [low, low, low],
            [high, low, low],
            [high, high, low],
            [low, high, low],
            [low, low, high],
            [high, low, high],
            [high, high, high],
            [low, high, high],
        ],
        dtype=np.float64,
    )
    surface_faces = np.asarray(
        [
            [0, 2, 1],
            [0, 3, 2],
            [4, 5, 6],
            [4, 6, 7],
            [0, 1, 5],
            [0, 5, 4],
            [3, 7, 6],
            [3, 6, 2],
            [0, 4, 7],
            [0, 7, 3],
            [1, 2, 6],
            [1, 6, 5],
        ],
        dtype=np.int64,
    )
    return points, cell_faces, surface_points, surface_faces


def _select_native(module: Any | None) -> None:
    snap._NATIVE_SNAP = module
    snap._NATIVE_SNAP_IMPORT_ATTEMPTED = True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--grid", type=int, default=16)
    parser.add_argument("--repeats", type=int, default=12)
    parser.add_argument("--memory-repeats", type=int, default=5)
    args = parser.parse_args()
    if args.grid <= 0 or args.repeats <= 0 or args.memory_repeats <= 0:
        parser.error("grid and repeat counts must be positive")

    native_module = snap._load_native_snap()
    if native_module is None:
        raise RuntimeError("native_snap is required; set AUTOTESSELL_EXT_BUILD_DIR")
    points, cell_faces, surface_points, surface_faces = _fixture(args.grid)

    def run(module: Any | None) -> tuple[np.ndarray, dict[str, object]]:
        _select_native(module)
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
        run(None)
        run(native_module)

    baseline_times: list[float] = []
    native_times: list[float] = []
    snapshots: list[tuple[str, dict[str, object]]] = []
    for repeat in range(args.repeats):
        order = [(None, baseline_times), (native_module, native_times)]
        if repeat % 2:
            order.reverse()
        for module, samples in order:
            started = time.perf_counter()
            output, stats = run(module)
            samples.append(time.perf_counter() - started)
            snapshots.append((hashlib.sha256(output.tobytes()).hexdigest(), stats))

    def memory_peaks(module: Any | None) -> list[int]:
        peaks: list[int] = []
        for _ in range(args.memory_repeats):
            tracemalloc.start()
            run(module)
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            peaks.append(peak)
        return peaks

    baseline_peak = memory_peaks(None)
    native_peak = memory_peaks(native_module)
    baseline_median = statistics.median(baseline_times)
    native_median = statistics.median(native_times)
    print(
        json.dumps(
            {
                "absolute_budget_pass": native_median <= 0.57,
                "baseline_median_s": baseline_median,
                "baseline_peak_bytes_median": statistics.median(baseline_peak),
                "baseline_samples_s": baseline_times,
                "exact_hashes": len({digest for digest, _ in snapshots}) == 1,
                "exact_stats": all(stats == snapshots[0][1] for _, stats in snapshots),
                "fixture_cells": len(cell_faces),
                "fixture_points": len(points),
                "memory_gate_pass": statistics.median(native_peak)
                <= statistics.median(baseline_peak),
                "native_median_s": native_median,
                "native_peak_bytes_median": statistics.median(native_peak),
                "native_samples_s": native_times,
                "output_sha256": snapshots[0][0],
                "relative_gate_pass": baseline_median / native_median >= 1.10,
                "speedup": baseline_median / native_median,
                "stats": snapshots[0][1],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
