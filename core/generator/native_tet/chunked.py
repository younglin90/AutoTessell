"""P5 — Chunked Delaunay for large inputs.

100k+ vertex 가 들어오면 scipy.spatial.Delaunay 가 메모리 bound 에 부딪힘.
본 모듈은 점 집합을 공간 octant / grid 청크로 분할해 각 청크 독립
Delaunay 후 청크 경계 tet 을 stitch 하는 간단한 greedy 전략을 제공한다.

전략
    1) AABB 를 n × n × n grid 로 분할.
    2) 각 셀 + 이웃 overlap 영역 점을 모아 독립 Delaunay.
    3) 전체 결과 tet 중 이웃 영역 stitch 에 속한 tet 은 중복 제거.

주의
    본 MVP 는 **근사** 통합이라 결과가 전체 Delaunay 와 엄격히 같진 않다.
    fTetWild 처럼 대형 입력 처리용 "분할 정복" 스켈레톤.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class ChunkedResult:
    n_chunks: int
    n_points: int
    n_tets: int
    n_overlap_filtered: int
    elapsed_s: float = 0.0


def _chunk_bounds(
    V: np.ndarray, n_div: int,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """C-PERF-32 / beta2483 — vectorize via np.indices."""
    mn = V.min(axis=0)
    mx = V.max(axis=0)
    step = (mx - mn) / float(n_div)
    ii, jj, kk = np.indices((n_div, n_div, n_div))
    ijk = np.stack(
        [ii.ravel(), jj.ravel(), kk.ravel()], axis=1,
    ).astype(np.float64)
    cmins = mn[None, :] + step[None, :] * ijk
    cmaxs = mn[None, :] + step[None, :] * (ijk + 1.0)
    return [(cmins[i], cmaxs[i]) for i in range(cmins.shape[0])]


def chunked_delaunay(
    V: np.ndarray, *,
    n_div: int = 2,
    overlap_ratio: float = 0.15,
) -> tuple[np.ndarray, np.ndarray, ChunkedResult]:
    """공간 청크 기반 Delaunay + 청크 경계 tet merge.

    Args:
        V: (N, 3) 점.
        n_div: 각 축 분할 수 (총 chunk = n_div^3).
        overlap_ratio: 이웃 청크 간 겹침 범위 (청크 크기 대비 비율).

    Returns:
        (pts_out, tets_out, info).
    """
    import time
    from scipy.spatial import Delaunay

    V = np.asarray(V, dtype=np.float64)
    t0 = time.perf_counter()

    if V.shape[0] < 4:
        return V, np.zeros((0, 4), dtype=np.int64), ChunkedResult(0, int(V.shape[0]), 0, 0, 0.0)

    # 청크 < 4 점이면 전부 한 번에.
    if n_div <= 1 or V.shape[0] < 200:
        D = Delaunay(V)
        return V, np.asarray(D.simplices, dtype=np.int64), ChunkedResult(
            1, int(V.shape[0]), int(D.simplices.shape[0]), 0,
            time.perf_counter() - t0,
        )

    bounds = _chunk_bounds(V, int(n_div))
    step = (V.max(axis=0) - V.min(axis=0)) / float(n_div)
    pad = step * float(overlap_ratio)

    all_tets_list: list[np.ndarray] = []
    seen: set[tuple[int, int, int, int]] = set()
    n_overlap = 0
    for (cmin, cmax) in bounds:
        lo = cmin - pad
        hi = cmax + pad
        mask = np.all((V >= lo) & (V <= hi), axis=1)
        idx_local = np.where(mask)[0]
        if idx_local.size < 4:
            continue
        Vc = V[idx_local]
        try:
            D = Delaunay(Vc)
        except Exception:
            continue
        # 각 tet 의 centroid 가 이 청크의 중심 영역 (cmin, cmax) 안에 있을 때만 채택.
        cen = Vc[D.simplices].mean(axis=1)
        center_mask = np.all(
            (cen >= cmin - 1e-12) & (cen <= cmax + 1e-12), axis=1,
        )
        keep = D.simplices[center_mask]
        # global index 로 변환.
        gtets = idx_local[keep]
        # canonical dedup.
        for row in gtets.tolist():
            key = tuple(sorted(row))
            if key in seen:
                n_overlap += 1
                continue
            seen.add(key)
            all_tets_list.append(row)

    tets_out = np.asarray(all_tets_list, dtype=np.int64) if all_tets_list \
        else np.zeros((0, 4), dtype=np.int64)
    return V, tets_out, ChunkedResult(
        n_chunks=len(bounds),
        n_points=int(V.shape[0]),
        n_tets=int(tets_out.shape[0]),
        n_overlap_filtered=int(n_overlap),
        elapsed_s=time.perf_counter() - t0,
    )
