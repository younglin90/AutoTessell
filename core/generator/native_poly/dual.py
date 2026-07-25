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
from collections.abc import Callable, Mapping, Sequence
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


def _normalise_entity_label(label: Any) -> tuple[str, str]:
    """Convert a primal boundary-entity label to an OpenFOAM patch label.

    Garimella's construction classifies primal boundary faces before the dual
    subcomplex is assembled.  The polyMesh writer has two semantic fields for
    that classification (patch name and patch type), so accept the compact
    string/tuple forms as well as a mapping for callers that also carry an
    application-specific ``entity`` field.
    """
    if isinstance(label, Mapping):
        name = label.get("patch") or label.get("name") or label.get("label")
        patch_type = label.get("type") or "wall"
    elif isinstance(label, (tuple, list)):
        name = label[0] if label else None
        patch_type = label[1] if len(label) > 1 else "wall"
    else:
        name = label
        patch_type = "wall"
    return str(name or "defaultWall"), str(patch_type or "wall")


def _boundary_entity_labels(
    boundary_faces: Sequence[tuple[int, int, int]],
    vertices: np.ndarray,
    labels: Mapping[tuple[int, int, int], Any] | Sequence[Any] | None,
    classifier: Callable[[tuple[int, int, int], np.ndarray], Any] | None,
) -> dict[tuple[int, int, int], tuple[str, str]]:
    """Resolve source labels for canonical primal boundary triangles."""
    if labels is not None and classifier is not None:
        raise ValueError("boundary_face_labels and boundary_face_classifier are mutually exclusive")

    if classifier is not None:
        return {tri: _normalise_entity_label(classifier(tri, vertices)) for tri in boundary_faces}

    if labels is None:
        return {}

    if isinstance(labels, Mapping):
        canonical_labels = {
            tuple(sorted(map(int, key))): value
            for key, value in labels.items()
            if isinstance(key, (tuple, list)) and len(key) == 3
        }
        resolved: dict[tuple[int, int, int], tuple[str, str]] = {}
        for tri in boundary_faces:
            raw = canonical_labels.get(tuple(sorted(tri)))
            resolved[tri] = _normalise_entity_label(raw)
        return resolved

    if len(labels) != len(boundary_faces):
        raise ValueError(
            "boundary_face_labels sequence must align with the extracted "
            f"boundary faces ({len(boundary_faces)} expected, {len(labels)} received)"
        )
    return {tri: _normalise_entity_label(raw) for tri, raw in zip(boundary_faces, labels)}


def _group_classified_boundary_faces(
    faces: list[list[int]],
    owners: list[int],
    labels: list[tuple[str, str]],
    n_internal: int,
) -> tuple[list[list[int]], list[int], list[dict[str, Any]]]:
    """Make classified boundary faces contiguous and emit boundary entries."""
    groups: dict[tuple[str, str], list[int]] = {}
    for rel_idx, label in enumerate(labels):
        groups.setdefault(label, []).append(rel_idx)

    grouped_faces: list[list[int]] = []
    grouped_owners: list[int] = []
    entries: list[dict[str, Any]] = []
    cursor = n_internal
    for (name, patch_type), rel_indices in groups.items():
        start = cursor
        grouped_faces.extend(faces[rel_idx] for rel_idx in rel_indices)
        grouped_owners.extend(owners[rel_idx] for rel_idx in rel_indices)
        cursor += len(rel_indices)
        entries.append(
            {
                "name": name,
                "type": patch_type,
                "nFaces": len(rel_indices),
                "startFace": start,
            }
        )
    return grouped_faces, grouped_owners, entries


def _ordered_boundary_labels(
    labels: list[tuple[str, str]], owners: list[int]
) -> list[tuple[str, str]]:
    """Apply the same stable owner ordering used by ``_order_and_concat``."""
    order = sorted(range(len(labels)), key=lambda idx: owners[idx])
    return [labels[idx] for idx in order]


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
    (0, 1),
    (0, 2),
    (0, 3),
    (1, 2),
    (1, 3),
    (2, 3),
)


