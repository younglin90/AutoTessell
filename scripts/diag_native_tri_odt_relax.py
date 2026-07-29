"""Report-only A/B for the Dunyach sizing-aware ODT relocation target."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.analyzer.readers import read_stl  # noqa: E402
from core.preprocessor.native_tri import OperatorKind, OperatorTransaction  # noqa: E402


FIXTURES = (
    "cube.stl",
    "sphere.stl",
    "cylinder.stl",
)


def _min_angle(vertices: np.ndarray, faces: np.ndarray) -> float:
    values: list[float] = []
    for face in faces:
        tri = vertices[face]
        for i in range(3):
            a = tri[(i + 1) % 3] - tri[i]
            b = tri[(i + 2) % 3] - tri[i]
            denom = float(np.linalg.norm(a) * np.linalg.norm(b))
            if denom <= np.finfo(float).tiny:
                return 0.0
            values.append(float(np.degrees(np.arccos(np.clip(np.dot(a, b) / denom, -1.0, 1.0)))))
    return float(min(values)) if values else 0.0


def _run(path: Path, *, sizing_aware: bool) -> dict[str, object]:
    mesh = read_stl(path)
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    tx = OperatorTransaction(vertices, faces, curvature_epsilon=0.01)
    reports = tx.run_one_round(
        smooth=True,
        sizing_aware_relocation=sizing_aware,
    )
    result = trimesh.Trimesh(tx.state.vertices, tx.state.faces, process=False)
    return {
        "fixture": path.name,
        "sizing_aware": sizing_aware,
        "vertices": int(len(tx.state.vertices)),
        "faces": int(len(tx.state.faces)),
        "accepted_smooth": int(sum(report.operator is OperatorKind.SMOOTH and report.accepted for report in reports)),
        "min_angle_deg": _min_angle(tx.state.vertices, tx.state.faces),
        "finite": bool(np.isfinite(tx.state.vertices).all()),
        "manifold": bool(result.is_watertight and result.is_winding_consistent),
    }


def main() -> int:
    benchmark_dir = ROOT / "tests" / "benchmarks"
    rows: list[dict[str, object]] = []
    for fixture in FIXTURES:
        path = benchmark_dir / fixture
        for sizing_aware in (False, True):
            row = _run(path, sizing_aware=sizing_aware)
            rows.append(row)
            print(json.dumps(row, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
