"""C5 / beta2365 — Multithreaded chunked Delaunay (concurrent.futures).

목적:
    fTetWild full-CGAL parallel 동등 — 100k+ vertex mesh 의 Delaunay 시간을
    n_cpu 만큼 분담. scipy QHull 자체는 single-thread 이므로 chunk 별로
    independent process 에 분배.

알고리즘 (Phase 5 W3):
    1. 기존 chunked_delaunay 의 chunk 분할 그대로 활용.
    2. 각 chunk 의 Delaunay 호출을 ProcessPoolExecutor 에 dispatch.
    3. 결과 merge — 기존 chunked 의 dedup 로직 재사용.

CLAUDE.md 정책 준수:
    - stdlib concurrent.futures 만 사용 (외부 lib 신규 의존 0).
    - 단일 파일 < 350 줄.
    - n_cpu ≥ 2 일 때만 활성, 그 외 단일 process fallback.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass

import numpy as np

from core.utils.logging import get_logger

log = get_logger(__name__)


@dataclass
class ParallelDelaunayResult:
    """병렬 Delaunay 결과."""

    n_chunks: int
    n_workers: int
    elapsed_s: float
    speedup_estimate: float


def _delaunay_one_chunk(
    points_chunk: np.ndarray,
) -> np.ndarray:
    """단일 chunk 의 Delaunay 호출 — multiprocessing worker 진입점.

    pickle-able 시그너쳐 (np.ndarray in/out only) 필요.
    """
    from scipy.spatial import Delaunay
    if points_chunk.shape[0] < 4:
        return np.zeros((0, 4), dtype=np.int64)
    try:
        D = Delaunay(points_chunk)
        return np.asarray(D.simplices, dtype=np.int64)
    except Exception:
        return np.zeros((0, 4), dtype=np.int64)


def parallel_chunked_delaunay(
    V: np.ndarray,
    *,
    n_div: int = 2,
    overlap_ratio: float = 0.15,
    n_workers: int | None = None,
) -> tuple[np.ndarray, np.ndarray, ParallelDelaunayResult]:
    """fTetWild §3.x 동등 multithreaded chunked Delaunay.

    Args:
        V: (N, 3) 점.
        n_div: 각 축 분할 수 (총 chunk = n_div^3, default 2 → 8 chunks).
        overlap_ratio: 이웃 청크 간 겹침 비율.
        n_workers: ProcessPool worker 수. None=os.cpu_count().

    Returns:
        (pts_out, tets_out, ParallelDelaunayResult).

    Note: chunked.py 의 단일-process 버전과 결과 호환 (dedup + merge 동일).
    n_chunks=1 또는 n_workers=1 일 때 자동 fallback.
    """
    from concurrent.futures import ProcessPoolExecutor, as_completed

    V = np.asarray(V, dtype=np.float64)
    t0 = time.perf_counter()
    n_v = int(V.shape[0])

    # 작은 mesh — chunked 무의미, 단일 호출 fallback.
    if n_v < 200 or n_div < 2:
        from core.generator.native_tet.chunked import chunked_delaunay
        pts, tets, _info = chunked_delaunay(V, n_div=1, overlap_ratio=overlap_ratio)
        return pts, tets, ParallelDelaunayResult(
            n_chunks=1, n_workers=1,
            elapsed_s=time.perf_counter() - t0,
            speedup_estimate=1.0,
        )

    if n_workers is None:
        n_workers = max(1, int(os.cpu_count() or 1))
    n_workers = min(n_workers, n_div ** 3)

    # n_workers=1 → ProcessPool 없이 단일 호출.
    if n_workers <= 1:
        from core.generator.native_tet.chunked import chunked_delaunay
        pts, tets, _info = chunked_delaunay(V, n_div=n_div, overlap_ratio=overlap_ratio)
        return pts, tets, ParallelDelaunayResult(
            n_chunks=n_div ** 3, n_workers=1,
            elapsed_s=time.perf_counter() - t0,
            speedup_estimate=1.0,
        )

    # 청크 분할 (chunked.py 의 _chunk_bounds 재사용).
    from core.generator.native_tet.chunked import _chunk_bounds
    bounds = _chunk_bounds(V, int(n_div))
    step = (V.max(axis=0) - V.min(axis=0)) / float(n_div)
    pad = step * float(overlap_ratio)

    # 각 chunk 의 indices.
    chunks: list[tuple[np.ndarray, np.ndarray]] = []   # (idx_local, Vc)
    for (cmin, cmax) in bounds:
        lo = cmin - pad
        hi = cmax + pad
        mask = np.all((V >= lo) & (V <= hi), axis=1)
        idx_local = np.where(mask)[0]
        if idx_local.size < 4:
            continue
        chunks.append((idx_local, V[idx_local]))

    if not chunks:
        # 모든 chunk 가 비어있음 — fallback.
        from core.generator.native_tet.chunked import chunked_delaunay
        pts, tets, _info = chunked_delaunay(V, n_div=1, overlap_ratio=overlap_ratio)
        return pts, tets, ParallelDelaunayResult(
            n_chunks=0, n_workers=n_workers,
            elapsed_s=time.perf_counter() - t0,
            speedup_estimate=1.0,
        )

    # ProcessPool dispatch — 각 chunk 의 Delaunay 병렬 실행.
    chunk_results: list[tuple[np.ndarray, np.ndarray]] = []  # (idx_local, simplices_local)
    try:
        with ProcessPoolExecutor(max_workers=n_workers) as executor:
            futures = {
                executor.submit(_delaunay_one_chunk, Vc): idx_local
                for idx_local, Vc in chunks
            }
            for fut in as_completed(futures):
                idx_local = futures[fut]
                simplices_local = fut.result()
                chunk_results.append((idx_local, simplices_local))
    except Exception:
        # ProcessPool 실패 시 (pickle 등) 단일 호출 fallback.
        from core.generator.native_tet.chunked import chunked_delaunay
        pts, tets, _info = chunked_delaunay(V, n_div=n_div, overlap_ratio=overlap_ratio)
        return pts, tets, ParallelDelaunayResult(
            n_chunks=len(chunks), n_workers=1,
            elapsed_s=time.perf_counter() - t0,
            speedup_estimate=1.0,
        )

    # Merge — chunked.py 와 동일 dedup 로직.
    all_tets_list: list[np.ndarray] = []
    seen: set[tuple[int, int, int, int]] = set()
    n_overlap = 0
    for idx_local, simplices_local in chunk_results:
        if simplices_local.size == 0:
            continue
        # local idx → global idx 변환.
        global_simplices = idx_local[simplices_local]
        for tet in global_simplices:
            key = tuple(sorted(tet.tolist()))
            if key in seen:
                n_overlap += 1
                continue
            seen.add(key)
            all_tets_list.append(tet)

    if not all_tets_list:
        return V, np.zeros((0, 4), dtype=np.int64), ParallelDelaunayResult(
            n_chunks=len(chunks), n_workers=n_workers,
            elapsed_s=time.perf_counter() - t0,
            speedup_estimate=float(n_workers),
        )

    all_tets = np.array(all_tets_list, dtype=np.int64)
    elapsed = time.perf_counter() - t0
    # N3 / beta2655 — audit log: chunk size 분포 + worker 활용도.
    try:
        log.info(
            "parallel_delaunay_audit",
            n_chunks=len(chunks),
            n_workers=n_workers,
            n_input_pts=int(V.shape[0]),
            n_output_tets=int(all_tets.shape[0]),
            elapsed_s=round(elapsed, 3),
            speedup_estimate=float(n_workers),
            avg_pts_per_chunk=int(V.shape[0] // max(len(chunks), 1)),
        )
    except Exception:
        pass
    return V, all_tets, ParallelDelaunayResult(
        n_chunks=len(chunks), n_workers=n_workers,
        elapsed_s=elapsed,
        speedup_estimate=float(n_workers),  # 이론치 — 실측은 caller 가 비교.
    )
