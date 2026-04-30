"""V5 / beta2713 — bench JSON → CSV exporter.

bench_difficulty_tiers / engine_matrix_bench 출력 JSON → flat CSV.
spreadsheet 분석 / pandas 입력 / regression 시계열.

Usage:
    python3 scripts/bench_json_to_csv.py result.json -o result.csv
    python3 scripts/bench_json_to_csv.py *.json -o all.csv  # multi-merge
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path


# 출력 컬럼 순서.
PRIORITY_COLS = [
    "stl", "engine", "tier", "grade", "elapsed", "success",
    "n_tets", "n_cells", "n_vertices",
    "skewness_max", "non_ortho_max", "aspect_max",
]


def collect_rows(paths: list[Path]) -> list[dict]:
    rows: list[dict] = []
    for p in paths:
        if not p.exists():
            print(f"[WARN] missing: {p}", file=sys.stderr)
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[WARN] parse {p}: {exc}", file=sys.stderr)
            continue
        if not isinstance(data, list):
            print(f"[WARN] {p}: top-level not list", file=sys.stderr)
            continue
        for r in data:
            if isinstance(r, dict):
                r["_source_file"] = p.name
                rows.append(r)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+", type=Path)
    ap.add_argument("-o", "--output", type=Path, default=Path("bench.csv"))
    ap.add_argument("--cols", type=str, default=None,
                    help="comma-separated columns (default: priority + extras)")
    args = ap.parse_args()

    rows = collect_rows(args.inputs)
    if not rows:
        print("[ERR] no rows", file=sys.stderr)
        return 1

    # determine columns.
    if args.cols:
        cols = [c.strip() for c in args.cols.split(",")]
    else:
        # union of keys across all rows, priority first.
        all_keys: set[str] = set()
        for r in rows:
            all_keys.update(r.keys())
        cols = [c for c in PRIORITY_COLS if c in all_keys]
        extras = sorted(all_keys - set(cols) - {"_source_file"})
        cols.extend(extras)
        cols.append("_source_file")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            # flatten any nested dict to JSON string.
            flat = {}
            for k, v in r.items():
                if isinstance(v, (dict, list)):
                    flat[k] = json.dumps(v, ensure_ascii=False)
                else:
                    flat[k] = v
            w.writerow(flat)

    print(f"[OK] {len(rows)} rows × {len(cols)} cols → {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
