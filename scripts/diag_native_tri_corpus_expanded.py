"""TRI-CORPUS-1 — expanded L2 baseline with per-fixture failure isolation.

This wrapper reuses the existing report-only ``bench_native_tri.measure``
function and catches one fixture at a time so an empty-face or non-manifold
failure cannot hide the remainder of the corpus.  It does not call the new
native-tri operator loop and does not change the L2 remesher.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.stl.bench_native_tri import measure  # noqa: E402


FIXTURES = (
    "tests/benchmarks/cube.stl",
    "tests/benchmarks/sphere.stl",
    "tests/benchmarks/cylinder.stl",
    "tests/benchmarks/very_thin_disk_0_01mm.stl",
    "tests/benchmarks/mixed_features_wing_with_spike.stl",
    "tests/benchmarks/extreme_aspect_ratio_needle.stl",
    "tests/benchmarks/many_small_features_perforated_plate.stl",
    "tests/benchmarks/multi_scale_sphere_with_micro_spikes.stl",
    "tests/benchmarks/sharp_features_micro_ridge.stl",
    "tests/benchmarks/high_genus_dual_torus.stl",
)


def main() -> int:
    rows: list[dict[str, object]] = []
    for fixture in FIXTURES:
        path = ROOT / fixture
        if not path.exists():
            rows.append({"fixture": fixture, "status": "missing"})
            continue
        try:
            row = measure(path, target_scale=1.0, iterations=2)
        except Exception as exc:  # noqa: BLE001 — corpus diagnostic boundary
            row = {
                "fixture": fixture,
                "status": "engine_exception",
                "exception_type": type(exc).__name__,
                "exception": str(exc),
            }
        else:
            row = {"status": "measured", **row}
        rows.append(row)
        print(json.dumps(row, sort_keys=True))
    payload = {"engine": "native_tri_phase0_l2_baseline", "rows": rows}
    output = ROOT / "tests" / "stl" / "tri_corpus_20260727.json"
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
