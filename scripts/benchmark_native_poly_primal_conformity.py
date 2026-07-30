#!/usr/bin/env python3
"""Alternating-order benchmark for the Poly primal-conformity audit."""

from __future__ import annotations

import argparse
import json
import statistics
import time
from collections.abc import Callable

import numpy as np

from core.generator.native_poly import dual
from core.utils.native_extensions import load_native_polymesh


def _fixture(n_tets: int) -> tuple[np.ndarray, np.ndarray]:
    offsets = np.arange(n_tets, dtype=np.float64) * 2.0
    points: np.ndarray = np.empty((n_tets * 4, 3), dtype=np.float64)
    points[0::4] = np.column_stack((offsets, np.zeros(n_tets), np.zeros(n_tets)))
    points[1::4] = points[0::4] + (1.0, 0.0, 0.0)
    points[2::4] = points[0::4] + (0.0, 1.0, 0.0)
    points[3::4] = points[0::4] + (0.0, 0.0, 1.0)
    tets: np.ndarray = np.arange(n_tets * 4, dtype=np.int64).reshape(-1, 4)
    return points, tets


def _median_seconds(function: Callable[[], object], repeat: int) -> float:
    samples = []
    for _ in range(repeat):
        start = time.perf_counter()
        function()
        samples.append(time.perf_counter() - start)
    return statistics.median(samples)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tets", type=int, default=50_000)
    parser.add_argument("--repeat", type=int, default=5)
    args = parser.parse_args()
    if args.tets <= 0 or args.repeat <= 0:
        raise SystemExit("--tets and --repeat must be positive")

    native = load_native_polymesh()
    if native is None or not hasattr(native, "audit_tet_primal_conformity"):
        raise SystemExit("fresh native_polymesh primal-conformity kernel required")
    points, tets = _fixture(args.tets)

    def python_run() -> dual.TetPrimalConformityAudit:
        return dual._audit_tet_primal_conformity_python(points, tets)

    def native_run() -> dual.TetPrimalConformityAudit:
        return dual._normalise_tet_primal_conformity_audit(
            native.audit_tet_primal_conformity(points, tets),
            n_points=int(points.shape[0]),
            n_tets=args.tets,
        )

    if python_run() != native_run():
        raise SystemExit("native/Python parity failure")
    python_samples: list[float] = []
    native_samples: list[float] = []
    for repeat_index in range(args.repeat):
        first, second = (
            ((python_run, python_samples), (native_run, native_samples))
            if repeat_index % 2 == 0
            else ((native_run, native_samples), (python_run, python_samples))
        )
        for function, samples in (first, second):
            samples.append(_median_seconds(function, 1))

    python_median = statistics.median(python_samples)
    native_median = statistics.median(native_samples)
    print(
        json.dumps(
            {
                "n_tets": args.tets,
                "repeat": args.repeat,
                "python_median_s": python_median,
                "native_median_s": native_median,
                "speedup": python_median / native_median,
                "parity": True,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
