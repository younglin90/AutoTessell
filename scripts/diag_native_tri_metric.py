"""Report-only four-fixture audit for the native-tri metric primitive."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import sys

import numpy as np
import trimesh

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.preprocessor.native_tri.metric import (
    audit_spd_metrics,
    make_bl_metric,
    metric_edge_lengths,
    tangent_metric_edge_lengths,
    vertex_normal_spread_deg,
)
from core.preprocessor.native_tri.operator_loop import estimate_curvature_sizing


def _edges(faces: np.ndarray) -> np.ndarray:
    rows = np.concatenate(
        (faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]),
        axis=0,
    )
    return np.unique(np.sort(rows, axis=1), axis=0)


def _audit(name: str, mesh: trimesh.Trimesh, *, bl: bool) -> None:
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    normals = np.asarray(mesh.vertex_normals, dtype=np.float64)
    lengths = estimate_curvature_sizing(vertices, faces, epsilon=0.01)
    normal_spread = vertex_normal_spread_deg(vertices, faces)
    feature_mask = normal_spread > 45.0
    edges = _edges(faces)
    safe_edges = edges[~feature_mask[edges].any(axis=1)]
    if bl:
        metrics = make_bl_metric(
            normals,
            lengths,
            normal_length=lengths * 0.1,
        )
    else:
        metrics = make_bl_metric(normals, lengths, normal_length=lengths)
    report = audit_spd_metrics(metrics)
    edge_lengths = metric_edge_lengths(vertices, edges, metrics)
    tangent_lengths = tangent_metric_edge_lengths(
        vertices,
        safe_edges,
        metrics,
        normals,
        feature_vertices=feature_mask,
    )
    eigenvalues = np.linalg.eigvalsh(metrics)
    print(
        name,
        {
            "vertices": int(len(vertices)),
            "faces": int(len(faces)),
            "bl_mode": bl,
            "target_length_min_median_max": [
                float(lengths.min()),
                float(np.median(lengths)),
                float(lengths.max()),
            ],
            "metric_eigen_min_max": [
                float(eigenvalues.min()),
                float(eigenvalues.max()),
            ],
            "audit": asdict(report),
            "edge_metric_length_min_median_max": [
                float(edge_lengths.min()),
                float(np.median(edge_lengths)),
                float(edge_lengths.max()),
            ],
            "tangent_edge_metric_length_min_median_max": [
                float(tangent_lengths.min()) if len(tangent_lengths) else None,
                float(np.median(tangent_lengths)) if len(tangent_lengths) else None,
                float(tangent_lengths.max()) if len(tangent_lengths) else None,
            ],
            "normal_spread_max_deg": float(normal_spread.max()),
            "feature_vertices_gt45deg": int((normal_spread > 45.0).sum()),
            "edges_total": int(len(edges)),
            "edges_rejected_at_feature_vertices": int(len(edges) - len(safe_edges)),
        },
    )


def main() -> None:
    cube = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    sphere = trimesh.creation.icosphere(subdivisions=2, radius=1.0)
    cylinder = trimesh.creation.cylinder(radius=1.0, height=2.0, sections=32)
    _audit("cube-isotropic", cube, bl=False)
    _audit("cube-bl-stretched", cube, bl=True)
    _audit("sphere-curvature", sphere, bl=False)
    _audit("cylinder-curvature", cylinder, bl=False)


if __name__ == "__main__":
    main()
