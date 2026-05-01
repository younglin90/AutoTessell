"""GAP4 / beta2764 — Post-extrude BL aspect ratio cap enforcer.

목적 (Pointwise T-Rex parity, aspect 11500 → 1000):
    LCR 후에도 aspect > target 인 prism wedge 가 있으면, outer node 를 wall normal
    방향으로 끌어당겨 (shrink) prism height 를 강제로 감소.

알고리즘 (per prism):
    1. 6-vertex prism = (wall 3, outer 3). edge length 측정.
    2. aspect_current = max_edge / min_edge across all 9 edges.
    3. aspect_current > target → 새 outer = wall + (outer - wall) * scale,
       scale 은 aspect = target 가 되도록 binary search (max 8 iter).
    4. 같은 outer vertex 가 여러 prism 에 공유될 때 가장 작은 scale 사용 (보수적).

monotone guard:
    outer vertex 는 wall 쪽으로만 이동 (절대 outward 안 됨).
    각 vertex 의 누적 scale ≥ 0.05 (5% 이하로는 줄이지 않음 — degenerate 회피).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass
class AspectCapResult:
    n_prisms: int = 0
    n_violations_pre: int = 0       # aspect > target 였던 prism.
    n_violations_post: int = 0      # 적용 후에도 남은 위반.
    aspect_max_pre: float = 0.0
    aspect_max_post: float = 0.0
    aspect_mean_pre: float = 0.0
    aspect_mean_post: float = 0.0
    n_outer_modified: int = 0       # 위치 바뀐 outer vertex 수.
    elapsed_s: float = 0.0


def _prism_aspect(p: NDArray[np.float64]) -> float:
    """6-vertex prism (wall 3, outer 3) → max_edge / min_edge."""
    # 9 edges: 3 wall, 3 outer, 3 vertical.
    edges = np.array([
        [0, 1], [1, 2], [2, 0],   # wall
        [3, 4], [4, 5], [5, 3],   # outer
        [0, 3], [1, 4], [2, 5],   # vertical
    ], dtype=np.int64)
    L = np.linalg.norm(p[edges[:, 1]] - p[edges[:, 0]], axis=1)
    L_max = float(L.max())
    L_min = float(L.min())
    if L_min < 1e-30:
        return 1e9
    return L_max / L_min


def _shrink_outer_to_target(
    wall: NDArray[np.float64],
    outer: NDArray[np.float64],
    target_aspect: float,
    *,
    min_scale: float = 0.05,
    max_iter: int = 8,
) -> tuple[NDArray[np.float64], float]:
    """outer 를 wall 쪽으로 binary search 로 scale → aspect ≤ target.

    Returns:
        (new_outer, scale_applied). scale=1.0 → no change.
    """
    p_full = np.vstack([wall, outer])
    a_full = _prism_aspect(p_full)
    if a_full <= target_aspect:
        return outer, 1.0

    lo, hi = float(min_scale), 1.0
    best_outer = outer
    best_scale = 1.0

    for _ in range(int(max_iter)):
        mid = 0.5 * (lo + hi)
        new_outer = wall + (outer - wall) * mid
        p = np.vstack([wall, new_outer])
        a = _prism_aspect(p)
        if a <= target_aspect:
            best_outer = new_outer
            best_scale = mid
            lo = mid   # try a bit more (less shrink).
        else:
            hi = mid   # need more shrink.

    return best_outer, best_scale


def enforce_prism_aspect_cap_v2(
    pts: NDArray[np.float64],
    prisms: NDArray[np.int64],
    *,
    target_aspect: float = 1000.0,
    min_height_factor: float = 0.05,
) -> tuple[NDArray[np.float64], AspectCapResult]:
    """GAP-BL / beta2778 — direct height shrink (degenerate wall 도 작동).

    이전 v1: outer 를 wall 쪽으로 binary search (degenerate wall = 작은 wall edge
    인 경우 outer 줄여도 aspect 안 줄어듦, 1017017 같은 extreme 무효).

    v2: outer node 의 height (== prism direction) 를 직접 축소.
        새 outer = wall_centroid + outer_dir * (h * scale)
        h = 원래 height. scale = target_aspect / current_aspect (clamped).
        wall_edge_max 와 무관하게 wall→outer 거리 직접 제어.
    """
    import time
    t0 = time.perf_counter()

    pts = np.asarray(pts, dtype=np.float64).copy()
    prisms = np.asarray(prisms, dtype=np.int64)
    n_p = int(prisms.shape[0])
    if n_p == 0:
        return pts, AspectCapResult(elapsed_s=time.perf_counter() - t0)

    # pre stats.
    aspects_pre = np.zeros(n_p, dtype=np.float64)
    for i in range(n_p):
        aspects_pre[i] = _prism_aspect(pts[prisms[i]])
    n_viol_pre = int((aspects_pre > target_aspect).sum())

    # 각 outer vertex 별 가장 보수적 (smallest) height scale.
    outer_scale: dict[int, float] = {}
    outer_orig_height: dict[int, tuple[float, np.ndarray, np.ndarray]] = {}

    for i in range(n_p):
        if aspects_pre[i] <= target_aspect:
            continue
        wall_idx = prisms[i, :3]
        outer_idx = prisms[i, 3:]
        wall_pts = pts[wall_idx]
        outer_pts = pts[outer_idx]
        wall_centroid = wall_pts.mean(axis=0)

        # 각 outer vertex 별 height (wall_centroid → outer_v).
        for k in range(3):
            oi = int(outer_idx[k])
            wi = int(wall_idx[k])
            wall_v = pts[wi]  # paired wall vertex.
            outer_v = pts[oi]
            h_vec = outer_v - wall_v
            h = float(np.linalg.norm(h_vec))
            if h < 1e-30:
                continue
            # required scale: target / current aspect.
            target_scale = target_aspect / float(aspects_pre[i])
            # 최소 scale 한도.
            target_scale = max(min_height_factor, min(1.0, target_scale))
            if oi not in outer_scale or target_scale < outer_scale[oi]:
                outer_scale[oi] = target_scale
                outer_orig_height[oi] = (h, wall_v.copy(), outer_v.copy())

    # 적용.
    n_modified = 0
    for oi, scale in outer_scale.items():
        if scale >= 1.0 - 1e-9:
            continue
        if oi not in outer_orig_height:
            continue
        h_orig, wall_v, outer_orig = outer_orig_height[oi]
        h_dir = outer_orig - wall_v
        h_norm = np.linalg.norm(h_dir)
        if h_norm < 1e-30:
            continue
        h_unit = h_dir / h_norm
        new_outer = wall_v + h_unit * (h_orig * scale)
        pts[oi] = new_outer
        n_modified += 1

    # post stats.
    aspects_post = np.zeros(n_p, dtype=np.float64)
    for i in range(n_p):
        aspects_post[i] = _prism_aspect(pts[prisms[i]])
    n_viol_post = int((aspects_post > target_aspect).sum())

    return pts, AspectCapResult(
        n_prisms=n_p,
        n_violations_pre=n_viol_pre,
        n_violations_post=n_viol_post,
        aspect_max_pre=float(aspects_pre.max()),
        aspect_max_post=float(aspects_post.max()),
        aspect_mean_pre=float(aspects_pre.mean()),
        aspect_mean_post=float(aspects_post.mean()),
        n_outer_modified=n_modified,
        elapsed_s=time.perf_counter() - t0,
    )


def enforce_prism_aspect_cap(
    pts: NDArray[np.float64],
    prisms: NDArray[np.int64],
    *,
    target_aspect: float = 1000.0,
    min_scale: float = 0.05,
) -> tuple[NDArray[np.float64], AspectCapResult]:
    """post-extrude aspect cap enforcement.

    Args:
        pts: (N, 3). 일반적으로 outer vertex 가 다수 prism 에 공유됨.
        prisms: (P, 6). [wall_0, wall_1, wall_2, outer_0, outer_1, outer_2].
        target_aspect: 목표 max aspect ratio.
        min_scale: outer vertex 누적 scale 하한 (0.05 = 5%).

    Returns:
        (new_pts (수정된 outer 포함), AspectCapResult).
    """
    import time
    t0 = time.perf_counter()

    pts = np.asarray(pts, dtype=np.float64).copy()
    prisms = np.asarray(prisms, dtype=np.int64)
    n_p = int(prisms.shape[0])

    if n_p == 0:
        return pts, AspectCapResult(elapsed_s=time.perf_counter() - t0)

    # pre stats.
    aspects_pre = np.zeros(n_p, dtype=np.float64)
    for i in range(n_p):
        aspects_pre[i] = _prism_aspect(pts[prisms[i]])

    n_viol_pre = int((aspects_pre > target_aspect).sum())

    # outer vertex 별 최소 scale 누적 (보수적).
    # outer index 는 prisms[:, 3:6].
    outer_min_scale: dict[int, float] = {}
    outer_orig_pos: dict[int, NDArray[np.float64]] = {}

    for i in range(n_p):
        if aspects_pre[i] <= target_aspect:
            continue
        wall_idx = prisms[i, :3]
        outer_idx = prisms[i, 3:]
        wall_pts = pts[wall_idx]
        outer_pts = pts[outer_idx]
        # 3 outer vertex 를 한꺼번에 (각각 wall_k 와 짝).
        # 보수적 접근: 같은 scale s 로 3 vertex 동시 → wall + (outer - wall) * s.
        new_outer, s = _shrink_outer_to_target(
            wall_pts, outer_pts, target_aspect, min_scale=min_scale,
        )
        # 각 outer vertex 에 대해 누적 scale (min 으로 보수적 합성).
        for k in range(3):
            oi = int(outer_idx[k])
            if oi not in outer_orig_pos:
                outer_orig_pos[oi] = pts[oi].copy()
                outer_min_scale[oi] = 1.0
            outer_min_scale[oi] = min(outer_min_scale[oi], float(s))

    # outer pts 갱신: 원래 wall side 추정 어려움 → 평균 wall 위치 활용.
    # 단순화: outer_orig_pos 와 paired wall 평균 사이를 scale 만큼.
    # 더 정확: prism 별 wall_centroid 와 outer 사이 → scale.
    # 여기서는 vertex 별 최소 scale 만 적용 (모든 paired wall 평균 사용).
    n_modified = 0
    if outer_min_scale:
        # outer vertex 별 paired wall mean 위치 추출.
        outer_to_wall_pts: dict[int, list[NDArray[np.float64]]] = {}
        for i in range(n_p):
            if aspects_pre[i] <= target_aspect:
                continue
            for k in range(3):
                oi = int(prisms[i, 3 + k])
                wi = int(prisms[i, k])
                if oi in outer_min_scale:
                    outer_to_wall_pts.setdefault(oi, []).append(pts[wi])

        for oi, scale in outer_min_scale.items():
            if scale >= 1.0 - 1e-9:
                continue
            wall_neighbors = outer_to_wall_pts.get(oi)
            if not wall_neighbors:
                continue
            wmean = np.mean(wall_neighbors, axis=0)
            orig = outer_orig_pos[oi]
            new_pos = wmean + (orig - wmean) * scale
            pts[oi] = new_pos
            n_modified += 1

    # post stats.
    aspects_post = np.zeros(n_p, dtype=np.float64)
    for i in range(n_p):
        aspects_post[i] = _prism_aspect(pts[prisms[i]])
    n_viol_post = int((aspects_post > target_aspect).sum())

    return pts, AspectCapResult(
        n_prisms=n_p,
        n_violations_pre=n_viol_pre,
        n_violations_post=n_viol_post,
        aspect_max_pre=float(aspects_pre.max()),
        aspect_max_post=float(aspects_post.max()),
        aspect_mean_pre=float(aspects_pre.mean()),
        aspect_mean_post=float(aspects_post.mean()),
        n_outer_modified=n_modified,
        elapsed_s=time.perf_counter() - t0,
    )
