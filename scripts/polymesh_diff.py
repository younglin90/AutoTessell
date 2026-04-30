"""L5 / beta2644 — polyMesh diff utility.

두 polyMesh 비교: vertex count / face count / cell count / file sizes.
디버깅용 — A vs B mesh 의 toplogy 변화 빠른 점검.

Usage:
    python3 scripts/polymesh_diff.py case_A/constant/polyMesh case_B/constant/polyMesh
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _count_lines(p: Path) -> int:
    if not p.exists():
        return 0
    try:
        return sum(1 for _ in p.open(encoding="utf-8", errors="replace"))
    except Exception:
        return 0


def _summarize_pm(pm_dir: Path) -> dict:
    out: dict = {"path": str(pm_dir)}
    files = ("points", "faces", "owner", "neighbour", "boundary")
    for fname in files:
        fpath = pm_dir / fname
        out[f"{fname}_lines"] = _count_lines(fpath)
        out[f"{fname}_bytes"] = fpath.stat().st_size if fpath.exists() else 0
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("a", type=Path, help="polyMesh A 디렉터리")
    ap.add_argument("b", type=Path, help="polyMesh B 디렉터리")
    args = ap.parse_args()

    if not args.a.exists() or not args.b.exists():
        print(f"[ERR] dir not found: {args.a} or {args.b}", file=sys.stderr)
        return 1

    sa = _summarize_pm(args.a)
    sb = _summarize_pm(args.b)

    print(f"\n[polyMesh DIFF]")
    print(f"  A: {args.a}")
    print(f"  B: {args.b}\n")

    files = ("points", "faces", "owner", "neighbour", "boundary")
    print(f"{'file':12} {'A lines':>10} {'B lines':>10} {'Δ lines':>10} "
          f"{'A bytes':>12} {'B bytes':>12} {'Δ bytes':>12}")
    print("-" * 84)
    for fname in files:
        la = sa[f"{fname}_lines"]
        lb = sb[f"{fname}_lines"]
        ba = sa[f"{fname}_bytes"]
        bb = sb[f"{fname}_bytes"]
        print(
            f"{fname:12} {la:>10,} {lb:>10,} {lb - la:>+10,} "
            f"{ba:>12,} {bb:>12,} {bb - ba:>+12,}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
