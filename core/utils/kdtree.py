"""NumpyKDTree — scipy.spatial.cKDTree 의 numpy-only 대체 (v0.4.0-beta28).

API subset 호환:
    tree = NumpyKDTree(points)          # (N, 3) array
    dists, idx = tree.query(queries, k=1, distance_upper_bound=inf)

전략:
    - 소형 reference set (N ≤ 2048): 순수 brute-force pairwise distance.
    - 대형 reference set: 3D uniform grid bucket — query 점의 셀과 8 근방 셀의
      candidate 만 거리 계산 (평균 O(k) per query).
    - k > 1: brute-force 에서는 argpartition, grid bucket 에서는 search radius
      를 점진 확대하며 충분한 candidate 확보.

반환 형식 (scipy 호환):
    - k == 1: dists (N,), idx (N,)
    - k  > 1: dists (N, k), idx (N, k)
    distance_upper_bound 를 넘는 query 는 dist=inf, idx=len(points).
"""
from __future__ import annotations

import numpy as np


_BRUTE_FORCE_THRESHOLD = 2048


class NumpyKDTree:
    """scipy.spatial.cKDTree API subset 의 numpy-only 구현."""

    def __init__(self, points: np.ndarray) -> None:
        P = np.asarray(points, dtype=np.float64)
        if P.ndim != 2 or P.shape[1] != 3:
            raise ValueError(f"points must be (N, 3), got {P.shape}")
        self._P = P
        self._n = int(P.shape[0])

        self._use_grid = self._n > _BRUTE_FORCE_THRESHOLD
        if self._use_grid and self._n > 0:
            # grid cell size = bbox_diag / N^(1/3), clipped
            bmin = P.min(axis=0)
            bmax = P.max(axis=0)
            diag = float(np.linalg.norm(bmax - bmin))
            if diag <= 0.0:
                # degenerate — all points coincident
                self._use_grid = False
            else:
                self._bmin = bmin
                self._bmax = bmax
                self._diag = diag
                h = diag / max(1.0, self._n ** (1.0 / 3.0))
                self._h = float(max(h, diag * 1e-6))
                # bucket indices per point
                idx = np.floor((P - bmin) / self._h).astype(np.int64)
                idx = np.clip(idx, 0, None)
                self._grid_shape = (
                    int(idx[:, 0].max()) + 1,
                    int(idx[:, 1].max()) + 1,
                    int(idx[:, 2].max()) + 1,
                )
                # flat bucket id
                flat = (
                    idx[:, 0] * self._grid_shape[1] * self._grid_shape[2]
                    + idx[:, 1] * self._grid_shape[2]
                    + idx[:, 2]
                )
                order = np.argsort(flat)
                self._sorted_idx = order.astype(np.int64)
                self._sorted_flat = flat[order]
                # cumulative start per unique bucket id
                uq, starts = np.unique(self._sorted_flat, return_index=True)
                self._bucket_ids = uq
                self._bucket_starts = starts

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def query(
        self,
        x: np.ndarray,
        k: int = 1,
        distance_upper_bound: float = float("inf"),
    ) -> tuple[np.ndarray, np.ndarray]:
        """각 query 점의 nearest k 를 반환.

        Args:
            x: (M, 3) float.
            k: 반환할 최근접 개수.
            distance_upper_bound: 이 값을 넘는 거리는 (inf, n) 으로 반환.

        Returns:
            scipy.cKDTree.query 와 동일한 shape/의미의 ``(dists, idx)``.
        """
        Q = np.asarray(x, dtype=np.float64)
        single = False
        if Q.ndim == 1:
            Q = Q[None, :]
            single = True
        if Q.shape[1] != 3:
            raise ValueError(f"queries must be (*, 3), got {Q.shape}")

        if self._n == 0 or k <= 0:
            dists = np.full((Q.shape[0], max(1, k)), np.inf)
            idx = np.full((Q.shape[0], max(1, k)), self._n, dtype=np.int64)
            if k <= 1:
                dists = dists[:, 0]; idx = idx[:, 0]
            if single:
                return dists[0], idx[0]
            return dists, idx

        if self._use_grid:
            dists, idx = self._query_grid(Q, k, distance_upper_bound)
        else:
            dists, idx = self._query_brute(Q, k, distance_upper_bound)

        if k == 1:
            dists = dists[:, 0]
            idx = idx[:, 0]
        if single:
            return dists[0], idx[0]
        return dists, idx

    # ------------------------------------------------------------------
    # brute force
    # ------------------------------------------------------------------

    def _query_brute(
        self, Q: np.ndarray, k: int, ub: float,
    ) -> tuple[np.ndarray, np.ndarray]:
        # (M, N) pairwise distances — 소형이라 메모리 OK
        diff = Q[:, None, :] - self._P[None, :, :]
        d = np.linalg.norm(diff, axis=2)
        m = Q.shape[0]
        k_eff = min(k, self._n)
        if k_eff == 1:
            nn = np.argmin(d, axis=1)
            dists = d[np.arange(m), nn][:, None]
            idx = nn[:, None].astype(np.int64)
        else:
            part = np.argpartition(d, kth=min(k_eff - 1, self._n - 1), axis=1)[:, :k_eff]
            rows = np.arange(m)[:, None]
            dsort_within = np.argsort(d[rows, part], axis=1)
            idx = part[rows, dsort_within].astype(np.int64)
            dists = d[rows, idx]

        # pad if k > n
        if k > k_eff:
            pad_d = np.full((m, k - k_eff), np.inf)
            pad_i = np.full((m, k - k_eff), self._n, dtype=np.int64)
            dists = np.concatenate([dists, pad_d], axis=1)
            idx = np.concatenate([idx, pad_i], axis=1)

        # distance_upper_bound 적용
        mask = dists > ub
        if mask.any():
            dists = np.where(mask, np.inf, dists)
            idx = np.where(mask, self._n, idx)
        return dists, idx

    # ------------------------------------------------------------------
    # grid bucket
    # ------------------------------------------------------------------

    def _neighbors_in_cells(self, cells: list[tuple[int, int, int]]) -> np.ndarray:
        """주어진 3D 셀 목록에 속한 point indices 를 모은다."""
        gs = self._grid_shape
        flat_ids = np.array([
            c[0] * gs[1] * gs[2] + c[1] * gs[2] + c[2]
            for c in cells
            if 0 <= c[0] < gs[0] and 0 <= c[1] < gs[1] and 0 <= c[2] < gs[2]
        ], dtype=np.int64)
        if flat_ids.size == 0:
            return np.zeros(0, dtype=np.int64)

        # sorted_flat 에서 해당 bucket 들을 찾아 slice 수집
        collected: list[np.ndarray] = []
        # bucket_ids 는 unique ascending. searchsorted 로 start/end.
        for fid in flat_ids:
            pos = np.searchsorted(self._bucket_ids, fid)
            if pos >= len(self._bucket_ids) or self._bucket_ids[pos] != fid:
                continue
            start = self._bucket_starts[pos]
            end = (
                self._bucket_starts[pos + 1]
                if pos + 1 < len(self._bucket_starts)
                else len(self._sorted_flat)
            )
            collected.append(self._sorted_idx[start:end])
        if not collected:
            return np.zeros(0, dtype=np.int64)
        return np.concatenate(collected)

    def _query_grid(
        self, Q: np.ndarray, k: int, ub: float,
    ) -> tuple[np.ndarray, np.ndarray]:
        m = Q.shape[0]
        dists = np.full((m, k), np.inf)
        idx = np.full((m, k), self._n, dtype=np.int64)

        # query cell index
        qi = np.floor((Q - self._bmin) / self._h).astype(np.int64)

        for q_idx in range(m):
            qx, qy, qz = int(qi[q_idx, 0]), int(qi[q_idx, 1]), int(qi[q_idx, 2])
            # 점진 확장 검색 반경 r (cell 단위). 충분한 candidate 확보까지 증가.
            r = 1
            cand: np.ndarray | None = None
            while True:
                cells = [
                    (qx + dx, qy + dy, qz + dz)
                    for dx in range(-r, r + 1)
                    for dy in range(-r, r + 1)
                    for dz in range(-r, r + 1)
                ]
                cand_idx = self._neighbors_in_cells(cells)
                if cand_idx.size >= k or r * self._h > max(self._diag, 1e-9) * 1.1:
                    cand = cand_idx
                    break
                r += 1

            if cand is None or cand.size == 0:
                continue
            diff = self._P[cand] - Q[q_idx]
            d = np.linalg.norm(diff, axis=1)
            k_eff = min(k, d.shape[0])
            if k_eff == 1:
                j = int(np.argmin(d))
                dists[q_idx, 0] = float(d[j])
                idx[q_idx, 0] = int(cand[j])
            else:
                part = np.argpartition(d, kth=k_eff - 1)[:k_eff]
                dsort = np.argsort(d[part])
                order = part[dsort]
                dists[q_idx, :k_eff] = d[order]
                idx[q_idx, :k_eff] = cand[order]

        mask = dists > ub
        if mask.any():
            dists = np.where(mask, np.inf, dists)
            idx = np.where(mask, self._n, idx)
        return dists, idx
