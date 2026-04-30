"""U5 / beta2706 — bench .json schema validator.

bench_difficulty_tiers.py / engine_matrix_bench.py 출력 JSON 의 row schema 검증.
필드 누락 / 타입 mismatch / 값 범위 벗어남 탐지.

Usage:
    python3 scripts/validate_bench_json.py result.json [more.json ...]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


# 권장 schema. row 가 dict 일 때 검사.
EXPECTED_FIELDS = {
    # field_name : (type, required, value_check_fn or None)
    "engine": (str, True, None),
    "stl": (str, False, None),
    "elapsed": ((int, float), False, lambda v: v >= 0),
    "success": (bool, False, None),
    "grade": (str, False, lambda v: v in {"A", "B", "C", "D", "F", "?", ""}),
    "n_tets": (int, False, lambda v: v >= 0),
    "n_cells": (int, False, lambda v: v >= 0),
}


def validate_row(row: dict, idx: int) -> list[str]:
    errs: list[str] = []
    if not isinstance(row, dict):
        errs.append(f"row[{idx}] not dict")
        return errs
    for fname, (ftype, required, vcheck) in EXPECTED_FIELDS.items():
        if fname not in row:
            if required:
                errs.append(f"row[{idx}] missing required field '{fname}'")
            continue
        v = row[fname]
        if not isinstance(v, ftype):
            errs.append(
                f"row[{idx}] '{fname}' type {type(v).__name__} not "
                f"{ftype if isinstance(ftype, type) else [t.__name__ for t in ftype]}"
            )
            continue
        if vcheck is not None:
            try:
                if not vcheck(v):
                    errs.append(f"row[{idx}] '{fname}'={v!r} failed value check")
            except Exception as exc:
                errs.append(f"row[{idx}] '{fname}' check raised: {exc}")
    return errs


def validate_file(path: Path) -> tuple[int, int, list[str]]:
    """returns (n_rows, n_errors, error_messages)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return 0, 1, [f"{path}: parse error: {exc}"]

    if not isinstance(data, list):
        return 0, 1, [f"{path}: top-level not list (got {type(data).__name__})"]

    all_errs: list[str] = []
    for i, row in enumerate(data):
        all_errs.extend(validate_row(row, i))
    return len(data), len(all_errs), all_errs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+", type=Path)
    ap.add_argument("--max-show", type=int, default=20,
                    help="show first N errors per file (default: 20)")
    args = ap.parse_args()

    total_rows = 0
    total_errs = 0
    n_clean_files = 0

    print(f"\n=== validate_bench_json ({len(args.inputs)} files) ===\n")
    for p in args.inputs:
        if not p.exists():
            print(f"  [MISS] {p}")
            total_errs += 1
            continue
        n_rows, n_err, errs = validate_file(p)
        total_rows += n_rows
        total_errs += n_err
        tag = "OK" if n_err == 0 else "ERR"
        print(f"  [{tag:>3}] {p.name:<40} rows={n_rows} errors={n_err}")
        if n_err == 0:
            n_clean_files += 1
        else:
            for e in errs[: args.max_show]:
                print(f"        {e}")
            if len(errs) > args.max_show:
                print(f"        ... +{len(errs) - args.max_show} more")

    print(f"\n--- summary: {n_clean_files}/{len(args.inputs)} clean, "
          f"{total_rows} rows, {total_errs} errors")
    return 0 if total_errs == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