def _compute_tet_centroids(V: np.ndarray, T: np.ndarray) -> np.ndarray:
    return V[T].mean(axis=1)


def _build_tet_topology(
    T: np.ndarray,
    n_verts: int,
) -> tuple[
    dict[int, list[int]],  # vertex → list of tet indices
    dict[tuple[int, int], list[int]],  # edge (sorted) → list of tet indices
    dict[tuple[int, int, int], list[int]],  # face (sorted triple) → list of tet indices
]:
    """tet 배열에서 vertex/edge/face 기반 topology map 생성 (vectorized)."""
    vert_tets: dict[int, list[int]] = defaultdict(list)
    edge_tets: dict[tuple[int, int], list[int]] = defaultdict(list)
    face_tets: dict[tuple[int, int, int], list[int]] = defaultdict(list)

    n_tets = T.shape[0]
    ti_arr = np.arange(n_tets, dtype=np.int64)

    # --- vertex → tet (4 verts per tet) ---
    # T shape: (n_tets, 4); repeat ti for each of the 4 verts
    vert_col = T.reshape(-1)  # (n_tets*4,)
    ti_col = np.repeat(ti_arr, 4)  # (n_tets*4,)
    for v, ti in zip(vert_col.tolist(), ti_col.tolist()):
        vert_tets[v].append(ti)

    # --- edge → tet (6 edges per tet, fixed indices _TET_EDGES) ---
    _EA = np.array([a for a, _ in _TET_EDGES], dtype=np.int64)  # (6,)
    _EB = np.array([b for _, b in _TET_EDGES], dtype=np.int64)  # (6,)
    # for each tet gather the two endpoint global indices
    ea = T[:, _EA]  # (n_tets, 6)
    eb = T[:, _EB]  # (n_tets, 6)
    emin = np.minimum(ea, eb)  # (n_tets, 6)
    emax = np.maximum(ea, eb)  # (n_tets, 6)
    ti_e = np.repeat(ti_arr, 6)  # (n_tets*6,)
    for (a, b), ti in zip(zip(emin.reshape(-1).tolist(), emax.reshape(-1).tolist()), ti_e.tolist()):
        edge_tets[(a, b)].append(ti)

    # --- face → tet (4 faces per tet, fixed indices _TET_FACES) ---
    _FA = np.array([tri[0] for tri in _TET_FACES], dtype=np.int64)  # (4,)
    _FB = np.array([tri[1] for tri in _TET_FACES], dtype=np.int64)  # (4,)
    _FC = np.array([tri[2] for tri in _TET_FACES], dtype=np.int64)  # (4,)
    fa = T[:, _FA]  # (n_tets, 4)
    fb = T[:, _FB]  # (n_tets, 4)
    fc = T[:, _FC]  # (n_tets, 4)
    # stack and sort each row of 3 to get canonical key
    face_verts = np.stack([fa, fb, fc], axis=2)  # (n_tets, 4, 3)
    face_verts_sorted = np.sort(face_verts, axis=2)  # (n_tets, 4, 3)
    ti_f = np.repeat(ti_arr, 4)  # (n_tets*4,)
    fv = face_verts_sorted.reshape(-1, 3)  # (n_tets*4, 3)
    for row, ti in zip(fv.tolist(), ti_f.tolist()):
        face_tets[(row[0], row[1], row[2])].append(ti)

    return vert_tets, edge_tets, face_tets


def _extract_boundary(
    face_tets: dict[tuple[int, int, int], list[int]],
) -> list[tuple[int, int, int]]:
    """단 1 tet 만 공유하는 triangle = boundary face."""
    return [k for k, tl in face_tets.items() if len(tl) == 1]


