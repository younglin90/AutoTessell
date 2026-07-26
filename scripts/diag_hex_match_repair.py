"""HEX-MATCH-2 measurement — cylinder / sphere / gear (real mesh edits, gated).

Runs the executable local repair (``core/generator/native_hex/match_repair.py``)
on the same three shapes, at the same settings, as the HEX-MATCH-1 census
(``scripts/diag_hex_match_candidates.py``): fine quality, **pre-BL** (the
boundary-layer pass re-triangulates the wall into prism caps that hide the hex
boundary quads this card targets), skew >= 2.0, depth <= 2.

Reports, per shape:

* the HEX-MATCH-1 census as committed at ``HEAD`` (loaded straight out of git so
  the "before" column is the real previous behaviour, not a reconstruction) next
  to the census after this card's two ``match_diagnostic`` bug fixes;
* the **falsification check** the card requires — re-run the diagnostic on a
  pristine copy of the input mesh and compare its targets, operation choices and
  footprints against what HEX-MATCH-2 actually attempted in its first round;
* per-outcome counts (committed / rejected by the quality gate / rejected by the
  boundary guard / footprint conflict / no candidate);
* whole-mesh and per-repaired-neighbourhood skewness and non-orthogonality
  before and after, and the cell-count change.

Generated meshes are cached under ``--cache-dir`` so the analysis can be re-run
without paying for mesh generation again.

Usage:
    python scripts/diag_hex_match_repair.py [max_cells] [--cache-dir DIR]
"""

from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
import tempfile
import types
from pathlib import Path

import numpy as np

REPO = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, REPO)

from core.utils.logging import configure_logging  # noqa: E402

configure_logging(verbose=False, json=False)

from core.generator.native_hex.match_diagnostic import (  # noqa: E402
    classify_repair_candidates,
    compute_boundary_face_skew,
    flag_bad_skew_faces,
)
from core.generator.native_hex.match_repair import (  # noqa: E402
    RepairReport,
    run_match_repair,
)
from core.generator.native_hex.metrics import read_written_polymesh_cells  # noqa: E402

_SHAPES = {
    "cylinder": Path(REPO) / "tests" / "benchmarks" / "cylinder.stl",
    "sphere": Path(REPO) / "tests" / "benchmarks" / "sphere.stl",
    "gear": Path(REPO) / "tests" / "stl" / "04_extreme_gear.stl",
}

_MODULE_PATH = "core/generator/native_hex/match_diagnostic.py"


def _load_head_diagnostic() -> types.ModuleType | None:
    """Import the committed (pre-fix) ``match_diagnostic`` for the before column."""
    try:
        src = subprocess.run(  # noqa: S603
            ["git", "-C", REPO, "show", f"HEAD:{_MODULE_PATH}"],  # noqa: S607
            capture_output=True,
            check=True,
            text=True,
        ).stdout
    except Exception as exc:  # noqa: BLE001
        print(f"  (could not load HEAD diagnostic: {exc})")
        return None
    path = Path(tempfile.gettempdir()) / "hexmatch1_head_diagnostic.py"
    path.write_text(src, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("hexmatch1_head_diagnostic", path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    # dataclass() resolves annotations through sys.modules, so the module has to
    # be registered before it is executed.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _generate(name: str, stl_path: Path, max_cells: int) -> tuple[np.ndarray, list] | None:
    from core.pipeline.orchestrator import PipelineOrchestrator  # noqa: PLC0415

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
            tier_specific_params={
                "max_cells": max_cells,
                "target_cells": max_cells,
                "bl_layers": 0,
            },
        )
        if not (case / "constant" / "polyMesh" / "points").exists():
            print(f"{name}: NO POLYMESH (pipeline failed) error={res.error}")
            return None
        return read_written_polymesh_cells(case)


def _cached(name: str, stl_path: Path, max_cells: int, cache_dir: Path) -> tuple | None:
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
        blob, points=points, cells=np.array([[list(f) for f in c] for c in cells], dtype=object)
    )
    return points, cells


def _census(module: types.ModuleType | None, points: np.ndarray, cells: list) -> str:
    if module is None:
        return "n/a"
    faces = module.compute_boundary_face_skew(points, cells)
    flagged = module.flag_bad_skew_faces(faces, threshold=2.0)
    cands = module.classify_repair_candidates(points, cells, flagged, max_depth=2)
    n = {"pillow": 0, "collapse": 0, "none": 0}
    for c in cands:
        n[c.candidate_type] += 1
    return (
        f"bfaces={len(faces)} flagged={len(flagged)} pillow={n['pillow']} "
        f"collapse={n['collapse']} none={n['none']}"
    )


def _falsification(points: np.ndarray, cells: list, report: RepairReport) -> str:
    """Re-derive HEX-MATCH-1's targets on a pristine copy and diff them."""
    pristine_pts = np.array(points, dtype=np.float64, copy=True)
    pristine_cells = [[[int(v) for v in f] for f in c] for c in cells]
    faces = compute_boundary_face_skew(pristine_pts, pristine_cells)
    flagged = flag_bad_skew_faces(faces, threshold=2.0)
    expected = classify_repair_candidates(pristine_pts, pristine_cells, flagged, max_depth=2)

    exp = {(c.face_key, c.candidate_type, c.footprint_cells) for c in expected}
    got = {
        (c.face_key, c.candidate_type, c.footprint_cells) for c in report.round0_candidates
    }
    if exp == got:
        return f"PASS — {len(exp)} targets identical (face, operation, footprint)"
    only_diag = exp - got
    only_exec = got - exp
    return (
        f"FAIL — {len(only_diag)} target(s) the diagnostic reports that HEX-MATCH-2 did not "
        f"attempt, {len(only_exec)} the other way; examples diag-only={sorted(only_diag)[:2]} "
        f"exec-only={sorted(only_exec)[:2]}"
    )


