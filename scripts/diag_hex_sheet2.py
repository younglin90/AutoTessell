"""HEX-SHEET-2 report-only layer-wide wall pillow census.

Measures the actual fine-quality, pre-boundary-layer native_hex meshes used by
HEX-MATCH-1/2.  No mesh-editing feature flag is enabled and no mesh is changed.

Usage:
    python scripts/diag_hex_sheet2.py [max_cells] [--cache-dir DIR]
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path
from typing import cast

import numpy as np

REPO = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, REPO)

from core.generator.native_hex.metrics import read_written_polymesh_cells  # noqa: E402
from core.generator.native_hex.sheet_diagnostic import (  # noqa: E402
    Sheet2DiagnosticReport,
    analyze_layer_wide_shrink_set,
)
from core.utils.logging import configure_logging  # noqa: E402

configure_logging(verbose=False, json=False)

_SHAPES = {
    "cylinder": Path(REPO) / "tests" / "benchmarks" / "cylinder.stl",
    "sphere": Path(REPO) / "tests" / "benchmarks" / "sphere.stl",
    "gear": Path(REPO) / "tests" / "stl" / "04_extreme_gear.stl",
}

Cells = list[list[list[int]]]


def _generate(name: str, stl_path: Path, max_cells: int) -> tuple[np.ndarray, Cells] | None:
    from core.pipeline.orchestrator import PipelineOrchestrator  # noqa: PLC0415

    disabled = ("AUTO_TESSELL_HEX_MATCH2", "AUTO_TESSELL_HEX_SHEET2")
    previous = {key: os.environ.pop(key, None) for key in disabled}
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
            if not (case / "constant" / "polyMesh" / "points").exists():
                print(f"{name}: NO POLYMESH (pipeline failed) error={result.error}")
                return None
            loaded = read_written_polymesh_cells(case)
            if loaded is None:
                return None
            return cast(tuple[np.ndarray, Cells], loaded)
    finally:
        for key, value in previous.items():
            if value is not None:
                os.environ[key] = value


def _cached(
    name: str, stl_path: Path, max_cells: int, cache_dir: Path
) -> tuple[np.ndarray, Cells] | None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    blob = cache_dir / f"{name}_{max_cells}.npz"
    if blob.exists():
        data = np.load(blob, allow_pickle=True)
        return data["points"], [[[int(v) for v in f] for f in c] for c in data["cells"]]
    loaded = _generate(name, stl_path, max_cells)
    if loaded is None:
        return None
    points, cells = loaded
    np.savez_compressed(
        blob,
        points=points,
        cells=np.array([[list(face) for face in cell] for cell in cells], dtype=object),
    )
    return points, cells


def _format_hist(histogram: tuple[tuple[int, int], ...]) -> str:
    return "{" + ", ".join(f"{value}:{count}" for value, count in histogram) + "}"


def _print_report(report: Sheet2DiagnosticReport) -> None:
    print(f"\n===== {report.shape_name} =====")
    print(
        f"  points={report.n_points} cells={report.n_cells} "
        f"boundary={report.n_boundary_faces} "
        f"(quad={report.n_boundary_quads}, nonquad={report.n_boundary_nonquads})"
    )
    print(f"  S: shrink={report.n_shrink} nonhex={report.n_shrink_nonhex} " f"core={report.n_core}")
    print(
        f"  Q: faces={report.n_interface_faces} quad={report.n_interface_quads} "
        f"nonquad={report.n_interface_nonquads} bad_owner_count="
        f"{report.n_interface_bad_owner_count} vertices={report.n_interface_vertices} "
        f"boundary_vertices={report.n_interface_vertices_on_boundary}"
    )
    print(
        f"  Q topology: edge_incidence={_format_hist(report.edge_incidence_histogram)} "
        f"components={report.n_components} open_edges={report.n_open_edges} "
        f"nonmanifold_edges={report.n_nonmanifold_edges}"
    )
    print(
        f"  S boundary-face hist={_format_hist(report.shrink_boundary_face_histogram)} "
        f"interface-face hist={_format_hist(report.shrink_interface_face_histogram)}"
    )
    print(
        "  S (boundary,interface) hist={"
        + ", ".join(
            f"({boundary},{interface}):{count}"
            for boundary, interface, count in report.shrink_boundary_interface_histogram
        )
        + "}"
    )
    print(
        f"  expected growth: points +{report.expected_point_growth} "
        f"({report.n_points}->{report.n_points + report.expected_point_growth}), "
        f"cells +{report.expected_cell_growth} "
        f"({report.n_cells}->{report.n_cells + report.expected_cell_growth})"
    )
    print(
        f"  gates: Q_closed_manifold_quad={report.q_closed_manifold_quad_set} "
        f"wall_cell_incidence={report.wall_cell_incidence_contract} "
        f"TOPOLOGY_READY={report.topology_ready}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("max_cells", nargs="?", type=int, default=8000)
    parser.add_argument("--cache-dir", type=Path, default=Path(tempfile.gettempdir()) / "hexmatch")
    parser.add_argument("--shapes", default="cylinder,sphere,gear")
    args = parser.parse_args()

    failed = False
    for name in args.shapes.split(","):
        if name not in _SHAPES:
            continue
        loaded = _cached(name, _SHAPES[name], args.max_cells, args.cache_dir)
        if loaded is None:
            failed = True
            continue
        points, cells = loaded
        report = analyze_layer_wide_shrink_set(name, points, cells, log_only=False)
        _print_report(report)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
