#!/usr/bin/env python3
"""Persist one bounded Native Poly complex release diagnostic receipt."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path

import numpy as np

from core.analyzer.readers import read_stl
from core.generator.tier_native_poly import _runner


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    source = root / "tests/benchmarks/sphere_watertight.stl"
    output = root / "docs/qa/rounds/native-all-production-gate-011/complex-diagnostic"
    output.mkdir(parents=True, exist_ok=True)
    mesh = read_stl(source)
    result = _runner(
        np.asarray(mesh.vertices),
        np.asarray(mesh.faces),
        output / "case",
        release_route=True,
        source_path=source,
        max_iter=1,
    )
    payload = asdict(result) if is_dataclass(result) else vars(result)
    payload["source"] = str(source)
    payload["output"] = str(output / "case")
    (output / "result.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
