"""Round 043 receipt-bound non-cube corpus probe.

This is an evidence runner, not a release test: refusals are printed with
their strict reason so a failed quality/authority gate cannot be hidden by a
pytest assertion or a count-tuning fallback.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

import numpy as np

from core.analyzer.file_reader import load_mesh
from core.generator.tier_native_tet import _runner


CASES = {
    "ellipsoid": Path("tests/benchmarks/sphere_watertight.stl"),
    "naca": Path("tests/benchmarks/naca0012.stl"),
    "duct": Path("tests/benchmarks/trimesh_duct.stl"),
}


def _receipt(points: np.ndarray, faces: np.ndarray, name: str, repeat: int) -> dict[str, object]:
    return {
        "accepted": True,
        "receipt_sealed": True,
        "runtime_route": "default_off",
        "receipt_digest": f"round043-{name}-{repeat}",
        "source_sha256": f"round043-source-{name}",
        "canonical_source_vertices": points.tolist(),
        "canonical_source_faces": faces.tolist(),
        "positive_bl_volume_partition_available": False,
        "interface_triangles": [
            {
                "source_face": str(index),
                "output_face": f"{name}-out-{index}",
                "triangle": triangle.tolist(),
                "feature": "smooth",
                "patch": "wall",
                "physical_group": "fluid-wall",
                "component": "tetra",
                "provenance": f"{name}-surface#{index}",
            }
            for index, triangle in enumerate(faces)
        ],
    }


def run_case(name: str, repeats: int) -> list[dict[str, object]]:
    mesh = load_mesh(CASES[name])
    points = np.asarray(mesh.vertices, dtype=np.float64)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    if name == "ellipsoid":
        points = points * np.asarray([1.6, 1.0, 0.7], dtype=np.float64)
    rows: list[dict[str, object]] = []
    for repeat in range(repeats):
        case_dir = Path(tempfile.mkdtemp(prefix=f"autotessell-043-{name}-{repeat}-"))
        try:
            result = _runner(
                points,
                faces,
                case_dir,
                input_config={"surface_receipt": _receipt(points, faces, name, repeat)},
                max_iter=1,
                seed_density=6,
            )
            rows.append(
                {
                    "name": name,
                    "repeat": repeat,
                    "source_vertices": int(points.shape[0]),
                    "source_faces": int(faces.shape[0]),
                    "success": bool(result.success),
                    "message": result.message,
                    "route": result.route,
                    "contract": result.contract,
                    "details": result.contract_details,
                    "case_dir": str(case_dir),
                }
            )
        except Exception as exc:  # evidence runner must preserve hard failure
            rows.append(
                {
                    "name": name,
                    "repeat": repeat,
                    "source_vertices": int(points.shape[0]),
                    "source_faces": int(faces.shape[0]),
                    "success": False,
                    "message": f"exception:{type(exc).__name__}:{exc}",
                    "case_dir": str(case_dir),
                }
            )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=sorted(CASES), default="all")
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    names = sorted(CASES) if args.case == "all" else [args.case]
    for name in names:
        for row in run_case(name, max(1, int(args.repeats))):
            print(json.dumps(row, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
