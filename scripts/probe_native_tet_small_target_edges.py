"""Measure native-tet small-target output over a bounded edge-length sweep."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from core.analyzer.readers import read_stl
from core.generator.native_tet import generate_native_tet


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--target", type=int, nargs="+", required=True)
    parser.add_argument("--scale", type=float, nargs="+", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    arguments = parser.parse_args()

    mesh = read_stl(arguments.source)
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    span = float(np.prod(vertices.max(axis=0) - vertices.min(axis=0)))
    rows: list[dict[str, object]] = []
    for target in arguments.target:
        derived = float((span / (0.118 * target)) ** (1.0 / 3.0))
        for scale in arguments.scale:
            case_dir = arguments.output_root / f"target-{target}-scale-{scale:g}"
            result = generate_native_tet(
                vertices,
                faces,
                case_dir,
                target_cells=target,
                target_edge_length=derived * scale,
                min_final_vertices=None,
            )
            rows.append(
                {
                    "target_cells": target,
                    "scale": scale,
                    "target_edge_length": derived * scale,
                    "success": result.success,
                    "n_points": result.n_points,
                    "n_cells": result.n_cells,
                    "message": result.message,
                }
            )
    print(
        json.dumps(
            {"schema": "autotessell/native-tet-small-target-edge-probe/v1", "cases": rows},
            sort_keys=True,
            indent=2,
        )
    )
    return 0 if all(bool(row["success"]) for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
