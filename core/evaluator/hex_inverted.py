"""BB6 / beta2756 — hex inverted detector + worst hex localization.

기존 hex_jacobian (BETA2711) 의 j_min < 0 인 hex 를 찾아 인덱스 + worst stats 반환.
mesh repair / Generator FAIL 디버깅 입력.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass
class HexInvertedResult:
    n_hexes: int = 0
    n_inverted: int = 0
    inverted_indices: list[int] | None = None
    worst_j_min: float = 0.0
    worst_hex_idx: int = -1
    elapsed_s: float = 0.0

    def __post_init__(self):
        if self.inverted_indices is None:
            self.inverted_indices = []


_HEX_CORNER_EDGES = (
    (0, 1, 3, 4),
    (1, 2, 0, 5),
    (2, 3, 1, 6),
    (3, 0, 2, 7),
    (4, 7, 5, 0),
    (5, 4, 6, 1),
    (6, 5, 7, 2),
    (7, 6, 4, 3),
)


def detect_inverted_hexes(
    pts: NDArray[np.float64],
    hexes: NDArray[np.int64],
) -> HexInvertedResult:
    """j_min < 0 인 hex 의 인덱스 + worst hex 추출.

    Args:
        pts: (N, 3).
        hexes: (H, 8).

    Returns:
        HexInvertedResult.
    """
    import time
    t0 = time.perf_counter()

    pts = np.asarray(pts, dtype=np.float64)
    hexes = np.asarray(hexes, dtype=np.int64)
    n_h = int(hexes.shape[0])

    if n_h == 0:
        return HexInvertedResult(elapsed_s=time.perf_counter() - t0)

    corners = pts[hexes]  # (H, 8, 3).

    j_per = np.zeros((n_h, 8), dtype=np.float64)
    for ci, (c, na, nb, nc) in enumerate(_HEX_CORNER_EDGES):
        e1 = corners[:, na, :] - corners[:, c, :]
        e2 = corners[:, nb, :] - corners[:, c, :]
        e3 = corners[:, nc, :] - corners[:, c, :]
        j_per[:, ci] = np.einsum("ij,ij->i", np.cross(e1, e2), e3)

    j_min = j_per.min(axis=1)
    inverted_mask = j_min < 0
    inverted_idx = np.where(inverted_mask)[0]

    worst_idx = int(j_min.argmin())
    worst_val = float(j_min.min())

    return HexInvertedResult(
        n_hexes=n_h,
        n_inverted=int(inverted_idx.size),
        inverted_indices=[int(i) for i in inverted_idx[:100]],  # cap at 100.
        worst_j_min=worst_val,
        worst_hex_idx=worst_idx,
        elapsed_s=time.perf_counter() - t0,
    )
