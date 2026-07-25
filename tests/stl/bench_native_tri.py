#!/usr/bin/env python3
"""Native-tri Phase-0 corpus baseline for the existing L2 remesher.

This is a measurement harness only.  It calls ``native_remesh.isotropic`` and
does not claim that the L2 output is the future native-tri engine.  Hausdorff
is the symmetric sampled vertex distance; it is intentionally labelled as a
cheap baseline proxy until a point-to-triangle sampler is added.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.analyzer import topology  # noqa: E402
from core.analyzer.readers import read_stl  # noqa: E402
from core.preprocessor.native_remesh import isotropic_remesh  # noqa: E402

DEFAULT_FIXTURES = (
    "tests/benchmarks/cube.stl",
    "tests/benchmarks/sphere.stl",
    "tests/benchmarks/cylinder.stl",
    "tests/benchmarks/very_thin_disk_0_01mm.stl",
    "tests/benchmarks/mixed_features_wing_with_spike.stl",
)


def _angles(vertices: np.ndarray, faces: np.ndarray) -> tuple[float, float]:
    tri = vertices[faces]
    out: list[float] = []
    for p0, p1, p2 in tri:
        edges = (p1 - p0, p2 - p1, p0 - p2)
        lengths = [float(np.linalg.norm(e)) for e in edges]
        if min(lengths) <= 1e-15:
            out.extend((0.0, 0.0, 0.0))
            continue
        for a, b, opposite in (
            (p1 - p0, p2 - p0, p0),
            (p0 - p1, p2 - p1, p1),
            (p0 - p2, p1 - p2, p2),
        ):
            del opposite
            denom = np.linalg.norm(a) * np.linalg.norm(b)
            cosv = float(np.dot(a, b) / max(denom, 1e-30))
            out.append(math.degrees(math.acos(float(np.clip(cosv, -1.0, 1.0)))))
    return (float(min(out)) if out else 0.0, float(max(out)) if out else 0.0)


def _edge_keys(faces: np.ndarray) -> set[tuple[int, int]]:
    return {
        tuple(sorted((int(a), int(b))))
        for tri in faces.tolist()
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0]))
    }


def _feature_edges(
    vertices: np.ndarray,
    faces: np.ndarray,
    threshold: float = 30.0,
) -> set[tuple[int, int]]:
    edge_faces: dict[tuple[int, int], list[int]] = {}
    for fi, tri in enumerate(faces.tolist()):
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            edge_faces.setdefault(tuple(sorted((a, b))), []).append(fi)
    normals = np.cross(
        vertices[faces[:, 1]] - vertices[faces[:, 0]],
        vertices[faces[:, 2]] - vertices[faces[:, 0]],
    )
    normals /= np.maximum(np.linalg.norm(normals, axis=1)[:, None], 1e-30)
    result: set[tuple[int, int]] = set()
    for edge, attached in edge_faces.items():
        if len(attached) == 2:
            dot = float(np.clip(np.dot(normals[attached[0]], normals[attached[1]]), -1.0, 1.0))
            angle = math.degrees(math.acos(dot))
            if angle >= threshold:
                result.add(edge)
    return result


def _nearest_distance(source: np.ndarray, target: np.ndarray) -> float:
    if not len(source) or not len(target):
        return math.inf
    distances = np.min(
        np.linalg.norm(source[:, None, :] - target[None, :, :], axis=2),
        axis=1,
    )
    return float(max(distances))


def _feature_recall_proxy(
    source_vertices: np.ndarray,
    source_features: set[tuple[int, int]],
    output_vertices: np.ndarray,
    output_edges: set[tuple[int, int]],
) -> tuple[int, int, float | None]:
    """Nearest-vertex feature recall, explicitly marked as a proxy.

    The L2 path does not carry provenance IDs.  Mapping each source feature
    endpoint to its nearest output vertex gives a deterministic lower-cost
    diagnostic, not a contractual feature-preservation result.
    """
    if not source_features or not len(output_vertices):
        return (0, len(source_features), None)
    nearest = np.argmin(
        np.linalg.norm(source_vertices[:, None, :] - output_vertices[None, :, :], axis=2),
        axis=1,
    )
    preserved = 0
    for a, b in source_features:
        mapped = tuple(sorted((int(nearest[a]), int(nearest[b]))))
        preserved += int(mapped in output_edges and mapped[0] != mapped[1])
    return preserved, len(source_features), preserved / len(source_features)


def measure(path: Path, target_scale: float, iterations: int) -> dict[str, object]:
    path = path if path.is_absolute() else ROOT / path
    mesh = read_stl(path)
    vertices = np.asarray(mesh.vertices, dtype=float)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    edge_lengths = np.concatenate([
        np.linalg.norm(
            vertices[faces[:, i]] - vertices[faces[:, (i + 1) % 3]], axis=1,
        )
        for i in range(3)
    ])
    target = float(np.mean(edge_lengths) * target_scale)
    out_v, out_f = isotropic_remesh(vertices, faces, target_edge_length=target, n_iter=iterations)
    min_angle, max_angle = _angles(out_v, out_f)
    source_features = _feature_edges(vertices, faces)
    preserved, feature_total, feature_recall = _feature_recall_proxy(
        vertices, source_features, out_v, _edge_keys(out_f),
    )
    return {
        "fixture": str(path.relative_to(ROOT)),
        "input_vertices": int(len(vertices)),
        "input_faces": int(len(faces)),
        "output_vertices": int(len(out_v)),
        "output_faces": int(len(out_f)),
        "target_edge_length": target,
        "sampled_vertex_hausdorff": max(
            _nearest_distance(vertices, out_v),
            _nearest_distance(out_v, vertices),
        ),
        "min_angle_deg": min_angle,
        "max_angle_deg": max_angle,
        "manifold": bool(topology.is_manifold(out_f)),
        "watertight": bool(topology.is_watertight(out_f)),
        "input_feature_edges": len(source_features),
        "feature_preservation": "nearest_vertex_edge_recall_proxy",
        "feature_edges_preserved_proxy": preserved,
        "feature_edges_total": feature_total,
        "feature_edge_recall_proxy": feature_recall,
        "input_edge_count": len(_edge_keys(faces)),
        "output_edge_count": len(_edge_keys(out_f)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", action="append", type=Path)
    parser.add_argument("--target-scale", type=float, default=1.0)
    parser.add_argument("--iterations", type=int, default=2)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    paths = args.fixture or [ROOT / item for item in DEFAULT_FIXTURES]
    rows = []
    for path in paths:
        if path.exists():
            rows.append(measure(path, args.target_scale, args.iterations))
        else:
            rows.append({"fixture": str(path), "status": "missing"})
    payload = {"engine": "native_tri_phase0_l2_baseline", "rows": rows}
    text = json.dumps(payload, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
