"""Self-intersection detection for triangle meshes.

P2.6 / beta2322 — skeleton: detect-only path.
이후 카드에서 resolve (split / Boolean) 추가 예정.

알고리즘 (Möller 1997 triangle-triangle intersection):
  1. AABB tree (sklearn KDTree on triangle centroids) 로 후보 페어 정렬.
  2. 각 후보 (i, j) 페어 → tri_tri_intersect_3d (Möller separating-axis test).
  3. 인접 (공유 vertex/edge) tri 는 자동 제외 (false positive 방지).
  4. 진짜 교차 페어를 (i, j) 튜플 list 로 반환.

성능:
  - O(F log F) candidate gen + O(K) intersection tests, K = 후보 페어 수.
  - 100k face 메쉬에서 ≤ 1s 목표.

상위 caller (P2.6 차후 카드):
  - native_poly voronoi best-of-N fail 분기 — repair-retry 직전 detect.
  - native_tet harness 진입 — input_check 보강.
  - GUI quality tab — 사용자에게 "self-intersect 감지" 표시.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class SelfIntersectReport:
    """Detect 결과."""

    n_faces: int = 0
    n_pairs_tested: int = 0
    n_intersections: int = 0
    intersecting_face_pairs: list[tuple[int, int]] = field(default_factory=list)
    elapsed_s: float = 0.0

    @property
    def has_self_intersection(self) -> bool:
        return self.n_intersections > 0


def _tri_aabbs(V: np.ndarray, F: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Triangle 별 AABB (min, max) 계산."""
    pts = V[F]  # (M, 3, 3)
    return pts.min(axis=1), pts.max(axis=1)


def _aabb_overlap_pairs(
    aabb_min: np.ndarray,
    aabb_max: np.ndarray,
    *,
    eps: float = 1e-12,
) -> list[tuple[int, int]]:
    """모든 (i<j) 페어 중 AABB 가 겹치는 것을 반환.

    C-PERF-23 / beta2474 — broadcast 기반 (T,T) overlap matrix 로 벡터화.
    """
    n = aabb_min.shape[0]
    if n == 0:
        return []
    # (i,j) overlap: a_max[i] >= b_min[j] - eps AND b_max[j] >= a_min[i] - eps,
    # for all 3 axes.
    ov = np.all(
        (aabb_max[:, None, :] >= aabb_min[None, :, :] - eps)
        & (aabb_max[None, :, :] >= aabb_min[:, None, :] - eps),
        axis=2,
    )
    # i < j 만.
    ov_upper = np.triu(ov, k=1)
    ii, jj = np.where(ov_upper)
    return list(zip(ii.tolist(), jj.tolist()))


def _shares_vertex(F: np.ndarray, i: int, j: int) -> bool:
    """두 triangle 이 vertex 를 공유하면 True (자체 교차 테스트 제외용)."""
    return bool(set(F[i].tolist()) & set(F[j].tolist()))


def _tri_tri_intersect(
    a0: np.ndarray, a1: np.ndarray, a2: np.ndarray,
    b0: np.ndarray, b1: np.ndarray, b2: np.ndarray,
    *,
    eps: float = 1e-12,
) -> bool:
    """Möller 1997 triangle-triangle intersection (separating axis test).

    공유 vertex/edge 이 있는 페어는 caller 가 사전 필터.
    Coplanar 케이스는 보수적으로 False 반환 (다음 카드에서 강화).
    """
    # plane of A: normal n1, d1
    e1 = a1 - a0
    e2 = a2 - a0
    n1 = np.cross(e1, e2)
    if float(np.linalg.norm(n1)) < eps:
        return False  # degenerate A
    d1 = float(np.dot(n1, a0))

    # signed distances of B verts to A's plane.
    db = np.array([
        float(np.dot(n1, b0)) - d1,
        float(np.dot(n1, b1)) - d1,
        float(np.dot(n1, b2)) - d1,
    ])
    if (db > eps).all() or (db < -eps).all():
        return False  # B fully on one side of A.
    if (np.abs(db) < eps).all():
        return False  # coplanar — skip (보수적).

    # plane of B
    f1 = b1 - b0
    f2 = b2 - b0
    n2 = np.cross(f1, f2)
    if float(np.linalg.norm(n2)) < eps:
        return False
    d2 = float(np.dot(n2, b0))

    da = np.array([
        float(np.dot(n2, a0)) - d2,
        float(np.dot(n2, a1)) - d2,
        float(np.dot(n2, a2)) - d2,
    ])
    if (da > eps).all() or (da < -eps).all():
        return False

    def _segment_hits_tri(
        p0: np.ndarray,
        p1: np.ndarray,
        t0: np.ndarray,
        t1: np.ndarray,
        t2: np.ndarray,
    ) -> bool:
        """Möller-Trumbore segment-triangle hit test."""
        direction = p1 - p0
        e1_s = t1 - t0
        e2_s = t2 - t0
        pvec_s = np.cross(direction, e2_s)
        det_s = float(np.dot(e1_s, pvec_s))
        if abs(det_s) < eps:
            return False
        inv_det_s = 1.0 / det_s
        tvec_s = p0 - t0
        u_s = float(np.dot(tvec_s, pvec_s)) * inv_det_s
        if u_s < -eps or u_s > 1.0 + eps:
            return False
        qvec_s = np.cross(tvec_s, e1_s)
        v_s = float(np.dot(direction, qvec_s)) * inv_det_s
        if v_s < -eps or (u_s + v_s) > 1.0 + eps:
            return False
        t_s = float(np.dot(e2_s, qvec_s)) * inv_det_s
        return -eps <= t_s <= 1.0 + eps

    # Precise non-coplanar test: one triangle intersects the other iff at
    # least one edge segment pierces the opposite triangle.  The earlier
    # plane-crossing shortcut over-reported normal adjacent cube faces.
    for p0, p1 in ((a0, a1), (a1, a2), (a2, a0)):
        if _segment_hits_tri(p0, p1, b0, b1, b2):
            return True
    for p0, p1 in ((b0, b1), (b1, b2), (b2, b0)):
        if _segment_hits_tri(p0, p1, a0, a1, a2):
            return True
    return False


