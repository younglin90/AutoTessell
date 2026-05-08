"""Autoresearch verify — 21 STL (test_cube + thingi10k_bench20) bench.

각 STL 을 subprocess 로 격리 실행 (90s timeout). core dump 가 main 죽이지 않음.
incremental 로 결과 누적. 점수 = pass × 100 + bl_exact × 50.

stdout 마지막 줄 = score (높을수록 좋음).
"""
from __future__ import annotations
import os, sys, json, time, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUN_ONE = Path(__file__).parent / "run_one.py"
RESULTS_FILE = Path(__file__).parent / "last_results.json"
PER_STL_TIMEOUT = 90  # seconds


def _collect_stls() -> list[Path]:
    out: list[Path] = []
    test_cube = ROOT / "test_cube.stl"
    if test_cube.exists():
        out.append(test_cube)
    thingi = ROOT / "tests" / "stl" / "thingi10k_bench20"
    if thingi.exists():
        out.extend(sorted(thingi.glob("*.stl")))
    return out


def _run_one_subprocess(stl: Path, n_layers: int = 3) -> dict:
    """subprocess 로 STL 실행. timeout / crash / OOM 모두 catch."""
    default = {
        "stl": stl.name, "ok": False, "verdict": "TIMEOUT/CRASH",
        "n_cells": 0, "n_wall_faces": 0, "n_prism": 0, "bl_layers_actual": 0,
        "max_skew": 0.0, "max_non_ortho": 0.0, "max_aspect": 0.0,
        "elapsed": 0.0, "err": "",
    }
    cmd = [sys.executable, str(RUN_ONE), str(stl), str(n_layers)]
    t0 = time.time()
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=PER_STL_TIMEOUT,
            cwd=str(ROOT),
        )
        if proc.returncode != 0:
            default["err"] = f"rc={proc.returncode} {proc.stderr[-150:]}"
            default["verdict"] = "CRASH"
            default["elapsed"] = round(time.time() - t0, 1)
            return default
        # parse last JSON line of stdout
        for line in reversed(proc.stdout.strip().splitlines()):
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    pass
        default["err"] = "no_json_output"
        default["elapsed"] = round(time.time() - t0, 1)
        return default
    except subprocess.TimeoutExpired:
        default["err"] = f"timeout_{PER_STL_TIMEOUT}s"
        default["verdict"] = "TIMEOUT"
        default["elapsed"] = float(PER_STL_TIMEOUT)
        return default
    except Exception as exc:
        default["err"] = f"subproc_err: {exc}"[:200]
        default["elapsed"] = round(time.time() - t0, 1)
        return default


def main() -> int:
    stls = _collect_stls()
    if not stls:
        print("ERR: no STLs", file=sys.stderr)
        print(0.0)
        return 1
    n = len(stls)
    n_layers = 3
    pass_count = 0
    bl_exact_count = 0
    results: list[dict] = []
    print(f"\n{'idx':<3} {'STL':<33} {'verd':<6} {'cells':<7} {'BL':<3} {'skew':<6} {'no':<5} {'ar':<6} {'t':<5}", file=sys.stderr)
    print("-" * 80, file=sys.stderr)
    for i, stl in enumerate(stls):
        r = _run_one_subprocess(stl, n_layers)
        results.append(r)
        if r["ok"]:
            pass_count += 1
        if r["bl_layers_actual"] == n_layers:
            bl_exact_count += 1
        line = (
            f"{i+1:<3} {r['stl'][:32]:<33} {r['verdict'][:5]:<6} "
            f"{r['n_cells']:<7} {r['bl_layers_actual']:<3} "
            f"{r['max_skew']:<6.2f} {r['max_non_ortho']:<5.1f} "
            f"{r['max_aspect']:<6.1f} {r['elapsed']:<5.1f}"
        )
        if r["err"]:
            line += f" | {r['err'][:60]}"
        print(line, file=sys.stderr)
        # incremental save (in case loop is interrupted)
        RESULTS_FILE.write_text(json.dumps({
            "running": True, "i": i + 1, "total": n,
            "pass_count": pass_count, "bl_exact_count": bl_exact_count,
            "results": results,
        }, indent=2))

    score = pass_count * 100.0 + bl_exact_count * 50.0
    summary = {
        "n_total": n, "pass_count": pass_count, "bl_exact_count": bl_exact_count,
        "pass_rate_pct": round(pass_count / n * 100, 1),
        "bl_exact_rate_pct": round(bl_exact_count / n * 100, 1),
        "score": score,
    }
    print("\n" + "=" * 80, file=sys.stderr)
    print(json.dumps(summary, indent=2), file=sys.stderr)
    RESULTS_FILE.write_text(json.dumps({
        "running": False, "summary": summary, "results": results,
    }, indent=2))
    print(f"{score:.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