def _tet_faces_with_edge(tv: np.ndarray, a: int, b: int) -> list[tuple[int, int, int]]:
    """tet 정점 tv 중 edge(a,b) 를 포함하는 2개 face(정렬된 triple)."""
    out: list[tuple[int, int, int]] = []
    for face in _TET_FACES:
        tri = (int(tv[face[0]]), int(tv[face[1]]), int(tv[face[2]]))
        if a in tri and b in tri:
            out.append(tuple(sorted(tri)))
    return out


def _ordered_tet_ring(
    e: tuple[int, int],
    edge_tets: dict[tuple[int, int], list[int]],
    face_tets: dict[tuple[int, int, int], list[int]],
    T: np.ndarray,
) -> tuple[list[int], bool]:
    """edge e 를 공유하는 tet 들을 공유 face 로 walk 하여 정렬된 ring 반환.

    내부 edge(주변 face 가 모두 2-tet 공유) -> 닫힌 ring, closed=True.
    경계 edge(끝 face 가 1-tet, boundary face) -> open fan, closed=False.
    """
    a, b = e
    tets = edge_tets.get(e, [])
    if not tets:
        return [], False
    tet_faces = {ti: _tet_faces_with_edge(T[ti], a, b) for ti in tets}
    start, start_face = tets[0], tet_faces[tets[0]][0]
    for ti in tets:
        for f in tet_faces[ti]:
            if len(face_tets[f]) == 1:
                start, start_face = ti, f
                break
        else:
            continue
        break
    ring = [start]
    visited = {start}
    cur, cur_face = start, start_face
    while True:
        f0, f1 = tet_faces[cur]
        other = f1 if f0 == cur_face else f0
        nbrs = face_tets[other]
        if len(nbrs) < 2:
            return ring, False
        nxt = nbrs[1] if nbrs[0] == cur else nbrs[0]
        if nxt in visited:
            return ring, True
        ring.append(nxt)
        visited.add(nxt)
        cur, cur_face = nxt, other


def _surface_planes(
    V: np.ndarray,
    boundary_faces: list[tuple[int, int, int]],
) -> list[tuple[np.ndarray, float]]:
    """원본 입력 surface triangle 들의 고유 평면(normal, offset) 목록."""
    planes: list[tuple[np.ndarray, float]] = []
    seen: set[tuple[int, ...]] = set()
    for tri in boundary_faces:
        p0, p1, p2 = V[tri[0]], V[tri[1]], V[tri[2]]
        n = np.cross(p1 - p0, p2 - p0)
        norm = float(np.linalg.norm(n))
        if norm < 1e-12:
            continue
        n = n / norm
        d = -float(np.dot(n, p0))
        key = tuple(np.round(np.append(n, d) * 1e4).astype(np.int64).tolist())
        key = min(key, tuple(-x for x in key))
        if key in seen:
            continue
        seen.add(key)
        planes.append((n, d))
    return planes


def _area_split(
    points: np.ndarray,
    faces: list[list[int]],
    planes: list[tuple[np.ndarray, float]],
    tol: float = 1e-6,
) -> tuple[float, float]:
    """boundary face 들을 (원본 surface 평면 위 area, 그 외 area) 로 분리."""
    on = off = 0.0
    for f in faces:
        p = points[np.asarray(f, dtype=int)]
        acc = np.zeros(3)
        for i in range(1, len(f) - 1):
            acc = acc + np.cross(p[i] - p[0], p[i + 1] - p[0]) / 2.0
        area = float(np.linalg.norm(acc))
        is_on = any(np.all(np.abs(p @ n + d) < tol) for n, d in planes)
        if is_on:
            on += area
        else:
            off += area
    return on, off


