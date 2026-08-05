"""Round 035 private quality probe; no release artifact is published."""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import tempfile

import numpy as np
import trimesh


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=("cube", "naca"), default="cube")
    args = parser.parse_args()
    root = pathlib.Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    sys.path.insert(0, str(root / "auto_tessell_core" / "build"))
    from core.generator.native_tet.mesher import generate_native_tet
    from core.generator.native_tet.quality import snapshot

    if args.case == "cube":
        mesh = trimesh.creation.box()
        h = 0.4
    else:
        mesh = trimesh.load_mesh(str(root / "tests" / "benchmarks" / "naca0012.stl"), process=False)
        h = 0.05
    result = generate_native_tet(
        np.asarray(mesh.vertices, dtype=np.float64),
        np.asarray(mesh.faces, dtype=np.int64),
        pathlib.Path(tempfile.mkdtemp(prefix="round035_quality_probe_")) / args.case,
        target_edge_length=h,
        sliver_quality_threshold=0.0,
        enable_phase_a=True,
        recovery_iterations=0,
        smooth_iterations=2,
        enable_same_side_retriangulation=False,
        allow_external_fallback=False,
    )
    quality = None
    if result.tet_points is not None and result.tets is not None:
        quality = snapshot(result.tet_points, result.tets)
    print(json.dumps({
        "case": args.case,
        "success": bool(result.success),
        "n_cells": int(result.n_cells),
        "message": result.message,
        "min_q": None if quality is None else float(quality.min_q),
        "mean_q": None if quality is None else float(quality.mean_q),
    }, sort_keys=True))
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
