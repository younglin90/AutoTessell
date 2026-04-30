"""X5 / beta2727 — bench summary CLI (high-level wrapper).

bench JSON 의 grade A/B/C/D 분포 + 엔진별 success rate + slowest 5 / fastest 5.
한 번에 보기 좋은 표.

Usage:
    python3 scripts/bench_summary.py result.json
    python3 scripts/bench_summary.py *.json --top 10
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _load_all(paths: list[Path]) -> list[dict]:
    rows: list[dict] = []
    for p in paths:
        if not p.exists():
            print(f"[WARN] missing: {p}", file=sys.stderr)
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[WARN] {p}: parse {exc}", file=sys.stderr)
            continue
        if isinstance(data, list):
            rows.extend(d for d in data if isinstance(d, dict))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+", type=Path)
    ap.add_argument("--top", type=int, default=5)
    args = ap.parse_args()

    rows = _load_all(args.inputs)
    if not rows:
        print("[ERR] no rows", file=sys.stderr)
        return 1

    n = len(rows)
    n_ok = sum(1 for r in rows if r.get("success"))
    grades = {g: 0 for g in ["A", "B", "C", "D", "F", "?", ""]}
    for r in rows:
        g = str(r.get("grade", "?"))
        grades[g] = grades.get(g, 0) + 1

    print(f"\n=== bench_summary ({n} rows, {len(args.inputs)} files) ===\n")
    print(f"  total       {n}")
    print(f"  success     {n_ok} ({n_ok/max(n,1)*100:.1f}%)")
    print(f"  grade dist  ", " ".join(f"{g}:{c}" for g, c in grades.items() if c))

    # per engine.
    by_eng: dict[str, dict] = {}
    for r in rows:
        e = str(r.get("engine", "?"))
        if e not in by_eng:
            by_eng[e] = {"total": 0, "ok": 0, "A": 0, "elapsed_sum": 0.0}
        by_eng[e]["total"] += 1
        if r.get("success"):
            by_eng[e]["ok"] += 1
            by_eng[e]["elapsed_sum"] += float(r.get("elapsed", 0))
        if r.get("grade") == "A":
            by_eng[e]["A"] += 1

    print(f"\n  --- per engine ---")
    for e in sorted(by_eng):
        info = by_eng[e]
        rate = info["ok"] / max(info["total"], 1) * 100
        avg = info["elapsed_sum"] / max(info["ok"], 1)
        print(f"    {e:<22}  {info['ok']:>3}/{info['total']:<3} ok ({rate:5.1f}%)  "
              f"A={info['A']:<2}  avg={avg:6.2f}s")

    # top fastest / slowest.
    elapsed_rows = [(r, float(r.get("elapsed", 0))) for r in rows if r.get("success")]
    elapsed_rows.sort(key=lambda x: x[1])
    if elapsed_rows:
        print(f"\n  --- fastest {args.top} ---")
        for r, t in elapsed_rows[: args.top]:
            print(f"    {t:6.2f}s  {r.get('engine','?')} on {r.get('stl','?')}")
        print(f"\n  --- slowest {args.top} ---")
        for r, t in elapsed_rows[-args.top:][::-1]:
            print(f"    {t:6.2f}s  {r.get('engine','?')} on {r.get('stl','?')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
