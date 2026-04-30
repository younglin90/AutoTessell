"""S1 / beta2688 — Volume mesh bbox crop utility.

(pts, tets) → (cropped_pts, cropped_tets) within a 3D bounding box.
Mesh inspection / partition / debug 용 (전체 mesh 의 일부만 시각화).

Algorithm:
    1. cell centroid 가 bbox 내부 → 채택.
    2. used vertex 만 추출 + remap.
    3. inverse map 으로 tets 재인덱싱.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass
class MeshCropResult:
    n_input_cells: int = 0
    n_output_cells: int = 0
    n_input_pts: int = 0
    n_output_pts: int = 0
    elapsed_s: float = 0.0


def crop_tet_mesh_bbox(
    pts: NDArray[np.float64],
    tets: NDArray[np.int64],
    bbox_min: NDArray[np.float64],
    bbox_max: NDArray[np.float64],
) -> tuple[NDArray[np.float64], NDArray[np.int64], MeshCropResult]:
    """Tet mesh 의 bbox crop (centroid-based).

    Args:
        pts: (N, 3).
        tets: (T, 4).
        bbox_min / bbox_max: (3,) bbox bounds.

    Returns:
        (cropped_pts, cropped_tets, result). 빈 mesh 시 shape (0, 3) / (0, 4).
    """
    import time
    t0 = time.perf_counter()

    pts = np.asarray(pts, dtype=np.float64)
    tets = np.asarray(tets, dtype=np.int64)
    bmin = np.asarray(bbox_min, dtype=np.float64)
    bmax = np.asarray(bbox_max, dtype=np.float64)

    n_t_in = int(tets.shape[0])
    n_p_in = int(pts.shape[0])

    if n_t_in == 0 or n_p_in == 0:
        return (
            np.zeros((0, 3), dtype=np.float64),
            np.zeros((0, 4), dtype=np.int64),
            MeshCropResult(elapsed_s=time.perf_counter() - t0),
        )

    # centroid 계산.
    cents = pts[tets].mean(axis=1)  # (T, 3).
    in_box = np.all(
        (cents >= bmin[None, :]) & (cents <= bmax[None, :]),
        axis=1,
    )
    n_kept = int(in_box.sum())
    if n_kept == 0:
        return (
            np.zeros((0, 3), dtype=np.float64),
            np.zeros((0, 4), dtype=np.int64),
            MeshCropResult(
                n_input_cells=n_t_in, n_input_pts=n_p_in,
                elapsed_s=time.perf_counter() - t0,
            ),
        )

    kept_tets = tets[in_box]
    used_v = np.unique(kept_tets.ravel())
    remap = -np.ones(n_p_in, dtype=np.int64)
    remap[used_v] = np.arange(len(used_v), dtype=np.int64)
    new_tets = remap[kept_tets].astype(np.int64)
    new_pts = pts[used_v].copy()

    return (
        new_pts, new_tets,
        MeshCropResult(
            n_input_cells=n_t_in, n_output_cells=n_kept,
            n_input_pts=n_p_in, n_output_pts=int(new_pts.shape[0]),
            elapsed_s=time.perf_counter() - t0,
        ),
    )
