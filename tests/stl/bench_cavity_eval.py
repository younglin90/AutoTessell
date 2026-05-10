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
    # BLR-9c-d-g-3 — disable wildmesh tier fastpaths (structured box
    # / axis extrusion) so every STL routes through the main
    # native_bl pass.  Without this, geometries that look like a
    # constant-cross-section sweep emit a structured polyMesh with
    # its own ``native_bl_quality.json`` that bypasses the cavity
    # eval helpers entirely (see tier_wildmesh.py:1828, 1852).
    env["AUTO_TESSELL_WILDMESH_BOX_FASTPATH"] = "0"
    env["AUTO_TESSELL_WILDMESH_EXTRUSION_FASTPATH"] = "0"
    # BLR-9c-d-j-2 — non-ortho cap configurable; default to 80° to
    # match what downstream evaluators tolerate on transition cells
    # (the bench audit at 70° showed angles cluster in 70-90° band
    # without ever blowing past 90°).  Override via env to bench
    # other thresholds.
    env.setdefault(
        "AUTO_TESSELL_BL_TET_CAVITY_NON_ORTHO_DEG",
        os.environ.get("AUTO_TESSELL_BENCH_CAVITY_NON_ORTHO_DEG", "85"),
    )
    # BLR-9c-d-k-2 — Q-min cap configurable; default to 0.05 since
    # the BLR-9c-d-k-1 audit showed the rejected components cluster
    # in the [0.01, 0.1) range and only 2 of 51 fall below 0.01.
    env.setdefault(
        "AUTO_TESSELL_BL_TET_CAVITY_Q_MIN",
        os.environ.get("AUTO_TESSELL_BENCH_CAVITY_Q_MIN", "0.05"),
    )
    # BLR-9c-d-p-13 — anti-invert cap default ON for the bench so we
    # measure the new wall-vertex inversion guard's impact on the
    # 21-STL baseline.  Override via
    # ``AUTO_TESSELL_BENCH_ANTI_INVERT_CAP=0`` for A/B comparison.
    env.setdefault(
        "AUTO_TESSELL_BL_ANTI_INVERT_CAP",
        os.environ.get("AUTO_TESSELL_BENCH_ANTI_INVERT_CAP", "1"),
    )
    env.setdefault(
        "AUTO_TESSELL_BL_ANTI_INVERT_SAFETY",
        os.environ.get("AUTO_TESSELL_BENCH_ANTI_INVERT_SAFETY", "0.5"),
    )
    env.setdefault(
        "AUTO_TESSELL_BL_ANTI_INVERT_GLOBAL",
        os.environ.get("AUTO_TESSELL_BENCH_ANTI_INVERT_GLOBAL", "1"),
    )
    # BLR-9c-d-s-1 sweep showed floor=0.5 fixes 2 cap-induced
    # aspect+surface_dev FAILs (extreme_1017014, extreme_102308) at
    # the cost of 1 regression (medium_100330) — net +1 PASS.
    env.setdefault(
        "AUTO_TESSELL_BL_ANTI_INVERT_FLOOR",
        os.environ.get("AUTO_TESSELL_BENCH_ANTI_INVERT_FLOOR", "0.5"),
    )
    env.setdefault("AUTO_TESSELL_P4C_PYTETWILD", "0")
    env.setdefault("AUTO_TESSELL_ALLOW_EXTERNAL_OPENFOAM", "0")
    env.setdefault("AUTO_TESSELL_LCR_OFF", "1")
    env.setdefault("PYTHONUNBUFFERED", "1")

    row: dict[str, Any] = {
        "stl": stl_path.relative_to(ROOT).as_posix(),
        "case_dir": str(case_dir),
    }
    start = time.perf_counter()
    log_tail = ""
    try:
        proc = subprocess.run(
            cmd, cwd=ROOT, env=env, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=TIMEOUT_S,
        )
        row["returncode"] = int(proc.returncode)
        log_tail = (proc.stdout or "")[-4000:]
    except subprocess.TimeoutExpired as exc:
        row["returncode"] = 124
        row["timeout"] = True
        log_tail = (exc.stdout if isinstance(exc.stdout, str) else "")[-4000:]
    row["elapsed_s"] = round(time.perf_counter() - start, 3)
    row["log_tail"] = log_tail
    # Extract the evaluator verdict + first failing metric (if any) from
    # the captured log so the bench summary surfaces the real reject
    # reason — separate from the cavity_eval read-only audit.
    row["evaluator_verdict"] = "UNKNOWN"
    row["first_fail_metric"] = ""
    # The Python orchestrator emits two complementary verdict markers:
    # ``verdict=PASS`` / ``verdict=FAIL`` from the structured logger
    # *and* a Rich-rendered `Verdict: PASS|FAIL` panel from the CLI.
    # Different STLs end up trimming the log_tail differently, so we
    # match either format and also check for the final ``✓ PASS``/``✗ FAIL``
    # CLI summary line.  Returncode is the ultimate fallback when no
    # verdict line survives the tail truncation.
    pass_markers = (
        "verdict=PASS", "Verdict: PASS", "✓ PASS", "PASS — Mesh"
    )
    fail_markers = (
        "verdict=FAIL", "Verdict: FAIL", "✗ FAIL", "FAIL — Mesh"
    )
    for line in log_tail.splitlines():
        if any(m in line for m in fail_markers):
            row["evaluator_verdict"] = "FAIL"
        elif (
            row["evaluator_verdict"] != "FAIL"
            and any(m in line for m in pass_markers)
        ):
            row["evaluator_verdict"] = "PASS"
        if " FAIL " in line and not row["first_fail_metric"]:
            stripped = line.strip()
            if (
                stripped.startswith("Max ")
                or stripped.startswith("Min ")
                or stripped.startswith("Avg ")
                or stripped.startswith("Hausdorff")
                or stripped.startswith("Negative")
            ):
                row["first_fail_metric"] = stripped[:120]
    # Fallback: if the log was truncated past every verdict marker but
    # the CLI returned non-zero, treat as FAIL (matches the orchestrator
    # exit-code contract).  rc=0 + UNKNOWN keeps the UNKNOWN label so the
    # bench reader knows to investigate.
    if row["evaluator_verdict"] == "UNKNOWN" and row.get("returncode") not in (0, None):
        row["evaluator_verdict"] = "FAIL"

    # Read native_bl_quality.json and extract tet_cavity_eval +
    # fastpath bypass markers.
    bl_qual_path = case_dir / "native_bl_quality.json"
    eval_block: dict[str, Any] = {}
    fastpath_block: dict[str, Any] | None = None
    anti_invert_block: dict[str, Any] = {}
    if bl_qual_path.exists():
        try:
            data = json.loads(bl_qual_path.read_text())
            eval_block = dict(data.get("tet_cavity_eval", {}))
            fastpath_block = data.get("fastpath")
            anti_invert_block = dict(data.get("anti_invert_cap", {}))
        except Exception as exc:  # noqa: BLE001
            eval_block = {"read_error": str(exc)[:160]}
    row["tet_cavity_eval"] = eval_block
    row["fastpath"] = fastpath_block
    row["anti_invert_cap"] = anti_invert_block
    if eval_block:
        row["bl_path"] = (
            "vd" if eval_block.get("writer_path") == "vd" else "main"
        )
    elif fastpath_block:
        row["bl_path"] = (
            f"fastpath:{fastpath_block.get('kind', 'unknown')}"
        )
    elif bl_qual_path.exists():
        row["bl_path"] = "main_no_eval_block"
    else:
        row["bl_path"] = "missing_quality_json"
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
        print(
            f"        rc={row['returncode']} t={row['elapsed_s']}s "
            f"path={row.get('bl_path', '?')} "
            f"v={row.get('evaluator_verdict', '?')} {decision_str}"
        )
        if row.get("first_fail_metric"):
            print(f"        fail: {row['first_fail_metric']}")

    out_dir = ROOT / "tests" / "stl"
    json_path = out_dir / "bench_cavity_eval_result.json"
    # Drop the verbose log_tail from the persisted JSON to keep the
    # file readable; per-STL stdout is reconstructable from the live
    # run if needed.
    rows_json = []
    for r in rows:
        rj = {k: v for k, v in r.items() if k != "log_tail"}
        rows_json.append(rj)
    json_path.write_text(json.dumps(
        {"totals": totals, "rows": rows_json}, indent=2,
    ))
    tsv_path = out_dir / "bench_cavity_eval_summary.tsv"
    cols = [
        "stl", "returncode", "elapsed_s", "bl_path",
        "evaluator_verdict", "first_fail_metric",
        "anti_invert_n_capped", "anti_invert_max_reduction",
        "n_components", "n_accepted",
        "n_rejected_uncovered_shell", "n_rejected_bad_det",
        "n_rejected_bad_shape", "n_rejected_bad_non_ortho",
        "n_rejected_bad_skewness",
    ]
    lines = ["\t".join(cols)]
    for r in rows:
        ev = r.get("tet_cavity_eval") or {}
        ai = r.get("anti_invert_cap") or {}
        lines.append("\t".join([
            str(r.get("stl", "")),
            str(r.get("returncode", "")),
            str(r.get("elapsed_s", "")),
            str(r.get("bl_path", "?")),
            str(r.get("evaluator_verdict", "?")),
            str(r.get("first_fail_metric", ""))[:80],
            str(ai.get("n_capped", 0)),
            str(round(float(ai.get("max_reduction", 0.0)), 6)),
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
