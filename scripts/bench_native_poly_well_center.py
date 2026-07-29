"""Audit native-tet well-centeredness before attempting a Voronoi dual.

Diagnostic only: this script does not alter the generated primal or dual
mesh.  It fixes the pure-native protocol so the census is repeatable.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import numpy as np

os.environ.setdefault("AUTO_TESSELL_P4C_PYTETWILD", "0")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.analyzer.readers import read_stl  # noqa: E402
from core.generator.native_tet.mesher import generate_native_tet  # noqa: E402


def _census(vertices: np.ndarray, tets: np.ndarray) -> dict[str, float | int]:
    well_centered = 0
    finite = 0
    min_barycentric: list[float] = []
    for tet in tets:
        points = vertices[tet]
        try:
            matrix = 2.0 * np.stack([points[i] - points[0] for i in (1, 2, 3)])
            rhs = np.asarray(
                [points[i] @ points[i] - points[0] @ points[0] for i in (1, 2, 3)],
                dtype=np.float64,
            )
            circumcenter = np.linalg.solve(matrix, rhs)
            edge_matrix = np.column_stack([points[i] - points[0] for i in (1, 2, 3)])
            bary_tail = np.linalg.solve(edge_matrix, circumcenter - points[0])
            barycentric = np.asarray(
                [1.0 - bary_tail.sum(), *bary_tail],
                dtype=np.float64,
            )
        except np.linalg.LinAlgError:
            continue
        if not np.isfinite(circumcenter).all() or not np.isfinite(barycentric).all():
            continue
        finite += 1
        min_barycentric.append(float(barycentric.min()))
        if float(barycentric.min()) >= -1e-10:
            well_centered += 1
    values = np.asarray(min_barycentric, dtype=np.float64)
    boundary = set()
    face_counts: dict[tuple[int, int, int], int] = {}
    for tet in tets.tolist():
        for face in ((tet[1], tet[2], tet[3]), (tet[0], tet[3], tet[2]),
                     (tet[0], tet[1], tet[3]), (tet[0], tet[2], tet[1])):
            key = tuple(sorted(int(value) for value in face))
            face_counts[key] = face_counts.get(key, 0) + 1
    for face, count in face_counts.items():
        if count == 1:
            boundary.update(face)
    neighbours: list[set[int]] = [set() for _ in range(len(vertices))]
    for tet in tets.tolist():
        for vertex in tet:
            neighbours[int(vertex)].update(int(other) for other in tet if int(other) != int(vertex))
    interior_valences = [len(neighbours[index]) for index in range(len(vertices)) if index not in boundary]
    return {
        "tets": int(len(tets)),
        "finite_circumcenters": finite,
        "well_centered": well_centered,
        "well_centered_fraction": well_centered / max(finite, 1),
        "min_barycentric": float(values.min()) if len(values) else 0.0,
        "p05_min_barycentric": float(np.quantile(values, 0.05)) if len(values) else 0.0,
        "boundary_vertices": int(len(boundary)),
        "interior_vertices": int(len(interior_valences)),
        "interior_valence_min": int(min(interior_valences)) if interior_valences else 0,
        "interior_valence_lt7": int(sum(value < 7 for value in interior_valences)),
    }


def main() -> None:
    root = ROOT
    rows: dict[str, object] = {}
    for shape in ("cube", "cylinder", "sphere"):
        mesh = read_stl(root / "tests" / "benchmarks" / f"{shape}.stl")
        with tempfile.TemporaryDirectory(prefix="native_poly_well_center_") as temp:
            result = generate_native_tet(
                mesh.vertices,
                mesh.faces,
                Path(temp) / "primal",
                seed_density=6,
            )
            if not result.success or result.tet_points is None or result.tets is None:
                rows[shape] = {"success": False, "message": result.message}
                continue
            rows[shape] = {
                "success": True,
                "points": int(len(result.tet_points)),
                **_census(
                    np.asarray(result.tet_points, dtype=np.float64),
                    np.asarray(result.tets, dtype=np.int64),
                ),
            }
    print(json.dumps(rows, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
