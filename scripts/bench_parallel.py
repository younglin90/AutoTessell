"""BB4 / beta2754 — bench multiple JSON files in parallel.

여러 결과 JSON 의 처리 (validate / aggregate / summary) 를 병렬 ThreadPool 로 실행.
single-threaded 처리 시 30+ 파일 오래 걸림 → 8 thread 로 단축.

Usage:
    python3 scripts/bench_parallel.py file1.json file2.json --task summary
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


def _summarize_one(path: Path) -> dict:
    """단일 파일 summary."""
    if not path.exists():
        return {"file": str(path), "error": "missing"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"file": str(path), "error": f"parse: {exc}"}
    if not isinstance(data, list):
        return {"file": str(path), "error": "not list"}
    n_ok = sum(1 for r in data if isinstance(r, dict) and r.get("success"))
    n_a = sum(1 for r in data if isinstance(r, dict) and r.get("grade") == "A")
    return {
        "file": str(path),
        "n_total": len(data),
        "n_ok": n_ok,
        "n_a": n_a,
    }


def _validate_one(path: Path) -> dict:
    """단일 파일 schema validate (BETA2706 활용)."""
    sys_path = Path(__file__).resolve().parents[1]
    if str(sys_path) not in sys.path:
        sys.path.insert(0, str(sys_path))
    from scripts.validate_bench_json import validate_file
    n_rows, n_err, _ = validate_file(path)
    return {"file": str(path), "n_rows": n_rows, "n_errors": n_err}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+", type=Path)
    ap.add_argument("--task", choices=["summary", "validate"], default="summary")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    fn = _summarize_one if args.task == "summary" else _validate_one

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(fn, p): p for p in args.inputs}
        for f in as_completed(futs):
            try:
                results.append(f.result())
            except Exception as exc:
                results.append({"file": str(futs[f]), "error": f"task: {exc}"})

    print(f"\n=== bench_parallel ({args.task}, {len(args.inputs)} files, workers={args.workers}) ===\n")
    for r in sorted(results, key=lambda r: r.get("file", "")):
        if "error" in r:
            print(f"  [ERR]  {Path(r['file']).name:<40} {r['error']}")
        elif args.task == "summary":
            print(f"  [OK]   {Path(r['file']).name:<40} "
                  f"n={r['n_total']:<4} ok={r['n_ok']:<4} A={r['n_a']}")
        else:
            tag = "OK" if r['n_errors'] == 0 else "ERR"
            print(f"  [{tag:>3}]  {Path(r['file']).name:<40} "
                  f"rows={r['n_rows']:<4} errors={r['n_errors']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
