"""HEX-PROV-RETENTION-1 — writer boundary audit without production hooks.

The diagnostic monkey-patches only the public ``write_generic_polymesh`` symbol
at process scope, captures the exact in-memory points/cells passed by
``generate_native_hex``, calls the real writer, and compares coordinate-based
cell/face signatures with the written polyMesh.  It does not change generator
logic, gates, or output; the patch is removed when the process exits.

The current native_hex call supplies points, cells, and case_dir only.  No
octree level or source patch/provenance table is passed at this boundary.  The
absence is reported as evidence, not repaired here.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import sys
import tempfile
from typing import Any

import numpy as np

REPO = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, REPO)

from core.generator.native_hex.metrics import (  # noqa: E402
    _face_owners,
    read_written_polymesh_cells,
)
from core.pipeline.orchestrator import PipelineOrchestrator  # noqa: E402
from scripts.diag_hex_transition_provenance import analyze as analyze_transition  # noqa: E402


_SHAPES = {
    "cylinder": Path(REPO) / "tests" / "benchmarks" / "cylinder.stl",
    "sphere": Path(REPO) / "tests" / "benchmarks" / "sphere.stl",
    "gear": Path(REPO) / "tests" / "stl" / "04_extreme_gear.stl",
}


class _WriterCapture:
    def __init__(self, real_writer: Any) -> None:
        self.real_writer = real_writer
        self.points: np.ndarray | None = None
        self.cells: list[list[list[int]]] | None = None
        self.args_len = 0
        self.kwargs = {}

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.args_len = len(args)
        self.kwargs = dict(kwargs)
        if len(args) >= 2:
            self.points = np.asarray(args[0], dtype=np.float64).copy()
            self.cells = [
                [[int(v) for v in face] for face in cell]
                for cell in args[1]
            ]
        return self.real_writer(*args, **kwargs)


def _qpoint(point: np.ndarray) -> tuple[float, float, float]:
    # native_bl._write_points uses ``%.9g``; four decimals is a conservative
    # comparison grid that absorbs serialization rounding without merging
    # distinct fine-grid coordinates at the canonical bench scale.
    return tuple(float(v) for v in np.round(point, 4))


def _face_signature(points: np.ndarray, face: list[int]) -> tuple[tuple[float, float, float], ...]:
    return tuple(sorted(_qpoint(points[int(v)]) for v in face))


def _cell_signatures(
    points: np.ndarray, cells: list[list[list[int]]]
) -> Counter[tuple[tuple[tuple[float, float, float], ...], ...]]:
    return Counter(
        tuple(sorted(_face_signature(points, face) for face in cell))
        for cell in cells
    )


def _cell_id_signatures(
    cells: list[list[list[int]]]
) -> Counter[tuple[tuple[int, ...], ...]]:
    return Counter(
        tuple(sorted(tuple(sorted(int(v) for v in face)) for face in cell))
        for cell in cells
    )


def _boundary_signatures(
    points: np.ndarray, cells: list[list[list[int]]]
) -> set[tuple[tuple[float, float, float], ...]]:
    owners = _face_owners(cells)
    return {
        _face_signature(points, list(key))
        for key, face_owners in owners.items()
        if len(set(int(v) for v in face_owners)) == 1
    }


def _boundary_id_signatures(
    cells: list[list[list[int]]]
) -> set[tuple[int, ...]]:
    owners = _face_owners(cells)
    return {
        tuple(key)
        for key, face_owners in owners.items()
        if len(set(int(v) for v in face_owners)) == 1
    }


def _compare(
    raw_points: np.ndarray,
    raw_cells: list[list[list[int]]],
    written_points: np.ndarray,
    written_cells: list[list[list[int]]],
    surface_vertices: np.ndarray,
    surface_faces: np.ndarray,
) -> dict[str, Any]:
    raw_counter = _cell_signatures(raw_points, raw_cells)
    written_counter = _cell_signatures(written_points, written_cells)
    raw_id_counter = _cell_id_signatures(raw_cells)
    written_id_counter = _cell_id_signatures(written_cells)
    raw_boundary = _boundary_signatures(raw_points, raw_cells)
    written_boundary = _boundary_signatures(written_points, written_cells)
    raw_boundary_ids = _boundary_id_signatures(raw_cells)
    written_boundary_ids = _boundary_id_signatures(written_cells)
    raw_transition = analyze_transition(raw_points, raw_cells, surface_vertices, surface_faces)
    written_transition = analyze_transition(
        written_points, written_cells, surface_vertices, surface_faces
    )
    matched = sum((raw_counter & written_counter).values())
    return {
        "raw_cells": len(raw_cells),
        "written_cells": len(written_cells),
        "matched_cells": matched,
        "raw_only_cells": sum((raw_counter - written_counter).values()),
        "written_only_cells": sum((written_counter - raw_counter).values()),
        "raw_boundary": len(raw_boundary),
        "written_boundary": len(written_boundary),
        "boundary_removed": len(raw_boundary - written_boundary),
        "boundary_added": len(written_boundary - raw_boundary),
        "boundary_equal": raw_boundary == written_boundary,
        "id_matched_cells": sum((raw_id_counter & written_id_counter).values()),
        "id_boundary_equal": raw_boundary_ids == written_boundary_ids,
        "raw_transition_faces": raw_transition["n_transition_faces"],
        "written_transition_faces": written_transition["n_transition_faces"],
        "raw_transition_cells": raw_transition["n_transition_cells"],
        "written_transition_cells": written_transition["n_transition_cells"],
        "raw_bad_direct": sum(
            1 for row in raw_transition["rows"] if row["bad"] and row["direct_transition"]
        ),
        "written_bad_direct": sum(
            1
            for row in written_transition["rows"]
            if row["bad"] and row["direct_transition"]
        ),
        "max_point_delta_same_index": float(
            np.max(np.abs(raw_points - written_points))
        )
        if raw_points.shape == written_points.shape
        else None,
    }


def _run_one(name: str, stl_path: Path, max_cells: int) -> None:
    if not stl_path.exists():
        print(f"{name}: SKIP (fixture not found: {stl_path})")
        return
    from core.analyzer.readers.stl import read_stl  # noqa: PLC0415
    import core.generator.polymesh_writer as writer_module  # noqa: PLC0415

    surface_mesh = read_stl(str(stl_path))
    surface_vertices = np.asarray(surface_mesh.vertices, dtype=np.float64)
    surface_faces = np.asarray(surface_mesh.faces, dtype=np.int64)
    capture = _WriterCapture(writer_module.write_generic_polymesh)
    writer_module.write_generic_polymesh = capture
    try:
        with tempfile.TemporaryDirectory() as tmp:
            case = Path(tmp) / "case"
            result = PipelineOrchestrator().run(
                stl_path,
                case,
                quality_level="fine",
                mesh_type="hex_dominant",
                tier_hint="native_hex",
                max_iterations=1,
                auto_retry="off",
                strict_tier=True,
                write_of_case=True,
                max_cells=max_cells,
                tier_specific_params={
                    "max_cells": max_cells,
                    "target_cells": max_cells,
                    "bl_layers": 0,
                },
            )
            loaded = read_written_polymesh_cells(case)
            if loaded is None or capture.points is None or capture.cells is None:
                print(f"{name}: NO RETENTION DATA error={result.error}")
                return
            written_points, written_cells = loaded
            report = _compare(
                capture.points,
                capture.cells,
                written_points,
                written_cells,
                surface_vertices,
                surface_faces,
            )
            print(
                f"{name}: raw/written cells={report['raw_cells']}/{report['written_cells']} "
                f"coord-matched={report['matched_cells']} id-matched={report['id_matched_cells']} "
                f"raw_only={report['raw_only_cells']} "
                f"written_only={report['written_only_cells']}"
            )
            print(
                f"  boundary raw/written={report['raw_boundary']}/{report['written_boundary']} "
                f"removed={report['boundary_removed']} added={report['boundary_added']} "
                f"coord-equal={report['boundary_equal']} id-equal={report['id_boundary_equal']}"
            )
            print(
                f"  transition faces raw/written={report['raw_transition_faces']}/"
                f"{report['written_transition_faces']} cells="
                f"{report['raw_transition_cells']}/{report['written_transition_cells']} "
                f"bad-direct={report['raw_bad_direct']}/{report['written_bad_direct']}"
            )
            print(
                f"  point-shape={capture.points.shape}/{written_points.shape} "
                f"max-point-delta-same-index={report['max_point_delta_same_index']}"
            )
            print(
                f"  writer-call args={capture.args_len} kwargs={sorted(capture.kwargs)} "
                "source_patch_ids=not-provided octree_level_ids=not-provided"
            )
    finally:
        writer_module.write_generic_polymesh = capture.real_writer


def main() -> int:
    max_cells = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    selected = sys.argv[2].split(",") if len(sys.argv) > 2 else list(_SHAPES)
    for name in selected:
        path = _SHAPES.get(name)
        if path is None:
            print(f"{name}: SKIP (unknown shape)")
            continue
        _run_one(name, path, max_cells)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
