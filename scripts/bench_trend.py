"""W4 / beta2719 — bench A→B trend analyzer.

두 bench JSON 결과 (before / after) 의 grade A 카운트 + elapsed 평균 변화.
commit 별 regression / 개선 효과 정량 측정.

Usage:
    python3 scripts/bench_trend.py before.json after.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _summarize(rows: list[dict]) -> dict:
    n = len(rows)
    n_ok = sum(1 for r in rows if r.get("success"))
    n_a = sum(1 for r in rows if r.get("grade") == "A")
    n_b = sum(1 for r in rows if r.get("grade") == "B")
    n_c = sum(1 for r in rows if r.get("grade") == "C")
    avg_t = (
        sum(float(r.get("elapsed", 0)) for r in rows if r.get("success"))
        / max(n_ok, 1)
    )
    by_engine: dict[str, dict] = {}
    for r in rows:
        e = str(r.get("engine", "?"))
        if e not in by_engine:
            by_engine[e] = {"total": 0, "A": 0, "ok": 0, "elapsed_sum": 0.0}
        by_engine[e]["total"] += 1
        if r.get("success"):
            by_engine[e]["ok"] += 1
            by_engine[e]["elapsed_sum"] += float(r.get("elapsed", 0))
        if r.get("grade") == "A":
            by_engine[e]["A"] += 1
    return {
        "n": n, "ok": n_ok, "A": n_a, "B": n_b, "C": n_c,
        "avg_elapsed": round(avg_t, 3),
        "by_engine": by_engine,
    }


def _delta(a: dict, b: dict, key: str) -> str:
    av, bv = a.get(key, 0), b.get(key, 0)
    if isinstance(av, (int, float)) and isinstance(bv, (int, float)):
        d = bv - av
        return f"{av} → {bv} ({d:+})"
    return f"{av} → {bv}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("before", type=Path)
    ap.add_argument("after", type=Path)
    args = ap.parse_args()

    if not args.before.exists() or not args.after.exists():
        print(f"[ERR] missing input", file=sys.stderr)
        return 1

    a_rows = json.loads(args.before.read_text())
    b_rows = json.loads(args.after.read_text())
    if not isinstance(a_rows, list) or not isinstance(b_rows, list):
        print(f"[ERR] not list", file=sys.stderr)
        return 2

    a = _summarize(a_rows)
    b = _summarize(b_rows)

    print(f"\n=== bench trend ===")
    print(f"  total:    {_delta(a, b, 'n')}")
    print(f"  success:  {_delta(a, b, 'ok')}")
    print(f"  grade A:  {_delta(a, b, 'A')}")
    print(f"  grade B:  {_delta(a, b, 'B')}")
    print(f"  grade C:  {_delta(a, b, 'C')}")
    print(f"  avg_elapsed:  {a['avg_elapsed']}s → {b['avg_elapsed']}s "
          f"({(b['avg_elapsed'] - a['avg_elapsed']):+.3f}s)")

    print(f"\n  --- per engine ---")
    engines = sorted(set(a["by_engine"]) | set(b["by_engine"]))
    for e in engines:
        ae = a["by_engine"].get(e, {"A": 0, "ok": 0, "total": 0})
        be = b["by_engine"].get(e, {"A": 0, "ok": 0, "total": 0})
        d_a = be["A"] - ae["A"]
        sign = "+" if d_a > 0 else ("=" if d_a == 0 else "")
        print(f"    {e:<18}  A:{ae['A']:>2}/{ae['total']:<2} → "
              f"{be['A']:>2}/{be['total']:<2} ({sign}{d_a})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
