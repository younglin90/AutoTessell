"""Bounded native-poly target-cell probe for one immutable STL fixture."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from core.analyzer.readers import read_stl
from core.generator.native_poly.harness import run_native_poly_harness


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--target", type=int, nargs="+", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--max-iter", type=int, default=1)
    parser.add_argument("--max-tet-cells", type=int, default=5_000)
    arguments = parser.parse_args()

    mesh = read_stl(arguments.source)
    rows: list[dict[str, object]] = []
    for target in arguments.target:
        case_dir = arguments.output_root / str(target)
        result = run_native_poly_harness(
            np.asarray(mesh.vertices),
            np.asarray(mesh.faces),
            case_dir,
            target_cells=target,
            seed_density=10,
            max_iter=arguments.max_iter,
            max_tet_cells=arguments.max_tet_cells,
        )
        rows.append(
            {
                "target_cells": target,
                "success": result.success,
                "n_cells": result.n_cells,
                "final_poly_cells": result.final_poly_cells,
                "target_cells_absolute_error": result.target_cells_absolute_error,
                "target_cells_relative_error": result.target_cells_relative_error,
                "target_cells_status": result.target_cells_status,
                "tet_cells_by_iteration": list(result.tet_cells_by_iteration),
                "message": result.message,
            }
        )
    report = {
        "schema": "autotessell/native-poly-target-probe/v1",
        "source": str(arguments.source.resolve()),
        "cases": rows,
    }
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0 if all(bool(row["success"]) for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
