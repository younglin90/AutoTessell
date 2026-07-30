#!/usr/bin/env python3
"""Measure the end-to-end TRI-FLIP-QUALITY-CPP23-1 cylinder round."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
from pathlib import Path
from typing import Any
from unittest.mock import patch

import numpy as np

from core.analyzer.readers import read_stl
from core.preprocessor.native_tri.operator_loop import OperatorTransaction
from core.utils.native_extensions import load_native_metrics


class _WithoutTriangleQuality:
    """Forward every native symbol except the kernel measured by this card."""

    def __init__(self, native: Any) -> None:
        self._native = native

    def __getattr__(self, name: str) -> Any:
        if name == "triangle_quality_batch":
            raise AttributeError(name)
        return getattr(self._native, name)


def _sha256(values: np.ndarray) -> str:
    return hashlib.sha256(values.tobytes()).hexdigest()


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


def _run(
    vertices: np.ndarray,
    faces: np.ndarray,
    target: float,
    native: Any,
) -> tuple[float, tuple[Any, ...]]:
    started = time.perf_counter()
    with patch("core.utils.native_extensions.load_native_metrics", return_value=native):
        transaction = OperatorTransaction(vertices, faces, target_edge_length=target)
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
    return elapsed, signature


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=5)
    arguments = parser.parse_args()
    if arguments.repeats < 3:
        raise SystemExit("repeats must be at least 3")
    native = load_native_metrics()
    if native is None or not hasattr(native, "triangle_quality_batch"):
        raise SystemExit("native_metrics.triangle_quality_batch is unavailable")
    without_quality = _WithoutTriangleQuality(native)
    vertices, faces, target = _fixture()

    _run(vertices, faces, target, without_quality)
    _run(vertices, faces, target, native)
    python_samples: list[float] = []
    native_samples: list[float] = []
    reference_signature: tuple[Any, ...] | None = None
    for repeat in range(arguments.repeats):
        order = (
            ((python_samples, without_quality), (native_samples, native))
            if repeat % 2 == 0
            else ((native_samples, native), (python_samples, without_quality))
        )
        for samples, module in order:
            elapsed, signature = _run(vertices, faces, target, module)
            samples.append(elapsed)
            if reference_signature is None:
                reference_signature = signature
            elif signature != reference_signature:
                raise SystemExit("Python/native transaction signature mismatch")

    python_seconds = statistics.median(python_samples)
    native_seconds = statistics.median(native_samples)
    assert reference_signature is not None
    print(
        json.dumps(
            {
                "python_median_seconds": python_seconds,
                "native_median_seconds": native_seconds,
                "speedup": python_seconds / native_seconds,
                "reports": len(reference_signature[0]),
                "accepted": sum(report[1] for report in reference_signature[0]),
                "vertex_sha256": reference_signature[1],
                "face_sha256": reference_signature[2],
                "repeats": arguments.repeats,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
