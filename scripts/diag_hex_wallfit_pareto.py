"""HEX-WALLFIT-PARETO-1 — wall-fit ON/OFF report-only comparison.

The diagnostic reruns the canonical fine/pre-BL budget with wall-fit enabled
and disabled, then compares checker quality, written boundary area, cell
volume, and maximum boundary-vertex distance to the source STL.  It does not
change production gates or enable any repair lane.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import os
import sys
import tempfile
from typing import Any

import numpy as np

REPO = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, REPO)

from core.analyzer.readers.stl import read_stl  # noqa: E402
from core.evaluator.native_checker import NativeMeshChecker  # noqa: E402
from core.generator.native_hex.metrics import (  # noqa: E402
    _cell_volume,
    _face_owners,
    read_written_polymesh_cells,
)
from core.generator.native_hex.snap import _closest_point_on_triangle  # noqa: E402
from core.pipeline.orchestrator import PipelineOrchestrator  # noqa: E402
from core.utils.kdtree import NumpyKDTree  # noqa: E402


_SHAPES = {
    "cylinder": Path(REPO) / "tests" / "benchmarks" / "cylinder.stl",
    "sphere": Path(REPO) / "tests" / "benchmarks" / "sphere.stl",
    "gear": Path(REPO) / "tests" / "stl" / "04_extreme_gear.stl",
    "bracket": Path(REPO) / "tests" / "stl" / "03_hard_bracket.stl",
}


def _triangle_area(points: np.ndarray, face: np.ndarray) -> float:
    return 0.5 * float(np.linalg.norm(np.cross(points[face[1]] - points[face[0]], points[face[2]] - points[face[0]])))


def _source_area(points: np.ndarray, faces: np.ndarray) -> float:
    return float(sum(_triangle_area(points, face) for face in faces))


def _written_boundary_area(points: np.ndarray, cells: list[list[list[int]]]) -> float:
    owners = _face_owners(cells)
    total = 0.0
    for key, face_owners in owners.items():
        if len(set(int(owner) for owner in face_owners)) != 1:
            continue
        face = np.asarray(key, dtype=np.int64)
        if len(face) < 3:
            continue
        p = points[face]
        base = p[0]
        for i in range(1, len(face) - 1):
            total += 0.5 * float(np.linalg.norm(np.cross(p[i] - base, p[i + 1] - base)))
    return float(total)


def _max_boundary_vertex_dev(
    points: np.ndarray,
    cells: list[list[list[int]]],
    source_points: np.ndarray,
    source_faces: np.ndarray,
) -> float:
    owners = _face_owners(cells)
    boundary_ids = sorted(
        {
            int(vertex)
            for key, face_owners in owners.items()
            if len(set(int(owner) for owner in face_owners)) == 1
            for vertex in key
        }
    )
    if not boundary_ids:
        return 0.0
    tri_a = source_points[source_faces[:, 0]]
    tri_b = source_points[source_faces[:, 1]]
    tri_c = source_points[source_faces[:, 2]]
    centroids = (tri_a + tri_b + tri_c) / 3.0
    tree = NumpyKDTree(centroids)
    _, neighbours = tree.query(points[np.asarray(boundary_ids, dtype=np.int64)], k=min(8, len(centroids)))
    neighbours = np.atleast_2d(np.asarray(neighbours))
    max_distance = 0.0
    for row, vertex_id in enumerate(boundary_ids):
        best = float("inf")
        for triangle_id in np.asarray(neighbours[row]).reshape(-1).tolist():
            triangle_id = int(triangle_id)
            if triangle_id >= len(centroids):
                continue
            projected = _closest_point_on_triangle(
                points[vertex_id], tri_a[triangle_id], tri_b[triangle_id], tri_c[triangle_id]
            )
            best = min(best, float(np.linalg.norm(projected - points[vertex_id])))
        max_distance = max(max_distance, best)
    return float(max_distance)


def _run_one(name: str, path: Path, wallfit: bool) -> dict[str, Any]:
    surface = read_stl(str(path))
    source_points = np.asarray(surface.vertices, dtype=np.float64)
    source_faces = np.asarray(surface.faces, dtype=np.int64)
    previous = os.environ.get("AUTO_TESSELL_HEX_WALLFIT_OFF")
    if wallfit:
        os.environ.pop("AUTO_TESSELL_HEX_WALLFIT_OFF", None)
    else:
        os.environ["AUTO_TESSELL_HEX_WALLFIT_OFF"] = "1"
    try:
        with tempfile.TemporaryDirectory() as tmp:
            case = Path(tmp) / "case"
            run = PipelineOrchestrator().run(
                path,
                case,
                quality_level="fine",
                mesh_type="hex_dominant",
                tier_hint="native_hex",
                max_iterations=1,
                auto_retry="off",
                strict_tier=True,
                write_of_case=True,
                max_cells=8000,
                tier_specific_params={
                    "max_cells": 8000,
                    "target_cells": 8000,
                    "bl_layers": 0,
                },
            )
            loaded = read_written_polymesh_cells(case)
            if loaded is None:
                return {"shape": name, "wallfit": wallfit, "error": str(run.error)}
            points, cells = loaded
            check = NativeMeshChecker().run(case)
            boundary_area = _written_boundary_area(points, cells)
            volume = float(sum(_cell_volume(points, cell) for cell in cells))
            return {
                "shape": name,
                "wallfit": wallfit,
                "success": bool(run.success),
                "cells": int(check.cells),
                "skew": float(check.max_skewness),
                "boundary_skew": float(check.max_boundary_skewness or 0.0),
                "warpage": float(check.max_face_warpage or 0.0),
                "negative": int(check.negative_volumes),
                "source_area": _source_area(source_points, source_faces),
                "boundary_area": boundary_area,
                "area_error_pct": 100.0 * abs(boundary_area - _source_area(source_points, source_faces)) / max(_source_area(source_points, source_faces), 1e-30),
                "volume": volume,
                "wall_dev_max": _max_boundary_vertex_dev(points, cells, source_points, source_faces),
            }
    finally:
        if previous is None:
            os.environ.pop("AUTO_TESSELL_HEX_WALLFIT_OFF", None)
        else:
            os.environ["AUTO_TESSELL_HEX_WALLFIT_OFF"] = previous


def main() -> int:
    rows: list[dict[str, Any]] = []
    for name, path in _SHAPES.items():
        if not path.exists():
            print(f"{name}: SKIP missing={path}")
            continue
        for wallfit in (False, True):
            row = _run_one(name, path, wallfit)
            rows.append(row)
            print(row)
    for name in _SHAPES:
        pair = [row for row in rows if row.get("shape") == name]
        if len(pair) != 2 or any("error" in row for row in pair):
            continue
        off = next(row for row in pair if not row["wallfit"])
        on = next(row for row in pair if row["wallfit"])
        print(
            "DELTA "
            f"shape={name} "
            f"skew={on['skew'] - off['skew']:.9g} "
            f"boundary_skew={on['boundary_skew'] - off['boundary_skew']:.9g} "
            f"warpage={on['warpage'] - off['warpage']:.9g} "
            f"area_error_pct={on['area_error_pct'] - off['area_error_pct']:.9g} "
            f"wall_dev={on['wall_dev_max'] - off['wall_dev_max']:.9g} "
            f"negative={on['negative'] - off['negative']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
