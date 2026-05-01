"""AA4 / beta2747 — bench A vs B per-row diff CSV.

before/after JSON 의 동일 (engine, stl) 행 매칭 → grade/elapsed delta CSV.
regression detect / improvement quantification.

Usage:
    python3 scripts/bench_diff_csv.py before.json after.json -o diff.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path


def _key(r: dict) -> tuple[str, str]:
    return (str(r.get("engine", "?")), str(r.get("stl", "?")))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("before", type=Path)
    ap.add_argument("after", type=Path)
    ap.add_argument("-o", "--output", type=Path, default=Path("bench_diff.csv"))
    args = ap.parse_args()

    if not args.before.exists() or not args.after.exists():
        print("[ERR] missing input", file=sys.stderr)
        return 1

    a = json.loads(args.before.read_text(encoding="utf-8"))
    b = json.loads(args.after.read_text(encoding="utf-8"))
    if not isinstance(a, list) or not isinstance(b, list):
        print("[ERR] not list", file=sys.stderr)
        return 2

    a_map = {_key(r): r for r in a if isinstance(r, dict)}
    b_map = {_key(r): r for r in b if isinstance(r, dict)}

    keys = sorted(set(a_map) | set(b_map))

    rows = []
    n_improved = 0
    n_regressed = 0
    grade_order = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0, "?": -1, "": -1}

    for k in keys:
        ar = a_map.get(k)
        br = b_map.get(k)
        eng, stl = k
        ag = str(ar.get("grade", "")) if ar else ""
        bg = str(br.get("grade", "")) if br else ""
        ae = float(ar.get("elapsed", 0)) if ar else 0
        be = float(br.get("elapsed", 0)) if br else 0
        ag_o = grade_order.get(ag, -1)
        bg_o = grade_order.get(bg, -1)
        delta = bg_o - ag_o
        if delta > 0:
            n_improved += 1
        elif delta < 0:
            n_regressed += 1
        rows.append({
            "engine": eng,
            "stl": stl,
            "grade_a": ag,
            "grade_b": bg,
            "grade_delta": delta,
            "elapsed_a": ae,
            "elapsed_b": be,
            "elapsed_delta": be - ae,
            "in_a": ar is not None,
            "in_b": br is not None,
        })

    args.output.parent.mkdir(parents=True, exist_ok=True)
    cols = list(rows[0].keys()) if rows else []
    with args.output.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    print(f"[OK] {len(rows)} rows → {args.output}  "
          f"(improved={n_improved}, regressed={n_regressed})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
