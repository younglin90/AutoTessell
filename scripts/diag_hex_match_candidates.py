"""HEX-MATCH-1 targeting census — cylinder / sphere / gear (diagnostic only).

Generates a native_hex fine-quality mesh per shape, flags boundary ("side")
faces at OpenFOAM-style skewness >= 2.0 (the same threshold used in the
2026-07-24 wave-0 measurement recorded in
``docs/references/literature/native_hex/native_hex_literature_integrated_development_plan_2026-07-23.md``),
then runs the Staten-2010-adapted decision logic
(``core/generator/native_hex/match_diagnostic.py``) to report, per flagged
face, which local repair candidate (pillow / column-collapse / none) the
mesh-matching operator catalog would select and its depth-bounded footprint.

ZERO mesh edits happen anywhere in this script — see match_diagnostic.py's
module docstring. Bracket (03_hard_bracket.stl) is explicitly out of scope for
HEX-MATCH-1 (its 7-connected-component/6-patch damage is HEX-MATCH-3, a
separate uncertain-outcome research spike) and is not run here.

Usage:
    python scripts/diag_hex_match_candidates.py [max_cells]
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

REPO = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, REPO)

from core.utils.logging import configure_logging  # noqa: E402

configure_logging(verbose=False, json=False)

from core.generator.native_hex.match_diagnostic import run_match_diagnostic  # noqa: E402
from core.generator.native_hex.metrics import read_written_polymesh_cells  # noqa: E402
from core.pipeline.orchestrator import PipelineOrchestrator  # noqa: E402

_SHAPES = {
    "cylinder": Path(REPO) / "tests" / "benchmarks" / "cylinder.stl",
    "sphere": Path(REPO) / "tests" / "benchmarks" / "sphere.stl",
    "gear": Path(REPO) / "tests" / "stl" / "04_extreme_gear.stl",
}


def _run_one(name: str, stl_path: Path, max_cells: int) -> None:
    if not stl_path.exists():
        print(f"{name}: SKIP (fixture not found: {stl_path})")
        return
    with tempfile.TemporaryDirectory() as tmp:
        case = Path(tmp) / "case"
        res = PipelineOrchestrator().run(
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
            # bl_layers=0 — the wave-0/wave-1 measurements this diagnostic
            # continues from are explicitly "pre-BL" (boundary-layer prism
            # insertion re-triangulates the outer wall and would hide the
            # underlying octree-transition hex boundary faces this card
            # targets). See native_hex_literature_integrated_development_plan
            # section "2026-07-24 wave 0 result".
            tier_specific_params={
                "max_cells": max_cells,
                "target_cells": max_cells,
                "bl_layers": 0,
            },
        )
        poly = case / "constant" / "polyMesh"
        if not (poly / "points").exists():
            print(f"{name}: NO POLYMESH (pipeline failed) error={res.error}")
            return
        loaded = read_written_polymesh_cells(case)
        if loaded is None:
            print(f"{name}: could not reconstruct cell-face representation")
            return
        points, cell_faces = loaded
        report = run_match_diagnostic(name, points, cell_faces)
        print(
            f"{name}: cells={len(cell_faces)} boundary_faces={report.n_boundary_faces} "
            f"flagged={report.n_flagged} pillow={report.n_pillow} "
            f"collapse={report.n_collapse} none={report.n_none}"
        )
        for cand in report.candidates:
            print(
                f"    face={cand.face_key} owner={cand.owner_cell} skew={cand.skewness:.3f} "
                f"-> {cand.candidate_type} depth={cand.depth_used} "
                f"footprint={cand.footprint_cells} :: {cand.reason}"
            )


def main() -> int:
    max_cells = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    for name, path in _SHAPES.items():
        _run_one(name, path, max_cells)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
