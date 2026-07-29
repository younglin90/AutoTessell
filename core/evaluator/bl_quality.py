"""W2 / beta2717 — Boundary-layer prism quality stats.

Prism (wedge) cell = 6 vertices: 2 triangular faces (wall + outer).
- aspect ratio: outer_to_wall_distance / wall_edge_length
- thickness uniformity: 3 wall→outer edge length 의 std/mean
- skewness: wall normal vs prism direction 의 angle deviation

native_bl 출력 진단 + Evaluator wall-region check.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

try:
    from core.generator.native_tet._native import (
        bl_prism_quality_stats_batch as _c_bl_prism_quality_stats_batch,
    )
except Exception:  # pragma: no cover - native extension optional
    _c_bl_prism_quality_stats_batch = None


@dataclass
class BLQualityResult:
    n_prisms: int = 0
    aspect_min: float = 0.0
    aspect_max: float = 0.0
    aspect_mean: float = 0.0
    thickness_uniformity_mean: float = 1.0  # 1.0 = uniform.
    skew_max: float = 0.0   # max angle deviation (radian).
    skew_mean: float = 0.0
    n_inverted: int = 0
    elapsed_s: float = 0.0


def bl_prism_quality(
    pts: NDArray[np.float64],
    prisms: NDArray[np.int64],
) -> BLQualityResult:
    """prism (T, 6) 의 quality 통계.

    prism layout: 0,1,2 = wall (tri), 3,4,5 = outer (corresponds to 0→3, 1→4, 2→5).

    Args:
        pts: (N, 3).
        prisms: (T, 6).

    Returns:
        BLQualityResult.
    """
    import time
    t0 = time.perf_counter()

    pts = np.asarray(pts, dtype=np.float64)
    prisms = np.asarray(prisms, dtype=np.int64)
    n_p = int(prisms.shape[0])

    if n_p == 0:
        return BLQualityResult(elapsed_s=time.perf_counter() - t0)

    if _c_bl_prism_quality_stats_batch is not None:
        native = _c_bl_prism_quality_stats_batch(pts, prisms)
        if native is not None:
            stats, n_inv = native
            return BLQualityResult(
                n_prisms=n_p,
                aspect_min=stats[0],
                aspect_max=stats[1],
                aspect_mean=stats[2],
                thickness_uniformity_mean=stats[3],
                skew_max=stats[4],
                skew_mean=stats[5],
                n_inverted=n_inv,
                elapsed_s=time.perf_counter() - t0,
            )

    p0, p1, p2 = pts[prisms[:, 0]], pts[prisms[:, 1]], pts[prisms[:, 2]]
    p3, p4, p5 = pts[prisms[:, 3]], pts[prisms[:, 4]], pts[prisms[:, 5]]

    # wall edges (triangle).
    we0 = np.linalg.norm(p1 - p0, axis=1)
    we1 = np.linalg.norm(p2 - p1, axis=1)
    we2 = np.linalg.norm(p0 - p2, axis=1)
    wall_edge_mean = (we0 + we1 + we2) / 3.0

    # prism extrusion (wall→outer).
    h0 = np.linalg.norm(p3 - p0, axis=1)
    h1 = np.linalg.norm(p4 - p1, axis=1)
    h2 = np.linalg.norm(p5 - p2, axis=1)
    h_mean = (h0 + h1 + h2) / 3.0
    h_std = np.sqrt(((h0 - h_mean) ** 2 + (h1 - h_mean) ** 2 + (h2 - h_mean) ** 2) / 3.0)
    uniformity = 1.0 - (h_std / np.maximum(h_mean, 1e-30))  # 1.0 = uniform.

    # aspect ratio.
    aspect = h_mean / np.maximum(wall_edge_mean, 1e-30)

    # skew: wall normal vs prism direction.
    wall_n = np.cross(p1 - p0, p2 - p0)
    wall_n_norm = np.linalg.norm(wall_n, axis=1)
    safe = wall_n_norm > 1e-30
    wall_n[safe] = wall_n[safe] / wall_n_norm[safe, None]
    prism_dir = ((p3 - p0) + (p4 - p1) + (p5 - p2)) / 3.0
    pd_norm = np.linalg.norm(prism_dir, axis=1)
    safe2 = pd_norm > 1e-30
    prism_dir[safe2] = prism_dir[safe2] / pd_norm[safe2, None]
    cos_a = np.einsum("ij,ij->i", wall_n, prism_dir)
    cos_a = np.clip(np.abs(cos_a), 0.0, 1.0)
    skew = np.arccos(cos_a)  # smaller = more aligned.

    # inverted: dot(wall_normal, prism_dir) < 0 → wrong side.
    n_inv = int((np.einsum("ij,ij->i", wall_n, prism_dir) < 0).sum())

    return BLQualityResult(
        n_prisms=n_p,
        aspect_min=float(aspect.min()),
        aspect_max=float(aspect.max()),
        aspect_mean=float(aspect.mean()),
        thickness_uniformity_mean=float(uniformity.mean()),
        skew_max=float(skew.max()),
        skew_mean=float(skew.mean()),
        n_inverted=n_inv,
        elapsed_s=time.perf_counter() - t0,
    )
