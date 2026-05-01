"""Z4 / beta2740 — bench timing breakdown analyzer.

bench JSON 의 elapsed (full pipeline) 외 stage 별 timing (analyzer/preprocess/
generator/evaluator) 가 있을 경우 → fraction 분석. 어느 stage 가 bottleneck 인지.

Usage:
    python3 scripts/bench_timing_breakdown.py result.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


# 알려진 timing 필드 (bench script 들에서 사용).
STAGE_FIELDS = [
    "analyzer_s", "preprocessor_s", "strategist_s",
    "generator_s", "evaluator_s",
    "tier_elapsed", "stage_repair_s", "stage_remesh_s",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path)
    ap.add_argument("--by-engine", action="store_true", help="engine 별 평균")
    args = ap.parse_args()

    if not args.input.exists():
        print(f"[ERR] missing: {args.input}", file=sys.stderr)
        return 1

    rows = json.loads(args.input.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        print("[ERR] not list", file=sys.stderr)
        return 2

    n = len(rows)

    # 어떤 timing 필드가 등장하는지 detect.
    seen_stages: set[str] = set()
    for r in rows:
        if not isinstance(r, dict):
            continue
        for k in r:
            if k in STAGE_FIELDS or k.endswith("_s"):
                v = r.get(k)
                if isinstance(v, (int, float)):
                    seen_stages.add(k)

    print(f"\n=== bench timing breakdown ({n} rows) ===\n")
    print(f"detected stages: {sorted(seen_stages) or '(none)'}")

    if not seen_stages:
        # fallback: just total elapsed.
        avg = sum(float(r.get("elapsed", 0)) for r in rows) / max(n, 1)
        print(f"\n  avg elapsed (total): {avg:.3f}s")
        return 0

    # average per stage.
    print(f"\n  --- avg per stage ---")
    for stage in sorted(seen_stages):
        vs = [float(r.get(stage, 0)) for r in rows
              if isinstance(r, dict) and isinstance(r.get(stage), (int, float))]
        if vs:
            avg = sum(vs) / len(vs)
            print(f"    {stage:<26}  avg={avg:8.4f}s  n={len(vs)}")

    if args.by_engine:
        engines = sorted({r.get("engine", "?") for r in rows if isinstance(r, dict)})
        print(f"\n  --- by engine ---")
        for e in engines:
            erows = [r for r in rows if isinstance(r, dict) and r.get("engine") == e]
            if not erows:
                continue
            avg_t = sum(float(r.get("elapsed", 0)) for r in erows) / len(erows)
            print(f"    {e:<24}  n={len(erows):<3}  avg_elapsed={avg_t:6.3f}s")
            for stage in sorted(seen_stages):
                vs = [float(r.get(stage, 0)) for r in erows
                      if isinstance(r.get(stage), (int, float))]
                if vs:
                    avg = sum(vs) / len(vs)
                    print(f"      {stage:<22}  {avg:6.3f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
