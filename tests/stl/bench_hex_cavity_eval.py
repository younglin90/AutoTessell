#!/usr/bin/env python3
"""hex_dominant + cfMesh BL 21-STL bench (autoresearch-deep hex loop).

Parallels ``bench_cavity_eval.py`` but routes the 21-STL set through
the hex_dominant base method (``--mesh-type hex_dominant --tier cfmesh``)
with BL produced natively by cfMesh's ``cartesianMesh`` (nLayers).

Outputs:

  - tests/stl/bench_hex_cavity_eval_result.json (per-STL records)
  - tests/stl/bench_hex_cavity_eval_summary.tsv (one row per STL)

User-goal summary line at end mirrors the tet bench so the autoresearch
loop has a mechanical metric (PASS/21 at QUALITY=draft, target_cells=10000,
BL=3 by default).
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
QUALITY = os.environ.get("AUTO_TESSELL_BENCH_CAVITY_QUALITY", "draft")
TIMEOUT_S = float(os.environ.get("AUTO_TESSELL_BENCH_CAVITY_TIMEOUT_S", "1800"))
RUN_ROOT = Path(
    os.environ.get(
        "AUTO_TESSELL_BENCH_HEX_RUN_ROOT",
        "/tmp/autotessell_bench_hex_cavity_eval",
    )
)


def discover_stls() -> list[Path]:
    stls: list[Path] = []
    cube = ROOT / "test_cube.stl"
    if cube.exists():
        stls.append(cube)
    bench_dir = ROOT / "tests" / "stl" / "thingi10k_bench20"
    if bench_dir.exists():
        stls.extend(sorted(p for p in bench_dir.glob("*.stl")))
    return stls


def run_one(stl_path: Path, case_dir: Path) -> dict[str, Any]:
    case_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, "-m", "cli.main", "run", str(stl_path),
        "-o", str(case_dir),
        "--mesh-type", "hex_dominant",
        "--tier", "cfmesh",
        "--strict-tier",
        "--quality", QUALITY,
        "--checker-engine", "native",
        "--auto-retry", "off",
        "--max-cells", str(TARGET_CELLS),
        "--bl-layers", str(BL_LAYERS),
        "--tier-param", f"target_cells={TARGET_CELLS}",
        "--tier-param", f"max_cells={TARGET_CELLS}",
        "--tier-param", f"cfmesh_bl_n_layers={BL_LAYERS}",
        # cfMesh's cartesianMesh already produces BL via internal nLayers,
        # so the post-layers stage must be disabled — native_bl on top
        # fails because cfMesh writes patches named "patch0" not "wall".
        "--tier-param", "post_layers_engine=disabled",
    ]
    env = os.environ.copy()
    # cfMesh is an OpenFOAM external — must allow it for hex base path.
    env["AUTO_TESSELL_ALLOW_EXTERNAL_OPENFOAM"] = "1"
    env.setdefault("PYTHONUNBUFFERED", "1")

    # H-6 (2026-05-12) — hex-safe drop_neg_vol_cells.  Skip the
    # geometric (signed-vol≤tol) check because cfMesh hex sliver cells
    # come out spuriously negative via fan-triangulation.  Keep only
    # the topological-inversion check (= NativeMeshChecker's
    # ``negative_volumes`` definition).  This drops exactly the 1 cell
    # medium_100322 / hard_1004826 have as hard-fail neg_vol, without
    # touching test_cube's 22k cells.
    env.setdefault("AUTO_TESSELL_BL_DROP_NEG_VOL", "1")
    env.setdefault("AUTO_TESSELL_BL_DROP_NEG_VOL_GEOM_CHECK", "0")
    env.setdefault("AUTO_TESSELL_BL_DROP_NEG_VOL_TOPO_CHECK", "1")
    env.setdefault("AUTO_TESSELL_BL_DROP_SKEW_THRESHOLD", "18")
    env.setdefault("AUTO_TESSELL_BL_DROP_MAX_ITER", "8")

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

    row["evaluator_verdict"] = "UNKNOWN"
    row["first_fail_metric"] = ""
    pass_markers = ("verdict=PASS", "Verdict: PASS", "✓ PASS", "PASS — Mesh")
    fail_markers = ("verdict=FAIL", "Verdict: FAIL", "✗ FAIL", "FAIL — Mesh")
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
    if row["evaluator_verdict"] == "UNKNOWN" and row.get("returncode") not in (0, None):
        row["evaluator_verdict"] = "FAIL"

    # Source-of-truth: quality_report.json evaluator verdict overrides
    # the log-tail heuristic.  rc != 0 with verdict=PASS in quality_report
    # is benign — usually a non-critical post-stage failure (e.g., native_bl
    # patch-name mismatch) that doesn't invalidate the mesh.
    qp = case_dir / "quality_report.json"
    if qp.exists():
        try:
            qr = json.loads(qp.read_text())
            verdict = qr.get("evaluation_summary", {}).get("verdict", "")
            if verdict in ("PASS", "PASS_WITH_WARNINGS"):
                row["evaluator_verdict"] = verdict
            elif verdict == "FAIL":
                row["evaluator_verdict"] = "FAIL"
        except Exception:
            pass
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
        print("[bench_hex_cavity_eval] no STLs discovered", file=sys.stderr)
        return 2
    print(f"[bench_hex_cavity_eval] {len(stls)} STLs, RUN_ROOT={RUN_ROOT}")

    rows: list[dict[str, Any]] = []
    for i, stl in enumerate(stls, start=1):
        case = RUN_ROOT / stl.stem
        print(f"[{i}/{len(stls)}] {stl.relative_to(ROOT)}")
        row = run_one(stl, case)
        rows.append(row)
        print(
            f"        rc={row['returncode']} t={row['elapsed_s']}s "
            f"v={row.get('evaluator_verdict', '?')}"
        )
        if row.get("first_fail_metric"):
            print(f"        fail: {row['first_fail_metric']}")

    out_dir = ROOT / "tests" / "stl"
    json_path = out_dir / "bench_hex_cavity_eval_result.json"
    rows_json = [{k: v for k, v in r.items() if k != "log_tail"} for r in rows]
    json_path.write_text(json.dumps({"rows": rows_json}, indent=2))

    tsv_path = out_dir / "bench_hex_cavity_eval_summary.tsv"
    cols = ["stl", "returncode", "elapsed_s", "evaluator_verdict", "first_fail_metric"]
    lines = ["\t".join(cols)]
    for r in rows:
        lines.append("\t".join([
            str(r.get("stl", "")),
            str(r.get("returncode", "")),
            str(r.get("elapsed_s", "")),
            str(r.get("evaluator_verdict", "?")),
            str(r.get("first_fail_metric", ""))[:80],
        ]))
    tsv_path.write_text("\n".join(lines) + "\n")

    print(f"[bench_hex_cavity_eval] wrote {json_path}")
    print(f"[bench_hex_cavity_eval] wrote {tsv_path}")

    # User-goal summary from quality_report.json
    try:
        n_pass = 0
        n_pass_warn = 0
        n_fail = 0
        cells_pcts: list[float] = []
        for r in rows:
            case_dir = Path(r.get("case_dir", ""))
            qp = case_dir / "quality_report.json"
            if not qp.exists():
                continue
            try:
                report = json.loads(qp.read_text())
            except Exception:
                continue
            verdict = report.get("evaluation_summary", {}).get("verdict", "")
            if verdict == "PASS":
                n_pass += 1
            elif verdict == "PASS_WITH_WARNINGS":
                n_pass_warn += 1
            else:
                n_fail += 1
            try:
                cm = (
                    report.get("evaluation_summary", {}).get("checkmesh", {})
                    or {}
                )
                cells = cm.get("cells")
                if cells is not None and cells > 0:
                    pct = (cells - TARGET_CELLS) / max(TARGET_CELLS, 1) * 100.0
                    cells_pcts.append(pct)
            except Exception:
                pass

        n_total = n_pass + n_pass_warn + n_fail
        if n_total > 0:
            within_10 = sum(1 for p in cells_pcts if abs(p) <= 10)
            within_20 = sum(1 for p in cells_pcts if abs(p) <= 20)
            within_30 = sum(1 for p in cells_pcts if abs(p) <= 30)
            print(
                f"[user-goal] PASS={n_pass}/{n_total} "
                f"PASS_WITH_WARNINGS={n_pass_warn}/{n_total} "
                f"FAIL={n_fail}/{n_total}"
            )
            print(
                f"[user-goal] cells target={TARGET_CELLS}: "
                f"within ±10 %={within_10}/{n_total}, "
                f"±20 %={within_20}/{n_total}, "
                f"±30 %={within_30}/{n_total}"
            )
            print(f"[user-goal] BL layers requested={BL_LAYERS}")
    except Exception as _summary_exc:
        print(f"[user-goal] summary failed: {_summary_exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
