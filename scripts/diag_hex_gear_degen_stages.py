"""HEX-GEAR-DEGEN-DROP-1 — stage where zero-thickness gear cells appear.

Report-only process-local wrappers around native_hex stage functions.  The
wrappers capture counts and zero-area face keys after octree construction,
iterative snap, wall fit, and sliver relaxation; they do not alter return
values or production behavior.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import sys
import tempfile
from typing import Any, Callable

import numpy as np

REPO = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, REPO)

from core.pipeline.orchestrator import PipelineOrchestrator  # noqa: E402

GEAR = Path(REPO) / "tests" / "stl" / "04_extreme_gear.stl"


def _face_area(points: np.ndarray, face: list[int]) -> float:
    p = points[np.asarray(face, dtype=np.int64)]
    base = p[0]
    area = 0.0
    for i in range(1, len(face) - 1):
        area += 0.5 * float(np.linalg.norm(np.cross(p[i] - base, p[i + 1] - base)))
    return area


def _degenerate(points: np.ndarray, cells: list[list[list[int]]]) -> dict[str, Any]:
    points = np.asarray(points, dtype=np.float64)
    bbox_diag = float(np.linalg.norm(points.max(axis=0) - points.min(axis=0)))
    area_eps = max((bbox_diag * 1e-12) ** 2, 1e-30)
    keys: dict[tuple[int, ...], list[int]] = defaultdict(list)
    for ci, cell in enumerate(cells):
        for face in cell:
            if _face_area(points, [int(v) for v in face]) <= area_eps:
                keys[tuple(sorted(int(v) for v in face))].append(ci)
    return {
        "n_cells": len(cells),
        "n_bad_faces": sum(len(v) for v in keys.values()),
        "n_bad_keys": len(keys),
        "keys": {key: value for key, value in keys.items()},
    }


def _print(label: str, points: Any, cells: Any, rows: list[dict[str, Any]]) -> None:
    pts = np.asarray(points, dtype=np.float64)
    c = [
        [[int(v) for v in face] for face in cell]
        for cell in cells
    ]
    report = _degenerate(pts, c)
    rows.append({"stage": label, **report})
    print(
        f"STAGE {label}: points={len(pts)} cells={report['n_cells']} "
        f"zero_area_faces={report['n_bad_faces']} "
        f"unique_keys={report['n_bad_keys']} keys={report['keys']}"
    )


def main() -> int:
    import core.generator.native_hex.mesher as mesher
    import core.generator.native_hex.octree as octree
    import core.generator.native_hex.snap as snap
    import core.generator.polymesh_writer as writer

    rows: list[dict[str, Any]] = []
    original_build = octree.build_octree_hex_cells
    original_snap = snap.snap_to_surface_iterative
    original_wall = mesher._wall_fit_snap
    original_relax = mesher._relax_boundary_sliver_interior
    original_writer = writer.write_generic_polymesh

    def build_wrapper(*args: Any, **kwargs: Any) -> Any:
        result = original_build(*args, **kwargs)
        _print(f"octree_build_{len(rows)}", result[0], result[1], rows)
        return result

    def snap_wrapper(*args: Any, **kwargs: Any) -> Any:
        result = original_snap(*args, **kwargs)
        # The iterative snap only returns points; its cells are the most recent
        # octree cell list captured immediately before it.
        if rows:
            # Find the latest stage with cells; retain the object in closure.
            _print("iterative_snap", result[0], current_cells[0], rows)
        return result

    def wall_wrapper(*args: Any, **kwargs: Any) -> Any:
        result = original_wall(*args, **kwargs)
        _print("wall_fit", result[0], args[1], rows)
        before = np.asarray(args[0], dtype=np.float64)
        after = np.asarray(result[0], dtype=np.float64)
        bad = _degenerate(after, [
            [[int(v) for v in face] for face in cell]
            for cell in args[1]
        ])
        for key, cell_ids in bad["keys"].items():
            print(f"WALLFIT_DELTA face_key={key} cells={cell_ids}")
            for vi in key:
                delta = after[vi] - before[vi]
                print(
                    f"  vertex={vi} before={before[vi].tolist()} "
                    f"after={after[vi].tolist()} delta={delta.tolist()} "
                    f"norm={float(np.linalg.norm(delta)):.17g}"
                )
        return result

    def relax_wrapper(*args: Any, **kwargs: Any) -> Any:
        result = original_relax(*args, **kwargs)
        _print("sliver_relax", result[0], args[1], rows)
        return result

    captured_cells: list[list[list[int]]] | None = None
    current_cells: list[list[list[list[int]]] | None] = [None]

    def build_wrapper_with_cells(*args: Any, **kwargs: Any) -> Any:
        result = original_build(*args, **kwargs)
        current_cells[0] = [
            [[int(v) for v in face] for face in cell]
            for cell in result[1]
        ]
        _print(f"octree_build_{len(rows)}", result[0], result[1], rows)
        return result

    def writer_wrapper(*args: Any, **kwargs: Any) -> Any:
        if len(args) >= 2:
            _print("writer_input", args[0], args[1], rows)
        return original_writer(*args, **kwargs)

    octree.build_octree_hex_cells = build_wrapper_with_cells
    snap.snap_to_surface_iterative = snap_wrapper
    mesher._wall_fit_snap = wall_wrapper
    mesher._relax_boundary_sliver_interior = relax_wrapper
    writer.write_generic_polymesh = writer_wrapper
    try:
        with tempfile.TemporaryDirectory() as tmp:
            case = Path(tmp) / "case"
            result = PipelineOrchestrator().run(
                GEAR,
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
            print(f"pipeline_success={result.success} error={result.error}")
    finally:
        octree.build_octree_hex_cells = original_build
        snap.snap_to_surface_iterative = original_snap
        mesher._wall_fit_snap = original_wall
        mesher._relax_boundary_sliver_interior = original_relax
        writer.write_generic_polymesh = original_writer
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
