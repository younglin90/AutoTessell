"""V6 / beta2714 — mesh summary diff (count + bbox + cell vol).

두 mesh (V_a, F_a / Cells_a) vs (V_b, F_b / Cells_b) 의 통계 차이를 한 줄 요약.
regression test / before-after 검증 / commit diff.

Note: 정확한 vertex-by-vertex 비교는 안 함 (mesh order 가 달라도 OK).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass
class MeshDiffResult:
    n_vertices_a: int = 0
    n_vertices_b: int = 0
    delta_vertices: int = 0
    n_cells_a: int = 0
    n_cells_b: int = 0
    delta_cells: int = 0
    bbox_volume_a: float = 0.0
    bbox_volume_b: float = 0.0
    bbox_overlap_ratio: float = 0.0
    total_volume_delta: float = 0.0  # |V_a - V_b| / max(V_a, V_b).


def _bbox(V: NDArray[np.float64]) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    if V.shape[0] == 0:
        return (np.zeros(3), np.zeros(3))
    return (V.min(axis=0), V.max(axis=0))


def _bbox_vol(lo: NDArray[np.float64], hi: NDArray[np.float64]) -> float:
    return float(np.prod(np.maximum(hi - lo, 0.0)))


def _bbox_overlap(
    lo_a: NDArray[np.float64], hi_a: NDArray[np.float64],
    lo_b: NDArray[np.float64], hi_b: NDArray[np.float64],
) -> float:
    lo = np.maximum(lo_a, lo_b)
    hi = np.minimum(hi_a, hi_b)
    return _bbox_vol(lo, hi)


def _tet_volume_sum(pts: NDArray[np.float64], tets: NDArray[np.int64]) -> float:
    if tets.shape[0] == 0:
        return 0.0
    a = pts[tets[:, 0]]; b = pts[tets[:, 1]]
    c = pts[tets[:, 2]]; d = pts[tets[:, 3]]
    v = np.einsum("ij,ij->i", np.cross(b - a, c - a), d - a) / 6.0
    return float(np.abs(v).sum())


def mesh_diff(
    V_a: NDArray[np.float64], cells_a: NDArray[np.int64],
    V_b: NDArray[np.float64], cells_b: NDArray[np.int64],
) -> MeshDiffResult:
    """두 volume mesh (tet 가정) 통계 비교.

    cells_a/b: (T, 4) tet 인덱스 (필수 가정).
    """
    V_a = np.asarray(V_a, dtype=np.float64)
    V_b = np.asarray(V_b, dtype=np.float64)
    cells_a = np.asarray(cells_a, dtype=np.int64)
    cells_b = np.asarray(cells_b, dtype=np.int64)

    lo_a, hi_a = _bbox(V_a)
    lo_b, hi_b = _bbox(V_b)
    vol_bb_a = _bbox_vol(lo_a, hi_a)
    vol_bb_b = _bbox_vol(lo_b, hi_b)
    vol_overlap = _bbox_overlap(lo_a, hi_a, lo_b, hi_b)
    overlap_ratio = vol_overlap / max(min(vol_bb_a, vol_bb_b), 1e-30)

    cell_vol_a = _tet_volume_sum(V_a, cells_a) if cells_a.shape[1] == 4 else 0.0
    cell_vol_b = _tet_volume_sum(V_b, cells_b) if cells_b.shape[1] == 4 else 0.0
    max_v = max(cell_vol_a, cell_vol_b, 1e-30)
    total_dv = abs(cell_vol_a - cell_vol_b) / max_v

    return MeshDiffResult(
        n_vertices_a=int(V_a.shape[0]),
        n_vertices_b=int(V_b.shape[0]),
        delta_vertices=int(V_b.shape[0]) - int(V_a.shape[0]),
        n_cells_a=int(cells_a.shape[0]),
        n_cells_b=int(cells_b.shape[0]),
        delta_cells=int(cells_b.shape[0]) - int(cells_a.shape[0]),
        bbox_volume_a=vol_bb_a,
        bbox_volume_b=vol_bb_b,
        bbox_overlap_ratio=float(overlap_ratio),
        total_volume_delta=float(total_dv),
    )
