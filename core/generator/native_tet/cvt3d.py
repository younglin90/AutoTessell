"""C1.3 / beta2362 — Volumetric Lloyd CVT 3D (fTetWild §3.6 Centroidal Voronoi
Tessellation in 3D for tet interior vertex relocation).

목적:
    tet mesh 의 interior vertex (surface 가 아닌) 를 1-ring tet centroid 평균
    으로 이동 → 더 isotropic 한 tet → mean_q / min_q 향상 → grade A 도달도 ↑.

알고리즘 (Lloyd 1982 in 3D):
    for iter in range(n_iter):
        for each interior vertex v:
            target[v] = mean of incident tet centroids
        # surface vertex 는 envelope-bounded relocate (separate, fTetWild §3.5).
        for each interior vertex v:
            v <- (1 - relax) * v + relax * target[v]
        # monotone guard: post min_q drop ≤ 0.015, mean improve.
        if reject: revert.

상위 caller (mesher.py):
    Phase B/C 후 final_pts/final_tets 직전. RRR2 (AMIPS analytic) 와 다른
    relaxation pass — Lloyd 는 geometric centroid 기반, AMIPS 는 analytic
    energy 기반. 두 방법은 보완적.

CLAUDE.md 정책 준수:
    - 외부 lib 신규 의존 0 (numpy + 기존 quality.py).
    - monotone guard 표준 (worst -0.015 + mean improve, beta2307 / beta2320).
    - 단일 파일 < 350 줄.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass
class CVT3DResult:
    """Volumetric Lloyd 결과."""

    n_iter_used: int
    n_moved: int
    pre_min_q: float
    post_min_q: float
    pre_mean_q: float
    post_mean_q: float
    accepted: bool
    elapsed_s: float


def _tet_centroids(
    pts: NDArray[np.float64],
    tets: NDArray[np.int64],
) -> NDArray[np.float64]:
    """각 tet 의 centroid (4-vertex 평균). (T, 3)."""
    return pts[tets].mean(axis=1)


def _interior_vertex_mask(
    n_vertices: int,
    n_surface: int,
    locked_ids: NDArray[np.intp] | None = None,
) -> NDArray[np.bool_]:
    """interior 표시 mask. surface (idx < n_surface) + locked 제외."""
    mask = np.ones(n_vertices, dtype=np.bool_)
    if n_surface > 0:
        mask[:min(n_surface, n_vertices)] = False
    if locked_ids is not None and len(locked_ids) > 0:
        for vi in np.asarray(locked_ids).ravel():
            if 0 <= int(vi) < n_vertices:
                mask[int(vi)] = False
    return mask


def lloyd_cvt_3d(
    pts: NDArray[np.float64],
    tets: NDArray[np.int64],
    *,
    n_surface: int,
    n_iter: int = 3,
    relax: float = 0.5,
    locked_ids: NDArray[np.intp] | None = None,
    monotone_worst_drop_max: float = 0.015,
    monotone_mean_min: float = -1e-12,
) -> tuple[NDArray[np.float64], CVT3DResult]:
    """Volumetric Lloyd CVT 3D — interior vertex 를 1-ring tet centroid 평균으로 relax.

    Args:
        pts: (N, 3) vertex positions.
        tets: (T, 4) tet indices.
        n_surface: 첫 n_surface vertex 는 surface 로 간주 (제외).
        n_iter: Lloyd 반복 횟수 (3 = 안정적, 5+ = 더 isotropic 하지만 시간↑).
        relax: relaxation factor (0.5 = 50% 이동, 보수적).
        locked_ids: 추가로 잠글 vertex idx (envelope/feature lock 등).
        monotone_worst_drop_max: 허용 worst quality 하락 (RRR2/SSS 와 동일 0.015).
        monotone_mean_min: mean_q 변화 최소 (-1e-12 = 향상 또는 동등).

    Returns:
        (new_pts, CVT3DResult). reject 시 new_pts 는 원본 동일.
    """
    import time as _t
    t0 = _t.perf_counter()

    pts = np.asarray(pts, dtype=np.float64)
    tets = np.asarray(tets, dtype=np.int64)
    n_v = int(pts.shape[0])
    n_t = int(tets.shape[0])

    # quality snapshot (top-level import 회피 — caller 와 다른 quality.py 사용 가능).
    from core.generator.native_tet.quality import tet_shape_quality as _tsq  # noqa: PLC0415

    if n_t < 5 or n_v < 4:
        return pts.copy(), CVT3DResult(
            n_iter_used=0, n_moved=0,
            pre_min_q=-1.0, post_min_q=-1.0,
            pre_mean_q=-1.0, post_mean_q=-1.0,
            accepted=False, elapsed_s=_t.perf_counter() - t0,
        )

    pre_q = _tsq(pts, tets)
    pre_min = float(pre_q.min())
    pre_mean = float(pre_q.mean())

    # interior mask + neighbor list.
    interior_mask = _interior_vertex_mask(n_v, n_surface, locked_ids)
    interior_idx = np.where(interior_mask)[0]
    if interior_idx.size == 0:
        # 모든 vertex 가 surface — Lloyd 적용 대상 없음. 원본 그대로.
        return pts.copy(), CVT3DResult(
            n_iter_used=0, n_moved=0,
            pre_min_q=pre_min, post_min_q=pre_min,
            pre_mean_q=pre_mean, post_mean_q=pre_mean,
            accepted=False, elapsed_s=_t.perf_counter() - t0,
        )

    # C-PERF-16 / beta2465 — vectorize per-vertex Lloyd target via scatter-sum.
    # Replaces O(V) Python loop + per-vertex numpy mean with single np.add.at +
    # broadcast — speedup ~10-50× for V > 1k.
    cur_pts = pts.copy()
    n_moved_total = 0
    last_iter = 0
    relax_f = float(relax)
    # P3.1 / beta2586 — quality-weighted Lloyd opt-in. env=1 시 worst tet 의
    # centroid 가 (1/q) 가중되어 sliver 영역으로 강하게 pull. monotone guard
    # 가 final accept/reject 하므로 안전.
    import os as _os_p31
    _qw = _os_p31.environ.get("AUTO_TESSELL_CVT3D_QUALITY_WEIGHT", "0") == "1"
    for it in range(int(n_iter)):
        # Lloyd target = 인접 tet centroid 평균 (scatter-sum vectorized).
        centroids = _tet_centroids(cur_pts, tets)              # (T, 3)
        flat_v = tets.reshape(-1)                              # (T*4,)
        if _qw:
            # P3.1 — quality-weighted: poor tet (q < 0.3) → weight = 1/(q+0.05).
            #   high-q tet → weight ≈ 1.0. clamp to [0.95, 20] for stability.
            tet_q = _tsq(cur_pts, tets)
            tet_w = np.clip(1.0 / (tet_q + 0.05), 0.95, 20.0)  # (T,)
            flat_w = np.repeat(tet_w, 4)                        # (T*4,)
            flat_c = np.repeat(centroids * tet_w[:, None], 4, axis=0)  # (T*4, 3)
            sums = np.zeros((n_v, 3), dtype=np.float64)
            wts = np.zeros(n_v, dtype=np.float64)
            np.add.at(sums, flat_v, flat_c)
            np.add.at(wts, flat_v, flat_w)
            nz = wts > 0
            targets = np.zeros_like(sums)
            targets[nz] = sums[nz] / wts[nz, None]
            counts = (wts > 0).astype(np.int64)  # for movable mask compat.
        else:
            flat_c = np.repeat(centroids, 4, axis=0)               # (T*4, 3)
            sums = np.zeros((n_v, 3), dtype=np.float64)
            counts = np.zeros(n_v, dtype=np.int64)
            np.add.at(sums, flat_v, flat_c)
            np.add.at(counts, flat_v, 1)
            nz = counts > 0
            targets = np.zeros_like(sums)
            targets[nz] = sums[nz] / counts[nz, None]
        # Update only interior vertices that actually have ≥ 1 incident tet.
        movable = interior_mask & nz
        movable_idx = np.where(movable)[0]
        new_pts = cur_pts.copy()
        new_pts[movable_idx] = (
            (1.0 - relax_f) * cur_pts[movable_idx]
            + relax_f * targets[movable_idx]
        )

        # iteration 간 monotone check (cumulative — 최종 accept/reject).
        cur_pts = new_pts
        n_moved_total += int(movable_idx.size)
        last_iter = it + 1

    # Final monotone guard — pre vs post (cumulative).
    post_q = _tsq(cur_pts, tets)
    post_min = float(post_q.min())
    post_mean = float(post_q.mean())
    worst_drop = pre_min - post_min
    mean_gain = post_mean - pre_mean
    accepted = bool(
        worst_drop <= float(monotone_worst_drop_max)
        and mean_gain >= float(monotone_mean_min)
    )

    final_pts = cur_pts if accepted else pts.copy()
    return final_pts, CVT3DResult(
        n_iter_used=last_iter,
        n_moved=int(n_moved_total),
        pre_min_q=pre_min,
        post_min_q=post_min,
        pre_mean_q=pre_mean,
        post_mean_q=post_mean,
        accepted=accepted,
        elapsed_s=_t.perf_counter() - t0,
    )
