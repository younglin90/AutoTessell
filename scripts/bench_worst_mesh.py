"""DD4 / beta2788 — bench result 의 top-k worst mesh 추출.

bench JSON → grade D 또는 lowest-mq mesh K 개 추출 → 디버깅 / 회귀 우선순위.

Usage:
    python3 scripts/bench_worst_mesh.py result.json --top 5
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


GRADE_RANK = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0, "?": -1, "": -1}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path)
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--engine", default=None,
                    help="filter by engine (tet, hex, poly)")
    args = ap.parse_args()

    if not args.input.exists():
        print(f"[ERR] missing: {args.input}", file=sys.stderr)
        return 1

    rows = json.loads(args.input.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        print("[ERR] not list", file=sys.stderr)
        return 2

    # filter.
    if args.engine:
        rows = [r for r in rows
                if isinstance(r, dict) and r.get("engine") == args.engine]

    # rank: lower grade first, then lower mq, then higher elapsed.
    def _key(r):
        g = GRADE_RANK.get(str(r.get("grade", "?")), -1)
        mq = float(r.get("mq", 1.0))
        t = -float(r.get("elapsed", 0))
        return (g, mq, t)

    rows.sort(key=_key)
    worst = rows[: args.top]

    print(f"\n=== bench worst {len(worst)} mesh ===\n")
    cols = ["fid", "engine", "tier", "grade", "mq", "n_cells", "elapsed"]
    print("  " + "  ".join(f"{c:>10}" for c in cols))
    for r in worst:
        vals = [
            str(r.get("file_id", "-")),
            str(r.get("engine", "-")),
            str(r.get("tier", "-")),
            str(r.get("grade", "?")),
            f"{float(r.get('mq', -1)):.3f}" if "mq" in r else "-",
            str(r.get("n_cells", "-")),
            f"{float(r.get('elapsed', 0)):.1f}s",
        ]
        print("  " + "  ".join(f"{v:>10}" for v in vals))
    return 0


if __name__ == "__main__":
    sys.exit(main())
