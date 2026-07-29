"""Split the native-poly sphere wall time into primal and dual stages.

This is a diagnostic benchmark only.  It keeps one generated primal tet mesh
fixed, runs the dual conversion three times in separate output directories,
and records deterministic array/output digests without changing production
code or acceptance gates.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path

import numpy as np

from core.analyzer.readers import read_stl
from core.generator.native_poly.dual import tet_to_poly_dual
from core.generator.native_tet.mesher import generate_native_tet


def _digest(*arrays: np.ndarray) -> str:
    digest = hashlib.sha256()
    for array in arrays:
        values = np.ascontiguousarray(array)
        digest.update(str(values.dtype).encode())
        digest.update(repr(values.shape).encode())
        digest.update(values.tobytes())
    return digest.hexdigest()


def _directory_digest(directory: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in directory.rglob("*") if item.is_file()):
        digest.update(str(path.relative_to(directory)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    sphere = root / "tests" / "benchmarks" / "sphere.stl"
    mesh = read_stl(sphere)

    with tempfile.TemporaryDirectory(prefix="native_poly_sphere_stages_") as temp:
        work = Path(temp)
        start = time.perf_counter()
        tet_result = generate_native_tet(
            mesh.vertices,
            mesh.faces,
            work / "base_tet",
            seed_density=8,
        )
        primal_seconds = time.perf_counter() - start
        if not tet_result.success or tet_result.tets is None or tet_result.tet_points is None:
            raise RuntimeError(f"native-tet primal failed: {tet_result}")

        points = np.asarray(tet_result.tet_points, dtype=np.float64).copy()
        tets = np.asarray(tet_result.tets, dtype=np.int64).copy()
        rows: list[dict[str, object]] = []
        repeats = max(1, int(os.environ.get("NATIVE_POLY_DUAL_REPEATS", "3")))
        for index in range(repeats):
            started = time.perf_counter()
            result = tet_to_poly_dual(points, tets, work / f"dual_{index}")
            elapsed = time.perf_counter() - started
            rows.append(
                {
                    "repeat": index,
                    "seconds": elapsed,
                    "success": result.success,
                    "cells": result.n_cells,
                    "points": result.n_points,
                    "invalid_star_cells": result.invalid_star_cells,
                    "invalid_star_subtets": result.invalid_star_subtets,
                    "primal_digest": _digest(points, tets),
                    "mesh_digest": _directory_digest(work / f"dual_{index}"),
                },
            )
            if not result.success:
                raise RuntimeError(f"dual failed on repeat {index}: {result.message}")

        print(
            json.dumps(
                {
                    "sphere": str(sphere),
                    "primal_seconds": primal_seconds,
                    "primal_vertices": len(points),
                    "primal_tets": len(tets),
                    "primal_digest": _digest(points, tets),
                    "dual_repeats": rows,
                    "dual_seconds_min": min(float(row["seconds"]) for row in rows),
                    "dual_seconds_max": max(float(row["seconds"]) for row in rows),
                },
                indent=2,
                sort_keys=True,
            ),
        )


if __name__ == "__main__":
    main()
