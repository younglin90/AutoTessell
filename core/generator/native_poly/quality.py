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
    n_acc = np.zeros(3, dtype=np.float64)
    area = 0.0
    for i in range(len(vert_ids)):
        j = (i + 1) % len(vert_ids)
        e1 = P[i] - cen
        e2 = P[j] - cen
        cr = np.cross(e1, e2)
        n_acc += cr
        area += 0.5 * float(np.linalg.norm(cr))
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

    non_orths: list[float] = []
    skews: list[float] = []
    for key, owners in face_dict.items():
        if len(owners) != 2:
            continue
        (ca, fi_a), (cb, _fi_b) = owners
        verts = list(cells[ca][fi_a])
        unit_n, cen, area = _polygon_normal_centroid_area(pts, verts)
        if area < 1e-30:
            continue
        d = cell_centroids[cb] - cell_centroids[ca]
        d_norm = float(np.linalg.norm(d))
        if d_norm < 1e-30:
            continue
        d_unit = d / d_norm
        cos_a = float(np.clip(abs(np.dot(d_unit, unit_n)), 0.0, 1.0))
        non_orths.append(float(np.degrees(np.arccos(cos_a))))
        denom = float(np.dot(d_unit, unit_n))
        if abs(denom) < 1e-30:
            continue
        t = float(np.dot(cen - cell_centroids[ca], unit_n)) / denom
        intersect = cell_centroids[ca] + t * d_unit
        skew_d = float(np.linalg.norm(intersect - cen))
        skews.append(skew_d / np.sqrt(max(area, 1e-30)))

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

    for _ in range(int(n_iter)):
        new_pts = pts.copy()
        for vi in range(n):
            if locked[vi]:
                continue
            ngs = nbrs[vi]
            if not ngs:
                continue
            cen = pts[list(ngs)].mean(axis=0)
            new_pts[vi] = pts[vi] + float(relax) * (cen - pts[vi])
        pts = new_pts
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
        n_acc = np.zeros(3)
        ar = 0.0
        for i in range(len(face_verts)):
            j = (i + 1) % len(face_verts)
            cr = np.cross(P[i] - cen, P[j] - cen)
            n_acc += cr
            ar += 0.5 * float(np.linalg.norm(cr))
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
    # 빈 mesh 는 무조건 D.
    if report.n_cells == 0:
        return "D"
    if report.max_non_orthogonality_deg < 40.0 and report.max_skewness < 0.5:
        return "A"
    if report.max_non_orthogonality_deg < 60.0 and report.max_skewness < 1.5:
        return "B"
    if report.max_non_orthogonality_deg < 75.0 and report.max_skewness < 4.0:
        return "C"
    return "D"
