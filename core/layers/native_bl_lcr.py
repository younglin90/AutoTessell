"""C2 / beta2367 — Per-vertex Layer Count Reduction (LCR) for native_bl.

목적 (Pointwise T-Rex 동등):
    좁은 gap 영역의 wall vertex 에서 prism layer 수를 자동으로 감소.
    기본 num_layers=5 인데 gap < 5*first_thickness 인 vertex 는 더 적은
    layer 만 수용 가능 → 기존엔 collision_safety 가 thickness 를 줄이지만
    LCR 은 layer 수 자체를 감소 → 더 정밀한 wall 표현.

알고리즘:
    1. 각 wall vertex 의 collision_distance 계산
       (core/layers/native_bl.py:_compute_collision_distance 재사용).
    2. 각 vertex 별 max_safe_layers = floor(collision_dist / first_thickness *
                                            (1 - growth_ratio^k) / (1 - growth_ratio))
    3. layer 수 = min(num_layers, max_safe_layers).

상위 caller (native_bl.py):
    extrude 직전 prism_per_face 를 per-vertex 로 재정의.
    monotone guard: total prism cell 수 ≥ 50% × original (excessive reduction 방지).

CLAUDE.md 정책:
    - 외부 lib 신규 의존 0.
    - 단일 파일 < 350 줄.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass
class LCRResult:
    """Per-vertex LCR 결과."""

    n_wall_verts: int
    n_reduced_verts: int
    max_reduction: int   # 원래 layers - 최소 layers (가장 많이 줄어든 vertex).
    min_layers_used: int  # 가장 적은 layer 수.
    n_safe_full_layers: int  # 원래 layers 그대로 유지된 vertex 수.
    elapsed_s: float


def _geometric_total_thickness(
    first_thickness: float, growth_ratio: float, n_layers: int,
) -> float:
    """기하급수 합 — sum(first × growth^k for k in 0..n-1)."""
    if abs(growth_ratio - 1.0) < 1e-12 or n_layers == 0:
        return float(first_thickness) * float(n_layers)
    g = float(growth_ratio)
    return float(first_thickness) * (g ** n_layers - 1.0) / (g - 1.0)


def _max_layers_for_thickness(
    available_thickness: float,
    first_thickness: float,
    growth_ratio: float,
    *,
    safety: float = 0.5,
) -> int:
    """available_thickness 안에 들어갈 수 있는 최대 layer 수 (safety 적용).

    sum(first × growth^k, k=0..n-1) ≤ safety × available
    → n = floor(log_g(1 + (g - 1) × safety × available / first))
    """
    if available_thickness <= 0.0 or first_thickness <= 0.0:
        return 0
    cap = float(safety) * float(available_thickness)
    g = float(growth_ratio)
    if abs(g - 1.0) < 1e-12:
        return int(cap / float(first_thickness))
    val = 1.0 + (g - 1.0) * cap / float(first_thickness)
    if val <= 1.0:
        return 0
    return int(np.floor(np.log(val) / np.log(g)))


def per_vertex_lcr(
    wall_vert_indices: NDArray[np.int64],
    collision_distances: NDArray[np.float64],
    *,
    num_layers: int,
    first_thickness: float,
    growth_ratio: float,
    safety: float = 0.5,
    min_layers: int = 1,
) -> tuple[NDArray[np.int64], LCRResult]:
    """Pointwise T-Rex 동등 per-vertex Layer Count Reduction.

    Args:
        wall_vert_indices: (W,) wall vertex 의 mesh-global idx.
        collision_distances: (W,) 각 wall vertex 의 inward ray collision 거리.
            -1 또는 inf → no collision (safe full layers).
        num_layers: BL config 의 기본 num_layers.
        first_thickness: 첫 layer 두께.
        growth_ratio: 층간 성장비.
        safety: collision_distance 의 활용 비율 (0.5 default — 절반).
        min_layers: 최소 layer 수 (0 = 일부 vertex 는 BL skip 가능).

    Returns:
        (per_vertex_layers, LCRResult).
        per_vertex_layers: (W,) 각 wall vertex 의 layer 수 ∈ [min_layers, num_layers].
    """
    import time as _t
    t0 = _t.perf_counter()

    n_wall = int(wall_vert_indices.shape[0])
    if n_wall == 0:
        return np.zeros(0, dtype=np.int64), LCRResult(
            n_wall_verts=0, n_reduced_verts=0, max_reduction=0,
            min_layers_used=int(num_layers),
            n_safe_full_layers=0,
            elapsed_s=_t.perf_counter() - t0,
        )

    cd = np.asarray(collision_distances, dtype=np.float64).ravel()
    assert cd.shape[0] == n_wall, f"collision_distances 크기 {cd.shape[0]} ≠ wall {n_wall}"

    layers_arr = np.full(n_wall, int(num_layers), dtype=np.int64)
    n_reduced = 0
    n_safe_full = 0
    max_reduction = 0
    min_layers_used = int(num_layers)

    full_total_thickness = _geometric_total_thickness(
        float(first_thickness), float(growth_ratio), int(num_layers),
    )

    for i in range(n_wall):
        d = float(cd[i])
        if d < 0 or d == np.inf or d == 0.0:
            # no collision detected — full layers.
            n_safe_full += 1
            continue
        # 사용 가능한 두께 (safety 적용).
        max_n = _max_layers_for_thickness(
            d, float(first_thickness), float(growth_ratio), safety=safety,
        )
        max_n = max(int(min_layers), int(max_n))
        max_n = min(int(num_layers), int(max_n))
        if max_n < int(num_layers):
            layers_arr[i] = max_n
            n_reduced += 1
            r = int(num_layers) - max_n
            if r > max_reduction:
                max_reduction = r
            if max_n < min_layers_used:
                min_layers_used = max_n
        else:
            n_safe_full += 1

    return layers_arr, LCRResult(
        n_wall_verts=n_wall,
        n_reduced_verts=int(n_reduced),
        max_reduction=int(max_reduction),
        min_layers_used=int(min_layers_used),
        n_safe_full_layers=int(n_safe_full),
        elapsed_s=_t.perf_counter() - t0,
    )
