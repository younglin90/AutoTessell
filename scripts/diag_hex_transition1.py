"""HEX-TRANSITION-DIAG1 report-only cache audit.

The runner reuses PATCH-LAYER-DIAG1 and measures geometry-only baselines.  It
does not regenerate a mesh, enable a production flag, or infer transition
chains/templates from final connectivity.  Current cache blobs are expected to
report ``BLOCKED`` until the required transition metadata is exported.

Usage:
    python scripts/diag_hex_transition1.py [--cache-dir DIR] [--max-cells N]
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import cast

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from core.generator.native_hex.transition_diagnostic import (  # noqa: E402
    TransitionDiagnosticReport,
    audit_transition_inputs,
)
from core.utils.logging import configure_logging  # noqa: E402

configure_logging(verbose=False, json=False)

Cells = list[list[list[int]]]
_SHAPES = ("cylinder", "sphere", "gear")


def _load_cached(
    name: str, max_cells: int, cache_dir: Path
) -> tuple[np.ndarray, Cells, tuple[str, ...]]:
    path = cache_dir / f"{name}_{max_cells}.npz"
    if not path.exists():
        raise FileNotFoundError(f"required cached pre-BL mesh is missing: {path}")
    with np.load(path, allow_pickle=True) as data:
        points = np.asarray(data["points"], dtype=np.float64).copy()
        cells = [
            [[int(vertex) for vertex in face] for face in cell]
            for cell in cast(np.ndarray, data["cells"])
        ]
        fields = tuple(str(field) for field in data.files)
    return points, cells, fields


def _print_metric(label: str, report: TransitionDiagnosticReport) -> None:
    summary = getattr(report, label)
    print(
        f"  {label}: n={summary.n} min={summary.minimum} p50={summary.p50} "
        f"p95={summary.p95} max={summary.maximum}"
    )


def _print_report(report: TransitionDiagnosticReport) -> None:
    patch = report.patch_layer
    print(f"\n===== {report.shape_name} =====")
    print(
        f"status={report.status} points={report.n_points} cells={report.n_cells} "
        f"cache_fields={','.join(report.cache_fields)}"
    )
    print(
        f"  patch-layer reuse: decision={patch.decision} components={patch.n_components} "
        f"eligible_s/q={patch.n_eligible_s}/{patch.n_eligible_q}"
    )
    print(f"  provenance mode: {report.patch_provenance_mode}")
    _print_metric("all_face_warpage", report)
    _print_metric("boundary_face_warpage", report)
    _print_metric("cell_local_scaled_jacobian_magnitude", report)
    print("  blockers:")
    for reason in report.blocker_reasons:
        print(f"    - {reason}")
    print("  required inputs:")
    for required in report.required_metadata_inputs:
        print(f"    - {required}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path(tempfile.gettempdir()) / "hexmatch",
    )
    parser.add_argument("--max-cells", type=int, default=8000)
    parser.add_argument("--shapes", default=",".join(_SHAPES))
    parser.add_argument("--json", action="store_true", help="emit one JSON document")
    args = parser.parse_args()

    reports: list[TransitionDiagnosticReport] = []
    for name in args.shapes.split(","):
        if name not in _SHAPES:
            raise ValueError(f"unsupported shape: {name}")
        points, cells, fields = _load_cached(name, args.max_cells, args.cache_dir)
        reports.append(audit_transition_inputs(name, points, cells, cache_fields=fields))
    if args.json:
        print(json.dumps([report.to_dict() for report in reports], indent=2, sort_keys=True))
    else:
        for report in reports:
            _print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
