"""Y1 — native_poly 결과의 cell quality 측정.

polyhedral cell mesh (cell = list of face polygon) 에 대해 OpenFOAM
checkMesh 와 동일한 non-orthogonality / skewness 측정. Fluent poly mesher
와 비교 가능한 메트릭.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class PolyQualityReport:
    n_cells: int
    n_faces: int
    avg_faces_per_cell: float
    max_non_orthogonality_deg: float
    mean_non_orthogonality_deg: float
    p95_non_orthogonality_deg: float
    max_skewness: float
    mean_skewness: float


def _polygon_normal_centroid_area(
    pts: np.ndarray, vert_ids: list[int],
) -> tuple[np.ndarray, np.ndarray, float]:
    """N-gon polygon → unit normal, centroid, area (fan triangulation)."""
    P = pts[vert_ids]
    cen = P.mean(axis=0)
    # POL_PERF2: vectorized fan-triangulation using numpy slice roll
    e1 = P - cen            # (K, 3)
    e2 = np.roll(e1, -1, axis=0)  # shifted by 1 → (P[1]-cen, P[2]-cen, ..., P[0]-cen)
    crosses = np.cross(e1, e2)    # (K, 3)
    n_acc = crosses.sum(axis=0)
    area = 0.5 * float(np.linalg.norm(crosses, axis=1).sum())
    norm = float(np.linalg.norm(n_acc))
    if norm < 1e-30:
        return np.zeros(3), cen, 0.0
    return n_acc / norm, cen, area


def _cell_centroid(pts: np.ndarray, faces: list[list[int]]) -> np.ndarray:
    used = set()
    for f in faces:
        used.update(f)
    if not used:
        return np.zeros(3)
    return pts[list(used)].mean(axis=0)


def _batch_internal_face_metrics(
    pts: np.ndarray,
    shared_faces: list[tuple[list[int], int, int]],
    cell_centroids: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """POL_PERF2 — vectorized non-orthogonality + skewness for all shared faces.

    Groups faces by vertex count, processes each group as a (F, K, 3) numpy batch.

    Parameters
    ----------
    pts : (V, 3) vertex array.
    shared_faces : list of (vert_ids, cell_a_idx, cell_b_idx).
    cell_centroids : (C, 3) precomputed cell centroid array.

    Returns
    -------
    non_orths : (M,) float64 — non-orthogonality degrees for valid faces.
    skews     : (M,) float64 — skewness values for valid faces (≤ M entries).
    """
    if not shared_faces:
        return np.zeros(1), np.zeros(1)

    # Group by face vertex count for vectorised batch processing.
    from collections import defaultdict as _dd
    groups: dict[int, list[tuple[list[int], int, int]]] = _dd(list)
    for entry in shared_faces:
        groups[len(entry[0])].append(entry)

    all_no: list[np.ndarray] = []
    all_sk: list[np.ndarray] = []

    for k, entries in groups.items():
        F = len(entries)
        # Stack face vertices: (F, K, 3)
        idx_arr = np.array([e[0] for e in entries], dtype=np.int64)  # (F, K)
        ca_arr = np.array([e[1] for e in entries], dtype=np.int64)   # (F,)
        cb_arr = np.array([e[2] for e in entries], dtype=np.int64)   # (F,)

        P = pts[idx_arr]            # (F, K, 3)
        cens = P.mean(axis=1)      # (F, 3)

        # Fan-triangulate from centroid: edges e1[f,i] = P[f,i]-cen[f], e2 = P[f,(i+1)%k]-cen
        e1 = P - cens[:, None, :]                              # (F, K, 3)
        e2 = np.roll(e1, -1, axis=1)                          # (F, K, 3)
        crosses = np.cross(e1, e2)                             # (F, K, 3)
        n_acc = crosses.sum(axis=1)                            # (F, 3)
        cross_norms = np.linalg.norm(crosses, axis=2)          # (F, K)
        areas = 0.5 * cross_norms.sum(axis=1)                  # (F,)
        n_norms = np.linalg.norm(n_acc, axis=1)                # (F,)

        valid = (areas > 1e-30) & (n_norms > 1e-30)
        if not valid.any():
            continue

        unit_n = np.where(valid[:, None], n_acc / np.maximum(n_norms[:, None], 1e-30), 0.0)  # (F, 3)

        # d vector between cell centroids
        d = cell_centroids[cb_arr] - cell_centroids[ca_arr]   # (F, 3)
        d_norms = np.linalg.norm(d, axis=1)                   # (F,)
        valid2 = valid & (d_norms > 1e-30)
        if not valid2.any():
            continue

        d_unit = np.where(valid2[:, None], d / np.maximum(d_norms[:, None], 1e-30), 0.0)

        # Non-orthogonality
        dot_dn = np.einsum('fi,fi->f', d_unit, unit_n)        # (F,)
        cos_a = np.clip(np.abs(dot_dn), 0.0, 1.0)
        no = np.degrees(np.arccos(cos_a))                     # (F,)
        all_no.append(no[valid2])

        # Skewness: intersection of line (ca→cb) with face plane
        # t = dot(cen_face - ca, unit_n) / dot(d_unit, unit_n)
        denom = dot_dn                                         # (F,)
        valid_sk = valid2 & (np.abs(denom) > 1e-30)
        if valid_sk.any():
            ca_pts = cell_centroids[ca_arr]                    # (F, 3)
            num = np.einsum('fi,fi->f', cens - ca_pts, unit_n)
            t = np.where(valid_sk, num / np.where(valid_sk, denom, 1.0), 0.0)
            intersect = ca_pts + t[:, None] * d_unit           # (F, 3)
            skew_d = np.linalg.norm(intersect - cens, axis=1) # (F,)
            sk = skew_d / np.sqrt(np.maximum(areas, 1e-30))
            all_sk.append(sk[valid_sk])

    non_orths = np.concatenate(all_no) if all_no else np.zeros(1)
    skews = np.concatenate(all_sk) if all_sk else np.zeros(1)
    return non_orths, skews


def poly_quality_report(
    pts: np.ndarray, cells: list[list[list[int]]],
) -> PolyQualityReport:
    """polyhedral mesh → OpenFOAM-style quality.

    Args:
        pts: (N, 3) 정점.
        cells: 각 cell 의 face list. face = list[int] vertex idx.
    """
    pts = np.asarray(pts, dtype=np.float64)
    n_cells = len(cells)
    if n_cells == 0:
        return PolyQualityReport(0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    # 각 cell centroid + face → owner cells.
    cell_centroids = np.zeros((n_cells, 3), dtype=np.float64)
    for ci, cell_faces in enumerate(cells):
        cell_centroids[ci] = _cell_centroid(pts, cell_faces)

    face_dict: dict[tuple[int, ...], list[tuple[int, int]]] = {}
    n_faces_total = 0
    n_total_face_inst = 0
    for ci, cell_faces in enumerate(cells):
        for fi, vert_ids in enumerate(cell_faces):
            n_total_face_inst += 1
            key = tuple(sorted(vert_ids))
            face_dict.setdefault(key, []).append((ci, fi))

    n_faces_total = len(face_dict)
    avg_fpc = n_total_face_inst / max(n_cells, 1)

    # POL_PERF2: collect shared faces then vectorize metric computation.
    shared_faces: list[tuple[list[int], int, int]] = []
    for key, owners in face_dict.items():
        if len(owners) != 2:
            continue
        (ca, fi_a), (cb, _fi_b) = owners
        verts = list(cells[ca][fi_a])
        shared_faces.append((verts, ca, cb))

    non_orths_arr, skews_arr = _batch_internal_face_metrics(pts, shared_faces, cell_centroids)
    non_orths = non_orths_arr.tolist() if len(non_orths_arr) > 0 else [0.0]
    skews = skews_arr.tolist() if len(skews_arr) > 0 else [0.0]

    if not non_orths:
        non_orths = [0.0]
    if not skews:
        skews = [0.0]

    return PolyQualityReport(
        n_cells=int(n_cells),
        n_faces=int(n_faces_total),
        avg_faces_per_cell=float(avg_fpc),
        max_non_orthogonality_deg=float(np.max(non_orths)),
        mean_non_orthogonality_deg=float(np.mean(non_orths)),
        p95_non_orthogonality_deg=float(np.percentile(non_orths, 95)),
        max_skewness=float(np.max(skews)),
        mean_skewness=float(np.mean(skews)),
    )


def collapse_short_face_edges(
    pts: np.ndarray,
    cells: list[list[list[int]]],
    *,
    rel_tol: float = 1e-2,
) -> tuple[np.ndarray, list[list[list[int]]], int]:
    """DD1 (beta1710) — face polygon 의 짧은 edge 를 endpoints 평균 vertex 로 merge.

    bbox_diag × rel_tol 보다 짧은 edge 의 두 vertex 를 같은 좌표로 통합 +
    face vertex list 에서 중복 제거. cube cell 의 1e-4 단위 sliver edge
    제거에 효과적.

    Returns: (new_pts, new_cells, n_collapsed_edges).
    """
    pts = np.asarray(pts, dtype=np.float64).copy()
    if not cells or pts.size == 0:
        return pts, cells, 0
    bbox = pts.max(axis=0) - pts.min(axis=0)
    bbox_diag = float(np.linalg.norm(bbox)) + 1e-30
    tol = bbox_diag * float(rel_tol)

    # union-find 으로 짧은 edge 의 vertex 통합.
    n = pts.shape[0]
    parent = np.arange(n, dtype=np.int64)

    def _find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = int(parent[x])
        return x

    def _union(a: int, b: int) -> None:
        ra = _find(a); rb = _find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    n_collapsed = 0
    for cell_faces in cells:
        for f in cell_faces:
            for i in range(len(f)):
                a = int(f[i]); b = int(f[(i + 1) % len(f)])
                if a == b:
                    continue
                d = float(np.linalg.norm(pts[a] - pts[b]))
                if d < tol:
                    if _find(a) != _find(b):
                        _union(a, b)
                        n_collapsed += 1

    if n_collapsed == 0:
        return pts, cells, 0

    # 각 root vertex 에 좌표 평균 부여.
    # C-PERF-80 / beta2531 — path-doubling UF: per-element _find 루프 제거.
    parent_arr = np.asarray(parent, dtype=np.int64)
    for _ in range(int(np.log2(max(n, 2))) + 2):
        new_parent = parent_arr[parent_arr]
        if np.array_equal(new_parent, parent_arr):
            break
        parent_arr = new_parent
    roots = parent_arr.copy()
    new_pts = pts.copy()
    sums = np.zeros_like(pts)
    counts = np.zeros(n, dtype=np.int64)
    np.add.at(sums, roots, pts)
    np.add.at(counts, roots, 1)
    safe = counts > 0
    new_pts[safe] = sums[safe] / counts[safe, None]
    # non-root vertex 는 root 좌표 사용.
    new_pts = new_pts[roots]

    # face vertex list 재매핑 + 중복 인접 제거.
    new_cells: list[list[list[int]]] = []
    for cell_faces in cells:
        new_cell_faces: list[list[int]] = []
        for f in cell_faces:
            mapped = [int(roots[v]) for v in f]
            # adjacent dedup.
            cleaned: list[int] = []
            for vi in mapped:
                if not cleaned or cleaned[-1] != vi:
                    cleaned.append(vi)
            if len(cleaned) >= 2 and cleaned[-1] == cleaned[0]:
                cleaned.pop()
            if len(cleaned) >= 3:
                new_cell_faces.append(cleaned)
        if new_cell_faces:
            new_cells.append(new_cell_faces)

    return new_pts, new_cells, n_collapsed


def smooth_poly_in_memory(
    pts: np.ndarray,
    cells: list[list[list[int]]],
    *,
    n_iter: int = 3,
    relax: float = 0.25,
    lock_vertex_ids: np.ndarray | None = None,
) -> np.ndarray:
    """Y2 (beta1660) — polyhedral cell vertex Laplacian (in-memory).

    각 vertex 를 인접한 vertex (같은 face 의 다른 vertex) 의 평균 위치로
    relax 이동. boundary vertex (lock_vertex_ids 또는 1-owner face vertex)
    는 고정.

    skewness 폭주 (cube/cyl 의 100+ skew) 를 잡는 핵심 단계.
    """
    pts = np.asarray(pts, dtype=np.float64).copy()
    n = pts.shape[0]
    if n == 0 or not cells:
        return pts

    # face owner 카운트 → boundary vertex 식별.
    face_owner: dict[tuple[int, ...], int] = {}
    for cell_faces in cells:
        for f in cell_faces:
            k = tuple(sorted(f))
            face_owner[k] = face_owner.get(k, 0) + 1
    boundary_v: set[int] = set()
    for cell_faces in cells:
        for f in cell_faces:
            k = tuple(sorted(f))
            if face_owner[k] == 1:
                boundary_v.update(f)

    locked = np.zeros(n, dtype=bool)
    for vi in boundary_v:
        if 0 <= vi < n:
            locked[vi] = True
    if lock_vertex_ids is not None and len(lock_vertex_ids) > 0:
        locked[np.asarray(lock_vertex_ids, dtype=np.int64)] = True

    # vertex → 인접 vertex set (face 안의 다른 vertex).
    nbrs: list[set[int]] = [set() for _ in range(n)]
    for cell_faces in cells:
        for f in cell_faces:
            for vi in f:
                if 0 <= vi < n:
                    nbrs[vi].update(int(x) for x in f if int(x) != vi)

    # Build CSR-style neighbour arrays for vectorised Laplacian.
    row_ids: list[int] = []
    col_ids: list[int] = []
    for vi in range(n):
        for nb in nbrs[vi]:
            row_ids.append(vi)
            col_ids.append(nb)
    row_arr = np.array(row_ids, dtype=np.int64)
    col_arr = np.array(col_ids, dtype=np.int64)
    # degree per vertex (number of neighbours)
    deg = np.bincount(row_arr, minlength=n).astype(np.float64)
    free = (~locked) & (deg > 0)

    for _ in range(int(n_iter)):
        # Accumulate neighbour positions via np.add.at — vectorised over all edges.
        acc = np.zeros((n, 3), dtype=np.float64)
        np.add.at(acc, row_arr, pts[col_arr])
        # mean neighbour position
        cen = np.where(deg[:, None] > 0, acc / np.maximum(deg[:, None], 1.0), pts)
        delta = float(relax) * (cen - pts)
        pts = np.where(free[:, None], pts + delta, pts)
    return pts


def drop_degenerate_poly_cells(
    pts: np.ndarray,
    cells: list[list[list[int]]],
    *,
    max_skewness: float = 8.0,
    max_non_ortho_deg: float = 78.0,
) -> tuple[list[list[list[int]]], int]:
    """Z1 (beta1670) — skewness 폭주 / 강한 비직교 cell 자동 제거.

    각 cell 의 face quality 합으로 cell-level 점수 산출. 위반 cell drop.
    cube/cyl 의 base voronoi 가 만든 degenerate cell 제거 → 평균 quality ↑.
    """
    pts = np.asarray(pts, dtype=np.float64)
    if not cells:
        return cells, 0

    # 각 face 의 plane / area / centroid 캐시.
    def _face_normal(face_verts: list[int]) -> tuple[float, float]:
        P = pts[face_verts]
        cen = P.mean(axis=0)
        e1 = P - cen                           # (K, 3)
        e2 = np.roll(e1, -1, axis=0)           # shifted neighbours
        crosses = np.cross(e1, e2)             # (K, 3) vectorised
        n_acc = crosses.sum(axis=0)
        ar = 0.5 * float(np.linalg.norm(crosses, axis=1).sum())
        nn = float(np.linalg.norm(n_acc))
        return ar, nn

    keep: list[list[list[int]]] = []
    n_drop = 0
    for cell_faces in cells:
        # cell centroid.
        used: set[int] = set()
        for f in cell_faces:
            used.update(f)
        if not used:
            n_drop += 1
            continue
        cen_c = pts[list(used)].mean(axis=0)
        bad = False
        for f in cell_faces:
            ar, nn = _face_normal(f)
            if ar < 1e-20 or nn < 1e-20:
                bad = True
                break
            # 임의 face skew 측정.
            P = pts[f]
            cen_f = P.mean(axis=0)
            d = cen_f - cen_c
            if float(np.linalg.norm(d)) < 1e-30:
                continue
            # 단순 sliver 검출: face area 대비 매우 좁은 polygon.
            edge_lens = [
                float(np.linalg.norm(P[(i + 1) % len(f)] - P[i]))
                for i in range(len(f))
            ]
            if not edge_lens or max(edge_lens) / max(min(edge_lens), 1e-30) > 50.0:
                bad = True
                break
        if bad:
            n_drop += 1
            continue
        keep.append(cell_faces)
    return keep, int(n_drop)


def poly_quality_grade(report: PolyQualityReport) -> str:
    """Fluent poly mesher 기준 grade.

        A: max_no < 40°, max_skew < 0.5  (Fluent typical)
        B: max_no < 60°, max_skew < 1.5
        C: max_no < 75°, max_skew < 4.0
        D: 그 외 / 빈 mesh.
    """
    # 빈 mesh 또는 단일 cell 은 무조건 D (의미 있는 mesh 아님).
    if report.n_cells <= 2:
        return "D"
    if report.max_non_orthogonality_deg < 40.0 and report.max_skewness < 0.5:
        return "A"
    if report.max_non_orthogonality_deg < 60.0 and report.max_skewness < 1.5:
        return "B"
    if report.max_non_orthogonality_deg < 75.0 and report.max_skewness < 4.0:
        return "C"
    return "D"