def _order_and_concat(
    i_faces: list[list[int]],
    i_own: list[int],
    i_nbr: list[int],
    b_faces: list[list[int]],
    b_own: list[int],
) -> tuple[list[list[int]], list[int], list[int], int]:
    """internal(owner,nbr 정렬) + boundary(owner 정렬) face 를 하나로 합친다."""
    oi = sorted(range(len(i_faces)), key=lambda k: (i_own[k], i_nbr[k]))
    ob = sorted(range(len(b_faces)), key=lambda k: b_own[k])
    faces = [i_faces[k] for k in oi] + [b_faces[k] for k in ob]
    owner = [i_own[k] for k in oi] + [b_own[k] for k in ob]
    nbr = [i_nbr[k] for k in oi]
    return faces, owner, nbr, len(b_faces)


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
    V: np.ndarray,
    T: np.ndarray,
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
        for a, b in boundary_edges_of_vert.get(v_in, []):
            pts.append(0.5 * (V[a] + V[b]))
        # vertex 자신
        pts.append(V[v_in])
    return np.asarray(pts, dtype=np.float64) if pts else np.zeros((0, 3))


def _smooth_interior_tet_verts(
    V: np.ndarray,
    T: np.ndarray,
    is_boundary_vert: np.ndarray,
    edge_tets: dict[tuple[int, int], list[int]],
    n_iter: int = 10,
    relax: float = 0.5,
) -> np.ndarray:
    """interior tet vertex 만 Laplacian smoothing (boundary vertex 는 고정).

    per-vertex inversion 가드: 이동 후 incident tet vol 이 하나라도
    ``<= 1e-4*orig_vol`` 이면 그 vertex 이동만 revert. 전역적으로
    min_tet_vol <= 0 이 남으면 전체 V 를 원본으로 revert.
    """

    def _tet_vols(Vc: np.ndarray, idx: np.ndarray) -> np.ndarray:
        tv = T[idx]
        p0, p1, p2, p3 = Vc[tv[:, 0]], Vc[tv[:, 1]], Vc[tv[:, 2]], Vc[tv[:, 3]]
        return np.einsum("ij,ij->i", p1 - p0, np.cross(p2 - p0, p3 - p0)) / 6.0

    V0 = V.copy()
    orig_vol = np.abs(_tet_vols(V0, np.arange(T.shape[0])))
    nbrs: dict[int, set[int]] = defaultdict(set)
    vert_tets: dict[int, list[int]] = defaultdict(list)
    for a, b in edge_tets:
        nbrs[a].add(b)
        nbrs[b].add(a)
    for ti, tv in enumerate(T):
        for v in tv:
            vert_tets[int(v)].append(ti)
    interior = [v for v in range(V.shape[0]) if not is_boundary_vert[v] and nbrs.get(v)]

    Vs = V0.copy()
    for _ in range(n_iter):
        for v in interior:
            nb = np.array(list(nbrs[v]), dtype=np.int64)
            old = Vs[v].copy()
            Vs[v] = old + relax * (Vs[nb].mean(axis=0) - old)
            idx = np.asarray(vert_tets[v], dtype=np.int64)
            if np.any(np.abs(_tet_vols(Vs, idx)) <= 1e-4 * orig_vol[idx]):
                Vs[v] = old

    if np.any(_tet_vols(Vs, np.arange(T.shape[0])) <= 0):
        return V0
    return Vs


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------


