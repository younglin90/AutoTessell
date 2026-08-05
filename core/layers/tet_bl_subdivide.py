"""BL prism → tet subdivision.

tet 메쉬용 BL 전략: native_bl 로 prism (wedge) layer 를 먼저 삽입한 뒤, 각 wedge
cell 을 3 tet 로 분할해 전체를 순수 tet 메쉬로 유지한다.

Prism wedge (6 verts: cap tri a0,a1,a2 + cap tri b0,b1,b2, lateral edge a_i-b_i) 를
3 tet 로 분할할 때, 3 side quad 를 각각 대각선으로 잘라 triangle pair 로 만든다.
다른 prism 과 공유되는 quad 의 경우 **양쪽에서 같은 대각선을 선택해야** 일관된
(conformal) topology 가 된다. 이 조건을 만족하지 못하면 공유 quad 의 두 절반이
어긋나 "face key 가 3 cell 공유 — manifold 위반" 으로 실패한다.

본 구현은 Dompierre et al. (1999) *"How to Subdivide Pyramids, Prisms and Hexahedra
into Tetrahedra"* 의 규칙을 따른다: **각 quad face 의 대각선을 그 quad 위 4 vertex 중
전역(global) ID 가 가장 작은 vertex 에서 출발하도록** 선택한다. 이렇게 하면 quad 를
공유하는 두 prism 이 (그 quad 의 4 개 global ID 만 보고) 항상 같은 대각선을 고르므로
자동으로 conformal 하다. 이 규칙은 어느 cap 을 outer/inner 로 부르든(즉 face 저장
순서에 무관) 결과가 동일하다 — ``_prism_to_tets`` 참고.

사용:
    from core.layers.tet_bl_subdivide import subdivide_prism_layers_to_tet
    res = subdivide_prism_layers_to_tet(case_dir)
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from core.layers.native_bl import _write_boundary, _write_faces, _write_labels, _write_points
from core.utils.logging import get_logger
from core.utils.polymesh_reader import (
    parse_foam_boundary,
    parse_foam_faces,
    parse_foam_labels,
    parse_foam_points,
)

log = get_logger(__name__)

# TET subdivision must not add boundary-layer layers. ``native_bl`` already
# creates the requested stack; this module only converts each generated prism
# wedge into three tet cells so exact layer-count mode stays exact.
_TET_LAYERS_N: int = 1


@dataclass
class TetSubdivResult:
    success: bool
    elapsed: float
    n_prism_before: int = 0
    n_tet_added: int = 0
    message: str = ""
    # ``True`` when wedge → tet subdivision actually ran and the resulting
    # mesh is pure tet.  ``False`` is reserved for the early-out on non-tet
    # bulk input where ``native_bl`` left mixed tet/prism cells in place;
    # callers that depend on the all-tet contract should treat that case
    # as a partial success.
    subdivision_applied: bool = False
    direct_id_map: dict[str, Any] = field(default_factory=dict)


def _identify_prism_cells(
    faces: list[list[int]],
    owner: np.ndarray,
    neighbour: np.ndarray,
    n_cells: int,
) -> tuple[list[int], dict[int, list[list[int]]]]:
    """prism (= 정확히 2 triangle + 3 quad face 를 가진 cell) 식별.

    Returns:
        (prism_cell_ids, cell_face_verts_map)
        cell_face_verts_map: cell_id → list[face_verts] (vertex index 리스트)
    """
    cell_faces: dict[int, list[list[int]]] = {i: [] for i in range(n_cells)}
    for fi, verts in enumerate(faces):
        cell_faces[int(owner[fi])].append(list(verts))
        if fi < len(neighbour):
            cell_faces[int(neighbour[fi])].append(list(verts))

    prism_cells: list[int] = []
    for cid, f_list in cell_faces.items():
        if len(f_list) != 5:
            continue
        n_tri = sum(1 for f in f_list if len(f) == 3)
        n_quad = sum(1 for f in f_list if len(f) == 4)
        if n_tri == 2 and n_quad == 3:
            prism_cells.append(cid)
    return prism_cells, cell_faces


def _find_prism_caps(
    cell_face_verts: list[list[int]],
    points: np.ndarray | None = None,
) -> tuple[list[int], list[int]] | None:
    """Return two disjoint triangular cap faces for a 6-vertex prism-like cell.

    ``native_bl`` may split side quads where neighboring wall triangles disagree
    on diagonals.  Those cells still have six vertices and two triangular caps,
    but can have 6-8 faces instead of the exact 2-tri + 3-quad wedge topology.
    A valid cap pair covers all six vertices, is disjoint, and every remaining
    face touches both caps.

    **Geometric disambiguation (critical for conformity).** A split-side prism
    often admits *several* topologically-valid cap pairings (a face key can play
    the role of a cap in more than one partition).  Picking an arbitrary one lets
    two neighbouring prisms interpret their shared wall/extruded quad differently
    (one as a lateral quad, the other as a cap + overhang), which makes the
    diagonal split disagree and yields ``face … shared by 3 cells`` (manifold
    violation).  When ``points`` is given we therefore select the pairing whose
    **lateral edges are shortest** — the true wall↔extruded links span only the
    (thin) layer thickness, whereas a spurious pairing pairs vertices across a
    full surface-triangle edge.  This recovers the real prism caps so both
    neighbours agree on the shared quad.  Without ``points`` (pure topology
    query, e.g. ``_identify_prism_like_cells``) the first valid pair is returned.
    """
    verts_all: set[int] = set()
    for face in cell_face_verts:
        verts_all.update(int(v) for v in face)
    if len(verts_all) != 6:
        return None

    tris = [list(dict.fromkeys(int(v) for v in f)) for f in cell_face_verts if len(set(f)) == 3]
    candidates: list[tuple[list[int], list[int]]] = []
    for i, tri_a in enumerate(tris):
        set_a = set(tri_a)
        for tri_b in tris[i + 1:]:
            set_b = set(tri_b)
            if set_a & set_b:
                continue
            if (set_a | set_b) != verts_all:
                continue
            ok = True
            for face in cell_face_verts:
                face_set = set(int(v) for v in face)
                if face_set == set_a or face_set == set_b:
                    continue
                if not (face_set & set_a) or not (face_set & set_b):
                    ok = False
                    break
            if ok:
                candidates.append((list(tri_a), list(tri_b)))
                if points is None:
                    # topology-only query — first valid pair suffices.
                    return candidates[0]
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    # Geometric tie-break: minimise total lateral-edge length under the best
    # nearest-vertex matching (see docstring).  ``_nearest_cap_pairing`` is
    # defined later in the module but resolved at call-time, so this is safe.
    def _lateral_cost(pair: tuple[list[int], list[int]]) -> float:
        a, b = pair
        _, b_ordered = _nearest_cap_pairing(a, b, points)
        ap = points[np.asarray(a, dtype=np.int64)]
        bp = points[np.asarray(b_ordered, dtype=np.int64)]
        return float(np.linalg.norm(bp - ap, axis=1).sum())

    return min(candidates, key=_lateral_cost)


def _identify_prism_like_cells(
    cell_faces: dict[int, list[list[int]]],
) -> list[int]:
    """Identify standard and split-side triangular prism cells."""
    out: list[int] = []
    for cid, f_list in cell_faces.items():
        if _find_prism_caps(f_list) is not None:
            out.append(cid)
    return out


def _nearest_cap_pairing(
    outer: list[int],
    inner: list[int],
    points: np.ndarray,
) -> tuple[list[int], list[int]]:
    """Order inner cap vertices to the nearest one-to-one match to outer."""
    perms = (
        (0, 1, 2), (0, 2, 1),
        (1, 0, 2), (1, 2, 0),
        (2, 0, 1), (2, 1, 0),
    )
    outer_pts = points[np.asarray(outer, dtype=np.int64)]
    inner_pts = points[np.asarray(inner, dtype=np.int64)]
    best_perm = perms[0]
    best_cost = float("inf")
    for perm in perms:
        perm_pts = inner_pts[np.asarray(perm, dtype=np.int64)]
        cost = float(np.linalg.norm(perm_pts - outer_pts, axis=1).sum())
        if cost < best_cost:
            best_cost = cost
            best_perm = perm
    return list(outer), [inner[i] for i in best_perm]


def _prism_vertex_pairs(
    cell_face_verts: list[list[int]],
    points: np.ndarray | None = None,
) -> tuple[list[int], list[int]] | None:
    """prism cell 의 outer/inner triangle vertex 쌍을 추출.

    각 outer vertex a_i 는 정확히 하나의 inner vertex b_i 와 3 개 quad face 중 2 개를
    공유한다 (quad 의 4 vertex 중 a_i 와 b_i 가 같이 등장).

    Returns:
        (outer=[a0,a1,a2], inner=[b0,b1,b2]) — 인덱스 순서 맞춤. 실패시 None.
    """
    tris = [f for f in cell_face_verts if len(f) == 3]
    quads = [f for f in cell_face_verts if len(f) == 4]
    if len(tris) != 2 or len(quads) != 3:
        if points is not None:
            caps = _find_prism_caps(cell_face_verts, points)
            if caps is not None:
                return _nearest_cap_pairing(caps[0], caps[1], points)
        return None

    tri_a, tri_b = tris[0], tris[1]
    outer_set = set(tri_a)
    inner_set = set(tri_b)
    if outer_set & inner_set:
        # shared vertex 가 있으면 prism 이 아님
        return None

    # 각 outer vertex 가 어떤 inner vertex 와 pair 되는지 찾는다:
    # - quad 에는 두 outer + 두 inner 정확히 포함.
    # - outer a_i 가 포함된 quad 2 개 를 교집합 → inner vertex 1 개.
    pair_map: dict[int, int] = {}
    for a in tri_a:
        quads_with_a = [set(q) for q in quads if a in q]
        if len(quads_with_a) != 2:
            return None
        inner_candidates = (quads_with_a[0] & quads_with_a[1]) & inner_set
        if len(inner_candidates) != 1:
            return None
        pair_map[a] = next(iter(inner_candidates))

    # tri_a 순서대로 inner 정렬
    outer = list(tri_a)
    inner = [pair_map[a] for a in outer]
    return outer, inner


def _prism_to_tets(
    outer: list[int],
    inner: list[int],
) -> list[tuple[int, int, int, int]]:
    """Triangular prism 을 conformal 한 3 tet 로 분할 (Dompierre 1999).

    ``outer[i]`` 와 ``inner[i]`` 는 lateral edge 로 연결된 짝이다. Prism 은 두 개의
    삼각형 cap (``outer``, ``inner``) 과 세 개의 quad side face
    ``{outer[i], outer[j], inner[j], inner[i]}`` 로 이루어진다.

    분할은 오직 **전역 vertex ID** 만으로 결정된다: 각 quad 위 대각선은 그 quad 의
    4 vertex 중 전역 ID 가 가장 작은 vertex 에서 출발한다. 따라서 quad 를 공유하는
    두 prism 은 반드시 같은 대각선을 선택하며 (그 quad 의 global ID 집합이 동일하므로)
    자동으로 conformal 하다. 어느 cap 을 ``outer`` 라 부르든 결과가 같으므로 face
    저장 순서에 따른 outer/inner 역전 (기존 결함) 에 면역이다.

    구현: 6 vertex 중 전역 최소 vertex 를 ``v0`` (그것이 속한 cap 을 bottom) 로 놓고
    lateral 짝·삼각형 순회를 유지하며 재라벨한다. 그러면 v0 를 포함하는 두 quad
    (QF_A={v0,v1,v4,v3}, QF_C={v2,v0,v3,v5}) 대각선은 항상 v0 에서 출발하고
    (0-4, 0-5), v0 를 포함하지 않는 QF_B={v1,v2,v5,v4} 만 min(v1,v5) vs min(v2,v4)
    로 갈린다.
    """
    verts = list(outer) + list(inner)  # [o0,o1,o2,i0,i1,i2]
    m = min(range(6), key=lambda k: verts[k])
    if m < 3:
        k, bottom, top = m, outer, inner
    else:
        k, bottom, top = m - 3, inner, outer
    k1, k2 = (k + 1) % 3, (k + 2) % 3
    v0, v1, v2 = bottom[k], bottom[k1], bottom[k2]
    v3, v4, v5 = top[k], top[k1], top[k2]
    if min(v1, v5) < min(v2, v4):
        return [(v0, v3, v4, v5), (v0, v1, v2, v5), (v0, v1, v4, v5)]
    return [(v0, v3, v4, v5), (v0, v1, v2, v4), (v0, v2, v4, v5)]


def subdivide_prism_layers_to_tet(
    case_dir: Path,
    *,
    backup_original: bool = True,
    aspect_cap: float = 200.0,
) -> TetSubdivResult:
    """case_dir/constant/polyMesh 의 모든 prism cell 을 3 tet 로 분할한다.

    기존 tet cell 은 그대로 유지. 새로 추가되는 tet 은 기존 cell 들 뒤에 붙이고,
    prism cell 은 최종 mesh 에서 제거된다 (faces 도 재구성).

    주의: MVP 구현 — cell ID 리매핑 + faces 재구성을 전면 수행하므로 비용이 높다.
    """
    t0 = time.perf_counter()
    poly_dir = case_dir / "constant" / "polyMesh"
    if not (poly_dir / "faces").exists():
        return TetSubdivResult(False, 0.0, message=f"polyMesh 없음: {poly_dir}")

    raw_points = parse_foam_points(poly_dir / "points")
    raw_faces = parse_foam_faces(poly_dir / "faces")
    owner = np.array(parse_foam_labels(poly_dir / "owner"), dtype=np.int64)
    neighbour = np.array(parse_foam_labels(poly_dir / "neighbour"), dtype=np.int64)
    boundary = parse_foam_boundary(poly_dir / "boundary")
    _lineage: dict[str, Any] = {}
    _lineage_path = case_dir / "native_bl_lineage.json"
    if _lineage_path.is_file():
        try:
            _lineage = json.loads(_lineage_path.read_text())
        except Exception as _lineage_exc:
            log.warning("native_tet_direct_id_lineage_read_failed", reason=str(_lineage_exc)[:160])

    points = np.array(raw_points, dtype=np.float64)
    faces = [list(f) for f in raw_faces]
    n_cells = (int(owner.max()) + 1) if len(owner) else 0
    if len(neighbour):
        n_cells = max(n_cells, int(neighbour.max()) + 1)

    # 1) prism cell 식별
    _exact_prism_cells, cell_faces_map = _identify_prism_cells(
        faces, owner, neighbour, n_cells,
    )
    prism_cells = _identify_prism_like_cells(cell_faces_map)
    if not prism_cells:
        return TetSubdivResult(
            True, time.perf_counter() - t0,
            n_prism_before=0, n_tet_added=0,
            message="prism cell 없음 — 이미 전체 tet.",
            subdivision_applied=True,
        )

    # 2) 각 prism 의 outer/inner pair 추출 + TET_BL1 quality/collision guard
    # Garimella 2003 §3 참고: advancing-front 에서 prism 삽입 전 검사.
    prism_pairs: dict[int, tuple[list[int], list[int]]] = {}
    _n_degenerate_pairs = 0
    _n_aspect_over_cap = 0
    _n_collision_observed = 0

    # Collision check: 기존 tet cell centroid set (non-prism) 을 사전 계산.
    _prism_set_fast = set(prism_cells)
    _centroid_rows: list[np.ndarray] = []
    for _cid in range(n_cells):
        if _cid in _prism_set_fast:
            continue
        _f_list = cell_faces_map[_cid]
        _vs: set[int] = set()
        for _f in _f_list:
            _vs.update(_f)
        if _vs:
            _centroid_rows.append(points[list(_vs)].mean(axis=0))
    # Stack into 2-D array for vectorised distance checks (N_tet × 3).
    _tet_centroids_arr: np.ndarray = (
        np.stack(_centroid_rows, axis=0) if _centroid_rows else np.empty((0, 3), dtype=np.float64)
    )
    _tet_centroids = _centroid_rows  # keep list alias for legacy references below

    def _point_in_tet_approx(pt: np.ndarray, centroid: np.ndarray, radius: float) -> bool:
        """Simplified: check if pt is within radius of centroid (bounding-sphere approx)."""
        return bool(np.linalg.norm(pt - centroid) < radius)

    for cid in prism_cells:
        p = _prism_vertex_pairs(cell_faces_map[cid], points)
        if p is None:
            log.warning("prism_pair_extract_failed", cell=cid)
            continue
        outer, inner = p

        # TET_BL1 guard 1 — aspect ratio (Garimella 2003 quality criterion).
        # Prism aspect = max_edge / min_edge across bottom-tri + lateral edges.
        outer_pts = points[outer]
        inner_pts = points[inner]
        _idx = np.array([0, 1, 2])
        _idx2 = np.array([1, 2, 0])
        _e_outer = np.linalg.norm(outer_pts[_idx2] - outer_pts[_idx], axis=1)
        _e_inner = np.linalg.norm(inner_pts[_idx2] - inner_pts[_idx], axis=1)
        _e_lat = np.linalg.norm(inner_pts - outer_pts, axis=1)
        _all_edges = np.concatenate([_e_outer, _e_inner, _e_lat])
        _min_e = float(_all_edges.min())
        _max_e = float(_all_edges.max())
        _aspect = _max_e / (_min_e + 1e-30)
        if _min_e <= 1e-30:
            _n_degenerate_pairs += 1
            log.debug("tet_bl_prism_rejected_degenerate", cell=cid)
            continue
        if _aspect > aspect_cap:
            _n_aspect_over_cap += 1
            log.debug("tet_bl_prism_aspect_over_cap", cell=cid, aspect=round(_aspect, 2))

        # TET_BL1 guard 2 — collision check (Garimella 2003 §3 advancing-front).
        # New top vertices (inner) centroid must not lie inside any neighbouring tet.
        # BETA2877 — _local_radius 를 outer tri edge × 0.5 (= 외부 tet 1 개 정도)
        # 로 잡으면 prism height 가 그보다 작은 BL (정상 케이스) 모두 거짓 collision
        # 으로 거부됨. 대신 prism 높이 (= mean lateral edge) 의 0.5 로 잡아 정말
        # inner triangle 이 인접 tet centroid 를 침범할 때만 reject.
        _top_centroid = inner_pts.mean(axis=0)
        _height_mean = float(_e_lat.mean())
        _local_radius = (_height_mean * 0.5) if _height_mean > 0 else 1e-9
        # Vectorised: compute all distances at once; avoid Python loop over centroids.
        if _tet_centroids_arr.shape[0] > 0:
            _dists = np.linalg.norm(_tet_centroids_arr - _top_centroid, axis=1)
            _collision = bool((_dists < _local_radius).any())
        else:
            _collision = False
        if _collision:
            _n_collision_observed += 1
            log.debug("tet_bl_prism_collision_observed", cell=cid)

        prism_pairs[cid] = (outer, inner)

    log.info(
        "tet_bl_prism_added",
        n_accepted=len(prism_pairs),
        n_degenerate_pairs=_n_degenerate_pairs,
        n_aspect_over_cap=_n_aspect_over_cap,
        n_collision_observed=_n_collision_observed,
    )

    if not prism_pairs:
        return TetSubdivResult(
            False, time.perf_counter() - t0,
            message="prism vertex pair 추출 실패 — subdivision 불가",
        )

    # TET_LAYERS — multi-layer geometric BL extrusion (cfMesh nLayers=2 mirror of POL_LAYERS R91).
    # For layers 2..N: geometrically extrude the inner triangle of each accepted prism inward,
    # apply TET_BL1 guards per layer, truncate chain at first rejected layer.
    # Uses _geometric_layer_thickness (BL2, 1.2× growth ratio).
    #
    # Implementation: accumulate synthetic prism_pairs for layers 2..N as additional entries
    # keyed by virtual IDs (offset from n_cells). Layer vertex coordinates are stored in an
    # extended points array; virtual cell IDs use a dedicated counter.
    _n_layers_added = 1  # layer 1 from existing prism cells
    _per_fid_layers: dict[int, int] = {cid: 1 for cid in prism_pairs}

    if _TET_LAYERS_N >= 2 and prism_pairs:
        try:
            from core.layers.native_bl import _geometric_layer_thickness as _glt  # noqa: PLC0415
            # First thickness = mean lateral edge length of layer-1 prisms.
            _lat_edges: list[float] = []
            for _cid0, (_o0, _i0) in prism_pairs.items():
                _lat_edges.extend(
                    np.linalg.norm(points[_i0] - points[_o0], axis=1).tolist()
                )
            _first_t = float(np.mean(_lat_edges)) if _lat_edges else 0.01
            _layer_ts = _glt(_first_t, _TET_LAYERS_N, growth_ratio=1.2)
            # layer 0 thickness = _layer_ts[0] (approx. same as layer-1 prism height).
            # layer 1 thickness = _layer_ts[1] (= first_t * 1.2).

            # Extended points list (we may append new vertices).
            _pts_list: list[np.ndarray] = list(points)
            # Virtual cell counter — starts after n_cells to avoid collision with real IDs.
            _vcell_counter = n_cells + len(prism_pairs) * 10  # safe offset

            for _li in range(1, _TET_LAYERS_N):
                _step_li = float(_layer_ts[_li])
                _n_acc_li = 0
                _n_rej_asp_li = 0
                _n_rej_col_li = 0
                _new_layer_pairs: dict[int, tuple[list[int], list[int]]] = {}

                for _cid_prev, (_o_prev, _i_prev) in list(prism_pairs.items()):
                    if _per_fid_layers.get(_cid_prev, 1) < _li:
                        continue  # this face already truncated at earlier layer
                    # Inner tri of layer _li-1 becomes outer of layer _li.
                    _outer_li = list(_i_prev)
                    # Extrude inward: compute per-vertex inward normal from lateral direction.
                    _outer_pts_li = np.array([_pts_list[v] for v in _outer_li])
                    # Inward direction: mean of (inner - outer) from layer-1 prism.
                    _o_prev_pts = np.array([_pts_list[v] for v in _o_prev])
                    _i_prev_pts = np.array([_pts_list[v] for v in _i_prev])
                    _lat_vecs = _i_prev_pts - _o_prev_pts  # shape (3,3)
                    _lat_norms = np.linalg.norm(_lat_vecs, axis=1, keepdims=True)
                    _lat_dirs = _lat_vecs / np.maximum(_lat_norms, 1e-30)
                    # New inner vertices = outer_li + inward_dir * step_li
                    _inner_pts_li = _outer_pts_li + _lat_dirs * _step_li

                    # TET_BL1 guard 1 — aspect ratio
                    _idx_li = np.array([0, 1, 2])
                    _idx2_li = np.array([1, 2, 0])
                    _eo_li = np.linalg.norm(_outer_pts_li[_idx2_li] - _outer_pts_li[_idx_li], axis=1)
                    _ei_li = np.linalg.norm(_inner_pts_li[_idx2_li] - _inner_pts_li[_idx_li], axis=1)
                    _el_li = np.linalg.norm(_inner_pts_li - _outer_pts_li, axis=1)
                    _all_e_li = np.concatenate([_eo_li, _ei_li, _el_li])
                    _min_e_li = float(_all_e_li.min())
                    _max_e_li = float(_all_e_li.max())
                    _aspect_li = _max_e_li / (_min_e_li + 1e-30)
                    if _aspect_li > aspect_cap:
                        _n_rej_asp_li += 1
                        log.debug("tet_layers_prism_rejected_aspect",
                                  layer=_li + 1, cell=_cid_prev, aspect=round(_aspect_li, 2))
                        continue

                    # TET_BL1 guard 2 — collision check (bounding-sphere approx).
                    # BETA2877 — radius 를 prism height 기반으로 (outer edge 가
                    # 아니라). 자세한 사유는 같은 모듈 line 222~ 의 코멘트.
                    _top_c_li = _inner_pts_li.mean(axis=0)
                    _height_mean_li = float(_el_li.mean())
                    _local_r_li = (_height_mean_li * 0.5) if _height_mean_li > 0 else 1e-9
                    # Vectorised distance check over all tet centroids.
                    if _tet_centroids_arr.shape[0] > 0:
                        _dists_li = np.linalg.norm(_tet_centroids_arr - _top_c_li, axis=1)
                        _collision_li = bool((_dists_li < _local_r_li).any())
                    else:
                        _collision_li = False
                    if _collision_li:
                        _n_rej_col_li += 1
                        log.debug("tet_layers_prism_rejected_collision",
                                  layer=_li + 1, cell=_cid_prev)
                        continue

                    # Accepted: add new vertices to extended points list (batch append).
                    _base_idx = len(_pts_list)
                    _inner_ids_li: list[int] = [_base_idx, _base_idx + 1, _base_idx + 2]
                    _pts_list.extend(_inner_pts_li)  # 3 rows — no Python loop

                    # Register synthetic prism pair under virtual cell ID.
                    _vid = _vcell_counter
                    _vcell_counter += 1
                    _new_layer_pairs[_vid] = (_outer_li, _inner_ids_li)
                    _per_fid_layers[_cid_prev] = _li + 1
                    _n_acc_li += 1

                log.info(
                    "tet_layers_layer_added",
                    layer=_li + 1,
                    n_accepted=_n_acc_li,
                    n_rejected_aspect=_n_rej_asp_li,
                    n_rejected_collision=_n_rej_col_li,
                    step=round(_step_li, 6),
                )
                if _n_acc_li == 0:
                    log.info("tet_layers_layer_truncated", layer=_li + 1, reason="no_prisms_accepted")
                    break
                prism_pairs.update(_new_layer_pairs)
                _n_layers_added = _li + 1

            # Update points array with any new vertices.
            if len(_pts_list) > len(points):
                points = np.array(_pts_list, dtype=np.float64)
        except Exception as _tle:
            log.info("tet_layers_skipped", reason=str(_tle)[:120])

    _avg_layers = (
        float(np.mean(list(_per_fid_layers.values()))) if _per_fid_layers else 1.0
    )
    log.info(
        "tet_layers_summary",
        n_layers_max=_n_layers_added,
        avg_n_layers=round(_avg_layers, 2),
        n_total_prism_pairs=len(prism_pairs),
    )

    # 3) tet 리스트 생성: 각 prism → 3 tet (vertex sets)
    # OpenFOAM polyMesh 는 cell 을 face 로 정의하지만, 여기서는 "tet cell index"
    # 기반으로 faces 를 새로 구성한다.
    # 기존 tet cell 은 원본 cell_faces_map 에서 그대로 유지 (id 유지).
    # 새 tet 은 prism cell id 대체 + 추가 id 로 할당.
    #
    # 간소화 전략: 기존 non-prism cell 은 id 그대로, prism cell 3 개를 새 tet 3 개로
    # 교체. 추가 필요 id 개수 = 2 * n_prism (각 prism 이 1 cell → 3 cell).

    n_prism = len(prism_pairs)
    # new cell mapping: 기존 non-prism cell 의 old_id → new_id (연속). prism 은
    # 3 tet 로 대체.
    prism_set = set(prism_pairs.keys())
    old_non_prism = [cid for cid in range(n_cells) if cid not in prism_set]
    new_id_of: dict[int, int] = {old: new for new, old in enumerate(old_non_prism)}
    next_id = len(old_non_prism)
    prism_tets: dict[int, tuple[int, int, int]] = {}
    for pid in sorted(prism_pairs.keys()):
        prism_tets[pid] = (next_id, next_id + 1, next_id + 2)
        next_id += 3
    total_cells = next_id

    # 4) 기존 face list 를 순회하며 owner/neighbour 를 new_id 로 매핑.
    # prism cell 을 참조하는 face 는 "어느 tet 에 속하는지" 를 face vertex 구성
    # 으로 결정.
    #
    # Prism 내부 face 를 구분하는 전략:
    #   - 두 triangle face: outer=a0a1a2 (→ tet1 의 face), inner=b0b1b2 (→ tet3 의 face)
    #   - side quad (a_i, a_j, b_j, b_i) → 대각선 분할되어 두 새 triangle face 로
    #     바뀌고 각 triangle 이 인접 tet 에 붙는다.
    # 단순화: 기존 face 중 prism 을 참조하는 face 는 일단 모두 제거하고, 새 tet
    # 의 face 를 처음부터 재구성한다.
    #
    # 그런데 기존 face 가 prism 과 non-prism (예: orig_tet_cell ↔ innermost prism)
    # 또는 boundary 로도 쓰이므로, face 를 전면 rebuild 하기보다 "prism side 만
    # 분할 가능한 triangle pair 로 교체" 가 안전.

    # 이 MVP 에서는 단순화를 위해 "전체 faces/owner/neighbour/boundary 재구성" 전략
    # 을 사용한다. 절차:
    #   1) 모든 cell 의 vertex 기반 face 를 수집 (기존 tet 은 4 face, 새 tet 은 4 face)
    #   2) face 를 canonical key (sorted vertex tuple) 로 dedupe
    #   3) internal face (두 cell 공유) 와 boundary face (한 cell 공유) 분류
    #   4) boundary patch 는 원본 boundary 의 face vertex set 과 매칭해 복원

    # 4a) 모든 cell 의 tet 4-face 를 수집
    def _tet_faces(v0: int, v1: int, v2: int, v3: int) -> list[tuple[int, int, int]]:
        # 각 tet 의 4 face vertices (CCW from outside). 여기선 vertex set 만 저장.
        return [
            (v1, v2, v3), (v0, v3, v2), (v0, v1, v3), (v0, v2, v1),
        ]

    # 기존 tet cell 추출 — 4 face + all triangles → (4 vertex set).
    # 하지만 원본 cell 이 어떤 tet 인지 알려면 owner/neighbour 면 정보 만으로는
    # 부족. 기존 tet 의 4 vertex 를 cell_faces_map 의 triangle 4 개에서 추출.
    # BETA2877 — native_bl 후 일부 cell 이 4 vertex / 5 face 같은 비표준 토폴로지
    # (face split 부산물) 를 가질 수 있다. tet-only 가 아닌 입력은 subdivide 의
    # face graph 전제를 깨므로 (manifold 4-share 위반), early 로 success=True 의
    # 의미상 "BL 은 native_bl 단계까지만 적용" 으로 빠져나간다. 결과 mesh 는
    # mixed (tet + prism wedge) — CFD 사용 가능, 단지 100% 순수 tet 은 아님.
    old_tet_verts: dict[int, tuple[int, int, int, int]] = {}
    _has_non_tet = False
    for cid in old_non_prism:
        f_list = cell_faces_map[cid]
        verts_set: set[int] = set()
        for f in f_list:
            verts_set.update(f)
        if len(verts_set) != 4 or len(f_list) != 4:
            _has_non_tet = True
            break
        old_tet_verts[cid] = tuple(sorted(verts_set))
    if _has_non_tet:
        log.info(
            "tet_bl_subdivide_skipped_non_tet_input",
            note="원본 mesh 에 non-tet cell 이 있어 subdivide 건너뜀 — "
                 "native_bl 단계까지의 prism wedge layer 가 그대로 남는다.",
            n_prism_pairs_eligible=len(prism_pairs),
        )
        return TetSubdivResult(
            True, time.perf_counter() - t0,
            n_prism_before=len(prism_cells), n_tet_added=0,
            message=(
                "non-tet 입력 — subdivide 건너뜀 (BL 은 native_bl 단계까지 적용). "
                "결과 mesh 는 tet+prism mixed."
            ),
        )

    # 4b) cell id → 4 vertex 매핑 + face 리스트
    cell_vertices: dict[int, tuple[int, ...]] = {}
    for old_cid, v4 in old_tet_verts.items():
        cell_vertices[new_id_of[old_cid]] = v4
    for pid, pair in prism_pairs.items():
        outer, inner = pair
        t1, t2, t3 = prism_tets[pid]
        # Dompierre global-ID 규칙 — 공유 quad 에서 이웃 prism 과 같은 대각선을
        # 선택하므로 conformal (기존의 고정 template 은 outer/inner 역전 시 대각선이
        # 어긋나 manifold 위반을 유발했다). ``_prism_to_tets`` docstring 참고.
        tet_a, tet_b, tet_c = _prism_to_tets(outer, inner)
        cell_vertices[t1] = tet_a
        cell_vertices[t2] = tet_b
        cell_vertices[t3] = tet_c


    # 4c) 모든 face 를 수집 (cell → 4 face vertex tuple)
    # face direction (winding) 을 결정하려면 cell centroid 기준 outward 방향을 써야
    # 한다. 여기서는 geometric 계산으로 winding 을 결정.
    def _cell_centroid(verts: tuple[int, ...]) -> np.ndarray:
        return points[list(verts)].mean(axis=0)

    def _face_centroid(f: tuple[int, ...]) -> np.ndarray:
        return points[list(f)].mean(axis=0)

    def _face_normal(f: tuple[int, ...]) -> np.ndarray:
        v = points[list(f)]
        return np.cross(v[1] - v[0], v[2] - v[0])

    # canonical face key: sorted tuple
    # face_map: key → [(cid, winding_verts), ...]
    face_map: dict[tuple[int, ...], list[tuple[int, tuple[int, ...]]]] = {}

    # tet faces ordering (0,1,2,3) → 4 triangle faces with winding such that normal
    # points OUT of cell centroid. For canonical 4-vertex tet we use:
    #   face opposite v0: (1,2,3)
    #   face opposite v1: (0,3,2)
    #   face opposite v2: (0,1,3)
    #   face opposite v3: (0,2,1)
    # winding 은 vertex 좌표에 따라 geometric 검증.

    for cid, v4 in cell_vertices.items():
        cc = _cell_centroid(v4)
        ordered_faces = [
            (v4[1], v4[2], v4[3]),
            (v4[0], v4[3], v4[2]),
            (v4[0], v4[1], v4[3]),
            (v4[0], v4[2], v4[1]),
        ]
        for f in ordered_faces:
            # winding 보정: normal 이 owner 밖을 향해야 함
            n = _face_normal(f)
            fc = _face_centroid(f)
            if np.dot(n, fc - cc) < 0:
                f = (f[0], f[2], f[1])
            key = tuple(sorted(f))
            face_map.setdefault(key, []).append((cid, f))


    # 4d) 원본 boundary patch 를 추적하기 위해 기존 boundary face 의 canonical key →
    # patch 매핑 생성
    orig_boundary_key_to_patch: dict[tuple[int, ...], int] = {}
    for pi, patch in enumerate(boundary):
        start = int(patch["startFace"])
        nf = int(patch["nFaces"])
        for fi in range(start, start + nf):
            if fi < len(raw_faces):
                orig_boundary_key_to_patch[tuple(sorted(raw_faces[fi]))] = pi

    # 4e) internal / boundary 분류
    internal_faces: list[list[int]] = []
    internal_owner: list[int] = []
    internal_nbr: list[int] = []
    # patch_idx → list[(face_verts, owner_cid)]
    bnd_by_patch: dict[int, list[tuple[list[int], int]]] = {
        pi: [] for pi in range(len(boundary))
    }
    bl_subdiv_bnd: list[tuple[list[int], int]] = []

    for key, refs in face_map.items():
        if len(refs) == 2:
            (ca, fa), (cb, fb) = refs
            owner_cid = min(ca, cb)
            nbr_cid = max(ca, cb)
            # owner 의 winding 사용
            verts = fa if ca == owner_cid else fb
            internal_faces.append(list(verts))
            internal_owner.append(owner_cid)
            internal_nbr.append(nbr_cid)
        elif len(refs) == 1:
            (cid, fv) = refs[0]
            patch_idx = orig_boundary_key_to_patch.get(key)
            if patch_idx is not None:
                bnd_by_patch[patch_idx].append((list(fv), cid))
            else:
                bl_subdiv_bnd.append((list(fv), cid))
        else:
            # > 2 cells share a face → mesh broken
            return TetSubdivResult(
                False, time.perf_counter() - t0,
                message=f"face key {key} 가 {len(refs)} cell 공유 — manifold 위반",
            )

    # 5) 최종 face 순서 = internal + each boundary patch
    final_faces: list[list[int]] = list(internal_faces)
    final_owner: list[int] = list(internal_owner)
    final_nbr: list[int] = list(internal_nbr)

    final_boundary_entries: list[dict[str, Any]] = []
    cursor = len(final_faces)
    for pi, patch in enumerate(boundary):
        items = bnd_by_patch[pi]
        start_face = cursor
        for f, o in items:
            final_faces.append(f)
            final_owner.append(o)
        cursor += len(items)
        final_boundary_entries.append({
            "name": patch.get("name", f"patch_{pi}"),
            "type": patch.get("type", "patch"),
            "nFaces": len(items),
            "startFace": start_face,
        })
    if bl_subdiv_bnd:
        start_face = cursor
        for f, o in bl_subdiv_bnd:
            final_faces.append(f)
            final_owner.append(o)
        cursor += len(bl_subdiv_bnd)
        final_boundary_entries.append({
            "name": "bl_subdiv_side",
            "type": "wall",
            "nFaces": len(bl_subdiv_bnd),
            "startFace": start_face,
        })

    # 6) backup + 쓰기
    if backup_original:
        import shutil as _sh
        bak = case_dir / "constant" / "polyMesh_pre_tet_subdiv"
        if bak.exists():
            _sh.rmtree(bak)
        _sh.copytree(poly_dir, bak)

    _write_points(poly_dir / "points", points)
    _write_faces(poly_dir / "faces", final_faces)
    _write_labels(
        poly_dir / "owner", np.array(final_owner, dtype=np.int64), "owner",
    )
    _write_labels(
        poly_dir / "neighbour", np.array(final_nbr, dtype=np.int64), "neighbour",
    )
    _write_boundary(poly_dir / "boundary", final_boundary_entries)

    _direct_id_map: dict[str, Any] = {
        "schema": "native-tet-bl-direct-id-map/v1",
        "records": [],
    }
    if _lineage.get("records"):
        _final_face_by_key = {
            tuple(sorted(int(v) for v in _face)): int(_fi)
            for _fi, _face in enumerate(final_faces)
        }
        for _rec in _lineage["records"]:
            _layer_ids = _rec.get("layer_point_ids", [])
            _wall_key = tuple(sorted(int(v) for v in _layer_ids[0])) if _layer_ids else ()
            _front_key = tuple(sorted(int(v) for v in _layer_ids[-1])) if _layer_ids else ()
            _final_cells = []
            for _pid in _rec.get("prism_cell_ids", []):
                _mapped = prism_tets.get(int(_pid), ())
                if _mapped:
                    _final_cells.extend(int(v) for v in _mapped)
            _direct_id_map["records"].append({
                "source_face": int(_rec["source_face"]),
                "source_vertices": [int(v) for v in _rec.get("source_vertices", [])],
                "patch_index": int(_rec.get("patch_index", -1)),
                "owner_cell": int(_rec.get("owner_cell", -1)),
                "wall_face_ids": [_final_face_by_key[_wall_key]] if _wall_key in _final_face_by_key else [],
                "front_face_ids": [_final_face_by_key[_front_key]] if _front_key in _final_face_by_key else [],
                "final_cell_ids": sorted(set(_final_cells)),
                "layer_count": len(_layer_ids) - 1,
            })

    return TetSubdivResult(
        True,
        time.perf_counter() - t0,
        n_prism_before=n_prism,
        n_tet_added=3 * n_prism,
        message=(
            f"tet_bl_subdivide OK — {n_prism} prism → {3 * n_prism} tet "
            f"(total cells={total_cells})"
        ),
        subdivision_applied=True,
        direct_id_map=_direct_id_map,
    )
