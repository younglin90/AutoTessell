"""Compare centroid and clipped-circumcenter dual points on fixed native tets.

Diagnostic only.  The classifier activates the existing Garimella point path;
no production default is changed by this script.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("AUTO_TESSELL_P4C_PYTETWILD", "0")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.analyzer.readers import read_stl  # noqa: E402
from core.generator.native_poly.dual import tet_to_poly_dual  # noqa: E402
from core.generator.native_tet.mesher import generate_native_tet  # noqa: E402


def _hybrid_tet_dual_points(vertices, tets):
    """Use exact circumcenters only for already well-centered tets."""
    import numpy as np

    points = np.empty((len(tets), 3), dtype=np.float64)
    for index, tet in enumerate(tets):
        local = vertices[tet]
        centroid = local.mean(axis=0)
        try:
            matrix = 2.0 * np.stack([local[i] - local[0] for i in (1, 2, 3)])
            rhs = np.asarray(
                [local[i] @ local[i] - local[0] @ local[0] for i in (1, 2, 3)],
                dtype=np.float64,
            )
            circumcenter = np.linalg.solve(matrix, rhs)
            edge_matrix = np.column_stack([local[i] - local[0] for i in (1, 2, 3)])
            tail = np.linalg.solve(edge_matrix, circumcenter - local[0])
            barycentric = np.asarray([1.0 - tail.sum(), *tail], dtype=np.float64)
        except np.linalg.LinAlgError:
            points[index] = centroid
            continue
        if np.isfinite(barycentric).all() and float(barycentric.min()) >= -1e-10:
            points[index] = circumcenter
        else:
            points[index] = centroid
    return points


def main() -> None:
    rows: dict[str, object] = {}
    for shape in ("cube", "cylinder", "sphere"):
        mesh = read_stl(ROOT / "tests" / "benchmarks" / f"{shape}.stl")
        with tempfile.TemporaryDirectory(prefix="poly_dual_mode_") as temp:
            primal = generate_native_tet(
                mesh.vertices,
                mesh.faces,
                Path(temp) / "primal",
                seed_density=6,
            )
            if not primal.success or primal.tet_points is None or primal.tets is None:
                rows[shape] = {"success": False, "message": primal.message}
                continue
            modes: dict[str, object] = {}
            for mode, kwargs in (
                ("centroid", {}),
                (
                    "garimella",
                    {"boundary_face_classifier": lambda tri, vertices: "defaultWall"},
                ),
                (
                    "hybrid",
                    {"boundary_face_classifier": lambda tri, vertices: "defaultWall"},
                ),
            ):
                if mode == "hybrid":
                    import core.generator.native_poly.dual as dual_module

                    original = dual_module._compute_tet_dual_points
                    dual_module._compute_tet_dual_points = _hybrid_tet_dual_points
                else:
                    original = None
                result = tet_to_poly_dual(
                    primal.tet_points,
                    primal.tets,
                    Path(temp) / mode,
                    _dual_point_mode="garimella" if mode == "hybrid" else mode,
                    **kwargs,
                )
                if original is not None:
                    dual_module._compute_tet_dual_points = original
                modes[mode] = {
                    "success": bool(result.success),
                    "invalid_cells": int(result.invalid_star_cells),
                    "invalid_subtets": int(result.invalid_star_subtets),
                    "n_cells": int(result.n_cells),
                    "n_points": int(result.n_points),
                    "n_faces": int(result.n_faces),
                    "message": result.message,
                }
            rows[shape] = {
                "points": int(len(primal.tet_points)),
                "tets": int(len(primal.tets)),
                "modes": modes,
            }
    print(json.dumps(rows, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
