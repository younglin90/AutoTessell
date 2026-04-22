"""tet mesh → polyhedral dual mesh 자체 구현.

OpenFOAM ``polyDualMesh`` 와 동일한 개념:

    입력 tet mesh (V_in, T_in) 에 대해
      - internal input vertex v_i → dual cell C_i
      - dual cell 의 vertex 집합 = v_i 를 포함하는 모든 tet 의 centroid
      - dual cell 의 face 는 ConvexHull 로 생성 (같은 평면상의 triangle 은 polygon
        으로 병합)
      - boundary input vertex 는 surface 위에 그대로 남고, 인접 boundary face
        centroid 를 dual vertex 로 추가

본 MVP 는 internal vertex 만 dual cell 로 취급하고, boundary vertex 주위의 cell
은 surface patch 를 닫는 polygon 으로 마감한다. 결과는 OpenFOAM polyMesh 에 직접
기록 (핵심 face-list 형식).

제약:
    - 입력 tet mesh 는 watertight 하다고 가정.
    - degenerate tet 은 미리 제거되어야 함.
    - boundary vertex 주위 dual cell 은 "vertex + 인접 tet centroid + 인접
      boundary face centroid + 인접 boundary edge midpoint" 의 ConvexHull 로 생성.
"""
from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from core.utils.logging import get_logger

log = get_logger(__name__)


@dataclass
class PolyDualResult:
    success: bool
    elapsed: float
    n_cells: int = 0
    n_points: int = 0
    n_faces: int = 0
    message: str = ""


# ---------------------------------------------------------------------------
# Tet topology helpers
# ---------------------------------------------------------------------------

# tet 의 4 face (각 3 vertex), outward winding (v0,v1,v2,v3) 에서 normal 이
# cell 바깥 방향을 향하도록. OpenFOAM tet winding 과 동일한 규칙.
_TET_FACES: tuple[tuple[int, int, int], ...] = (
    (1, 2, 3),  # opposite v0
    (0, 3, 2),  # opposite v1
    (0, 1, 3),  # opposite v2
    (0, 2, 1),  # opposite v3
)

# tet 의 6 edges (정점 pair, sorted)
_TET_EDGES: tuple[tuple[int, int], ...] = (
    (0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3),
)


def _compute_tet_centroids(V: np.ndarray, T: np.ndarray) -> np.ndarray:
    return V[T].mean(axis=1)


def _build_tet_topology(
    T: np.ndarray, n_verts: int,
) -> tuple[
    dict[int, list[int]],               # vertex → list of tet indices
    dict[tuple[int, int], list[int]],   # edge (sorted) → list of tet indices
    dict[tuple[int, int, int], list[int]],  # face (sorted triple) → list of tet indices
]:
    """tet 배열에서 vertex/edge/face 기반 topology map 생성."""
    vert_tets: dict[int, list[int]] = defaultdict(list)
    edge_tets: dict[tuple[int, int], list[int]] = defaultdict(list)
    face_tets: dict[tuple[int, int, int], list[int]] = defaultdict(list)
    for ti, tet in enumerate(T):
        for v in tet:
            vert_tets[int(v)].append(int(ti))
        for a, b in _TET_EDGES:
            va, vb = int(tet[a]), int(tet[b])
            key = (min(va, vb), max(va, vb))
            edge_tets[key].append(int(ti))
        for tri in _TET_FACES:
            verts = [int(tet[i]) for i in tri]
            key = tuple(sorted(verts))
            face_tets[key].append(int(ti))
    return vert_tets, edge_tets, face_tets


def _extract_boundary(
    face_tets: dict[tuple[int, int, int], list[int]],
) -> list[tuple[int, int, int]]:
    """단 1 tet 만 공유하는 triangle = boundary face."""
    return [k for k, tl in face_tets.items() if len(tl) == 1]


# ---------------------------------------------------------------------------
# Dual cell 생성
# ---------------------------------------------------------------------------


def _unique_row_ids(pts: np.ndarray, tol: float = 1e-9) -> np.ndarray:
    """좌표 양자화 기반 unique row index (dedup 후 inverse)."""
    if pts.size == 0:
        return np.zeros(0, dtype=np.int64)
    scale = 1.0 / max(tol, 1e-30)
    keys = np.round(pts * scale).astype(np.int64)
    _, inverse = np.unique(keys, axis=0, return_inverse=True)
    return np.asarray(inverse, dtype=np.int64).reshape(-1)


