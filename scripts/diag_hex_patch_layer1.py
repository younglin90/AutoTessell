"""HEX-PATCH-LAYER-DIAG1 report-only census on cached fine pre-BL meshes.

The runner intentionally reads existing ``hexmatch`` cache blobs only.  It
does not regenerate a mesh, enable a production flag, or perform any mesh
operation.

Usage:
    python scripts/diag_hex_patch_layer1.py [--cache-dir DIR] [--max-cells N]
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path
from typing import cast

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from core.generator.native_hex.patch_layer_diagnostic import (  # noqa: E402
    PatchLayerDiagnosticReport,
    analyze_patch_layer_subsets,
)
from core.utils.logging import configure_logging  # noqa: E402

configure_logging(verbose=False, json=False)

Cells = list[list[list[int]]]
_SHAPES = ("cylinder", "sphere", "gear")


def _load_cached(name: str, max_cells: int, cache_dir: Path) -> tuple[np.ndarray, Cells]:
    path = cache_dir / f"{name}_{max_cells}.npz"
    if not path.exists():
        raise FileNotFoundError(f"required cached pre-BL mesh is missing: {path}")
    with np.load(path, allow_pickle=True) as data:
        points = np.asarray(data["points"], dtype=np.float64).copy()
        cells = [
            [[int(vertex) for vertex in face] for face in cell]
            for cell in cast(np.ndarray, data["cells"])
        ]
    return points, cells


def _format_hist(histogram: tuple[tuple[int, int], ...]) -> str:
    return "{" + ", ".join(f"{value}:{count}" for value, count in histogram) + "}"


def _format_components(report: PatchLayerDiagnosticReport) -> str:
    grouped: dict[tuple[str, str, int, int, int], int] = {}
    for component in report.components:
        key = (
            component.patch,
            component.provenance,
            component.n_s,
            component.n_open_edges,
            component.n_nonmanifold_edges,
        )
        grouped[key] = grouped.get(key, 0) + 1
    chunks = []
    for (patch, provenance, n_s, open_edges, nonmanifold_edges), count in sorted(grouped.items()):
        chunks.append(
            f"{patch}/{provenance}:nS={n_s}x{count},"
            f"open={open_edges},nonmanifold={nonmanifold_edges}"
        )
    return "; ".join(chunks) or "none"


def _print_report(report: PatchLayerDiagnosticReport, repeat_identical: bool) -> None:
    print(f"\n===== {report.shape_name} =====")
    print(
        "shape | cells | physical boundary | S exact1/nonhex | Q interface quad/nonquad "
        "| eligible S/Q | components | edge incidence | open/nonmanifold "
        "| Q vertices on physical boundary | predicted/approved pillow ops | decision"
    )
    print(
        f"{report.shape_name} | {report.n_cells} | {report.n_physical_boundary_faces} "
        f"| {report.n_wall_exact_one_boundary}/{report.n_wall_exact_one_boundary_nonhex} "
        f"| {report.n_interface_faces}/{report.n_interface_nonquads} "
        f"| {report.n_eligible_s}/{report.n_eligible_q} | {report.n_components} "
        f"| {_format_hist(report.edge_incidence_histogram)} "
        f"| {report.n_open_edges}/{report.n_nonmanifold_edges} "
        f"| {report.n_eligible_q_vertices_on_physical_boundary} "
        f"| {report.n_predicted_operations}/{report.n_approved_operations} "
        f"| {report.decision}"
    )
    print(
        f"  hypothetical growth (not executed): points +{report.predicted_point_growth}, "
        f"cells +{report.predicted_cell_growth}; repeat_identical={repeat_identical}"
    )
    print(f"  components: {_format_components(report)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path(tempfile.gettempdir()) / "hexmatch",
    )
    parser.add_argument("--max-cells", type=int, default=8000)
    parser.add_argument("--shapes", default=",".join(_SHAPES))
    args = parser.parse_args()

    for name in args.shapes.split(","):
        if name not in _SHAPES:
            raise ValueError(f"unsupported shape: {name}")
        points, cells = _load_cached(name, args.max_cells, args.cache_dir)
        first = analyze_patch_layer_subsets(name, points, cells, log_only=False)
        second = analyze_patch_layer_subsets(name, points, cells, log_only=False)
        if first != second:
            raise AssertionError(f"non-deterministic repeated measurement for {name}")
        _print_report(first, repeat_identical=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
