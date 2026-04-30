"""X6 / beta2728 — tet mesh region splitter.

cell tag 배열 (T,) → 각 region 별 (V_sub, T_sub) 추출 + vertex reindex.
multi-region mesh / 분할 후 처리 / region 별 export.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass
class MeshRegion:
    region_id: int = 0
    n_vertices: int = 0
    n_tets: int = 0
    V: NDArray[np.float64] | None = None
    T: NDArray[np.int64] | None = None


def split_by_region(
    pts: NDArray[np.float64],
    tets: NDArray[np.int64],
    region_id: NDArray[np.int64],
) -> list[MeshRegion]:
    """region tag 별 sub-mesh 분리.

    Args:
        pts: (N, 3).
        tets: (T, 4).
        region_id: (T,) integer tag per tet.

    Returns:
        list[MeshRegion] (region_id 오름차순).
    """
    pts = np.asarray(pts, dtype=np.float64)
    tets = np.asarray(tets, dtype=np.int64)
    region_id = np.asarray(region_id, dtype=np.int64)

    if region_id.shape[0] != tets.shape[0]:
        raise ValueError(
            f"region_id length {region_id.shape[0]} != tets {tets.shape[0]}"
        )

    out: list[MeshRegion] = []
    if tets.shape[0] == 0:
        return out

    unique_regions = np.unique(region_id)
    for rid in unique_regions:
        mask = region_id == rid
        sub_tets_global = tets[mask]
        # collect referenced vertex indices.
        used_vidx = np.unique(sub_tets_global.reshape(-1))
        # build mapping.
        n_used = used_vidx.shape[0]
        remap = -np.ones(int(used_vidx.max()) + 1, dtype=np.int64) if n_used > 0 \
            else np.zeros(0, dtype=np.int64)
        remap[used_vidx] = np.arange(n_used)

        V_sub = pts[used_vidx]
        T_sub = remap[sub_tets_global]

        out.append(MeshRegion(
            region_id=int(rid),
            n_vertices=int(n_used),
            n_tets=int(sub_tets_global.shape[0]),
            V=V_sub,
            T=T_sub,
        ))
    return out