def _dual_cell_verts(
    v_in: int,
    V: np.ndarray, T: np.ndarray,
    tet_centroids: np.ndarray,
    vert_tets: dict[int, list[int]],
    is_boundary_vert: np.ndarray,
    boundary_faces_of_vert: dict[int, list[tuple[int, int, int]]],
    boundary_edges_of_vert: dict[int, list[tuple[int, int]]],
) -> np.ndarray:
    """input vertex v_in 의 dual cell 을 이루는 3D vertex 집합 반환.

    - internal v: tet centroid 만
    - boundary v: tet centroid + boundary face centroid + boundary edge midpoint
                  + v 자체 (surface 에 남는다)
    """
    tets = vert_tets.get(v_in, [])
    pts = list(tet_centroids[tets])
    if is_boundary_vert[v_in]:
        # boundary face centroids (v_in 포함)
        for tri in boundary_faces_of_vert.get(v_in, []):
            pts.append(V[list(tri)].mean(axis=0))
        # boundary edge midpoints (v_in 포함)
        for (a, b) in boundary_edges_of_vert.get(v_in, []):
            pts.append(0.5 * (V[a] + V[b]))
        # vertex 자신
        pts.append(V[v_in])
    return np.asarray(pts, dtype=np.float64) if pts else np.zeros((0, 3))


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------


