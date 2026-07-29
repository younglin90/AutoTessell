"""TRI-OPERATOR-CORPUS-1 — guarded native-tri operator smoke corpus.

Runs one split→collapse→flip round with smoothing disabled on a compact
correctness corpus.  This is not a production tier: it measures whether the
transaction guards preserve finite non-degenerate faces and topology on
fixtures that the legacy L2 path already exposes as difficult.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.analyzer import topology  # noqa: E402
from core.analyzer.readers import read_stl  # noqa: E402
from core.preprocessor.native_tri.operator_loop import OperatorTransaction  # noqa: E402
from tests.stl.bench_native_tri import _nearest_distance  # noqa: E402


FIXTURES = (
    "tests/benchmarks/cube.stl",
    "tests/benchmarks/sphere.stl",
    "tests/benchmarks/cylinder.stl",
    "tests/benchmarks/very_thin_disk_0_01mm.stl",
    "tests/benchmarks/mixed_features_wing_with_spike.stl",
    "tests/benchmarks/extreme_aspect_ratio_needle.stl",
    "tests/benchmarks/multi_scale_sphere_with_micro_spikes.stl",
    "tests/benchmarks/high_genus_dual_torus.stl",
)


def _angles(vertices: np.ndarray, faces: np.ndarray) -> tuple[float, float]:
    values: list[float] = []
    for tri in vertices[faces]:
        p0, p1, p2 = tri
        for a, b in ((p1 - p0, p2 - p0), (p0 - p1, p2 - p1), (p0 - p2, p1 - p2)):
            denom = float(np.linalg.norm(a) * np.linalg.norm(b))
            if denom <= 1e-30:
                values.append(0.0)
            else:
                values.append(math.degrees(math.acos(float(np.clip(np.dot(a, b) / denom, -1.0, 1.0)))))
    return (min(values) if values else 0.0, max(values) if values else 0.0)


def measure(path: Path) -> dict[str, object]:
    mesh = read_stl(str(path))
    source_v = np.asarray(mesh.vertices, dtype=np.float64)
    source_f = np.asarray(mesh.faces, dtype=np.int64)
    lengths = np.concatenate(
        [
            np.linalg.norm(source_v[source_f[:, i]] - source_v[source_f[:, (i + 1) % 3]], axis=1)
            for i in range(3)
        ]
    )
    target = float(np.median(lengths[lengths > 0.0]))
    transaction = OperatorTransaction(source_v, source_f, target_edge_length=target)
    reports = transaction.run_one_round(target_edge_length=target, smooth=False)
    output_v = transaction.state.vertices
    output_f = transaction.state.faces
    tri = output_v[output_f] if len(output_f) else np.empty((0, 3, 3))
    doubled_area = np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1) if len(tri) else np.empty(0)
    accepted = sum(int(report.accepted) for report in reports)
    rejected = len(reports) - accepted
    return {
        "fixture": str(path.relative_to(ROOT)),
        "input_vertices": int(len(source_v)),
        "input_faces": int(len(source_f)),
        "output_vertices": int(len(output_v)),
        "output_faces": int(len(output_f)),
        "target_edge_length": target,
        "reports": len(reports),
        "accepted": accepted,
        "rejected": rejected,
        "manifold": bool(topology.is_manifold(output_f)),
        "watertight": bool(topology.is_watertight(output_f)),
        "finite": bool(np.isfinite(output_v).all() and np.isfinite(output_f).all()),
        "min_doubled_area": float(doubled_area.min()) if len(doubled_area) else 0.0,
        "min_angle_deg": _angles(output_v, output_f)[0],
        "max_angle_deg": _angles(output_v, output_f)[1],
        "sampled_vertex_hausdorff": max(
            _nearest_distance(source_v, output_v),
            _nearest_distance(output_v, source_v),
        ),
    }


def main() -> int:
    selected = tuple(sys.argv[1:]) or FIXTURES
    rows: list[dict[str, object]] = []
    for fixture in selected:
        path = Path(fixture)
        if not path.is_absolute():
            path = ROOT / path
        try:
            row = measure(path) if path.exists() else {"fixture": fixture, "status": "missing"}
        except Exception as exc:  # noqa: BLE001 — corpus diagnostic boundary
            row = {"fixture": fixture, "status": "engine_exception", "exception": type(exc).__name__ + ": " + str(exc)}
        else:
            row["status"] = "measured"
        rows.append(row)
        print(json.dumps(row, sort_keys=True), flush=True)
    output = ROOT / "tests" / "stl" / "tri_operator_corpus_20260727.json"
    output.write_text(json.dumps({"rows": rows}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
