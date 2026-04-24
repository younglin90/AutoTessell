"""P5 — chunked Delaunay tests."""
from __future__ import annotations

import numpy as np


def test_chunked_delaunay_small_falls_back() -> None:
    """< 200 점 입력은 단일 Delaunay 로 경로 우회."""
    from core.generator.native_tet.chunked import chunked_delaunay

    rng = np.random.default_rng(0)
    V = rng.random((50, 3))
    _, T, info = chunked_delaunay(V, n_div=2)
    assert info.n_chunks == 1
    assert T.shape[0] > 0


def test_chunked_delaunay_large_partitions() -> None:
    """2000 점 2x2x2 분할 → 청크 수 = 8, tet > 0."""
    from core.generator.native_tet.chunked import chunked_delaunay

    rng = np.random.default_rng(1)
    V = rng.random((2000, 3))
    _, T, info = chunked_delaunay(V, n_div=2, overlap_ratio=0.1)
    assert info.n_chunks == 8
    assert T.shape[0] > 500   # 비어 있지 않음.


def test_chunked_covers_no_duplicates() -> None:
    """dedup 후 tet 의 canonical key 는 unique."""
    from core.generator.native_tet.chunked import chunked_delaunay

    rng = np.random.default_rng(2)
    V = rng.random((1500, 3))
    _, T, _ = chunked_delaunay(V, n_div=2, overlap_ratio=0.15)
    keys = {tuple(sorted(map(int, r))) for r in T.tolist()}
    assert len(keys) == T.shape[0]
