"""T4 / beta2698 — bench result aggregator (multi JSON merge).

여러 bench 실행 결과를 하나의 통합 보고서로 집계.
시계열 추적 / commit 별 비교에 활용.

Usage:
    python3 scripts/bench_aggregate.py run1.json run2.json run3.json -o agg.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+", type=Path)
    ap.add_argument("-o", "--output", type=Path, default=Path("aggregate.json"))
    args = ap.parse_args()

    if not args.inputs:
        print("[ERR] no inputs", file=sys.stderr)
        return 1

    all_results: list[dict] = []
    for p in args.inputs:
        if not p.exists():
            print(f"[WARN] missing: {p}")
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[WARN] parse {p}: {exc}")
            continue
        if not isinstance(data, list):
            print(f"[WARN] not a list: {p}")
            continue
        all_results.append({"file": str(p), "rows": data})

    # Per-file summary.
    summary: dict = {
        "n_files": len(all_results),
        "total_rows": sum(len(r["rows"]) for r in all_results),
        "files": [],
    }
    for r in all_results:
        rows = r["rows"]
        n_ok = sum(1 for x in rows if x.get("success"))
        n_a = sum(1 for x in rows if x.get("grade") == "A")
        n_total = len(rows)
        avg_t = (
            sum(float(x.get("elapsed", 0)) for x in rows if x.get("success")) / max(n_ok, 1)
        )
        summary["files"].append({
            "file": r["file"],
            "n_rows": n_total,
            "n_ok": n_ok,
            "n_grade_A": n_a,
            "avg_elapsed_s": round(avg_t, 3),
            "success_rate": round(n_ok / max(n_total, 1) * 100, 1),
        })

    # Cross-file engine comparison (각 file 의 engine 별 grade A 합).
    engines: set[str] = set()
    for r in all_results:
        for x in r["rows"]:
            engines.add(str(x.get("engine", "?")))
    cross: dict[str, dict] = {e: {} for e in engines}
    for r in all_results:
        fname = Path(r["file"]).stem
        for e in engines:
            n_a = sum(1 for x in r["rows"] if x.get("engine") == e and x.get("grade") == "A")
            cross[e][fname] = n_a
    summary["cross_engine"] = cross

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    # human-readable.
    print(f"\n=== bench aggregate ({len(all_results)} files, {summary['total_rows']} rows) ===\n")
    for f_info in summary["files"]:
        print(f"  {Path(f_info['file']).name:<40} ok={f_info['n_ok']}/{f_info['n_rows']} "
              f"A={f_info['n_grade_A']} avg={f_info['avg_elapsed_s']}s "
              f"({f_info['success_rate']}%)")
    print(f"\n[OK] saved → {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
