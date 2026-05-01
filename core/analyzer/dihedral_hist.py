"""AA2 / beta2745 — surface dihedral angle histogram.

각 internal edge 의 dihedral angle (incident face normals 사이 각도).
- 0~30°: 매우 sharp (corner).
- 30~150°: 일반.
- 150~180°: 거의 flat.

Histogram → mesh complexity 진단 + sharp feature 분포.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass
class DihedralHistResult:
    n_edges: int = 0           # internal edges only.
    angle_min_deg: float = 180.0
    angle_max_deg: float = 0.0
    angle_mean_deg: float = 0.0
    bins_deg: tuple = ()       # bin edges in degrees.
    counts: tuple = ()         # count per bin.
    elapsed_s: float = 0.0


def dihedral_histogram(
    V: NDArray[np.float64],
    F: NDArray[np.int64],
    *,
    bin_edges_deg: tuple = (0, 30, 60, 90, 120, 150, 180),
) -> DihedralHistResult:
    """surface internal edge 의 dihedral 분포.

    Args:
        V: (N, 3).
        F: (M, 3).
        bin_edges_deg: histogram bin 경계 (degrees).

    Returns:
        DihedralHistResult.
    """
    import time
    t0 = time.perf_counter()

    V = np.asarray(V, dtype=np.float64)
    F = np.asarray(F, dtype=np.int64)
    n_f = int(F.shape[0])

    if n_f == 0:
        return DihedralHistResult(
            bins_deg=tuple(bin_edges_deg),
            counts=tuple([0] * (len(bin_edges_deg) - 1)),
            elapsed_s=time.perf_counter() - t0,
        )

    # face normals.
    e1 = V[F[:, 1]] - V[F[:, 0]]
    e2 = V[F[:, 2]] - V[F[:, 0]]
    fn = np.cross(e1, e2)
    fn_norm = np.linalg.norm(fn, axis=1)
    safe = fn_norm > 1e-30
    fn[safe] = fn[safe] / fn_norm[safe, None]

    # group edges by sorted endpoints.
    edges = np.concatenate([
        F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]],
    ], axis=0)
    edges_s = np.sort(edges, axis=1)
    face_ids = np.tile(np.arange(n_f, dtype=np.int64), 3)

    keys = edges_s[:, 0] * (1 << 32) + edges_s[:, 1]
    sort_idx = np.argsort(keys)
    keys_s = keys[sort_idx]
    face_s = face_ids[sort_idx]

    angles_deg: list[float] = []
    n_e = keys_s.shape[0]
    i = 0
    while i < n_e:
        j = i
        while j < n_e and keys_s[j] == keys_s[i]:
            j += 1
        if (j - i) == 2:
            f0, f1 = int(face_s[i]), int(face_s[i + 1])
            cos_a = float(np.dot(fn[f0], fn[f1]))
            cos_a = max(-1.0, min(1.0, cos_a))
            ang = float(np.degrees(np.arccos(cos_a)))
            angles_deg.append(ang)
        i = j

    if not angles_deg:
        return DihedralHistResult(
            bins_deg=tuple(bin_edges_deg),
            counts=tuple([0] * (len(bin_edges_deg) - 1)),
            elapsed_s=time.perf_counter() - t0,
        )

    arr = np.array(angles_deg, dtype=np.float64)
    counts, _ = np.histogram(arr, bins=bin_edges_deg)
    return DihedralHistResult(
        n_edges=arr.shape[0],
        angle_min_deg=float(arr.min()),
        angle_max_deg=float(arr.max()),
        angle_mean_deg=float(arr.mean()),
        bins_deg=tuple(bin_edges_deg),
        counts=tuple(int(c) for c in counts),
        elapsed_s=time.perf_counter() - t0,
    )