def tet_to_poly_dual(
    V: np.ndarray,
    T: np.ndarray,
    case_dir: Path,
    *,
    min_cell_verts: int = 4,
    boundary_face_labels: Mapping[tuple[int, int, int], Any] | Sequence[Any] | None = None,
    boundary_face_entities: Mapping[tuple[int, int, int], Any] | Sequence[Any] | None = None,
    boundary_face_classifier: Callable[[tuple[int, int, int], np.ndarray], Any] | None = None,
) -> PolyDualResult:
    """tet mesh (V, T) 를 polyhedral dual 로 변환 후 OpenFOAM polyMesh 로 저장.

    Args:
        V: (Nv, 3) tet mesh points.
        T: (Nt, 4) tet cell connectivity (zero-based).
        case_dir: 출력 OpenFOAM case 디렉터리.
        min_cell_verts: dual cell 을 생성하기 위한 최소 vertex 수. 4 이상이어야
            ConvexHull 이 3D polyhedron 을 만들 수 있다.
        boundary_face_labels: optional source patch/entity labels keyed by canonical
            primal boundary triangle or supplied in extracted-boundary order.
        boundary_face_entities: alias for ``boundary_face_labels`` for callers that
            name the Garimella classification explicitly.
        boundary_face_classifier: optional callback receiving ``(triangle, V)`` and
            returning a patch name, ``(name, type)`` pair, or mapping.

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
    if boundary_face_labels is not None and boundary_face_entities is not None:
        return PolyDualResult(
            False,
            time.perf_counter() - t0,
            message="boundary_face_labels and boundary_face_entities are mutually exclusive",
        )
    supplied_entity_labels = (
        boundary_face_labels if boundary_face_labels is not None else boundary_face_entities
    )
    try:
        source_entity_labels = _boundary_entity_labels(
            boundary_faces,
            V,
            supplied_entity_labels,
            boundary_face_classifier,
        )
    except (TypeError, ValueError) as exc:
        return PolyDualResult(
            False,
            time.perf_counter() - t0,
            message=f"boundary entity classification failed: {exc}",
        )
    classification_active = bool(
        supplied_entity_labels is not None or boundary_face_classifier is not None
    )

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
    for a, b in boundary_edges_set:
        boundary_edges_of_vert[a].append((a, b))
        boundary_edges_of_vert[b].append((a, b))

    V = _smooth_interior_tet_verts(V, T, is_boundary_vert, edge_tets)

    tet_centroids = _compute_tet_centroids(V, T)

    log.info(
        "native_poly_dual_topology",
        n_verts=n_verts,
        n_tets=n_tets,
        n_boundary_faces=len(boundary_faces),
        n_boundary_verts=int(is_boundary_vert.sum()),
    )

    # 2) 각 input vertex 마다 dual cell 점 집합 + boundary cap 후보(ConvexHull) 생성
    all_points: list[np.ndarray] = []  # unique dual points (나중에 stack)
    cell_face_lists: list[list[list[int]]] = []  # cell_i → [face_vertices, ...]
    cell_face_is_cap: list[list[bool]] = []  # cell_i → face 가 surface cap 인지
    cell_face_labels: list[list[tuple[str, str] | None]] = []
    cell_centroid_list: list[np.ndarray] = []  # cell_i → 3D centroid
    cell_index_of_vert: dict[int, int] = {}  # input vertex → cell index
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

    # tet centroid 는 인접 vertex 들이 공유하는 dual point 이므로 미리 고정 등록.
    tet_point_id = np.array(
        [_add_point(tet_centroids[ti]) for ti in range(n_tets)],
        dtype=np.int64,
    )
    # boundary face centroid / boundary edge midpoint 도 안정적인 dual point id 로
    # 미리 등록한다 (POLY-S3: on-plane cap + boundary-edge separating face 가 공유).
    bface_pid: dict[tuple[int, int, int], int] = {
        tri: _add_point(V[list(tri)].mean(axis=0)) for tri in boundary_faces
    }
    bedge_pid: dict[tuple[int, int], int] = {
        e: _add_point(0.5 * (V[e[0]] + V[e[1]])) for e in boundary_edges_set
    }
    boundary_vertex_pid: dict[int, int] = {}
    if classification_active:
        boundary_vertex_pid = {
            v: _add_point(V[v]) for v in np.flatnonzero(is_boundary_vert).tolist()
        }

    n_skipped = 0
    for v_in in range(n_verts):
        n_tet_pts = len(vert_tets.get(v_in, []))
        pts = _dual_cell_verts(
            v_in,
            V,
            T,
            tet_centroids,
            vert_tets,
            is_boundary_vert,
            boundary_faces_of_vert,
            boundary_edges_of_vert,
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
        cell_face_caps: list[bool] = []
        cell_face_entity_labels: list[tuple[str, str] | None] = []
        local_face_triangles = {
            n_tet_pts + local_idx: tri
            for local_idx, tri in enumerate(boundary_faces_of_vert.get(v_in, []))
        }
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
            is_cap = any(lv >= n_tet_pts for lv in ordered_verts_local)
            cell_face_caps.append(is_cap)
            cap_triangles = {
                local_face_triangles[lv] for lv in ordered_verts_local if lv in local_face_triangles
            }
            cap_labels = {
                source_entity_labels[tri] for tri in cap_triangles if tri in source_entity_labels
            }
            # A hull cap may span multiple coplanar source faces.  The
            # classified path below splits those caps per source triangle; the
            # single fallback label here keeps the old ConvexHull path usable
            # if its monotonic guard rejects the classified topology.
            cell_face_entity_labels.append(next(iter(cap_labels)) if len(cap_labels) == 1 else None)

        if not cell_face_verts:
            n_skipped += 1
            continue
        cell_index_of_vert[v_in] = len(cell_face_lists)
        cell_face_lists.append(cell_face_verts)
        cell_face_is_cap.append(cell_face_caps)
        cell_face_labels.append(cell_face_entity_labels)
        cell_centroid_list.append(local_cell_centroid)

    if not cell_face_lists:
        return PolyDualResult(
            False,
            time.perf_counter() - t0,
            message="dual cell 0 — 입력 mesh 가 너무 작거나 degenerate",
        )

    dual_points = np.asarray(all_points, dtype=np.float64)

    log.info(
        "native_poly_dual_cells",
        n_cells=len(cell_face_lists),
        n_points=dual_points.shape[0],
        skipped=n_skipped,
    )

    def _flip_if_inward(face: list[int], cell_centroid: np.ndarray) -> list[int]:
        """face normal 이 cell centroid 바깥 방향이면 유지, 안쪽이면 reverse."""
        pts3 = dual_points[face]
        fc = pts3.mean(axis=0)
        # 3-vertex 기반 normal
        n = np.cross(pts3[1] - pts3[0], pts3[2] - pts3[0])
        if float(np.dot(n, fc - cell_centroid)) < 0:
            return list(reversed(face))
        return face

    # 3a) path A (기존): ConvexHull face 정확 정점집합 dedup
    face_map: dict[tuple[int, ...], list[tuple[int, list[int]]]] = defaultdict(list)
    for ci, face_list in enumerate(cell_face_lists):
        for f in face_list:
            face_map[tuple(sorted(f))].append((ci, list(f)))

    a_i_faces: list[list[int]] = []
    a_i_own: list[int] = []
    a_i_nbr: list[int] = []
    a_b_faces: list[list[int]] = []
    a_b_own: list[int] = []
    a_b_labels: list[tuple[str, str]] = []
    for refs in face_map.values():
        if len(refs) == 2:
            (ca, fa), (cb, fb) = refs
            own, nbr = min(ca, cb), max(ca, cb)
            f_use = fa if ca == own else fb
            a_i_faces.append(_flip_if_inward(f_use, cell_centroid_list[own]))
            a_i_own.append(own)
            a_i_nbr.append(nbr)
        elif len(refs) == 1:
            ci, fv = refs[0]
            a_b_faces.append(_flip_if_inward(fv, cell_centroid_list[ci]))
            a_b_own.append(ci)
            if classification_active:
                face_idx = cell_face_lists[ci].index(fv)
                a_b_labels.append(cell_face_labels[ci][face_idx] or ("defaultWall", "wall"))

    # 3b) path B (신규): tet edge 주위 위상적 centroid ring → internal face,
    # boundary cap 은 path A 의 hull 결과 중 surface 점을 포함한 face 만 재사용.
    b_i_faces: list[list[int]] = []
    b_i_own: list[int] = []
    b_i_nbr: list[int] = []
    for e in edge_tets:
        if e in boundary_edges_set:
            continue
        u, w = e
        if u not in cell_index_of_vert or w not in cell_index_of_vert:
            continue
        ring, closed = _ordered_tet_ring(e, edge_tets, face_tets, T)
        if not closed or len(ring) < 3:
            continue
        own = cell_index_of_vert[u]
        face = [int(tet_point_id[ti]) for ti in ring]
        b_i_faces.append(_flip_if_inward(face, cell_centroid_list[own]))
        b_i_own.append(own)
        b_i_nbr.append(cell_index_of_vert[w])

    # 3b') boundary-edge separating face: 인접 boundary cell 이 surface edge 를
    # 가로질러 공유해야 할 내부면 (line-511 이 skip 하던 boundary edge 를 보완).
    edge_to_btris: dict[tuple[int, int], list[tuple[int, int, int]]] = defaultdict(list)
    for tri in boundary_faces:
        e01 = (min(tri[0], tri[1]), max(tri[0], tri[1]))
        e12 = (min(tri[1], tri[2]), max(tri[1], tri[2]))
        e20 = (min(tri[2], tri[0]), max(tri[2], tri[0]))
        for e in (e01, e12, e20):
            edge_to_btris[e].append(tri)
    for e in boundary_edges_set:
        u, w = e
        if u not in cell_index_of_vert or w not in cell_index_of_vert:
            continue
        btris = edge_to_btris.get(e, [])
        if len(btris) != 2:
            continue
        t_a, t_b = btris
        ring, _closed = _ordered_tet_ring(e, edge_tets, face_tets, T)
        if not ring:
            continue
        raw = (
            [bface_pid[t_a]]
            + [int(tet_point_id[ti]) for ti in ring]
            + [bface_pid[t_b], bedge_pid[e]]
        )
        be_face: list[int] = []
        for pid in raw:
            if not be_face or be_face[-1] != pid:
                be_face.append(pid)
        if len(be_face) > 1 and be_face[0] == be_face[-1]:
            be_face.pop()
        if len(be_face) < 3:
            continue
        own = cell_index_of_vert[u]
        b_i_faces.append(_flip_if_inward(be_face, cell_centroid_list[own]))
        b_i_own.append(own)
        b_i_nbr.append(cell_index_of_vert[w])

    # 3c) on-plane cap 필터: is_cap 은 surface 점을 하나라도 포함하면 true 이므로
    # 내부를 향한 hull face 까지 새어들어온다. 진짜 cap 은 "모든 정점이 한 입력
    # 평면 위" 인 face 뿐 — off-plane face 는 위 boundary-edge/edge-ring 이 이미
    # 내부를 닫으므로 버린다.
    surface_planes = _surface_planes(V, boundary_faces)

    def _is_on_plane(face: list[int], tol: float = 1e-6) -> bool:
        p = dual_points[np.asarray(face, dtype=int)]
        return any(np.all(np.abs(p @ n + d) < tol) for n, d in surface_planes)

    b_b_faces: list[list[int]] = []
    b_b_own: list[int] = []
    b_b_labels: list[tuple[str, str]] = []
    if classification_active:
        # Garimella-style entity classification: one boundary cap per
        # classified primal boundary face and incident primal vertex.  The
        # four points are already part of the unmodified dual point set, so
        # this only refines the surface subcomplex and never moves geometry.
        for v_in, ci in cell_index_of_vert.items():
            if not is_boundary_vert[v_in]:
                continue
            for tri in boundary_faces_of_vert.get(v_in, []):
                others = [int(v) for v in tri if int(v) != v_in]
                if len(others) != 2:
                    continue
                edge_a = (min(v_in, others[0]), max(v_in, others[0]))
                edge_b = (min(v_in, others[1]), max(v_in, others[1]))
                raw_face = [
                    boundary_vertex_pid[v_in],
                    bedge_pid[edge_a],
                    bface_pid[tri],
                    bedge_pid[edge_b],
                ]
                face: list[int] = []
                for pid in raw_face:
                    if not face or face[-1] != pid:
                        face.append(pid)
                if len(face) >= 3:
                    b_b_faces.append(_flip_if_inward(face, cell_centroid_list[ci]))
                    b_b_own.append(ci)
                    b_b_labels.append(source_entity_labels[tri])
    else:
        for v_in, ci in cell_index_of_vert.items():
            if not is_boundary_vert[v_in]:
                continue
            for f, is_cap in zip(cell_face_lists[ci], cell_face_is_cap[ci]):
                if is_cap and _is_on_plane(list(f)):
                    b_b_faces.append(_flip_if_inward(list(f), cell_centroid_list[ci]))
                    b_b_own.append(ci)

    # 3d) 단조 가드: on/off-plane boundary area split 으로 path 선택.
    # path B 가 void 를 늘리거나 surface coverage 를 깨면 path A 로 복귀한다.
    pre_on, pre_off = _area_split(dual_points, a_b_faces, surface_planes)
    post_on, post_off = _area_split(dual_points, b_b_faces, surface_planes)
    use_topo = (
        len(b_i_faces) > 0 and post_off <= pre_off and pre_on * 0.95 <= post_on <= pre_on * 1.05
    )
    if classification_active:
        # The classified cap subcomplex is the source-surface partition. Its
        # area is authoritative even when the legacy hull-cap area differs by
        # more than the old monotonic guard's diagnostic 5% window.
        use_topo = len(b_i_faces) > 0 and len(b_b_faces) > 0 and post_off <= pre_off + 1e-12
    log.info(
        "native_poly_dual_guard",
        pre_on=pre_on,
        pre_off=pre_off,
        post_on=post_on,
        post_off=post_off,
        classified=classification_active,
        use_topo=use_topo,
    )
    if use_topo:
        final_faces, final_owner, final_nbr, n_boundary = _order_and_concat(
            b_i_faces,
            b_i_own,
            b_i_nbr,
            b_b_faces,
            b_b_own,
        )
        final_boundary_labels = _ordered_boundary_labels(b_b_labels, b_b_own)
    else:
        final_faces, final_owner, final_nbr, n_boundary = _order_and_concat(
            a_i_faces,
            a_i_own,
            a_i_nbr,
            a_b_faces,
            a_b_own,
        )
        final_boundary_labels = _ordered_boundary_labels(a_b_labels, a_b_own)
    n_internal = len(final_faces) - n_boundary

    boundary_entries: list[dict[str, Any]] | None = None
    if classification_active:
        if len(final_boundary_labels) != n_boundary:
            return PolyDualResult(
                False,
                time.perf_counter() - t0,
                message=(
                    "classified dual boundary label count mismatch: "
                    f"{len(final_boundary_labels)} != {n_boundary}"
                ),
            )
        grouped_b_faces, grouped_b_owner, boundary_entries = _group_classified_boundary_faces(
            final_faces[n_internal:],
            final_owner[n_internal:],
            final_boundary_labels,
            n_internal,
        )
        final_faces = final_faces[:n_internal] + grouped_b_faces
        final_owner = final_owner[:n_internal] + grouped_b_owner

    # 5) polyMesh 쓰기
    poly_dir = case_dir / "constant" / "polyMesh"
    poly_dir.mkdir(parents=True, exist_ok=True)
    from core.generator.tier_layers_post import (  # noqa: PLC0415
        _ensure_minimal_controldict,
        _write_minimal_fv_dicts,
    )

    _ensure_minimal_controldict(case_dir)
    _write_minimal_fv_dicts(case_dir)
    from core.layers.native_bl import (  # noqa: PLC0415
        _write_boundary,
        _write_faces,
        _write_labels,
        _write_points,
    )

    _write_points(poly_dir / "points", dual_points)
    _write_faces(poly_dir / "faces", final_faces)
    _write_labels(
        poly_dir / "owner",
        np.array(final_owner, dtype=np.int64),
        "owner",
    )
    _write_labels(
        poly_dir / "neighbour",
        np.array(final_nbr, dtype=np.int64),
        "neighbour",
    )
    _write_boundary(
        poly_dir / "boundary",
        boundary_entries
        or [
            {
                "name": "defaultWall",
                "type": "wall",
                "nFaces": n_boundary,
                "startFace": n_internal,
            }
        ],
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
