"""CC6 / beta2763 — poly cell volume integrator (divergence theorem).

Polyhedral cell 의 volume = (1/3) * Σ_face center · normal * area.
- 일반 polyhedron 에 적용 가능.
- 음수 결과 = inverted (winding error).

OpenFOAM polyMesh writer 의 volume sanity check 입력.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

try:
    from core.generator.native_tet._native import (
        poly_volume_stats_batch as _c_poly_volume_stats_batch,
    )
except Exception:  # pragma: no cover - native extension optional
    _c_poly_volume_stats_batch = None


@dataclass
class PolyVolumeResult:
    n_cells: int = 0
    volume_min: float = 0.0
    volume_max: float = 0.0
    volume_mean: float = 0.0
    total_volume: float = 0.0
    n_negative: int = 0       # inverted cells.
    elapsed_s: float = 0.0


def poly_cell_volumes(
    pts: NDArray[np.float64],
    cell_face_lists: list[list[NDArray[np.int64]]],
) -> tuple[NDArray[np.float64], PolyVolumeResult]:
    """cell 별 polyhedral volume (divergence theorem).

    Args:
        pts: (N, 3).
        cell_face_lists: each cell = list of face vertex_idx arrays (CCW outward).

    Returns:
        (volumes (n_cells,), PolyVolumeResult).
    """
    import time
    t0 = time.perf_counter()

    pts = np.asarray(pts, dtype=np.float64)
    n_cells = len(cell_face_lists)

    if n_cells == 0:
        return np.zeros(0, dtype=np.float64), PolyVolumeResult(
            elapsed_s=time.perf_counter() - t0,
        )

    if _c_poly_volume_stats_batch is not None:
        native = _c_poly_volume_stats_batch(pts, cell_face_lists)
        if native is not None:
            vols, stats, n_neg = native
            return vols, PolyVolumeResult(
                n_cells=n_cells,
                volume_min=stats[0],
                volume_max=stats[1],
                volume_mean=stats[2],
                total_volume=stats[3],
                n_negative=n_neg,
                elapsed_s=time.perf_counter() - t0,
            )

    vols = np.zeros(n_cells, dtype=np.float64)

    for ci, faces in enumerate(cell_face_lists):
        cell_vol = 0.0
        for face in faces:
            face = np.asarray(face, dtype=np.int64)
            n_f_v = face.shape[0]
            if n_f_v < 3:
                continue
            face_pts = pts[face]
            # face fan triangulation from face[0].
            face_n = np.zeros(3, dtype=np.float64)
            face_center = face_pts.mean(axis=0)
            # use face center as fan apex for stability + signed sum.
            for k in range(n_f_v):
                p0 = face_pts[k]
                p1 = face_pts[(k + 1) % n_f_v]
                tri_n = np.cross(p0 - face_center, p1 - face_center)
                face_n += tri_n
            # divergence theorem: vol += (1/6) * face_center · (2*face_normal)
            # equivalent: (1/3) * face_center · face_normal_total
            cell_vol += float(np.dot(face_center, face_n)) / 6.0
        vols[ci] = cell_vol

    n_neg = int((vols < 0).sum())

    return vols, PolyVolumeResult(
        n_cells=n_cells,
        volume_min=float(vols.min()),
        volume_max=float(vols.max()),
        volume_mean=float(vols.mean()),
        total_volume=float(vols.sum()),
        n_negative=n_neg,
        elapsed_s=time.perf_counter() - t0,
    )
