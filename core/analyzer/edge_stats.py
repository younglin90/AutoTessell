"""Q5 / beta2678 — Triangle mesh edge length statistics.

remesh target_edge 자동 산정 / sliver 검출 / aspect ratio 통계.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

try:
    from core.generator.native_tet._native import (
        surface_edge_lengths_stats_batch as _c_surface_edge_lengths_stats_batch,
    )
except Exception:  # pragma: no cover - optional native extension
    _c_surface_edge_lengths_stats_batch = None


@dataclass
class EdgeStatsResult:
    n_edges_total: int = 0
    n_edges_unique: int = 0
    edge_min: float = 0.0
    edge_max: float = 0.0
    edge_mean: float = 0.0
    edge_std: float = 0.0
    edge_p5: float = 0.0
    edge_p50: float = 0.0
    edge_p95: float = 0.0
    aspect_ratio_max: float = 0.0    # max(edge) / min(edge) per face.
    aspect_ratio_mean: float = 0.0
    elapsed_s: float = 0.0


def compute_edge_stats(
    V: NDArray[np.float64],
    F: NDArray[np.int64],
) -> EdgeStatsResult:
    """Triangle mesh edge length 통계.

    Returns: EdgeStatsResult.
    """
    import time
    t0 = time.perf_counter()

    V = np.asarray(V, dtype=np.float64)
    F = np.asarray(F, dtype=np.int64)
    n_f = int(F.shape[0])

    if n_f == 0:
        return EdgeStatsResult(elapsed_s=time.perf_counter() - t0)

    native = (
        _c_surface_edge_lengths_stats_batch(V, F)
        if _c_surface_edge_lengths_stats_batch is not None
        else None
    )
    if native is not None:
        all_edges, n_unique, aspect_max, aspect_mean = native
        return EdgeStatsResult(
            n_edges_total=int(all_edges.size),
            n_edges_unique=n_unique,
            edge_min=float(all_edges.min()),
            edge_max=float(all_edges.max()),
            edge_mean=float(all_edges.mean()),
            edge_std=float(all_edges.std()),
            edge_p5=float(np.percentile(all_edges, 5)),
            edge_p50=float(np.percentile(all_edges, 50)),
            edge_p95=float(np.percentile(all_edges, 95)),
            aspect_ratio_max=aspect_max,
            aspect_ratio_mean=aspect_mean,
            elapsed_s=time.perf_counter() - t0,
        )

    # per-face 3 edges.
    e_a = np.linalg.norm(V[F[:, 1]] - V[F[:, 0]], axis=1)
    e_b = np.linalg.norm(V[F[:, 2]] - V[F[:, 1]], axis=1)
    e_c = np.linalg.norm(V[F[:, 0]] - V[F[:, 2]], axis=1)
    edges_per_face = np.stack([e_a, e_b, e_c], axis=1)  # (M, 3).

    # face aspect ratio = max / min.
    e_min_per_face = edges_per_face.min(axis=1)
    e_max_per_face = edges_per_face.max(axis=1)
    aspect_per_face = e_max_per_face / np.maximum(e_min_per_face, 1e-30)

    # all edges flat.
    all_edges = edges_per_face.ravel()

    # unique edge count via canonical sort.
    edges_canon = np.sort(np.stack([
        F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]],
    ], axis=1).reshape(-1, 2), axis=1)
    n_v = int(V.shape[0])
    keys = edges_canon[:, 0].astype(np.int64) * (n_v + 1) + edges_canon[:, 1].astype(np.int64)
    n_unique = int(np.unique(keys).size)

    return EdgeStatsResult(
        n_edges_total=int(all_edges.size),
        n_edges_unique=n_unique,
        edge_min=float(all_edges.min()),
        edge_max=float(all_edges.max()),
        edge_mean=float(all_edges.mean()),
        edge_std=float(all_edges.std()),
        edge_p5=float(np.percentile(all_edges, 5)),
        edge_p50=float(np.percentile(all_edges, 50)),
        edge_p95=float(np.percentile(all_edges, 95)),
        aspect_ratio_max=float(aspect_per_face.max()),
        aspect_ratio_mean=float(aspect_per_face.mean()),
        elapsed_s=time.perf_counter() - t0,
    )
