"""C3.1 / beta2370 — Anisotropic prism splitting (cfMesh splitInternalLayers 동등).

목적:
    Boundary layer prism cell 이 wall-normal 방향으로 base edge 보다 너무
    두껍게 형성되었을 때 (high aspect ratio), 이를 wall-normal 방향으로
    mid-split 하여 wall 해상도 ×2 향상. cfMesh `splitInternalLayers` 와
    동등 — Pointwise/Star-CCM+ 의 anisotropic refinement 와 유사.

알고리즘:
    각 prism (wedge, 6-vertex) 에 대해:
        1. base triangle = (v0, v1, v2), top = (v3, v4, v5).
        2. wall-normal length = mean(|v3-v0|, |v4-v1|, |v5-v2|).
        3. base length = mean(|v1-v0|, |v2-v1|, |v0-v2|).
        4. aspect = wall_normal / base_length.
        5. aspect > threshold (default 4.0) → mid-split.
            - mid-vertex i = (base_i + top_i) / 2 → v6, v7, v8.
            - 원본 prism (v0..v5) 를 두 prism 으로 분할:
                lower = (v0,v1,v2, v6,v7,v8)
                upper = (v6,v7,v8, v3,v4,v5)

이 모듈은 pure-function 한 입력→출력 매핑만 제공. native_bl 의 후처리
(post-extrusion) 단계에 wired 될 것 (C3.2 후속).

CLAUDE.md 정책:
    - 외부 lib 신규 의존 0.
    - 단일 파일 < 350 줄.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass
class PrismSplitResult:
    """Anisotropic prism splitting 결과 통계."""

    n_input_prisms: int
    n_split_prisms: int    # 분할된 원본 prism 수.
    n_output_prisms: int   # 출력 prism 총수 (n_input - n_split + 2*n_split).
    n_new_points: int      # 추가된 mid-vertex 수.
    max_aspect_in: float   # 입력 mesh 의 최대 wall-normal aspect.
    max_aspect_out: float  # 출력 mesh 의 최대 wall-normal aspect.
    elapsed_s: float


def _prism_aspect(points: NDArray[np.float64], prism: NDArray[np.int64]) -> float:
    """Wedge prism 의 wall-normal aspect = mean(top-bot 거리) / mean(base edge)."""
    p = points[prism]  # (6, 3).
    base = p[:3]
    top = p[3:]
    # wall-normal length per stack.
    wn = np.linalg.norm(top - base, axis=1)  # (3,).
    wn_mean = float(wn.mean())
    if wn_mean <= 0.0:
        return 0.0
    e0 = np.linalg.norm(base[1] - base[0])
    e1 = np.linalg.norm(base[2] - base[1])
    e2 = np.linalg.norm(base[0] - base[2])
    base_mean = (float(e0) + float(e1) + float(e2)) / 3.0
    if base_mean <= 1e-30:
        return 0.0
    return wn_mean / base_mean


def split_thick_prisms(
    points: NDArray[np.float64],
    prisms: NDArray[np.int64],
    *,
    threshold: float = 4.0,
    max_split_per_pass: int = 1,
) -> tuple[NDArray[np.float64], NDArray[np.int64], PrismSplitResult]:
    """Wall-normal aspect > threshold 인 prism 을 mid-split.

    Args:
        points: (P, 3) 좌표.
        prisms: (N, 6) wedge connectivity (base 0..2, top 3..5).
        threshold: aspect ratio threshold (4.0 기본 — wall-normal 이 base 의 4배 초과).
        max_split_per_pass: 단일 prism 당 최대 split 횟수 (1 = halving 만,
            2 = ¼ 까지 가능). 현재 구현은 1 만 지원 (단일 mid-split).

    Returns:
        (new_points, new_prisms, PrismSplitResult).
        새 vertex 는 points 끝에 append 됨.
    """
    import time as _t
    t0 = _t.perf_counter()

    pts = np.asarray(points, dtype=np.float64)
    if pts.ndim != 2 or pts.shape[1] != 3:
        raise ValueError(f"points 는 (P,3) 형태여야 함 (got {pts.shape})")

    pr = np.asarray(prisms, dtype=np.int64)
    if pr.ndim != 2 or pr.shape[1] != 6:
        raise ValueError(f"prisms 는 (N,6) wedge 형태여야 함 (got {pr.shape})")

    n_in = int(pr.shape[0])
    if n_in == 0:
        return pts.copy(), pr.copy(), PrismSplitResult(
            n_input_prisms=0, n_split_prisms=0, n_output_prisms=0,
            n_new_points=0, max_aspect_in=0.0, max_aspect_out=0.0,
            elapsed_s=_t.perf_counter() - t0,
        )

    aspects_in = np.array(
        [_prism_aspect(pts, pr[i]) for i in range(n_in)], dtype=np.float64,
    )
    max_asp_in = float(aspects_in.max())
    to_split = aspects_in > float(threshold)
    n_split = int(to_split.sum())

    if n_split == 0:
        return pts.copy(), pr.copy(), PrismSplitResult(
            n_input_prisms=n_in, n_split_prisms=0, n_output_prisms=n_in,
            n_new_points=0, max_aspect_in=max_asp_in, max_aspect_out=max_asp_in,
            elapsed_s=_t.perf_counter() - t0,
        )

    # 분할 — 각 split 마다 3 mid-vertex 추가.
    new_pts_list: list[NDArray[np.float64]] = [pts]
    new_prisms_list: list[list[int]] = []
    n_new_points = 0
    next_pid = pts.shape[0]

    for i in range(n_in):
        if not to_split[i]:
            new_prisms_list.append(pr[i].tolist())
            continue
        v0, v1, v2, v3, v4, v5 = pr[i].tolist()
        mid_pts = 0.5 * (pts[[v0, v1, v2]] + pts[[v3, v4, v5]])  # (3, 3).
        new_pts_list.append(mid_pts)
        m0, m1, m2 = next_pid, next_pid + 1, next_pid + 2
        next_pid += 3
        n_new_points += 3
        # lower: (v0,v1,v2, m0,m1,m2)
        new_prisms_list.append([v0, v1, v2, m0, m1, m2])
        # upper: (m0,m1,m2, v3,v4,v5)
        new_prisms_list.append([m0, m1, m2, v3, v4, v5])

    new_points = np.vstack(new_pts_list) if len(new_pts_list) > 1 else pts.copy()
    new_prisms = np.array(new_prisms_list, dtype=np.int64)

    # 출력 mesh 의 최대 aspect 측정 (split 후 ~aspect/2 기대).
    aspects_out = np.array(
        [_prism_aspect(new_points, new_prisms[k]) for k in range(new_prisms.shape[0])],
        dtype=np.float64,
    )
    max_asp_out = float(aspects_out.max()) if aspects_out.size else 0.0

    return new_points, new_prisms, PrismSplitResult(
        n_input_prisms=n_in,
        n_split_prisms=n_split,
        n_output_prisms=int(new_prisms.shape[0]),
        n_new_points=n_new_points,
        max_aspect_in=max_asp_in,
        max_aspect_out=max_asp_out,
        elapsed_s=_t.perf_counter() - t0,
    )
