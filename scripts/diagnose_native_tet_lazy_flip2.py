"""Run the read-only TET-LAZY-2 cavity diagnostic on an NPZ mesh.

The NPZ must contain ``points`` (N, 3) and ``tets`` (M, 4).  ``pts`` and
``cells`` are accepted as aliases.  The script never invokes the mesher and
never writes a mesh; it only emits JSON evidence.  ``--n-surface-vertices``
is optional but lets the report include an exact surface-prefix digest.

Usage:
    python scripts/diagnose_native_tet_lazy_flip2.py mesh.npz
    python scripts/diagnose_native_tet_lazy_flip2.py mesh.npz --output report.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from core.generator.native_tet.lazy_flip_diagnostic import (  # noqa: E402
    run_lazy_flip_diagnostic,
)


def _load_mesh(path: Path) -> tuple[np.ndarray, np.ndarray]:
    with np.load(path, allow_pickle=False) as data:
        point_key = "points" if "points" in data else "pts"
        tet_key = "tets" if "tets" in data else "cells"
        if point_key not in data or tet_key not in data:
            raise KeyError("NPZ must contain points/tets or pts/cells")
        points = np.asarray(data[point_key], dtype=np.float64).copy()
        tets = np.asarray(data[tet_key], dtype=np.int64).copy()
    return points, tets


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mesh", type=Path)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--n-surface-vertices", type=int, default=None)
    parser.add_argument("--max-rounds", type=int, default=2)
    parser.add_argument("--max-edges", type=int, default=128)
    parser.add_argument("--max-no-progress", type=int, default=1)
    args = parser.parse_args()

    points, tets = _load_mesh(args.mesh)
    report: dict[str, Any] = run_lazy_flip_diagnostic(
        points,
        tets,
        n_surface_vertices=args.n_surface_vertices,
        max_rounds=args.max_rounds,
        max_edges=args.max_edges,
        max_no_progress=args.max_no_progress,
    )
    rendered = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output is None:
        sys.stdout.write(rendered)
    else:
        args.output.write_text(rendered, encoding="utf-8")
        print(json.dumps({"report": str(args.output), "card": "TET-LAZY-2"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
