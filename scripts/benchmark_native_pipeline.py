"""Record repeatable native-engine E2E benchmarks.

Usage:
    python3 scripts/benchmark_native_pipeline.py --cells 2000
    python3 scripts/benchmark_native_pipeline.py --only tet --cells 500
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CUBE = ROOT / "tests" / "benchmarks" / "cube.stl"
sys.path.insert(0, str(ROOT))

from core.pipeline.orchestrator import PipelineOrchestrator  # noqa: E402


def _commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def _record(
    name: str,
    mesh_type: str,
    tier_hint: str,
    cells: int,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix=f"autotessell_bench_{name}_") as directory:
        output = Path(directory) / "case"
        started = time.perf_counter()
        result = PipelineOrchestrator().run(
            CUBE,
            output,
            quality_level="draft",
            mesh_type=mesh_type,
            tier_hint=tier_hint,
            max_iterations=1,
            auto_retry="off",
            strict_tier=True,
            write_of_case=True,
            max_cells=cells,
            tier_specific_params={"max_cells": cells, "target_cells": cells},
        )
        elapsed = time.perf_counter() - started
        quality_path = output / "quality_report.json"
        report = json.loads(quality_path.read_text(encoding="utf-8")) if quality_path.exists() else {}
        summary = report.get("evaluation_summary", {})
        check = summary.get("checkmesh", {})
        return {
            "case": name,
            "mesh_type": mesh_type,
            "tier_hint": tier_hint,
            "requested_cells": cells,
            "success": bool(result.success),
            "elapsed_seconds": round(elapsed, 6),
            "verdict": summary.get("verdict"),
            "tier": summary.get("tier_evaluated"),
            "cells": check.get("cells"),
            "points": check.get("points"),
            "negative_volumes": check.get("negative_volumes"),
            "max_non_orthogonality": check.get("max_non_orthogonality"),
            "max_skewness": check.get("max_skewness"),
            "error": result.error,
        }


def _write_records(output_dir: Path, records: list[dict[str, Any]]) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    payload = {
        "timestamp_utc": stamp,
        "commit": _commit(),
        "records": records,
    }
    json_path = output_dir / f"native_pipeline_{stamp}.json"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    csv_path = output_dir / "native_pipeline_history.csv"
    rows = [{"timestamp_utc": stamp, "commit": payload["commit"], **record} for record in records]
    exists = csv_path.exists()
    with csv_path.open("a", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        if not exists:
            writer.writeheader()
        writer.writerows(rows)
    return json_path, csv_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cells", type=int, default=2000)
    parser.add_argument("--only", choices=("tet", "hex", "poly"))
    parser.add_argument("--output-dir", type=Path, default=ROOT / "harness" / "benchmarks")
    args = parser.parse_args()
    cases = {
        "tet": ("tet", "native_tet"),
        "hex": ("hex_dominant", "native_hex"),
        "poly": ("poly", "native_poly"),
    }
    selected = [args.only] if args.only else list(cases)
    records = [_record(name, *cases[name], args.cells) for name in selected]
    json_path, csv_path = _write_records(args.output_dir, records)
    print(json.dumps({"json": str(json_path), "csv": str(csv_path), "records": records}, sort_keys=True))
    return 0 if all(record["success"] for record in records) else 1


if __name__ == "__main__":
    raise SystemExit(main())
