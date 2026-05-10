#!/usr/bin/env python3
"""BLR-9c-d-g-2 — 21-STL cavity-component evaluation bench.

Runs the tet + native_bl pipeline on the user-facing STL set
(test_cube.stl + tests/stl/thingi10k_bench20/*.stl, 21 cases) with
``AUTO_TESSELL_BL_TET_CAVITY_EVAL=1`` set so each case writes a
``native_bl_quality.tet_cavity_eval`` block.  The script then
aggregates the per-case blocks into:

  - bench_cavity_eval_result.json (raw per-STL records)
  - bench_cavity_eval_summary.tsv (one row per STL: counts +
    decision distribution + elapsed)

Designed as a read-only diagnostic — toggling the env flag never
mutates the emitted polyMesh, so this bench is safe to run on the
production tet+BL pipeline.

Usage::

    python3 tests/stl/bench_cavity_eval.py --limit 1     # smoke
    python3 tests/stl/bench_cavity_eval.py               # full 21
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
TARGET_CELLS = int(os.environ.get("AUTO_TESSELL_BENCH_CAVITY_TARGET_CELLS", "10000"))
BL_LAYERS = int(os.environ.get("AUTO_TESSELL_BENCH_CAVITY_BL_LAYERS", "3"))
QUALITY = os.environ.get("AUTO_TESSELL_BENCH_CAVITY_QUALITY", "fine")
TIMEOUT_S = float(os.environ.get("AUTO_TESSELL_BENCH_CAVITY_TIMEOUT_S", "600"))
RUN_ROOT = Path(
    os.environ.get(
        "AUTO_TESSELL_BENCH_CAVITY_RUN_ROOT",
        "/tmp/autotessell_bench_cavity_eval",
    )
)


def discover_stls() -> list[Path]:
    """Return the 21-STL bench set: test_cube + thingi10k_bench20/*.stl."""
    stls: list[Path] = []
    cube = ROOT / "test_cube.stl"
    if cube.exists():
        stls.append(cube)
    bench_dir = ROOT / "tests" / "stl" / "thingi10k_bench20"
    if bench_dir.exists():
        stls.extend(sorted(p for p in bench_dir.glob("*.stl")))
    return stls


def run_one(stl_path: Path, case_dir: Path) -> dict[str, Any]:
    """Run auto-tessell tet + native_bl with the cavity-eval flag on."""
    case_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, "-m", "cli.main", "run", str(stl_path),
        "-o", str(case_dir),
        "--mesh-type", "tet",
        "--tier", "wildmesh",
        "--strict-tier",
        "--quality", QUALITY,
        "--checker-engine", "native",
        "--auto-retry", "off",
        "--max-cells", str(TARGET_CELLS),
        "--bl-layers", str(BL_LAYERS),
        "--tier-param", "post_layers_engine=auto",
        "--tier-param", f"post_layers_num_layers={BL_LAYERS}",
        "--tier-param", f"target_cells={TARGET_CELLS}",
        "--tier-param", f"max_cells={TARGET_CELLS}",
    ]
    env = os.environ.copy()
    env["AUTO_TESSELL_BL_TET_CAVITY_EVAL"] = "1"
    env.setdefault("AUTO_TESSELL_P4C_PYTETWILD", "0")
    env.setdefault("AUTO_TESSELL_ALLOW_EXTERNAL_OPENFOAM", "0")
    env.setdefault("AUTO_TESSELL_LCR_OFF", "1")
    env.setdefault("PYTHONUNBUFFERED", "1")

    row: dict[str, Any] = {
        "stl": stl_path.relative_to(ROOT).as_posix(),
        "case_dir": str(case_dir),
    }
    start = time.perf_counter()
    try:
        proc = subprocess.run(
            cmd, cwd=ROOT, env=env, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=TIMEOUT_S,
        )
        row["returncode"] = int(proc.returncode)
    except subprocess.TimeoutExpired:
        row["returncode"] = 124
        row["timeout"] = True
    row["elapsed_s"] = round(time.perf_counter() - start, 3)

    # Read native_bl_quality.json and extract tet_cavity_eval.
    bl_qual_path = case_dir / "native_bl_quality.json"
    eval_block: dict[str, Any] = {}
    if bl_qual_path.exists():
        try:
            data = json.loads(bl_qual_path.read_text())
            eval_block = dict(data.get("tet_cavity_eval", {}))
        except Exception as exc:  # noqa: BLE001
            eval_block = {"read_error": str(exc)[:160]}
    row["tet_cavity_eval"] = eval_block
    return row


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0,
                        help="Cap number of STLs (0 = all).")
    parser.add_argument("--keep-cases", action="store_true",
                        help="Don't wipe RUN_ROOT before starting.")
    args = parser.parse_args()

    if not args.keep_cases and RUN_ROOT.exists():
        shutil.rmtree(RUN_ROOT)
    RUN_ROOT.mkdir(parents=True, exist_ok=True)

    stls = discover_stls()
    if args.limit > 0:
        stls = stls[: args.limit]
    if not stls:
        print("[bench_cavity_eval] no STLs discovered", file=sys.stderr)
        return 2
    print(f"[bench_cavity_eval] {len(stls)} STLs, RUN_ROOT={RUN_ROOT}")

    rows: list[dict[str, Any]] = []
    totals = {
        "n_stls": 0,
        "n_components": 0,
        "n_accepted": 0,
        "n_rejected_uncovered_shell": 0,
        "n_rejected_bad_det": 0,
        "n_rejected_bad_shape": 0,
        "n_rejected_bad_non_ortho": 0,
        "n_rejected_bad_skewness": 0,
    }
    for i, stl in enumerate(stls, start=1):
        case = RUN_ROOT / stl.stem
        print(f"[{i}/{len(stls)}] {stl.relative_to(ROOT)}")
        row = run_one(stl, case)
        rows.append(row)
        totals["n_stls"] += 1
        ev = row.get("tet_cavity_eval") or {}
        for key in (
            "n_components", "n_accepted",
            "n_rejected_uncovered_shell", "n_rejected_bad_det",
            "n_rejected_bad_shape", "n_rejected_bad_non_ortho",
            "n_rejected_bad_skewness",
        ):
            totals[key] += int(ev.get(key, 0))
        decision_str = (
            f"comps={ev.get('n_components', 0)} acc={ev.get('n_accepted', 0)} "
            f"shell={ev.get('n_rejected_uncovered_shell', 0)} "
            f"det={ev.get('n_rejected_bad_det', 0)} "
            f"shape={ev.get('n_rejected_bad_shape', 0)} "
            f"nort={ev.get('n_rejected_bad_non_ortho', 0)} "
            f"skew={ev.get('n_rejected_bad_skewness', 0)}"
        )
        print(f"        rc={row['returncode']} t={row['elapsed_s']}s {decision_str}")

    out_dir = ROOT / "tests" / "stl"
    json_path = out_dir / "bench_cavity_eval_result.json"
    json_path.write_text(json.dumps(
        {"totals": totals, "rows": rows}, indent=2,
    ))
    tsv_path = out_dir / "bench_cavity_eval_summary.tsv"
    cols = [
        "stl", "returncode", "elapsed_s",
        "n_components", "n_accepted",
        "n_rejected_uncovered_shell", "n_rejected_bad_det",
        "n_rejected_bad_shape", "n_rejected_bad_non_ortho",
        "n_rejected_bad_skewness",
    ]
    lines = ["\t".join(cols)]
    for r in rows:
        ev = r.get("tet_cavity_eval") or {}
        lines.append("\t".join([
            str(r.get("stl", "")),
            str(r.get("returncode", "")),
            str(r.get("elapsed_s", "")),
            str(ev.get("n_components", 0)),
            str(ev.get("n_accepted", 0)),
            str(ev.get("n_rejected_uncovered_shell", 0)),
            str(ev.get("n_rejected_bad_det", 0)),
            str(ev.get("n_rejected_bad_shape", 0)),
            str(ev.get("n_rejected_bad_non_ortho", 0)),
            str(ev.get("n_rejected_bad_skewness", 0)),
        ]))
    tsv_path.write_text("\n".join(lines) + "\n")

    print(f"[bench_cavity_eval] totals: {totals}")
    print(f"[bench_cavity_eval] wrote {json_path}")
    print(f"[bench_cavity_eval] wrote {tsv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