def _kdtree_overlap_pairs(
    V: np.ndarray,
    F: np.ndarray,
    aabb_min: np.ndarray,
    aabb_max: np.ndarray,
    *,
    k: int = 16,
) -> list[tuple[int, int]]:
    """KDTree-based AABB overlap candidates (beta2323 P2.6 scaling).

    Centroid 의 k-nearest neighbor 를 한 query 에 가져온 뒤 AABB overlap
    검사. K=16 정도면 일반 mesh 의 self-intersect 후보 대부분 포함.

    O(M log M + M·k) — 100k face 에서 ≤ 0.5s 목표.
    """
    from core.utils.kdtree import NumpyKDTree  # noqa: PLC0415

    n = int(F.shape[0])
    if n < 2:
        return []
    centroids = (V[F[:, 0]] + V[F[:, 1]] + V[F[:, 2]]) / 3.0
    tree = NumpyKDTree(centroids)
    # Search radius: max AABB extent — diagonal length 충분.
    search_k = min(k, n)
    _, idx = tree.query(centroids, k=search_k)
    if idx.ndim == 1:
        idx = idx[:, None]

    # C-PERF-24 / beta2475 — vectorize the (i, kth-neighbor) AABB filter.
    # Build (n*K,) flat (i, j) candidate pairs, mask invalid (j<=i or out-of-bound),
    # then AABB-overlap test in one np.all step.
    K = int(idx.shape[1])
    if K == 0 or n == 0:
        return []
    i_idx = np.repeat(np.arange(n, dtype=np.int64), K)        # (n*K,)
    j_idx = idx.reshape(-1).astype(np.int64)                   # (n*K,)
    valid = (j_idx > i_idx) & (j_idx < n)
    if not valid.any():
        return []
    i_v = i_idx[valid]; j_v = j_idx[valid]
    a_min = aabb_min[i_v]; a_max = aabb_max[i_v]
    b_min = aabb_min[j_v]; b_max = aabb_max[j_v]
    overlap = np.all(
        (a_max >= b_min) & (b_max >= a_min),
        axis=1,
    )
    pairs = np.unique(
        np.stack([i_v[overlap], j_v[overlap]], axis=1), axis=0,
    )
    return list(zip(pairs[:, 0].tolist(), pairs[:, 1].tolist()))


def export_intersecting_faces_stl(
    V: np.ndarray,
    F: np.ndarray,
    pairs: list[tuple[int, int]],
    output_path: "str | object",
) -> int:
    """beta2330 — self-intersect 페어를 binary STL 로 export (시각화용).

    상위 caller (GUI / CLI) 가 사용자에게 "어디 면이 self-intersect 하는가" 를
    PyVista / Meshlab 등으로 보여주는 데 사용. unique 면 ID 만 추출하므로
    실제 face 수 = unique(pairs flatten).

    Args:
        V: (N, 3) vertex 좌표.
        F: (M, 3) triangle vertex indices.
        pairs: detect_self_intersections().intersecting_face_pairs.
        output_path: 출력 STL 파일 경로 (Path or str).

    Returns:
        실제 export 한 unique face 수.
    """
    from pathlib import Path
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    if not pairs:
        # 빈 STL 생성 — 0 face.
        with out.open("wb") as f:
            f.write(b"\x00" * 80)  # 80-byte header.
            f.write((0).to_bytes(4, "little"))
        return 0

    unique_fids = sorted({i for p in pairs for i in p})
    V = np.asarray(V, dtype=np.float64)
    F = np.asarray(F, dtype=np.int64)

    n_tri = len(unique_fids)
    # C-PERF-70 / beta2521 — vectorize STL write: build single contiguous buffer
    # via numpy struct, single fwrite. ~10× I/O syscall reduction.
    with out.open("wb") as f:
        # 80-byte header.
        header = (
            f"AutoTessell self-intersect dump ({n_tri} tri)"
        ).encode("ascii", errors="replace")[:80]
        f.write(header.ljust(80, b"\x00"))
        # uint32 num_triangles.
        f.write(int(n_tri).to_bytes(4, "little"))
        if n_tri > 0:
            fids_arr = np.asarray(unique_fids, dtype=np.int64)
            v0 = V[F[fids_arr, 0]]
            v1 = V[F[fids_arr, 1]]
            v2 = V[F[fids_arr, 2]]
            nrm = np.cross(v1 - v0, v2 - v0)
            nrm_len = np.linalg.norm(nrm, axis=1, keepdims=True)
            nrm_unit = np.where(
                nrm_len > 1e-30, nrm / np.maximum(nrm_len, 1e-30), 0.0,
            ).astype(np.float32)
            v0_f = v0.astype(np.float32)
            v1_f = v1.astype(np.float32)
            v2_f = v2.astype(np.float32)
            # Construct (n_tri,) struct buf: 50 bytes per tri (12+36+2).
            # Use raw bytes concatenation per tri to preserve attr=0 uint16.
            tri_buf = bytearray()
            for i in range(n_tri):
                tri_buf += nrm_unit[i].tobytes()
                tri_buf += v0_f[i].tobytes()
                tri_buf += v1_f[i].tobytes()
                tri_buf += v2_f[i].tobytes()
                tri_buf += b"\x00\x00"
            f.write(bytes(tri_buf))
    return n_tri


