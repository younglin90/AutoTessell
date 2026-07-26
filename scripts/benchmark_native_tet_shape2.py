#!/usr/bin/env python3
"""Offline A/B measurement for the default-OFF TET-SHAPE-2 candidate.

The native mesh is generated once per fixed STL, then the isolated interior
pass is evaluated against the same ``(points, tets)`` baseline for each GSM
weight.  No mesher wiring or output file is touched by this script.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.generator.native_tet.mesher import generate_native_tet  # noqa: E402
from core.generator.native_tet.shape2 import run_shape2_pass  # noqa: E402

DEFAULT_MESHES = (
    Path("tests/benchmarks/naca0012.stl"),
    Path("tests/benchmarks/cylinder.stl"),
    Path("tests/benchmarks/cube.stl"),
)


def _run_mesh(
    mesh_path: Path,
    weights: list[float],
    sweeps: int,
    step_cap_frac: float,
) -> dict[str, Any]:
    loaded = trimesh.load(str(mesh_path), force="mesh")
    vertices = np.asarray(loaded.vertices, dtype=np.float64)
    faces = np.asarray(loaded.faces, dtype=np.int64)
    with tempfile.TemporaryDirectory(prefix="native_tet_shape2_") as temp_dir:
        started = time.perf_counter()
        result = generate_native_tet(
            vertices,
            faces,
            Path(temp_dir),
            seed_density=12,
            target_cells=2000,
        )
        generation_elapsed = time.perf_counter() - started
        row: dict[str, Any] = {
            "mesh": str(mesh_path),
            "generation_elapsed_s": generation_elapsed,
            "generation_success": bool(result.success),
            "generation_cells": int(result.n_cells),
            "generation_points": int(result.n_points),
            "input_surface_vertices": int(vertices.shape[0]),
        }
        if not result.success or result.tet_points is None or result.tets is None:
            row["error"] = str(result.message)
            return row

        points = np.asarray(result.tet_points, dtype=np.float64)
        tets = np.asarray(result.tets, dtype=np.int64)
        candidates: list[dict[str, Any]] = []
        for weight in weights:
            started = time.perf_counter()
            _, report = run_shape2_pass(
                points,
                tets,
                n_surface_vertices=vertices.shape[0],
                n_sweeps=int(sweeps),
                gsm_weight=float(weight),
                step_cap_frac=float(step_cap_frac),
                measure_only=True,
            )
            item = report.as_dict()
            item["shape2_elapsed_s"] = time.perf_counter() - started
            candidates.append(item)
        row["mesh_cells"] = int(tets.shape[0])
        row["mesh_points"] = int(points.shape[0])
        row["candidates"] = candidates
        return row


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mesh", action="append", type=Path, dest="meshes")
    parser.add_argument("--weight", action="append", type=float, dest="weights")
    parser.add_argument("--sweeps", type=int, default=3)
    parser.add_argument("--step-cap-frac", type=float, default=0.01)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    os.environ["AUTO_TESSELL_P4C_PYTETWILD"] = "0"
    os.environ["AUTO_TESSELL_TET_FLOW2"] = "0"
    os.environ["AUTO_TESSELL_FSL_WAVE1"] = "0"
    meshes = args.meshes or list(DEFAULT_MESHES)
    weights = args.weights or [0.20, 0.35, 0.50, 0.70]
    result = {
        "protocol": "native-only fixed-mesh offline A/B",
        "pytetwild_fallback": "off",
        "sweeps": int(args.sweeps),
        "weights": weights,
        "step_cap_frac": float(args.step_cap_frac),
        "rows": [
            _run_mesh(mesh, weights, int(args.sweeps), float(args.step_cap_frac)) for mesh in meshes
        ],
    }
    text = json.dumps(result, indent=2, sort_keys=True)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