def tet_to_poly_dual(
    V: np.ndarray,
    T: np.ndarray,
    case_dir: Path,
    *,
    min_cell_verts: int = 4,
) -> PolyDualResult:
    """tet mesh (V, T) 를 polyhedral dual 로 변환 후 OpenFOAM polyMesh 로 저장.

    Args:
        V: (Nv, 3) tet mesh points.
        T: (Nt, 4) tet cell connectivity (zero-based).
        case_dir: 출력 OpenFOAM case 디렉터리.
        min_cell_verts: dual cell 을 생성하기 위한 최소 vertex 수. 4 이상이어야
            ConvexHull 이 3D polyhedron 을 만들 수 있다.

    Returns:
        PolyDualResult.
    """
    t0 = time.perf_counter()

    V = np.asarray(V, dtype=np.float64)
    T = np.asarray(T, dtype=np.int64)
    n_verts = int(V.shape[0])
    n_tets = int(T.shape[0])
    if n_verts == 0 or n_tets == 0:
        return PolyDualResult(False, 0.0, message="빈 tet mesh")

    try:
        from scipy.spatial import ConvexHull  # noqa: PLC0415
    except Exception as exc:
        return PolyDualResult(False, 0.0, message=f"scipy 필요: {exc}")

    # 1) topology
    vert_tets, edge_tets, face_tets = _build_tet_topology(T, n_verts)
    boundary_faces = _extract_boundary(face_tets)

    # boundary vertex / edge 집합
    is_boundary_vert = np.zeros(n_verts, dtype=bool)
    boundary_edges_set: set[tuple[int, int]] = set()
    boundary_faces_of_vert: dict[int, list[tuple[int, int, int]]] = defaultdict(list)
    boundary_edges_of_vert: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for tri in boundary_faces:
        for v in tri:
            is_boundary_vert[v] = True
            boundary_faces_of_vert[v].append(tri)
        # boundary edges = 3 edges of boundary triangle
        e01 = (min(tri[0], tri[1]), max(tri[0], tri[1]))
        e12 = (min(tri[1], tri[2]), max(tri[1], tri[2]))
        e20 = (min(tri[2], tri[0]), max(tri[2], tri[0]))
        for e in (e01, e12, e20):
            boundary_edges_set.add(e)
    for (a, b) in boundary_edges_set:
        boundary_edges_of_vert[a].append((a, b))
        boundary_edges_of_vert[b].append((a, b))

    tet_centroids = _compute_tet_centroids(V, T)

    log.info(
        "native_poly_dual_topology",
        n_verts=n_verts, n_tets=n_tets,
        n_boundary_faces=len(boundary_faces),
        n_boundary_verts=int(is_boundary_vert.sum()),
    )

    # 2) 각 input vertex 마다 dual cell 생성 (ConvexHull)
    # 누적 점/셀 face 데이터
    all_points: list[np.ndarray] = []   # unique dual points (나중에 stack)
    cell_face_lists: list[list[list[int]]] = []  # cell_i → [face_vertices, ...]
    cell_centroid_list: list[np.ndarray] = []   # cell_i → 3D centroid
    # 점 dedup 을 위해 global dict (3D 좌표 → global idx)
    point_id_of: dict[tuple[int, int, int], int] = {}
    point_tol = 1e-9
    scale = 1.0 / point_tol

    def _add_point(p: np.ndarray) -> int:
        key = tuple(np.round(p * scale).astype(np.int64).tolist())
        if key in point_id_of:
            return point_id_of[key]
        idx = len(point_id_of)
        point_id_of[key] = idx
        all_points.append(p)
        return idx

    n_skipped = 0
    for v_in in range(n_verts):
        pts = _dual_cell_verts(
            v_in, V, T, tet_centroids, vert_tets,
            is_boundary_vert, boundary_faces_of_vert, boundary_edges_of_vert,
        )
        if pts.shape[0] < min_cell_verts:
            n_skipped += 1
            continue
        # ConvexHull 로 polyhedron 생성
        try:
            hull = ConvexHull(pts, qhull_options="QJ")
        except Exception:
            n_skipped += 1
            continue
        # hull.simplices 는 triangle 분할. 평면 coplanar triangle 을 병합해 polygon 생성.
        # hull.equations = (n_simplex, 4) [a, b, c, d] (a·x+b·y+c·z+d=0)
        simplices = hull.simplices
        eqs = hull.equations
        # 같은 face-plane 의 simplex 는 같은 group. 평면 방정식을 정규화해 dedup.
        # rounding 으로 grouping
        eq_key = np.round(eqs * 1e6).astype(np.int64)
        # group by eq_key
        group_of: dict[tuple[int, ...], list[int]] = defaultdict(list)
        for si, k in enumerate(map(tuple, eq_key.tolist())):
            group_of[k].append(si)
        # 각 group 에서 polygon vertex (ordered) 추출
        local_cell_centroid = pts.mean(axis=0)
        cell_face_verts: list[list[int]] = []
        for _, simp_ids in group_of.items():
            # union 의 vertex 집합
            verts_local: set[int] = set()
            for si in simp_ids:
                verts_local.update(int(x) for x in simplices[si])
            verts_list = sorted(verts_local)
            if len(verts_list) < 3:
                continue
            # 평면 위 CCW sort (cell centroid 밖 방향 normal)
            poly_pts = pts[verts_list]
            c = poly_pts.mean(axis=0)
            n_plane = np.array([eqs[simp_ids[0], 0], eqs[simp_ids[0], 1], eqs[simp_ids[0], 2]])
            # ConvexHull 은 normal 을 바깥 방향으로 내보냄 (d < 0 for inside). centroid
            # 에서 c 로 가는 방향이 n_plane 과 같은 부호여야 cell 바깥.
            # e1 = c 에서 첫 vertex 로
            e1 = poly_pts[0] - c
            e1 -= n_plane * float(np.dot(e1, n_plane))
            if float(np.linalg.norm(e1)) < 1e-30:
                # degenerate — 다른 vertex 로 재시도
                for k in range(1, len(poly_pts)):
                    e1 = poly_pts[k] - c
                    e1 -= n_plane * float(np.dot(e1, n_plane))
                    if float(np.linalg.norm(e1)) >= 1e-30:
                        break
            n_len = float(np.linalg.norm(e1))
            if n_len < 1e-30:
                continue
            e1 = e1 / n_len
            e2 = np.cross(n_plane, e1)
            rel = poly_pts - c
            proj = np.stack([rel @ e1, rel @ e2], axis=1)
            angles = np.arctan2(proj[:, 1], proj[:, 0])
            order = np.argsort(angles)
            ordered_verts_local = [verts_list[int(k)] for k in order]
            # global id 매핑
            global_ids = [_add_point(pts[lv]) for lv in ordered_verts_local]
            cell_face_verts.append(global_ids)

        if not cell_face_verts:
            n_skipped += 1
            continue
        cell_face_lists.append(cell_face_verts)
        cell_centroid_list.append(local_cell_centroid)

    if not cell_face_lists:
        return PolyDualResult(
            False, time.perf_counter() - t0,
            message="dual cell 0 — 입력 mesh 가 너무 작거나 degenerate",
        )

    dual_points = np.asarray(all_points, dtype=np.float64)

    log.info(
        "native_poly_dual_cells",
        n_cells=len(cell_face_lists), n_points=dual_points.shape[0],
        skipped=n_skipped,
    )

    # 3) face dedup + internal/boundary 분류 + winding 보정
    face_map: dict[tuple[int, ...], list[tuple[int, list[int]]]] = defaultdict(list)
    for ci, face_list in enumerate(cell_face_lists):
        for f in face_list:
            key = tuple(sorted(f))
            face_map[key].append((ci, list(f)))

    internal_faces: list[list[int]] = []
    internal_owner: list[int] = []
    internal_nbr: list[int] = []
    boundary_faces_out: list[list[int]] = []
    boundary_owner: list[int] = []

    def _flip_if_inward(face: list[int], cell_centroid: np.ndarray) -> list[int]:
        """face normal 이 cell centroid 바깥 방향이면 유지, 안쪽이면 reverse."""
        pts3 = dual_points[face]
        fc = pts3.mean(axis=0)
        # 3-vertex 기반 normal
        n = np.cross(pts3[1] - pts3[0], pts3[2] - pts3[0])
        if float(np.dot(n, fc - cell_centroid)) < 0:
            return list(reversed(face))
        return face

    for key, refs in face_map.items():
        if len(refs) == 2:
            (ca, fa), (cb, fb) = refs
            own = min(ca, cb); nbr = max(ca, cb)
            f_use = fa if ca == own else fb
            f_oriented = _flip_if_inward(f_use, cell_centroid_list[own])
            internal_faces.append(f_oriented)
            internal_owner.append(own)
            internal_nbr.append(nbr)
        elif len(refs) == 1:
            (ci, fv) = refs[0]
            f_oriented = _flip_if_inward(fv, cell_centroid_list[ci])
            boundary_faces_out.append(f_oriented)
            boundary_owner.append(ci)

    # 4) 정렬: internal 은 (owner, nbr), boundary 는 owner 기준
    int_order = sorted(
        range(len(internal_faces)),
        key=lambda i: (internal_owner[i], internal_nbr[i]),
    )
    bnd_order = sorted(range(len(boundary_faces_out)), key=lambda i: boundary_owner[i])

    final_faces: list[list[int]] = []
    final_owner: list[int] = []
    final_nbr: list[int] = []
    for i in int_order:
        final_faces.append(internal_faces[i])
        final_owner.append(internal_owner[i])
        final_nbr.append(internal_nbr[i])
    for i in bnd_order:
        final_faces.append(boundary_faces_out[i])
        final_owner.append(boundary_owner[i])

    # 5) polyMesh 쓰기
    poly_dir = case_dir / "constant" / "polyMesh"
    poly_dir.mkdir(parents=True, exist_ok=True)
    from core.generator.tier_layers_post import (  # noqa: PLC0415
        _ensure_minimal_controldict, _write_minimal_fv_dicts,
    )
    _ensure_minimal_controldict(case_dir)
    _write_minimal_fv_dicts(case_dir)
    from core.layers.native_bl import (  # noqa: PLC0415
        _write_boundary, _write_faces, _write_labels, _write_points,
    )
    _write_points(poly_dir / "points", dual_points)
    _write_faces(poly_dir / "faces", final_faces)
    _write_labels(
        poly_dir / "owner", np.array(final_owner, dtype=np.int64), "owner",
    )
    _write_labels(
        poly_dir / "neighbour", np.array(final_nbr, dtype=np.int64), "neighbour",
    )
    _write_boundary(
        poly_dir / "boundary",
        [{
            "name": "defaultWall",
            "type": "wall",
            "nFaces": len(boundary_faces_out),
            "startFace": len(internal_faces),
        }],
    )

    elapsed = time.perf_counter() - t0
    return PolyDualResult(
        success=True,
        elapsed=elapsed,
        n_cells=len(cell_face_lists),
        n_points=int(dual_points.shape[0]),
        n_faces=len(final_faces),
        message=(
            f"tet→poly dual OK — cells={len(cell_face_lists)}, "
            f"points={dual_points.shape[0]}, faces={len(final_faces)}, "
            f"skipped_cells={n_skipped}"
        ),
    )