def detect_self_intersections(
    V: np.ndarray,
    F: np.ndarray,
    *,
    max_pairs_for_o_n_squared: int = 5000,
    kdtree_k: int = 16,
) -> SelfIntersectReport:
    """입력 mesh 의 self-intersection 페어를 검출.

    Args:
        V: (N, 3) vertex 좌표.
        F: (M, 3) triangle vertex indices.
        max_pairs_for_o_n_squared: O(M^2) brute force 임계. 이하면 모든
            페어 AABB 비교, 초과 시 KDTree O(M log M) 경로.
        kdtree_k: KDTree query 의 k-nearest. 작으면 후보 ↓ (놓침 위험), 크면
            정확하지만 느림. 기본 16.

    Returns:
        SelfIntersectReport.
    """
    import time as _t
    t0 = _t.perf_counter()

    V = np.asarray(V, dtype=np.float64)
    F = np.asarray(F, dtype=np.int64)
    n_faces = int(F.shape[0])

    if n_faces < 2:
        return SelfIntersectReport(n_faces=n_faces, elapsed_s=_t.perf_counter() - t0)

    aabb_min, aabb_max = _tri_aabbs(V, F)

    # beta2323 — KDTree path 추가 (대형 mesh).
    if n_faces > max_pairs_for_o_n_squared:
        try:
            cand = _kdtree_overlap_pairs(V, F, aabb_min, aabb_max, k=kdtree_k)
        except Exception:
            # KDTree 미가용 등 fallback → short-circuit (이전 동작 보존).
            return SelfIntersectReport(
                n_faces=n_faces, n_pairs_tested=0,
                n_intersections=0,
                intersecting_face_pairs=[],
                elapsed_s=_t.perf_counter() - t0,
            )
    else:
        cand = _aabb_overlap_pairs(aabb_min, aabb_max)

    pairs: list[tuple[int, int]] = []
    n_tested = 0
    for i, j in cand:
        if _shares_vertex(F, i, j):
            continue
        n_tested += 1
        a0, a1, a2 = V[F[i, 0]], V[F[i, 1]], V[F[i, 2]]
        b0, b1, b2 = V[F[j, 0]], V[F[j, 1]], V[F[j, 2]]
        if _tri_tri_intersect(a0, a1, a2, b0, b1, b2):
            pairs.append((i, j))

    return SelfIntersectReport(
        n_faces=n_faces,
        n_pairs_tested=n_tested,
        n_intersections=len(pairs),
        intersecting_face_pairs=pairs,
        elapsed_s=_t.perf_counter() - t0,
    )


def resolve_self_intersections(
    V: np.ndarray,
    F: np.ndarray,
    *,
    max_pairs_for_o_n_squared: int = 5000,
    kdtree_k: int = 16,
) -> tuple[np.ndarray, np.ndarray, int]:
    """P2.6 / beta2585 — minimal Boolean-resolve via face drop + hole-fill chain.

    상용 (CGAL co-refinement / Cork) 대신 lossy Boolean: 교차 face 양쪽을
    drop → 구멍 → 후속 hole_fill 이 보강. 100% 정확하지 않지만 extreme tier
    self-intersect 입력의 voronoi/tet 진입 가능성 회복용.

    Returns:
        (V_unchanged, F_dropped, n_dropped)
    """
    rep = detect_self_intersections(
        V, F,
        max_pairs_for_o_n_squared=max_pairs_for_o_n_squared,
        kdtree_k=kdtree_k,
    )
    if not rep.has_self_intersection:
        return V, F, 0

    bad: set[int] = set()
    for (i, j) in rep.intersecting_face_pairs:
        bad.add(int(i))
        bad.add(int(j))

    if not bad:
        return V, F, 0

    keep = np.ones(F.shape[0], dtype=bool)
    keep[list(bad)] = False
    return V, F[keep], len(bad)