def _run_one(
    name: str, stl_path: Path, max_cells: int, cache_dir: Path, policy: str = "neighbourhood"
) -> None:
    if not stl_path.exists():
        print(f"{name}: SKIP (fixture not found: {stl_path})")
        return
    loaded = _cached(name, stl_path, max_cells, cache_dir)
    if loaded is None:
        return
    points, cells = loaded

    head = _load_head_diagnostic()
    print(f"\n===== {name} (cells={len(cells)}) =====")
    print(f"  census @HEAD (pre-fix) : {_census(head, points, cells)}")
    print(f"  census after bug fixes  : {_census(_CURRENT, points, cells)}")

    _new_pts, _new_cells, report = run_match_repair(name, points, cells, gate_policy=policy)

    print(f"  gate policy            : {policy}")
    print(f"  falsification check    : {_falsification(points, cells, report)}")
    print(
        f"  outcomes: committed={report.count('committed')} "
        f"rejected_quality={report.count('rejected_quality')} "
        f"rejected_boundary_guard={report.count('rejected_boundary_guard')} "
        f"rejected_conflict={report.count('rejected_conflict')} "
        f"no_candidate={report.count('no_candidate')} rounds={report.rounds_run}"
    )
    pre, post = report.pre, report.post
    print(
        f"  cells {pre.n_cells} -> {post.n_cells} ({post.n_cells - pre.n_cells:+d}), "
        f"points {pre.n_points} -> {post.n_points}"
    )
    print(
        f"  GLOBAL max boundary skew {pre.max_boundary_skew:.4f} -> {post.max_boundary_skew:.4f} | "
        f"mean {pre.mean_boundary_skew:.4f} -> {post.mean_boundary_skew:.4f} | "
        f"flagged {pre.n_flagged} -> {post.n_flagged}"
    )
    print(
        f"  GLOBAL max internal skew {pre.max_internal_skew:.4f} -> "
        f"{post.max_internal_skew:.4f} | max non-ortho {pre.max_non_ortho_deg:.3f} -> "
        f"{post.max_non_ortho_deg:.3f} | mean non-ortho {pre.mean_non_ortho_deg:.3f} -> "
        f"{post.mean_non_ortho_deg:.3f}"
    )
    print(
        f"  min signed volume {pre.min_signed_volume:.6e} -> {post.min_signed_volume:.6e} | "
        f"pass rolled back={report.pass_rolled_back} {report.rollback_reason}"
    )

    committed = [o for o in report.outcomes if o.status == "committed"]
    if committed:
        pre_f = np.array([o.pre_face_skew for o in committed])
        post_f = np.array([o.post_face_skew for o in committed])
        pre_no = np.array([o.pre_local.max_non_ortho_deg for o in committed])
        post_no = np.array([o.post_local.max_non_ortho_deg for o in committed])
        pre_is = np.array([o.pre_local.max_internal_skew for o in committed])
        post_is = np.array([o.post_local.max_internal_skew for o in committed])
        print(
            f"  PER-NEIGHBOURHOOD (committed only, n={len(committed)}): "
            f"target face skew mean {pre_f.mean():.4f} -> {post_f.mean():.4f}, "
            f"max {pre_f.max():.4f} -> {post_f.max():.4f}"
        )
        print(
            f"       local max non-ortho mean {pre_no.mean():.3f} -> {post_no.mean():.3f} deg, "
            f"worst {pre_no.max():.3f} -> {post_no.max():.3f} deg | "
            f"local max internal skew mean {pre_is.mean():.4f} -> {post_is.mean():.4f}"
        )
        print(f"       ladder rungs used: mean {np.mean([o.attempts for o in committed]):.2f}")

    from collections import Counter  # noqa: PLC0415

    rejected = [o for o in report.outcomes if o.status == "rejected_quality"]
    if rejected:
        kinds = Counter(
            "degenerate/inverted"
            if "degenerate" in o.reason
            else "non-orthogonality ceiling"
            if "non-orthogonality" in o.reason
            else "internal skew ceiling"
            if "internal skewness" in o.reason
            else "boundary skew regression"
            if "boundary skewness" in o.reason
            else "target not improved"
            if "did not strictly improve" in o.reason
            else "other"
            for o in rejected
        )
        print(f"  quality-gate rejection causes (last rung): {dict(kinds)}")


_CURRENT = sys.modules["core.generator.native_hex.match_diagnostic"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("max_cells", nargs="?", type=int, default=8000)
    parser.add_argument("--cache-dir", type=Path, default=Path(tempfile.gettempdir()) / "hexmatch")
    parser.add_argument("--shapes", default="cylinder,sphere,gear")
    parser.add_argument("--gate", default="neighbourhood,mesh")
    args = parser.parse_args()
    for policy in args.gate.split(","):
        print(f"\n########## gate policy = {policy} ##########")
        for name in args.shapes.split(","):
            if name in _SHAPES:
                _run_one(name, _SHAPES[name], args.max_cells, args.cache_dir, policy)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
