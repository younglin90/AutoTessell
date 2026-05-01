"""AA6 / beta2749 — Hex orthogonality stats.

OpenFOAM checkMesh non-orthogonality 와 유사:
  각 internal face 의 normal 과 (cell_center → neighbor_center) vector 사이 각도.
  90° 이면 orthogonal, > 70° 이면 non-orthogonal warning.

여기선 single hex 의 6 face vs cell center 만 측정 (간단 metric).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass
class HexOrthoResult:
    n_hexes: int = 0
    ortho_min_deg: float = 90.0   # min deviation from 90° (best case = 0).
    ortho_max_deg: float = 0.0    # max deviation from 90°.
    ortho_mean_deg: float = 0.0
    n_above_30deg: int = 0        # face deviation > 30° count.
    elapsed_s: float = 0.0


_HEX_FACES = (
    (0, 3, 2, 1),
    (4, 5, 6, 7),
    (0, 1, 5, 4),
    (2, 3, 7, 6),
    (0, 4, 7, 3),
    (1, 2, 6, 5),
)


def hex_ortho_stats(
    pts: NDArray[np.float64],
    hexes: NDArray[np.int64],
) -> HexOrthoResult:
    """face normal vs (face_center - cell_center) 의 각도 deviation from 90°.

    perfect cube → 모든 face normal 이 cell_center→face_center 방향과 같음 (0° dev).
    Args:
        pts: (N, 3).
        hexes: (H, 8).

    Returns:
        HexOrthoResult.
    """
    import time
    t0 = time.perf_counter()

    pts = np.asarray(pts, dtype=np.float64)
    hexes = np.asarray(hexes, dtype=np.int64)
    n_h = int(hexes.shape[0])

    if n_h == 0:
        return HexOrthoResult(elapsed_s=time.perf_counter() - t0)

    corners = pts[hexes]  # (H, 8, 3).
    cell_center = corners.mean(axis=1)  # (H, 3).

    deviations: list[float] = []

    for fi, (a, b, c, d) in enumerate(_HEX_FACES):
        p_a = corners[:, a, :]
        p_b = corners[:, b, :]
        p_c = corners[:, c, :]
        p_d = corners[:, d, :]
        face_center = (p_a + p_b + p_c + p_d) / 4.0

        # normal via diagonals.
        n = np.cross(p_c - p_a, p_d - p_b)
        n_norm = np.linalg.norm(n, axis=1)
        safe = n_norm > 1e-30
        n[safe] = n[safe] / n_norm[safe, None]

        cv = face_center - cell_center
        cv_norm = np.linalg.norm(cv, axis=1)
        safe2 = cv_norm > 1e-30
        cv[safe2] = cv[safe2] / cv_norm[safe2, None]

        cos_a = np.einsum("ij,ij->i", n, cv)
        cos_a = np.clip(np.abs(cos_a), 0.0, 1.0)
        # 0° deviation = perfectly orthogonal. ang = arccos(|cos|), deviation = 90 - ang? No.
        # if normal aligned with (center→face), it's a "structured" face, deviation = 0.
        # angle between them ∈ [0, 90]. structured → 0. non-orthogonal → larger.
        ang_deg = np.degrees(np.arccos(cos_a))
        deviations.extend(float(d) for d in ang_deg)

    arr = np.array(deviations, dtype=np.float64)
    return HexOrthoResult(
        n_hexes=n_h,
        ortho_min_deg=float(arr.min()),
        ortho_max_deg=float(arr.max()),
        ortho_mean_deg=float(arr.mean()),
        n_above_30deg=int((arr > 30.0).sum()),
        elapsed_s=time.perf_counter() - t0,
    )
