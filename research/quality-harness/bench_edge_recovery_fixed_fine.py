"""Fixed-condition A/B diagnostic for native-tet indexed edge recovery."""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

import numpy as np

from core.analyzer.file_reader import load_mesh
from core.generator.native_tet.mesher import generate_native_tet


def main() -> None:
    mesh = load_mesh(Path("tests/benchmarks/high_genus_dual_torus.stl"))
    edge_on = os.environ.get("EDGE_ON", "0") == "1"
    target_cells = int(os.environ.get("TARGET_CELLS", "600"))
    edge_max_iter = int(os.environ.get("EDGE_MAX_ITER", "2"))
    with tempfile.TemporaryDirectory(prefix="tet_edge_fixed_fine_") as temp:
        started = time.perf_counter()
        result = generate_native_tet(
            np.asarray(mesh.vertices, dtype=float),
            np.asarray(mesh.faces, dtype=np.int64),
            Path(temp) / "case",
            target_cells=target_cells,
            enable_edge_recovery=edge_on,
            edge_recovery_max_iter=edge_max_iter,
        )
        print(
            {
                "edge_on": edge_on,
                "target_cells": target_cells,
                "elapsed": result.elapsed,
                "wall": time.perf_counter() - started,
                "success": result.success,
                "cells": result.n_cells,
                "points": result.n_points,
                "grade": result.quality_grade,
                "cdt": result.cdt_ratio,
                "face": result.cdt_face_ratio,
                "plane": result.plane_coverage,
                "plane_area": result.plane_area_coverage,
                "mean_q": getattr(result.quality, "mean_q", None),
                "message": result.message,
            },
        )


if __name__ == "__main__":
    main()
