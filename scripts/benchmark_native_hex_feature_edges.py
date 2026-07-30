#!/usr/bin/env python3
"""Benchmark the native_hex feature-edge extractor against its Python oracle."""

from __future__ import annotations

import argparse
import gc
import json
import statistics
import time
from typing import Any

import numpy as np
import numpy.typing as npt

from core.generator.native_hex import snap

type FloatArray = npt.NDArray[np.float64]
type IntArray = npt.NDArray[np.int64]


def _surface_grid(axis_cells: int) -> tuple[FloatArray, IntArray]:
    axis: FloatArray = np.arange(axis_cells + 1, dtype=np.float64)
    x: FloatArray
    y: FloatArray
    x, y = np.meshgrid(axis, axis, indexing="ij")
    vertices = np.column_stack((x.ravel(), y.ravel(), np.zeros(x.size)))
    vertex_ids: IntArray = np.arange((axis_cells + 1) ** 2, dtype=np.int64).reshape(
        axis_cells + 1, axis_cells + 1
    )
    quads = np.stack(
        (
            vertex_ids[:-1, :-1],
            vertex_ids[1:, :-1],
            vertex_ids[1:, 1:],
            vertex_ids[:-1, 1:],
        ),
        axis=-1,
    ).reshape(-1, 4)
    faces = np.concatenate((quads[:, (0, 1, 2)], quads[:, (0, 2, 3)]), axis=0)
    return np.ascontiguousarray(vertices), np.ascontiguousarray(faces)


def _extract(backend: Any | None, vertices: FloatArray, faces: IntArray) -> Any:
    snap._NATIVE_SNAP = backend
    snap._NATIVE_SNAP_IMPORT_ATTEMPTED = True
    return snap._extract_feature_edge_segments(vertices, faces, 30.0)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--axis-cells", type=int, default=240)
    parser.add_argument("--repeats", type=int, default=7)
    args = parser.parse_args()
    if args.axis_cells < 1 or args.repeats < 3:
        parser.error("axis-cells must be positive and repeats must be at least 3")

    native = snap._load_native_snap()
    if native is None or not hasattr(native, "extract_feature_edges"):
        raise SystemExit("native_snap.extract_feature_edges is unavailable")

    vertices, faces = _surface_grid(args.axis_cells)
    expected = _extract(None, vertices, faces)
    actual = _extract(native, vertices, faces)
    parity = np.array_equal(expected, actual) and np.array_equal(
        getattr(expected, "_seg_weight"), getattr(actual, "_seg_weight")
    )

    _extract(None, vertices, faces)
    _extract(native, vertices, faces)
    timings: dict[str, list[float]] = {"python": [], "native": []}
    for repeat in range(args.repeats):
        order = (("python", None), ("native", native))
        if repeat % 2:
            order = tuple(reversed(order))
        for name, backend in order:
            gc.collect()
            start = time.perf_counter()
            result = _extract(backend, vertices, faces)
            timings[name].append(time.perf_counter() - start)
            if not np.array_equal(result, expected) or not np.array_equal(
                getattr(result, "_seg_weight"), getattr(expected, "_seg_weight")
            ):
                parity = False

    python_median = statistics.median(timings["python"])
    native_median = statistics.median(timings["native"])
    native_p95 = float(np.percentile(timings["native"], 95))
    report = {
        "vertices": int(vertices.shape[0]),
        "triangles": int(faces.shape[0]),
        "feature_segments": int(actual.shape[0]),
        "repeats": args.repeats,
        "python_seconds": timings["python"],
        "native_seconds": timings["native"],
        "python_median_seconds": python_median,
        "native_median_seconds": native_median,
        "native_p95_seconds": native_p95,
        "speedup": python_median / native_median,
        "exact_parity": parity,
        "acceptance": parity and native_median <= 0.203 and python_median / native_median >= 4.0,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["acceptance"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
