#!/usr/bin/env python3
"""Benchmark the TRI-FLIP-FILTER-CPP23-1 frozen-state filter and full round."""

from __future__ import annotations

import argparse
import hashlib
import json
import resource
import statistics
import time
from pathlib import Path
from typing import Any
from unittest.mock import patch

import numpy as np

from core.analyzer.readers import read_stl
from core.preprocessor.native_tri.operator_loop import OperatorTransaction
from core.utils.native_extensions import load_native_metrics


class _WithoutFlipFilter:
    def __init__(self, native: Any) -> None:
        self._native = native

    def __getattr__(self, name: str) -> Any:
        if name == "triangle_flip_candidate_mask":
            raise AttributeError(name)
        return getattr(self._native, name)


def _fixture() -> tuple[np.ndarray, np.ndarray, float]:
    root = Path(__file__).resolve().parents[2]
    mesh = read_stl(str(root / "tests/benchmarks/cylinder.stl"))
    vertices = np.ascontiguousarray(mesh.vertices, dtype=np.float64)
    faces = np.ascontiguousarray(mesh.faces, dtype=np.int64)
    lengths = np.concatenate(
        [
            np.linalg.norm(
                vertices[faces[:, index]] - vertices[faces[:, (index + 1) % 3]],
                axis=1,
            )
            for index in range(3)
        ]
    )
    return vertices, faces, float(np.median(lengths[lengths > 0.0]))


def _sha256(values: np.ndarray) -> str:
    return hashlib.sha256(values.tobytes()).hexdigest()


def _run_round(
    vertices: np.ndarray,
    faces: np.ndarray,
    target: float,
    module: Any,
) -> tuple[float, tuple[Any, ...], int]:
    transaction = OperatorTransaction(vertices, faces, target_edge_length=target)
    original = transaction._build_flip_candidate
    copy_pairs = 0

    def counted(*args: Any, **kwargs: Any) -> Any:
        nonlocal copy_pairs
        copy_pairs += 1
        return original(*args, **kwargs)

    transaction._build_flip_candidate = counted  # type: ignore[method-assign]
    started = time.perf_counter()
    with patch("core.utils.native_extensions.load_native_metrics", return_value=module):
        reports = transaction.run_one_round(target_edge_length=target, smooth=False)
    elapsed = time.perf_counter() - started
    signature = (
        tuple(
            (report.operator, report.accepted, report.reason, report.vertex_index)
            for report in reports
        ),
        _sha256(transaction.state.vertices),
        _sha256(transaction.state.faces),
    )
    return elapsed, signature, copy_pairs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("scalar", "native"), required=True)
    parser.add_argument("--repeats", type=int, default=7)
    arguments = parser.parse_args()
    if arguments.repeats < 3:
        raise SystemExit("repeats must be at least 3")

    native = load_native_metrics()
    if native is None or not hasattr(native, "triangle_flip_candidate_mask"):
        raise SystemExit("native_metrics.triangle_flip_candidate_mask is unavailable")
    module = _WithoutFlipFilter(native) if arguments.mode == "scalar" else native
    vertices, faces, target = _fixture()

    _run_round(vertices, faces, target, module)
    samples: list[float] = []
    signature: tuple[Any, ...] | None = None
    copy_pairs: int | None = None
    for _ in range(arguments.repeats):
        elapsed, current_signature, current_copy_pairs = _run_round(
            vertices,
            faces,
            target,
            module,
        )
        samples.append(elapsed)
        if signature is None:
            signature = current_signature
            copy_pairs = current_copy_pairs
        elif current_signature != signature or current_copy_pairs != copy_pairs:
            raise SystemExit("non-deterministic transaction result")

    assert signature is not None
    assert copy_pairs is not None
    print(
        json.dumps(
            {
                "accepted": sum(report[1] for report in signature[0]),
                "face_sha256": signature[2],
                "flip_candidate_copy_pairs": copy_pairs,
                "median_seconds": statistics.median(samples),
                "mode": arguments.mode,
                "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                "repeats": arguments.repeats,
                "reports": len(signature[0]),
                "vertex_sha256": signature[1],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
