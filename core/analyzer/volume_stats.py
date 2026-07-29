"""M4 / beta2650 — volume mesh statistics module.

cell quality 분포 + cell type 분류 + size 통계.
checkMesh 동등 — 디버깅 / quality report 용.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

try:
    from core.generator.native_tet._native import (
        tet_volume_stats_batch as _c_tet_volume_stats_batch,
    )
except Exception:  # pragma: no cover - native extension optional
    _c_tet_volume_stats_batch = None


@dataclass
class VolumeStatsResult:
    n_cells: int = 0
    n_tet: int = 0
    n_hex: int = 0
    n_wedge: int = 0
    n_pyramid: int = 0
    n_polyhedron: int = 0

    quality_min: float = 0.0
    quality_max: float = 0.0
    quality_mean: float = 0.0
    quality_p5: float = 0.0       # bottom 5%.
    quality_p50: float = 0.0
    quality_p95: float = 0.0

    volume_min: float = 0.0
    volume_max: float = 0.0
    volume_total: float = 0.0
    n_negative_volume: int = 0    # inverted cells.

    elapsed_s: float = 0.0
    histogram_bins: list[tuple[float, float, int]] = field(default_factory=list)


def _tet_volume6(p0, p1, p2, p3) -> float:
    return float(np.dot(np.cross(p1 - p0, p2 - p0), p3 - p0))


def _tet_quality(p0, p1, p2, p3) -> float:
    """Klingner mean-ratio (공식 동일)."""
    edges = [p1 - p0, p2 - p0, p3 - p0, p2 - p1, p3 - p1, p3 - p2]
    e_sq_sum = sum(float((e * e).sum()) for e in edges)
    if e_sq_sum < 1e-30:
        return 0.0
    vol6 = _tet_volume6(p0, p1, p2, p3)
    vol = abs(vol6) / 6.0
    return float(np.clip(
        12.0 * ((3.0 * vol) ** (2.0 / 3.0)) / e_sq_sum,
        0.0, 1.0,
    ))


def compute_tet_stats(
    pts: NDArray[np.float64],
    tets: NDArray[np.int64],
    *,
    n_bins: int = 20,
) -> VolumeStatsResult:
    """Tet mesh volume statistics."""
    import time
    t0 = time.perf_counter()

    pts = np.asarray(pts, dtype=np.float64)
    tets = np.asarray(tets, dtype=np.int64)
    n_t = int(tets.shape[0])

    if n_t == 0:
        return VolumeStatsResult(n_cells=0, elapsed_s=time.perf_counter() - t0)

    if _c_tet_volume_stats_batch is not None:
        native = _c_tet_volume_stats_batch(pts, tets, n_bins)
        if native is not None:
            stats, n_neg, counts = native
            edges = np.linspace(0.0, 1.0, n_bins + 1)
            histogram = [
                (float(edges[i]), float(edges[i + 1]), int(counts[i]))
                for i in range(n_bins)
            ]
            return VolumeStatsResult(
                n_cells=n_t,
                n_tet=n_t,
                quality_min=stats[0],
                quality_max=stats[1],
                quality_mean=stats[2],
                quality_p5=stats[3],
                quality_p50=stats[4],
                quality_p95=stats[5],
                volume_min=stats[6],
                volume_max=stats[7],
                volume_total=stats[8],
                n_negative_volume=n_neg,
                elapsed_s=time.perf_counter() - t0,
                histogram_bins=histogram,
            )

    # vectorized tet quality.
    p0 = pts[tets[:, 0]]
    p1 = pts[tets[:, 1]]
    p2 = pts[tets[:, 2]]
    p3 = pts[tets[:, 3]]

    e0 = p1 - p0; e1 = p2 - p0; e2 = p3 - p0
    e3 = p2 - p1; e4 = p3 - p1; e5 = p3 - p2
    e_sq_sum = (
        (e0 ** 2).sum(1) + (e1 ** 2).sum(1) + (e2 ** 2).sum(1)
        + (e3 ** 2).sum(1) + (e4 ** 2).sum(1) + (e5 ** 2).sum(1)
    )

    vol6 = (np.cross(e1, e2) * e0).sum(1)  # signed.
    vol = np.abs(vol6) / 6.0
    n_neg = int((vol6 < 0).sum())

    qualities = np.where(
        e_sq_sum > 1e-30,
        np.clip(12.0 * ((3.0 * vol) ** (2.0 / 3.0)) / e_sq_sum, 0.0, 1.0),
        0.0,
    )

    # histogram.
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    counts, _ = np.histogram(qualities, bins=edges)
    histogram = [
        (float(edges[i]), float(edges[i + 1]), int(counts[i]))
        for i in range(n_bins)
    ]

    return VolumeStatsResult(
        n_cells=n_t,
        n_tet=n_t,
        quality_min=float(qualities.min()),
        quality_max=float(qualities.max()),
        quality_mean=float(qualities.mean()),
        quality_p5=float(np.percentile(qualities, 5)),
        quality_p50=float(np.percentile(qualities, 50)),
        quality_p95=float(np.percentile(qualities, 95)),
        volume_min=float(vol.min()),
        volume_max=float(vol.max()),
        volume_total=float(vol.sum()),
        n_negative_volume=n_neg,
        elapsed_s=time.perf_counter() - t0,
        histogram_bins=histogram,
    )
