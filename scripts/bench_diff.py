"""J7 / beta2632 — bench result diff script.

두 bench_difficulty_tiers_result.json 비교 → grade A 카운트, 평균 quality, time delta.

Usage:
    python3 scripts/bench_diff.py baseline.json current.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _summarize(rows: list[dict]) -> dict:
    """rows → tier × engine 별 통계 dict."""
    out: dict[tuple[str, str], dict] = {}
    for r in rows:
        key = (r.get("tier", "?"), r.get("engine", "?"))
        if key not in out:
            out[key] = {
                "n_total": 0, "n_ok": 0, "n_grade_A": 0, "n_bl_ok": 0,
                "sum_mq": 0.0, "sum_elapsed": 0.0,
            }
        s = out[key]
        s["n_total"] += 1
        if r.get("success"):
            s["n_ok"] += 1
            mq = r.get("mq")
            if mq is not None and mq >= 0:
                s["sum_mq"] += float(mq)
            s["sum_elapsed"] += float(r.get("elapsed", 0))
        if r.get("grade") == "A":
            s["n_grade_A"] += 1
        if r.get("bl_success"):
            s["n_bl_ok"] += 1
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("baseline", type=Path, help="baseline JSON")
    ap.add_argument("current", type=Path, help="current JSON")
    args = ap.parse_args()

    if not args.baseline.exists():
        print(f"[ERR] baseline not found: {args.baseline}", file=sys.stderr)
        return 1
    if not args.current.exists():
        print(f"[ERR] current not found: {args.current}", file=sys.stderr)
        return 2

    base = json.loads(args.baseline.read_text(encoding="utf-8"))
    curr = json.loads(args.current.read_text(encoding="utf-8"))

    base_sum = _summarize(base)
    curr_sum = _summarize(curr)

    keys = sorted(set(base_sum) | set(curr_sum))

    print(f"\n{'='*78}")
    print(f"BENCH DIFF: {args.baseline.name} → {args.current.name}")
    print(f"{'='*78}")
    print(
        f"{'tier':10} {'engine':6} | "
        f"{'OK base/curr':12} {'A base/curr':12} {'BL base/curr':12} "
        f"{'mean Q Δ':>10} {'elapsed Δ':>10}"
    )
    print("-" * 78)

    total_a_base = 0
    total_a_curr = 0

    for tier, engine in keys:
        b = base_sum.get((tier, engine))
        c = curr_sum.get((tier, engine))
        if b is None:
            b = {"n_total": 0, "n_ok": 0, "n_grade_A": 0, "n_bl_ok": 0,
                 "sum_mq": 0.0, "sum_elapsed": 0.0}
        if c is None:
            c = {"n_total": 0, "n_ok": 0, "n_grade_A": 0, "n_bl_ok": 0,
                 "sum_mq": 0.0, "sum_elapsed": 0.0}
        b_n_ok = b["n_ok"]
        c_n_ok = c["n_ok"]
        b_a = b["n_grade_A"]
        c_a = c["n_grade_A"]
        b_bl = b["n_bl_ok"]
        c_bl = c["n_bl_ok"]

        b_mq = b["sum_mq"] / max(b_n_ok, 1)
        c_mq = c["sum_mq"] / max(c_n_ok, 1)
        d_mq = c_mq - b_mq

        b_t = b["sum_elapsed"] / max(b_n_ok, 1)
        c_t = c["sum_elapsed"] / max(c_n_ok, 1)
        d_t = c_t - b_t

        total_a_base += b_a
        total_a_curr += c_a

        ok_str = f"{b_n_ok}/{b['n_total']}→{c_n_ok}/{c['n_total']}"
        a_str = f"{b_a}→{c_a}"
        bl_str = f"{b_bl}→{c_bl}"
        print(
            f"{tier:10} {engine:6} | {ok_str:12} {a_str:12} {bl_str:12} "
            f"{d_mq:+10.4f} {d_t:+10.2f}"
        )

    print("-" * 78)
    print(f"TOTAL grade A: {total_a_base} → {total_a_curr} (Δ {total_a_curr - total_a_base:+d})")
    print(f"{'='*78}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
