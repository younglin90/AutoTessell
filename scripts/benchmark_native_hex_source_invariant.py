#!/usr/bin/env python3
"""Benchmark the native-hex source-surface invariant on mixed-scale input."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import tempfile
import time
from pathlib import Path

import numpy as np
import trimesh

from core.generator.native_hex.mesher import generate_native_hex

_POLYMESH_FILES = ("points", "faces", "owner", "neighbour", "boundary")
_PRE3_OFF_POINTS_SHA256 = "48828f117d68aa4d59691a0dabb9d5b4534df22991947153d2ac5c270b97f69a"


def _mixed_scale_surface() -> tuple[np.ndarray, np.ndarray]:
    surface = trimesh.creation.icosphere(subdivisions=5, radius=1.0)
    vertices = np.asarray(surface.vertices, dtype=np.float64).copy()
    faces = np.asarray(surface.faces, dtype=np.int64).copy()
    edge_a, edge_b = (int(index) for index in faces[0, :2])
    vertices[edge_b] = vertices[edge_a] + 1.0e-6 * (vertices[edge_b] - vertices[edge_a])
    return vertices, faces


def _hashes(case_dir: Path) -> dict[str, str]:
    poly_dir = case_dir / "constant" / "polyMesh"
    return {
        name: hashlib.sha256((poly_dir / name).read_bytes()).hexdigest() for name in _POLYMESH_FILES
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if args.repeats <= 0:
        parser.error("repeats must be positive")

    vertices, faces = _mixed_scale_surface()
    vertices_hash = hashlib.sha256(vertices.tobytes()).hexdigest()
    faces_hash = hashlib.sha256(faces.tobytes()).hexdigest()
    timings: list[float] = []
    output_hashes: list[dict[str, str]] = []
    result_signatures: list[tuple[object, ...]] = []

    for _ in range(args.repeats):
        with tempfile.TemporaryDirectory(prefix="hex-source-invariant-") as tmp:
            started = time.perf_counter()
            result = generate_native_hex(
                vertices,
                faces,
                Path(tmp),
                seed_density=6,
                max_cells_per_axis=8,
                snap_boundary=False,
            )
            timings.append(time.perf_counter() - started)
            if not result.success:
                raise RuntimeError(result.message)
            output_hashes.append(_hashes(Path(tmp)))
            result_signatures.append(
                (
                    result.n_points,
                    result.n_cells,
                    result.n_faces,
                    result.grid_shape,
                    result.hex_count,
                    result.quality_grade,
                    result.untangle_beta_pass,
                    result.total_volume,
                )
            )

    report = {
        "repeats": args.repeats,
        "median_seconds": statistics.median(timings),
        "all_seconds": timings,
        "input_vertices_sha256": vertices_hash,
        "input_faces_sha256": faces_hash,
        "input_unchanged": (
            hashlib.sha256(vertices.tobytes()).hexdigest() == vertices_hash
            and hashlib.sha256(faces.tobytes()).hexdigest() == faces_hash
        ),
        "deterministic_output": all(hashes == output_hashes[0] for hashes in output_hashes[1:]),
        "deterministic_result": all(
            signature == result_signatures[0] for signature in result_signatures[1:]
        ),
        "pre3_off_points_parity": (output_hashes[0]["points"] == _PRE3_OFF_POINTS_SHA256),
        "output_hashes": output_hashes[0],
        "result_signature": result_signatures[0],
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
