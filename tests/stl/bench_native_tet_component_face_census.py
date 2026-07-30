#!/usr/bin/env python3
"""Benchmark exact source-component census on tiled native-Tet spheres."""

from __future__ import annotations

import argparse
import json
import statistics
import tempfile
import time
from pathlib import Path

import numpy as np

from core.analyzer.readers import read_stl
from core.generator.native_tet import generate_native_tet
from core.generator.native_tet.rescue_gate import audit_source_component_bijection


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--copies", type=int, default=32)
    parser.add_argument("--repeats", type=int, default=9)
    args = parser.parse_args()
    if args.copies <= 0 or args.repeats <= 0:
        parser.error("copies and repeats must be positive")

    sphere = read_stl(Path("tests/benchmarks/sphere.stl"))
    with tempfile.TemporaryDirectory(prefix="tet_component_face_census_") as tmp:
        result = generate_native_tet(
            sphere.vertices,
            sphere.faces,
            Path(tmp),
            seed_density=8,
        )
    if not result.success or result.tet_points is None or result.tets is None:
        raise RuntimeError(result.message)

    offsets = [np.array([5.0 * copy, 0.0, 0.0]) for copy in range(args.copies)]
    source_points = np.ascontiguousarray(
        np.vstack([sphere.vertices + offset for offset in offsets]),
        dtype=np.float64,
    )
    source_faces = np.ascontiguousarray(
        np.vstack([sphere.faces + copy * len(sphere.vertices) for copy in range(args.copies)]),
        dtype=np.int64,
    )
    candidate_points = np.ascontiguousarray(
        np.vstack([result.tet_points + offset for offset in offsets]),
        dtype=np.float64,
    )
    candidate_tets = np.ascontiguousarray(
        np.vstack([result.tets + copy * len(result.tet_points) for copy in range(args.copies)]),
        dtype=np.int64,
    )

    expected = audit_source_component_bijection(
        source_points,
        source_faces,
        candidate_points,
        candidate_tets,
    )
    samples: list[float] = []
    for _ in range(args.repeats):
        started = time.perf_counter()
        actual = audit_source_component_bijection(
            source_points,
            source_faces,
            candidate_points,
            candidate_tets,
        )
        samples.append(time.perf_counter() - started)
        if actual != expected:
            raise RuntimeError("source-component report changed between repeats")

    print(
        json.dumps(
            {
                "bijective": expected.bijective,
                "candidate_points": len(candidate_points),
                "copies": args.copies,
                "median_seconds": statistics.median(samples),
                "minimum_seconds": min(samples),
                "repeats": args.repeats,
                "source_components": expected.n_source_components,
                "source_points": len(source_points),
                "tets": len(candidate_tets),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
