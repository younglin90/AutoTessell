"""Benchmark C++23 native-poly dual points against the Python oracle."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections.abc import Callable
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.generator.native_poly.dual import _compute_tet_dual_points_python  # noqa: E402
from core.utils.native_extensions import load_native_polymesh  # noqa: E402


def _fixture(n_tets: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    bases = rng.uniform(-10.0, 10.0, size=(n_tets, 3))
    offsets = np.asarray(
        ((0.0, 0.0, 0.0), (0.017, 0.0, 0.0), (0.0, 0.013, 0.0), (0.0, 0.0, 0.011)),
        dtype=np.float64,
    )
    points = np.ascontiguousarray((bases[:, None, :] + offsets).reshape(-1, 3))
    tets = np.arange(4 * n_tets, dtype=np.int64).reshape(n_tets, 4)
    return points, tets


def _measure(
    function: Callable[[], tuple[np.ndarray, np.ndarray]],
) -> tuple[float, tuple[np.ndarray, np.ndarray]]:
    start = time.perf_counter()
    result = function()
    return time.perf_counter() - start, result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tets", type=int, default=50_000)
    parser.add_argument("--repeats", type=int, default=7)
    parser.add_argument("--seed", type=int, default=29)
    args = parser.parse_args()
    if args.tets <= 0 or args.repeats < 3:
        parser.error("--tets must be positive and --repeats must be at least 3")

    native = load_native_polymesh()
    if native is None or not hasattr(native, "compute_tet_dual_points"):
        raise RuntimeError("native_polymesh.compute_tet_dual_points is unavailable")

    points, tets = _fixture(args.tets, args.seed)
    warm_count = min(args.tets, 256)
    native.compute_tet_dual_points(points[: 4 * warm_count], tets[:warm_count])
    _compute_tet_dual_points_python(points[: 4 * warm_count], tets[:warm_count])

    native_times: list[float] = []
    python_times: list[float] = []
    native_result: tuple[np.ndarray, np.ndarray] | None = None
    python_result: tuple[np.ndarray, np.ndarray] | None = None
    for repeat in range(args.repeats):
        functions = (
            ("native", lambda: native.compute_tet_dual_points(points, tets)),
            ("python", lambda: _compute_tet_dual_points_python(points, tets)),
        )
        if repeat % 2:
            functions = tuple(reversed(functions))
        for name, function in functions:
            elapsed, result = _measure(function)
            arrays = np.asarray(result[0]), np.asarray(result[1])
            if name == "native":
                native_times.append(elapsed)
                native_result = arrays
            else:
                python_times.append(elapsed)
                python_result = arrays

    assert native_result is not None and python_result is not None
    quantized_equal = np.array_equal(
        np.rint(native_result[0] * 1e9), np.rint(python_result[0] * 1e9)
    )
    status_equal = np.array_equal(native_result[1], python_result[1])
    if not quantized_equal or not status_equal:
        raise RuntimeError("native/Python dual-point provenance parity failed")

    native_median = statistics.median(native_times)
    python_median = statistics.median(python_times)
    print(
        json.dumps(
            {
                "n_tets": args.tets,
                "repeats": args.repeats,
                "native_median_seconds": native_median,
                "python_median_seconds": python_median,
                "speedup": python_median / max(native_median, 1e-30),
                "quantized_1e9_keys_equal": quantized_equal,
                "status_equal": status_equal,
                "status_counts": {
                    str(int(status)): int(count)
                    for status, count in zip(
                        *np.unique(native_result[1], return_counts=True), strict=True
                    )
                },
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
