"""U3 / beta2704 — combined surface feature stats report.

surface mesh 의 sharp edges + curvature + edge length 등을 한 번에 집계.
mesh "complexity score" 산출 → Strategist tier 선택 가이드.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray


@dataclass
class FeatureReport:
    n_vertices: int = 0
    n_triangles: int = 0
    edge_min: float = 0.0
    edge_max: float = 0.0
    edge_p99_ratio: float = 0.0  # edge_p99 / edge_p01.
    n_sharp_edges: int = 0
    sharp_ratio: float = 0.0  # sharp / total edges.
    curvature_max_abs: float = 0.0
    curvature_p99: float = 0.0
    complexity_score: float = 0.0  # composite (높을수록 복잡).
    elapsed_s: float = 0.0
    notes: list[str] = field(default_factory=list)


def feature_report(
    V: NDArray[np.float64],
    F: NDArray[np.int64],
    *,
    sharp_angle_deg: float = 30.0,
) -> FeatureReport:
    """surface mesh 의 통합 feature 진단.

    Args:
        V: (N, 3).
        F: (M, 3).
        sharp_angle_deg: dihedral 이 이 값보다 크면 sharp.

    Returns:
        FeatureReport.
    """
    import time
    t0 = time.perf_counter()

    V = np.asarray(V, dtype=np.float64)
    F = np.asarray(F, dtype=np.int64)
    n_v, n_f = int(V.shape[0]), int(F.shape[0])
    rep = FeatureReport(n_vertices=n_v, n_triangles=n_f)

    if n_v == 0 or n_f == 0:
        rep.elapsed_s = time.perf_counter() - t0
        return rep

    # edge length stats.
    edges = np.concatenate([
        F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]],
    ], axis=0)
    edges = np.sort(edges, axis=1)
    edges_unique = np.unique(edges, axis=0)
    e_lens = np.linalg.norm(V[edges_unique[:, 1]] - V[edges_unique[:, 0]], axis=1)
    rep.edge_min = float(e_lens.min())
    rep.edge_max = float(e_lens.max())
    p01, p99 = np.percentile(e_lens, [1, 99])
    rep.edge_p99_ratio = float(p99 / max(p01, 1e-30))

    # sharp edges via existing utility.
    try:
        from core.analyzer.feature_edges import extract_feature_edges
        info = extract_feature_edges(V, F, feature_angle_deg=sharp_angle_deg)
        rep.n_sharp_edges = int(info.n_sharp_dihedral_edges)
        n_total_edges = int(edges_unique.shape[0])
        rep.sharp_ratio = float(info.n_sharp_dihedral_edges) / max(n_total_edges, 1)
    except Exception as exc:
        rep.notes.append(f"feature_edges skipped: {exc}")

    # curvature.
    try:
        from core.analyzer.curvature import vertex_gaussian_curvature
        K, _ = vertex_gaussian_curvature(V, F)
        if K.size > 0:
            rep.curvature_max_abs = float(np.abs(K).max())
            rep.curvature_p99 = float(np.percentile(np.abs(K), 99))
    except Exception as exc:
        rep.notes.append(f"curvature skipped: {exc}")

    # complexity score (heuristic):
    # - edge ratio 높을수록 +
    # - sharp ratio 높을수록 +
    # - curvature p99 클수록 +
    rep.complexity_score = float(
        min(rep.edge_p99_ratio / 50.0, 1.0) * 0.4
        + min(rep.sharp_ratio * 5.0, 1.0) * 0.3
        + min(rep.curvature_p99 / 10.0, 1.0) * 0.3
    )
    rep.elapsed_s = time.perf_counter() - t0
    return rep
