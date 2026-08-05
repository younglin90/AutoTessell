"""Full-pipeline deterministic repeat for the fixed-condition tet replay."""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

import numpy as np

from core.analyzer.file_reader import load_mesh
from core.generator.native_tet.mesher import generate_native_tet


def _digest(result: object) -> str:
    points = np.asarray(getattr(result, "tet_points"), dtype=np.float64)
    tets = np.asarray(getattr(result, "tets"), dtype=np.int64)
    digest = hashlib.sha256()
    digest.update(np.ascontiguousarray(points).tobytes())
    digest.update(np.ascontiguousarray(tets).tobytes())
    return digest.hexdigest()


def main() -> int:
    mesh = load_mesh(Path("tests/benchmarks/high_genus_dual_torus.stl"))
    edge_on = os.environ.get("EDGE_ON", "0") == "1"
    target_cells = int(os.environ.get("TARGET_CELLS", "600"))
    rows: list[dict[str, object]] = []
    for repeat in range(2):
        with tempfile.TemporaryDirectory(prefix="tet_edge_repeat_") as temp:
            result = generate_native_tet(
                np.asarray(mesh.vertices, dtype=float),
                np.asarray(mesh.faces, dtype=np.int64),
                Path(temp) / "case",
                target_cells=target_cells,
                enable_edge_recovery=edge_on,
                edge_recovery_max_iter=2,
            )
            rows.append(
                {
                    "repeat": repeat,
                    "digest": _digest(result),
                    "cells": int(result.n_cells),
                    "points": int(result.n_points),
                    "grade": result.quality_grade,
                    "cdt": float(result.cdt_ratio),
                    "face": float(result.cdt_face_ratio),
                    "plane": float(result.plane_coverage),
                    "plane_area": float(result.plane_area_coverage),
                }
            )
    print({"edge_on": edge_on, "target_cells": target_cells, "rows": rows})
    return 0 if rows[0]["digest"] == rows[1]["digest"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
