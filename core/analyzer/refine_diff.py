"""Y5 / beta2734 — tet mesh refinement detector.

baseline (V_a, T_a) vs refined (V_b, T_b) → 신규 vertex/tet 위치 통계.
adaptive refinement / smoothing 효과 측정 / regression diff.

baseline vertex 들이 refined 에 포함된다고 가정 (id 또는 좌표 매칭).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass
class RefineDiffResult:
    n_v_a: int = 0
    n_v_b: int = 0
    n_v_new: int = 0
    n_t_a: int = 0
    n_t_b: int = 0
    n_t_new: int = 0
    new_v_bbox_min: tuple[float, float, float] = (0.0, 0.0, 0.0)
    new_v_bbox_max: tuple[float, float, float] = (0.0, 0.0, 0.0)
    elapsed_s: float = 0.0


def detect_refinement(
    V_a: NDArray[np.float64],
    T_a: NDArray[np.int64],
    V_b: NDArray[np.float64],
    T_b: NDArray[np.int64],
    *,
    tol: float = 1e-9,
) -> tuple[NDArray[np.int64], RefineDiffResult]:
    """V_a → V_b refinement.

    가정: V_b 는 V_a 의 super-set (좌표 ≤ tol 일치).

    Returns:
        (new_vert_indices_in_b (k,), RefineDiffResult).
    """
    import time
    t0 = time.perf_counter()

    V_a = np.asarray(V_a, dtype=np.float64)
    V_b = np.asarray(V_b, dtype=np.float64)
    T_a = np.asarray(T_a, dtype=np.int64)
    T_b = np.asarray(T_b, dtype=np.int64)
    n_a = int(V_a.shape[0])
    n_b = int(V_b.shape[0])

    # quantize coords for hashing.
    if tol > 0:
        keys_a = np.round(V_a / tol).astype(np.int64) * tol if n_a > 0 \
            else np.zeros((0, 3), dtype=np.float64)
        keys_b = np.round(V_b / tol).astype(np.int64) * tol if n_b > 0 \
            else np.zeros((0, 3), dtype=np.float64)
    else:
        keys_a = V_a
        keys_b = V_b

    set_a = set()
    for i in range(n_a):
        set_a.add((float(keys_a[i, 0]), float(keys_a[i, 1]), float(keys_a[i, 2])))

    new_idx: list[int] = []
    for i in range(n_b):
        key = (float(keys_b[i, 0]), float(keys_b[i, 1]), float(keys_b[i, 2]))
        if key not in set_a:
            new_idx.append(i)

    new_arr = np.array(new_idx, dtype=np.int64)
    if new_arr.size > 0:
        new_pts = V_b[new_arr]
        bb_min = tuple(float(x) for x in new_pts.min(axis=0))
        bb_max = tuple(float(x) for x in new_pts.max(axis=0))
    else:
        bb_min = (0.0, 0.0, 0.0)
        bb_max = (0.0, 0.0, 0.0)

    return new_arr, RefineDiffResult(
        n_v_a=n_a,
        n_v_b=n_b,
        n_v_new=int(new_arr.size),
        n_t_a=int(T_a.shape[0]),
        n_t_b=int(T_b.shape[0]),
        n_t_new=int(T_b.shape[0]) - int(T_a.shape[0]),
        new_v_bbox_min=bb_min,
        new_v_bbox_max=bb_max,
        elapsed_s=time.perf_counter() - t0,
    )
