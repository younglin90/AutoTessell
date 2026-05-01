"""CC4 / beta2761 — bench result dedupe merger.

여러 JSON 결과 → 동일 (engine, stl) row 가 있을 때 latest (또는 best) 선택.
시계열 / re-run 결과 통합 후 평가.

Usage:
    python3 scripts/bench_dedupe.py *.json -o merged.json --keep latest
    python3 scripts/bench_dedupe.py *.json -o merged.json --keep best  # grade A 우선
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


GRADE_ORDER = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0, "?": -1, "": -1}


def _key(r: dict) -> tuple[str, str]:
    return (str(r.get("engine", "?")), str(r.get("stl", "?")))


def _is_better(new: dict, old: dict) -> bool:
    """grade 우선, 같으면 elapsed 짧은 게 우선."""
    g_new = GRADE_ORDER.get(str(new.get("grade", "")), -1)
    g_old = GRADE_ORDER.get(str(old.get("grade", "")), -1)
    if g_new != g_old:
        return g_new > g_old
    return float(new.get("elapsed", float("inf"))) < float(old.get("elapsed", float("inf")))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+", type=Path)
    ap.add_argument("-o", "--output", type=Path, required=True)
    ap.add_argument("--keep", choices=["latest", "best"], default="latest")
    args = ap.parse_args()

    merged: dict[tuple[str, str], dict] = {}
    n_in = 0
    n_dup = 0

    for p in args.inputs:
        if not p.exists():
            print(f"[WARN] missing: {p}", file=sys.stderr)
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[WARN] parse {p}: {exc}", file=sys.stderr)
            continue
        if not isinstance(data, list):
            continue

        for r in data:
            if not isinstance(r, dict):
                continue
            n_in += 1
            k = _key(r)
            if k not in merged:
                merged[k] = r
                continue
            n_dup += 1
            if args.keep == "latest":
                merged[k] = r
            else:  # best.
                if _is_better(r, merged[k]):
                    merged[k] = r

    out_rows = list(merged.values())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out_rows, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"[OK] in={n_in} duplicates={n_dup} out={len(out_rows)} → {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
