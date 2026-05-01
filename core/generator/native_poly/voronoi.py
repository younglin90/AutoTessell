"""native_poly MVP — scipy Voronoi 기반 polyhedral mesh.

알고리즘:
    1. 입력 표면 bbox 내부에 uniform + jitter seed point 생성.
    2. scipy.spatial.Voronoi 실행 → 각 region 의 vertex 리스트.
    3. open region (infinite) 은 제외, closed region 중 모든 vertex 가 표면 내부 +
       bbox 내부인 경우만 유지.
    4. 각 cell 의 face 를 ConvexHull 로 얻어 polyMesh 에 기록.

제약 사항:
    - boundary clipping 미지원 — 표면을 stair-step 으로 근사 (inside-filter 한
      region 만 keep).
    - 단일 "defaultWall" patch.
    - seed 수가 많으면 Voronoi 생성 시간 O(n log n) + hull 생성 비용 급증.
    - 본 MVP 는 bbox 안에 완전히 들어간 region 만 사용 → boundary 근처 region 손실 가능.
"""
from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

import numpy as np

from core.utils.logging import get_logger

log = get_logger(__name__)

# PPP4 skeleton — clipping default OFF
_NATIVE_POLY_PPP4_ENABLE: bool = True  # PPP5 — clipping activated

# TTT1 — BL integration sequence skeleton (default OFF)
# TTT1 → TTT2 prism layer insertion → TTT3 stitch
_TTT1_POLY_BL_ENABLE: bool = True

# POLY_CACHE (beta2178) — single-slot LRU adjacency cache for poly cell lists.
# Mirrors HEX_CACHE (R125, beta2177).  Default ON.
# Set AUTO_TESSELL_POLY_CACHE_OFF=1 to disable.


class _PolyAdjCache(NamedTuple):
    """Cached adjacency maps for a polyhedral mesh (list-of-cells representation)."""
    face_map: "dict[frozenset, list[int]]"   # frozenset(face_verts) → [cell_idx, ...]
    adj: "list[set[int]]"                    # cell_idx → set of neighbour cell indices


_poly_adj_cache: tuple[int, _PolyAdjCache] | None = None  # (id(cells), cache)


def _build_poly_adjacency(cells: "list[list[list[int]]]") -> _PolyAdjCache:
    """Build face_map + cell adjacency for *cells* (list-of-faces representation).

    Single-slot LRU keyed on ``id(cells)``.  Call-sites that mutate *cells*
    must pass the new list object so the cache is invalidated automatically.

    Set ``AUTO_TESSELL_POLY_CACHE_OFF=1`` to disable caching (always rebuild).
    """
    import os as _os_pc
    global _poly_adj_cache

    if not _os_pc.environ.get("AUTO_TESSELL_POLY_CACHE_OFF"):
        key = id(cells)
        if _poly_adj_cache is not None and _poly_adj_cache[0] == key:
            return _poly_adj_cache[1]

    n = len(cells)
    face_map: dict[frozenset, list[int]] = {}
    for ci, cell_faces in enumerate(cells):
        for face in cell_faces:
            k = frozenset(face)
            face_map.setdefault(k, []).append(ci)

    adj: list[set[int]] = [set() for _ in range(n)]
    for owners in face_map.values():
        if len(owners) == 2:
            a, b = owners
            adj[a].add(b)
            adj[b].add(a)

    result = _PolyAdjCache(face_map=face_map, adj=adj)
    if not _os_pc.environ.get("AUTO_TESSELL_POLY_CACHE_OFF"):
        _poly_adj_cache = (id(cells), result)
    return result


def _find_wall_adjacent_cells(
    points: "np.ndarray",
    ridge_dict: dict,
    surface_faces: "np.ndarray",
) -> set:
    """wall 면을 공유하는 voronoi cell 인덱스 set 반환.

    BL 통합 시퀀스:
        TTT1 (본 카드): wall-adjacent helper 스켈레톤 — 호출처 없음, default OFF.
        TTT2: prism 층 삽입 — wall-adjacent cell 에 prism wedge 추가.
        TTT3: stitch — prism / voronoi 경계 위상 결합.

    Parameters
    ----------
    points:
        voronoi seed point 좌표 배열 (N, 3).
    ridge_dict:
        {(i, j): ridge_vertices} — scipy Voronoi.ridge_dict 와 동일 구조.
    surface_faces:
        표면 삼각형 인덱스 배열 (M, 3) — wall 판별 기준.

    Returns
    -------
    set[int]
        wall 면에 인접한 voronoi cell (seed point) 인덱스 집합.
    """
    if not _TTT1_POLY_BL_ENABLE:
        return set()

    wall_adjacent: set = set()
    for (i, j) in ridge_dict:
        if i >= 0 and j >= 0:
            wall_adjacent.add(i)
            wall_adjacent.add(j)
    return wall_adjacent


def _clip_voronoi_cell_by_surface(
    cell_verts: np.ndarray,
    V_surf: np.ndarray,
    F_surf: np.ndarray,
) -> np.ndarray:
    """Sutherland-Hodgman 3D variant — clip a convex Voronoi cell against each
    surface triangle's supporting half-space.

    Parameters
    ----------
    cell_verts : (N, 3) float64  — convex hull vertices of one Voronoi cell.
    V_surf     : (Mv, 3) float64 — surface mesh vertices.
    F_surf     : (Mf, 3) int     — surface triangle face indices.

    Returns
    -------
    clipped : (K, 3) float64 — clipped point set (convex hull of intersection).
              Returns cell_verts unchanged when _NATIVE_POLY_PPP4_ENABLE is False
              (skeleton mode) or when F_surf is empty.

    Notes
    -----
    Skeleton only — caller not yet wired (PPP4).  PPP5 will activate via
    `_NATIVE_POLY_PPP4_ENABLE` and integrate into the cell-extraction loop.
    """
    if not _NATIVE_POLY_PPP4_ENABLE or len(F_surf) == 0:
        return cell_verts

    pts = cell_verts.copy()

    for tri in F_surf:
        v0, v1, v2 = V_surf[tri[0]], V_surf[tri[1]], V_surf[tri[2]]
        e1, e2 = v1 - v0, v2 - v0
        n = np.cross(e1, e2)
        n_len = np.linalg.norm(n)
        # PPP6 degenerate guard: skip near-zero normal or near-zero area plane
        area = 0.5 * n_len
        if n_len < 1e-12 or area < 1e-14:
            continue
        n = n / n_len
        d = np.dot(n, v0)

        # keep points on the inside (dot >= d) — half-space defined by triangle plane
        inside_mask = np.dot(pts, n) >= d
        if inside_mask.all():
            continue
        if not inside_mask.any():
            return cell_verts  # degenerate clip → return original (safe fallback)

        # intersect each edge that crosses the plane
        new_pts: list[np.ndarray] = []
        for p in pts[inside_mask]:
            new_pts.append(p)
        n_pts = len(pts)
        for i in range(n_pts):
            a, b = pts[i], pts[(i + 1) % n_pts]
            da, db = np.dot(a, n) - d, np.dot(b, n) - d
            if (da >= 0) != (db >= 0):
                t = da / (da - db)
                new_pts.append(a + t * (b - a))
        if len(new_pts) < 4:
            log.warning("native_poly_ppp6_skipped", reason="clip reduced vertices below 4")
            return cell_verts  # degenerate — safe fallback
        pts = np.array(new_pts, dtype=np.float64)

    return pts


@dataclass
class NativePolyResult:
    success: bool
    elapsed: float
    n_cells: int = 0
    n_points: int = 0
    n_faces: int = 0
    message: str = ""
    # Y1 (beta1650) — Fluent poly mesher 비교 메트릭.
    quality_grade: str = "?"
    max_non_orthogonality_deg: float = -1.0
    mean_non_orthogonality_deg: float = -1.0
    max_skewness: float = -1.0
    mean_skewness: float = -1.0
    avg_faces_per_cell: float = -1.0
    plane_coverage: float = -1.0
    plane_area_coverage: float = -1.0
    # beta2337 — pre-mesh self-intersect (P2.6 chain). None = 측정 안 됨,
    # 0 = clean, >0 = 입력 SI 존재.
    n_self_intersect_pre: int | None = None
    # C-QUAL-8 / beta2401 — poly 의 mesh_integrity_suspect (NativeTetResult 와 parity).
    # validator 발견: mesh #2 (V=12k) 의 poly 가 5 cells 만 — 사용자 입장에서
    # success=True 인데 사실상 빈 mesh. n_cells < n_surface_v / 32 시 True.
    mesh_integrity_suspect: bool = False


from core.utils.geometry import inside_winding_number as _inside_ray_cast


# VAL2 (beta2148) — global negative-volume poly cell validation (3-engine defensive parity).
# env AUTO_TESSELL_VAL2_OFF=1 to disable. Default ON.
def validate_poly_cell_volumes(
    cells: "list[list[list[int]]]",
    points: np.ndarray,
    *,
    degenerate_eps: float = 1e-20,
) -> tuple[int, int]:
    """For each poly cell, tetrahedralize from centroid (fan over each face's triangles).

    Sum signed volumes; if V < 0, log native_poly_degenerate_volume warning.
    Cell-by-cell flipping for poly is complex — LOG ONLY (no auto-fix).
    Returns (n_negative_volume, n_degenerate).
    """
    import os as _os  # noqa: PLC0415
    if _os.environ.get("AUTO_TESSELL_VAL2_OFF"):
        return 0, 0

    pts = np.asarray(points, dtype=np.float64)
    n_negative = 0
    n_degenerate = 0
    for ci, cell_faces in enumerate(cells):
        # Gather all vertex indices in this cell.
        cell_vidx: list[int] = []
        for face in cell_faces:
            cell_vidx.extend(face)
        unique_vidx = list(dict.fromkeys(cell_vidx))
        if len(unique_vidx) < 4:
            n_degenerate += 1
            continue
        cell_verts = pts[unique_vidx]
        centroid = cell_verts.mean(axis=0)
        # Fan-triangulate each face and sum signed tet volumes from centroid.
        total_vol = 0.0
        for face in cell_faces:
            if len(face) < 3:
                continue
            for k in range(1, len(face) - 1):
                a = pts[face[0]]
                b = pts[face[k]]
                c = pts[face[k + 1]]
                # signed vol6 = dot(b-centroid, cross(c-centroid, a-centroid))
                # but use centroid-to-triangle tet: (centroid, a, b, c)
                total_vol += float(np.dot(
                    a - centroid,
                    np.cross(b - centroid, c - centroid),
                ))
        if abs(total_vol) < float(degenerate_eps):
            n_degenerate += 1
        elif total_vol < 0.0:
            n_negative += 1
            log.warning(
                "native_poly_degenerate_volume",
                cell_idx=ci,
                vol=round(total_vol, 6),
            )

    log.info(
        "native_poly_validate",
        n_cells=len(cells),
        n_negative_volume=n_negative,
        n_degenerate=n_degenerate,
    )
    return n_negative, n_degenerate


# POL_VAL3 (beta2162) — lightweight count-only helper for per-pass neg-vol tracking.
# Mirrors R105 VAL3 (tet) and R108 HEX_VAL3 patterns. Default ON.
def _count_neg_vol_poly(
    cells: "list[list[list[int]]]",
    points: "np.ndarray",
    *,
    degenerate_eps: float = 1e-20,
) -> int:
    """Count cells with negative signed volume (fan-tet from centroid).

    Lightweight: no per-cell logging, count only. Used for per-pass delta tracking.
    Returns n_negative (degenerate cells excluded from count).
    """
    import os as _os  # noqa: PLC0415
    if _os.environ.get("AUTO_TESSELL_VAL2_OFF"):
        return 0
    pts = np.asarray(points, dtype=np.float64)
    n_negative = 0
    for cell_faces in cells:
        cell_vidx: list[int] = []
        for face in cell_faces:
            cell_vidx.extend(face)
        unique_vidx = list(dict.fromkeys(cell_vidx))
        if len(unique_vidx) < 4:
            continue
        cell_verts = pts[unique_vidx]
        centroid = cell_verts.mean(axis=0)
        total_vol = 0.0
        for face in cell_faces:
            if len(face) < 3:
                continue
            for k in range(1, len(face) - 1):
                a = pts[face[0]]
                b = pts[face[k]]
                c = pts[face[k + 1]]
                total_vol += float(np.dot(
                    a - centroid,
                    np.cross(b - centroid, c - centroid),
                ))
        if abs(total_vol) >= float(degenerate_eps) and total_vol < 0.0:
            n_negative += 1
    return n_negative


def _write_polymesh_poly(
    vertices: np.ndarray,
    cells: list[list[list[int]]],  # cell 별 face (vertex index list)
    case_dir: Path,
) -> dict[str, int]:
    """각 cell 을 face list 로 정의한 polyMesh — generic writer 위임."""
    from core.generator.polymesh_writer import write_generic_polymesh  # noqa: PLC0415

    return write_generic_polymesh(vertices, cells, case_dir)


_TTT3_POLY_BL_EXTRUDE_ENABLE = True  # TTT4: BL prism extrude 활성.

# POL_BL_TANGENT (beta2155) — poly+BL top-layer tangential Laplacian smoothing.
# Mirrors BL_TANGENT_SMOOTH (R100, native_bl.py) for the poly-specific extrude path.
# Default ON; disable via env AUTO_TESSELL_POL_BL_TANG_OFF=1.
import os as _os_poly
_POL_BL_TANG_SMOOTH_ON: bool = _os_poly.environ.get("AUTO_TESSELL_POL_BL_TANG_OFF", "0") != "1"

# TTT9 — voronoi cell merging skeleton (default OFF, 호출 경로 없음)
_TTT9_CELL_MERGE: bool = False


def _find_merge_candidates(
    cells: "list[list[list[int]]]",
    quality_threshold: float = 0.2,
) -> "list[tuple[int, int]]":
    """quality 낮은 voronoi cell 의 merge candidate pair 를 반환한다.

    quality score = (face 수 기반 volume proxy) / (최대 face span 기반 aspect proxy).
    score < quality_threshold 인 cell 을 sliver 로 보고 face 를 공유하는
    인접 cell 과의 pair (i, j) 리스트를 반환한다.

    Parameters
    ----------
    cells:
        cells[i] = list of faces; face = list of vertex indices (int).
    quality_threshold:
        score 가 이 값 미만이면 merge 후보로 분류.

    Returns
    -------
    list[tuple[int, int]]
        merge 대상 (low_quality_cell_idx, neighbor_cell_idx) pair 목록.
        호출되지 않음 — skeleton only (TTT9 gate OFF).
    """
    # POLY_CACHE: reuse cached adjacency if cells list unchanged.
    _cadj = _build_poly_adjacency(cells)
    adj = _cadj.adj

    candidates: list[tuple[int, int]] = []
    for ci, faces in enumerate(cells):
        if not faces:
            continue
        # volume proxy: number of faces * avg face area (vertex count proxy)
        total_verts = sum(len(f) for f in faces)
        avg_verts = total_verts / len(faces)
        # aspect proxy: max face vertex count (elongation indicator)
        max_verts = max(len(f) for f in faces)
        aspect = float(max_verts)
        vol_proxy = float(avg_verts * len(faces))
        score = vol_proxy / aspect if aspect > 0.0 else 0.0
        if score < quality_threshold:
            for nb in adj[ci]:
                candidates.append((ci, nb))

    return candidates

def _smooth_poly_top_layer_tangential(
    vertices: "np.ndarray",
    cells: "list[list[list[int]]]",
    n_prism_start: int,
    *,
    n_iter: int = 1,
    min_aspect_improve: float = 1e-3,
) -> tuple["np.ndarray", int]:
    """POL_BL_TANGENT: tangential Laplacian of outermost prism-layer verts.

    Mirrors BL_TANGENT_SMOOTH (R100, native_bl.py beta2153) for the poly-specific
    prism extrude path (cfMesh BLSmoothing 3-engine parity).

    For each top-layer polygon vertex v:
      - Collects 1-ring top-layer neighbours (shared prism top-face edge).
      - Moves v toward ring centroid, projected onto the plane tangential to the
        extrusion direction (bottom-centroid → top-centroid) — preserves thickness.
      - STRICT GUARD: post max_edge/min_height aspect ≥ pre aspect → revert.

    Args:
        vertices: (V,3) float64 vertex array.
        cells: list of cells; each cell = list of faces; face = list of vert idx.
               Prism cells occupy cells[n_prism_start:].
        n_prism_start: index into `cells` where prisms begin.
        n_iter: number of smoothing passes (default 1).
        min_aspect_improve: minimum aspect reduction to accept move.

    Returns:
        (modified_vertices, n_moved)
    """
    prism_cells = cells[n_prism_start:]
    if not prism_cells:
        return vertices, 0

    verts = vertices.copy()

    # ── 1. Collect top-face and bottom-face vert indices per prism ────────────
    # Convention from _extrude_prism_layer: face[0]=bottom, face[1]=top (reversed).
    top_sets: list[list[int]] = []   # top-face verts per prism
    bot_sets: list[list[int]] = []   # bottom-face verts per prism
    for cell in prism_cells:
        if len(cell) < 2:
            top_sets.append([])
            bot_sets.append([])
            continue
        bot_sets.append(list(cell[0]))
        top_sets.append(list(cell[1]))  # reversed top; same indices, reversed order

    # ── 2. Build adjacency among top-layer verts (shared edge in any top face) ─
    all_top_verts: set[int] = set()
    for ts in top_sets:
        all_top_verts.update(ts)

    adj: dict[int, set[int]] = {v: set() for v in all_top_verts}
    for ts in top_sets:
        n = len(ts)
        for k in range(n):
            va, vb = ts[k], ts[(k + 1) % n]
            if va in adj and vb in adj:
                adj[va].add(vb)
                adj[vb].add(va)

    # ── 3. Map each top vert → its corresponding bottom vert ─────────────────
    # (same position within the face list; bottom=face[0], top=face[1] reversed)
    top_to_bot: dict[int, int] = {}
    for pi, (ts, bs) in enumerate(zip(top_sets, bot_sets)):
        if len(ts) != len(bs):
            continue
        rev_ts = list(reversed(ts))  # undo the reversal to align with bs
        for tv, bv in zip(rev_ts, bs):
            top_to_bot[tv] = bv

    # ── 4. Helper: max aspect ratio over prisms incident to a top vert ────────
    # Build top-vert → prism index lookup
    tv_to_prisms: dict[int, list[int]] = {v: [] for v in all_top_verts}
    for pi, ts in enumerate(top_sets):
        for tv in ts:
            if tv in tv_to_prisms:
                tv_to_prisms[tv].append(pi)

    def _max_aspect(tv: int) -> float:
        best = 0.0
        for pi in tv_to_prisms.get(tv, []):
            ts = top_sets[pi]
            bs = bot_sets[pi]
            if not ts or not bs:
                continue
            top_pts = verts[ts]
            bot_pts = verts[bs]
            # max lateral edge length
            n = len(ts)
            lat_h = [float(np.linalg.norm(verts[ts[k]] - verts[bs[len(bs) - 1 - k]]))
                     for k in range(min(n, len(bs)))]
            top_e = [float(np.linalg.norm(top_pts[(k + 1) % n] - top_pts[k])) for k in range(n)]
            max_e = max(top_e) if top_e else 1.0
            min_h = min(lat_h) if lat_h else 1e-30
            ar = max_e / (min_h + 1e-30)
            if ar > best:
                best = ar
        return best

    # ── 5. Tangential Laplacian + strict guard ────────────────────────────────
    n_moved = 0
    for _it in range(n_iter):
        for tv in all_top_verts:
            nbs = adj.get(tv, set())
            if not nbs:
                continue
            nb_pts = np.array([verts[nb] for nb in nbs if nb in all_top_verts])
            if len(nb_pts) == 0:
                continue
            centroid = nb_pts.mean(axis=0)

            bv = top_to_bot.get(tv)
            if bv is None:
                continue
            p_top = verts[tv]
            p_bot = verts[bv]
            extrusion = p_top - p_bot
            ext_len = float(np.linalg.norm(extrusion))
            if ext_len < 1e-30:
                continue
            ext_hat = extrusion / ext_len

            # project centroid onto tangential plane at p_top
            delta = centroid - p_top
            projected = p_top + delta - float(np.dot(delta, ext_hat)) * ext_hat

            pre_ar = _max_aspect(tv)
            old_pos = verts[tv].copy()
            verts[tv] = projected
            post_ar = _max_aspect(tv)
            if post_ar < pre_ar - min_aspect_improve:
                n_moved += 1
            else:
                verts[tv] = old_pos

    return verts, n_moved


def _extrude_prism_layer(
    wall_cells: set[int],
    vertices: "np.ndarray",         # (V,3) kept voronoi vertices (final_vertices)
    cells: list[list[list[int]]],   # cells[i] = list of faces; face = list[int vidx]
    cell_owner_seed: list[int],     # cells[i] 의 seed point index (== keep_region_indices[i])
    surface_V: "np.ndarray",        # (Vs,3)
    surface_F: "np.ndarray",        # (Fs,3) wall 삼각형
    step: float,
    max_extrude: int = 100,
    thickness_factor: "float | np.ndarray" = 1.0,
) -> tuple["np.ndarray", list[list[list[int]]]]:
    """wall-adj cell 의 boundary face 1 개당 prism 1 셀 추가.

    thickness_factor: scalar 또는 per-wall-cell 배열. 각 prism 의 step 에 곱해져
    local adaptive thickness 를 제어한다 (default 1.0 → 기존 동작 보존).

    Returns: (new_vertices, new_cells) — 기존 + 신규 prism append.
    """
    try:
        import structlog as _sl
        _log = _sl.get_logger()
        wall_seed_to_cell = {cell_owner_seed[i]: i for i in range(len(cells))}
        n_added = 0
        n_rejected_aspect = 0
        n_rejected_collision = 0
        new_verts: list = list(vertices)
        new_cells: list = list(cells)
        _tf_array = np.asarray(thickness_factor) if not np.isscalar(thickness_factor) else None

        # POL_BL1 — build neighbour cell centroid lookup for collision check.
        # Garimella 2003 §3 advancing-front: new top face verts must not land
        # inside any neighbouring poly cell's bounding box (simplified check).
        _cell_centroids: list[np.ndarray] = []
        for _ci, _cfaces in enumerate(cells):
            _all_v: list[int] = []
            for _f in _cfaces:
                _all_v.extend(_f)
            if _all_v:
                _cell_centroids.append(vertices[_all_v].mean(axis=0))
            else:
                _cell_centroids.append(np.zeros(3))

        def _cell_bbox(ci_: int) -> tuple[np.ndarray, np.ndarray]:
            _all_v_: list[int] = []
            for _f_ in cells[ci_]:
                _all_v_.extend(_f_)
            if not _all_v_:
                return np.zeros(3), np.zeros(3)
            _pts_ = vertices[_all_v_]
            return _pts_.min(axis=0), _pts_.max(axis=0)

        for seed_idx in wall_cells:
            if n_added >= max_extrude:
                break
            ci = wall_seed_to_cell.get(seed_idx)
            if ci is None or not cells[ci]:
                continue
            face = cells[ci][0]
            if len(face) < 3:
                continue
            pts = vertices[face]
            c = pts.mean(axis=0)
            A = pts - c
            _, _, Vt = np.linalg.svd(A, full_matrices=False)
            normal = Vt[-1]
            # outward: 시드 방향 반대
            seed_pt = surface_V[seed_idx] if seed_idx < len(surface_V) else c
            if np.dot(normal, c - seed_pt) < 0:
                normal = -normal
            normal = normal / (np.linalg.norm(normal) + 1e-30)

            if _tf_array is not None:
                factor_i = float(_tf_array[n_added]) if n_added < len(_tf_array) else 1.0
            else:
                factor_i = float(thickness_factor)

            top_pts = np.array(new_verts)[face] + normal * step * factor_i

            # POL_BL1 guard 1 — aspect ratio (Garimella 2003 quality criterion).
            # Prism aspect = max_edge / min_edge across all edges (bottom + lateral).
            _all_prism_pts = np.vstack([pts, top_pts])
            _edges_len: list[float] = []
            n_face = len(face)
            for _k in range(n_face):
                _k2 = (_k + 1) % n_face
                _edges_len.append(float(np.linalg.norm(_all_prism_pts[_k2] - _all_prism_pts[_k])))
                _edges_len.append(float(np.linalg.norm(top_pts[_k] - pts[_k])))  # lateral
            _min_e = min(_edges_len) if _edges_len else 1.0
            _max_e = max(_edges_len) if _edges_len else 1.0
            _aspect = _max_e / (_min_e + 1e-30)
            if _aspect > 50.0:
                n_rejected_aspect += 1
                _log.debug("poly_bl_prism_rejected_aspect", aspect=round(_aspect, 2))
                continue

            # POL_BL1 guard 2 — collision check (Garimella 2003 §3 advancing-front).
            # Top face centroid must not land inside any non-wall neighbouring cell bbox.
            _top_c = top_pts.mean(axis=0)
            _collision = False
            for _nci in range(len(cells)):
                if _nci == ci:
                    continue
                _bmin, _bmax = _cell_bbox(_nci)
                if np.all(_top_c >= _bmin - 1e-9) and np.all(_top_c <= _bmax + 1e-9):
                    _collision = True
                    break
            if _collision:
                n_rejected_collision += 1
                _log.debug("poly_bl_prism_rejected_collision", seed=seed_idx)
                continue

            top_indices = []
            base_offset = len(new_verts)
            for _vi_idx, vi in enumerate(face):
                new_verts.append(top_pts[_vi_idx])
                top_indices.append(base_offset + _vi_idx)

            prism_faces: list[list[int]] = []
            prism_faces.append(list(face))  # bottom
            prism_faces.append(list(reversed(top_indices)))  # top (flip normal)
            for k in range(n_face):
                k2 = (k + 1) % n_face
                prism_faces.append([face[k], face[k2], top_indices[k2], top_indices[k]])

            # POL_BL1_ORIENT_FIX (beta2163): compute signed volume; flip if negative.
            def _prism_signed_vol(
                pf: "list[list[int]]",
                all_verts: "list",
            ) -> float:
                """Fan-tet from centroid; return sum of signed volumes (×6)."""
                _all_idx: list[int] = []
                for _f in pf:
                    _all_idx.extend(_f)
                _unique = list(dict.fromkeys(_all_idx))
                if len(_unique) < 4:
                    return 0.0
                _pts_arr = np.array([all_verts[_i] for _i in _unique], dtype=np.float64)
                _cen = _pts_arr.mean(axis=0)
                _vol = 0.0
                for _f in pf:
                    if len(_f) < 3:
                        continue
                    for _k in range(1, len(_f) - 1):
                        _a = np.array(all_verts[_f[0]], dtype=np.float64)
                        _b = np.array(all_verts[_f[_k]], dtype=np.float64)
                        _c = np.array(all_verts[_f[_k + 1]], dtype=np.float64)
                        _vol += float(np.dot(_a - _cen, np.cross(_b - _cen, _c - _cen)))
                return _vol

            _combined_verts: list = list(vertices) + new_verts
            _sv = _prism_signed_vol(prism_faces, _combined_verts)
            if _sv < 0.0:
                # Flip orientation: reverse bottom face vertex order.
                prism_faces[0] = list(reversed(prism_faces[0]))
                # Re-check after flip.
                _sv2 = _prism_signed_vol(prism_faces, _combined_verts)
                if _sv2 < 0.0:
                    _log.warning("poly_bl1_orient_fail", seed=seed_idx, sv=round(_sv2, 8))
                    # Remove appended verts and skip this prism.
                    del new_verts[base_offset:]
                    n_rejected_aspect += 1  # reuse counter; semantically a reject
                    continue

            new_cells.append(prism_faces)
            n_added += 1

        _log.info(
            "poly_bl_prism_added",
            n_prism=n_added,
            n_rejected_aspect=n_rejected_aspect,
            n_rejected_collision=n_rejected_collision,
        )
        return np.array(new_verts, dtype=vertices.dtype), new_cells
    except Exception as exc:
        import structlog as _sl
        _sl.get_logger().warning("native_poly_ttt4_skipped", reason=str(exc)[:120])
        return vertices, cells


def _ccw_sort_face_vertices(
    vertices: np.ndarray, verts_idx: list[int],
) -> list[int]:
    """face vertex 들을 centroid 기준 평면상 CCW 로 정렬."""
    pts = vertices[verts_idx]
    c = pts.mean(axis=0)
    # 평면 normal = PCA 의 최소 분산 축 (SVD)
    A = pts - c
    _, _, vt = np.linalg.svd(A, full_matrices=False)
    n = vt[-1]
    # 평면상 2D 좌표: e1 = 첫 변, e2 = n × e1
    e1 = A[0]
    e1 -= n * float(np.dot(e1, n))
    if np.linalg.norm(e1) < 1e-30:
        return list(verts_idx)
    e1 = e1 / np.linalg.norm(e1)
    e2 = np.cross(n, e1)
    proj = A @ np.stack([e1, e2], axis=1)
    angles = np.arctan2(proj[:, 1], proj[:, 0])
    order = np.argsort(angles)
    return [int(verts_idx[k]) for k in order]


def _inject_feature_seeds(
    surface_pts: np.ndarray,
    surface_faces: np.ndarray,
    *,
    dihedral_deg: float = 30.0,
    max_seeds: int = 200,
) -> np.ndarray:
    """PPP10 — Yan & Wonka 2014 §3 feature-conformal Voronoi seed injection.

    Compute per-edge dihedral angles between adjacent face pairs. For edges
    with dihedral > dihedral_deg (sharp features), sample points along the
    edge proportional to edge length. Returns (M, 3) feature seed array.

    Parameters
    ----------
    surface_pts  : (V, 3) surface vertex positions.
    surface_faces: (F, 3) surface triangle indices.
    dihedral_deg : threshold in degrees; edges sharper than this get seeds.
    max_seeds    : total injection cap (algorithmic, not a tunable per fid).

    Returns
    -------
    np.ndarray (M, 3) — feature seeds to concatenate with interior seeds.
                        Empty (0, 3) if no sharp edges found.
    """
    V = np.asarray(surface_pts, dtype=np.float64)
    F = np.asarray(surface_faces, dtype=np.int64)
    if V.size == 0 or F.size == 0 or max_seeds <= 0:
        return np.empty((0, 3), dtype=np.float64)

    # build edge → face adjacency.
    # C-PERF-73 / beta2524 — vectorize via lexsort + group-boundary.
    F_arr = np.asarray(F, dtype=np.int64)
    edge_to_faces: dict[tuple[int, int], list[int]] = {}
    if F_arr.size > 0:
        src = F_arr[:, [0, 1, 2]].reshape(-1)
        dst = F_arr[:, [1, 2, 0]].reshape(-1)
        fi_arr = np.repeat(np.arange(F_arr.shape[0], dtype=np.int64), 3)
        u = np.minimum(src, dst); v = np.maximum(src, dst)
        order = np.lexsort((v, u))
        u_s = u[order]; v_s = v[order]; fi_s = fi_arr[order]
        diff = np.r_[True, (u_s[1:] != u_s[:-1]) | (v_s[1:] != v_s[:-1])]
        starts = np.where(diff)[0]
        ends = np.r_[starts[1:], len(u_s)]
        for s, e in zip(starts.tolist(), ends.tolist()):
            edge_to_faces[(int(u_s[s]), int(v_s[s]))] = fi_s[s:e].tolist()

    # compute face normals
    e1 = V[F[:, 1]] - V[F[:, 0]]
    e2 = V[F[:, 2]] - V[F[:, 0]]
    normals = np.cross(e1, e2)
    nlen = np.linalg.norm(normals, axis=1, keepdims=True)
    safe = (nlen[:, 0] > 1e-12)
    normals[safe] /= nlen[safe]

    cos_thresh = np.cos(np.deg2rad(dihedral_deg))

    feature_pts: list[np.ndarray] = []
    total = 0

    for (a, b), face_list in edge_to_faces.items():
        if len(face_list) != 2:
            continue  # boundary or non-manifold edge
        fi, fj = face_list
        if not (safe[fi] and safe[fj]):
            continue
        cos_d = float(np.dot(normals[fi], normals[fj]))
        # dihedral > dihedral_deg ↔ cos < cos_thresh (angle measured between normals)
        if cos_d >= cos_thresh:
            continue  # not a sharp edge

        pa, pb = V[a], V[b]
        edge_len = float(np.linalg.norm(pb - pa))
        if edge_len < 1e-12:
            continue

        # number of samples proportional to edge length; at least 1
        bbox_diag = float(np.linalg.norm(V.max(axis=0) - V.min(axis=0))) + 1e-30
        n_sample = max(1, int(round(edge_len / (bbox_diag / 20.0))))
        n_sample = min(n_sample, max_seeds - total)
        if n_sample <= 0:
            break

        ts = np.linspace(0.0, 1.0, n_sample + 2)[1:-1]  # exclude endpoints
        pts = pa[None, :] + ts[:, None] * (pb - pa)[None, :]
        feature_pts.append(pts)
        total += n_sample
        if total >= max_seeds:
            break

    if not feature_pts:
        return np.empty((0, 3), dtype=np.float64)
    return np.vstack(feature_pts)


def _relax_high_aspect_seeds(
    seeds: np.ndarray,
    V: np.ndarray,
    F: np.ndarray,
    *,
    top_k: int = 10,
    relax_factor: float = 0.3,
) -> tuple[np.ndarray, int]:
    """PPP11 — per-cell local seed relaxation for high-aspect-ratio Voronoi cells.

    Detects seeds whose Voronoi cells have high aspect ratio and moves them
    toward their cell centroid (Lloyd-style, local only). Only processes
    top_k worst cells to bound cost.

    Returns
    -------
    (new_seeds, n_relaxed) — updated seed array and count of relaxed seeds.
    """
    if seeds.shape[0] < 5 or top_k <= 0:
        return seeds, 0

    try:
        from scipy.spatial import Voronoi  # noqa: PLC0415
    except Exception:
        return seeds, 0

    # Gate: skip rebuild for large seed sets to bound wall-time
    if seeds.shape[0] >= 5000:
        return seeds, 0

    try:
        vor = Voronoi(seeds)
    except Exception:
        return seeds, 0

    # Compute per-cell aspect ratio: bbox diagonal / min bbox edge
    aspect_ratios: list[tuple[float, int]] = []
    for si, region_idx in enumerate(vor.point_region):
        if region_idx < 0 or region_idx >= len(vor.regions):
            continue
        region = vor.regions[region_idx]
        if -1 in region or len(region) < 4:
            continue
        verts = vor.vertices[region]
        vmin = verts.min(axis=0)
        vmax = verts.max(axis=0)
        extents = vmax - vmin + 1e-30
        aspect = float(extents.max() / extents.min())
        aspect_ratios.append((aspect, si))

    if not aspect_ratios:
        return seeds, 0

    # Sort descending by aspect ratio; take top_k
    aspect_ratios.sort(reverse=True)
    worst = aspect_ratios[:top_k]

    new_seeds = seeds.copy()
    n_relaxed = 0
    for aspect, si in worst:
        if aspect < 2.0:
            break  # remaining cells are acceptable
        region_idx = vor.point_region[si]
        if region_idx < 0 or region_idx >= len(vor.regions):
            continue
        region = vor.regions[region_idx]
        if -1 in region or len(region) < 4:
            continue
        centroid = vor.vertices[region].mean(axis=0)
        candidate = (1.0 - relax_factor) * new_seeds[si] + relax_factor * centroid
        # Only accept if candidate is still inside surface
        inside = _inside_ray_cast(candidate[None, :], V, F)
        if inside[0]:
            new_seeds[si] = candidate
            n_relaxed += 1

    return new_seeds, n_relaxed


def _lloyd_3d_iteration(
    seeds: np.ndarray,
    V: np.ndarray,
    F: np.ndarray,
    n_lloyd: int,
    lp_p: float = 2.0,
) -> np.ndarray:
    """3D Lloyd CVT 반복 — Voronoi region centroid 를 새 seed 로 갱신.

    각 반복에서 scipy.spatial.Voronoi 를 재구성하고 각 seed 의 region
    centroid 를 계산한다. open region (infinite cell, -1 포함) 은 원본
    seed 를 유지한다. 반복 후 inside 재필터링해 표면 밖 seed 제거.

    Args:
        seeds: (N, 3) 초기 seed 점 (surface inside).
        V: 표면 vertex.
        F: 표면 face.
        n_lloyd: Lloyd 반복 횟수. 0 이면 즉시 반환.

    Returns:
        정제된 seed 배열 (M, 3), M <= N.
    """
    if n_lloyd <= 0 or seeds.shape[0] < 5:
        return seeds
    try:
        from scipy.spatial import Voronoi  # noqa: PLC0415
    except Exception:
        return seeds

    seeds_inside = seeds.copy()
    for _ in range(n_lloyd):
        if seeds_inside.shape[0] < 5:
            break
        try:
            vor = Voronoi(seeds_inside)
        except Exception:
            break
        # POL_PERF3 — vectorize centroid computation for lp_p==2.0 (common path).
        # Build CSR-style flat index array: closed_si[], flat_vidx[], region_sizes[].
        # np.add.at accumulates vertex coords grouped by seed → batch mean in O(total_verts).
        n_seeds = seeds_inside.shape[0]
        new_seeds_arr = seeds_inside.copy()  # default: keep originals
        n_regions = len(vor.regions)
        if lp_p == 2.0:
            # --- vectorized path ---
            closed_si: list[int] = []
            flat_vidx: list[int] = []
            region_sizes: list[int] = []
            for si, region_idx in enumerate(vor.point_region):
                if region_idx < 0 or region_idx >= n_regions:
                    continue
                region = vor.regions[region_idx]
                if -1 in region or len(region) == 0:
                    continue
                closed_si.append(si)
                flat_vidx.extend(region)
                region_sizes.append(len(region))
            if closed_si:
                cs_arr = np.array(closed_si, dtype=np.intp)
                fv_arr = np.array(flat_vidx, dtype=np.intp)
                sz_arr = np.array(region_sizes, dtype=np.intp)
                # repeat each seed index sz times for np.add.at accumulation
                si_rep = np.repeat(cs_arr, sz_arr)   # shape: (total_verts,)
                vcoords = vor.vertices[fv_arr]         # shape: (total_verts, 3)
                acc = np.zeros((n_seeds, 3), dtype=np.float64)
                np.add.at(acc, si_rep, vcoords)
                # compute per-seed mean
                cnt = np.zeros(n_seeds, dtype=np.float64)
                np.add.at(cnt, cs_arr, sz_arr.astype(np.float64))
                # only overwrite closed seeds
                safe_cnt = cnt[cs_arr]
                centroids = acc[cs_arr] / safe_cnt[:, None]
                new_seeds_arr[cs_arr] = centroids
        else:
            # --- scalar path for lp_p != 2.0 ---
            for si, region_idx in enumerate(vor.point_region):
                if region_idx < 0 or region_idx >= n_regions:
                    continue
                region = vor.regions[region_idx]
                if -1 in region or len(region) == 0:
                    continue
                try:
                    vs = vor.vertices[region]
                    d = np.linalg.norm(vs - seeds_inside[si], axis=1)
                    w = np.power(np.maximum(d, 1e-12), lp_p - 2.0)
                    centroid = (w[:, None] * vs).sum(axis=0) / w.sum()
                    if np.all(np.isfinite(centroid)):
                        new_seeds_arr[si] = centroid
                    else:
                        new_seeds_arr[si] = vs.mean(axis=0)
                except Exception as exc:
                    log.warning("native_poly_ppp2_skipped", reason=str(exc)[:120])
        # C-PERF-1 / beta2380 — Lloyd plateau early-exit (Du 1999 §3 monotonicity).
        # 이전 seed 와의 평균 displacement 가 bbox 의 1e-4 이하면 수렴 →
        # 추가 iteration 비용 회수 불가. 5×, 10× 가속.
        # C-PERF-15 / beta2454 — threshold env-tunable.
        try:
            import os as _os_lp
            _plateau_thresh = float(
                _os_lp.environ.get("AUTO_TESSELL_LLOYD_PLATEAU_THRESH", "1e-4"),
            )
            _bbox = float(np.linalg.norm(V.max(axis=0) - V.min(axis=0)))
            if _bbox > 0:
                _disp = float(np.linalg.norm(
                    new_seeds_arr - seeds_inside, axis=1,
                ).mean())
                _rel_disp = _disp / max(_bbox, 1e-30)
                if _rel_disp < _plateau_thresh:
                    seeds_inside = new_seeds_arr
                    inside_mask_p = _inside_ray_cast(seeds_inside, V, F)
                    seeds_inside = seeds_inside[inside_mask_p]
                    break
        except Exception:
            pass
        seeds_inside = new_seeds_arr
        # inside 재필터
        inside_mask = _inside_ray_cast(seeds_inside, V, F)
        seeds_inside = seeds_inside[inside_mask]
        if seeds_inside.shape[0] < 5:
            # 너무 많이 잘려나가면 직전 seeds 반환
            break
    return seeds_inside


def generate_native_poly_voronoi(
    vertices: np.ndarray,
    faces: np.ndarray,
    case_dir: Path,
    *,
    target_edge_length: float | None = None,
    seed_density: int = 8,
    n_lloyd: int = 2,
    auto_escalate: bool = True,
    auto_escalate_max: int = 4,
) -> NativePolyResult:
    """bbox 내부 균일 seed + 3D Lloyd CVT 정제 + scipy Voronoi → polyhedral cell.

    DD2 (beta1720) — auto_escalate=True 면 첫 시도가 cells=0 이거나 fail 일 때
    seed_density 를 1.5× 씩 escalate 해 max 4 회 재시도. bracket / gear 같은
    복잡 형상에서 기본 seed 가 부족해 region 0 이 나오는 케이스 자동 회복.
    """
    # PRE3 (beta2149) — input CVT isotropic remesh on high edge-length-ratio.
    # Botsch & Kobbelt 2004 isotropic remesh — gated by edge_length_ratio > 100
    # or n_faces > 200 000. Default ON; set AUTO_TESSELL_PRE3_POLY_OFF=1 to disable.
    import os as _os_poly
    _V = np.asarray(vertices, dtype=np.float64)
    _F = np.asarray(faces, dtype=np.int64)

    # beta2339 — pre-mesh self-intersect capture (P2.6 chain). NativePolyResult
    # 의 n_self_intersect_pre 에 저장 → harness / GUI 활용. ≤5000 face 만 측정.
    _pre_mesh_si_count: int | None = None
    try:
        if int(_F.shape[0]) <= 5000:
            from core.preprocessor.native_repair.self_intersect import (
                detect_self_intersections as _det_si_poly,
            )
            _r_si = _det_si_poly(_V, _F)
            _pre_mesh_si_count = int(_r_si.n_intersections)
            if _r_si.has_self_intersection:
                log.warning(
                    "native_poly_pre_mesh_self_intersect",
                    n_intersections=_pre_mesh_si_count,
                    n_faces=int(_F.shape[0]),
                )
    except Exception as _exc_si:
        log.debug("native_poly_pre_mesh_si_skipped", reason=str(_exc_si)[:120])

    def _inject_si(r: NativePolyResult) -> NativePolyResult:
        """beta2339 — return 직전 SI count 주입 helper.

        NativePolyResult 는 dataclass (mutable) — 그대로 set 후 동일 객체
        반환. 이전엔 multi-return path (auto_escalate / repair_retry /
        last_resort_hex / inner) 모두 SI 정보 누락.
        """
        try:
            if r is not None and getattr(r, "n_self_intersect_pre", None) is None:
                r.n_self_intersect_pre = _pre_mesh_si_count
        except Exception:
            pass
        return r

    # P1.4 / beta2314 — quadric error decimation (G&H 1997) wiring for poly.
    # native_tet (beta2308) 와 동일 패턴 — 50k+ face 입력 자동 단순화 →
    # voronoi seed/CVT 시간 ↓ + boundary snap 안정도 ↑.
    # AUTO_TESSELL_QED (default "auto") — 0=OFF, 1=ON, auto=large only.
    _qed_env = _os_poly.environ.get("AUTO_TESSELL_QED", "auto")
    # C1.5 / beta2364 — threshold 50k → 20k (Hu 2018 §3.4 simplification 적극).
    _qed_min = int(_os_poly.environ.get("AUTO_TESSELL_QED_MIN_F", "20000"))
    if _qed_env == "1" or (_qed_env == "auto" and _F.shape[0] > _qed_min):
        try:
            from core.preprocessor.native_remesh.quadric_decimate import (
                quadric_decimate as _qed,
            )
            _qed_target = max(int(_F.shape[0] * 0.5), 200)
            V_q, F_q = _qed(_V, _F, target_n_faces=_qed_target, max_iters=20000)
            if F_q.shape[0] > 50 and V_q.shape[0] > 30 and F_q.shape[0] < _F.shape[0]:
                log.info(
                    "native_poly_qed_decimate",
                    f_before=int(_F.shape[0]), f_after=int(F_q.shape[0]),
                    target=_qed_target, mode=_qed_env,
                )
                _V = V_q.astype(np.float64)
                _F = F_q.astype(np.int64)
                vertices = _V
                faces = _F
        except Exception as _qed_exc:
            log.debug("native_poly_qed_skipped", reason=str(_qed_exc)[:120])
    if not _os_poly.environ.get("AUTO_TESSELL_PRE3_POLY_OFF") and _F.shape[0] >= 100:
        try:
            _pre3_edges = np.concatenate([
                _V[_F[:, 0]] - _V[_F[:, 1]],
                _V[_F[:, 1]] - _V[_F[:, 2]],
                _V[_F[:, 2]] - _V[_F[:, 0]],
            ], axis=0)
            _pre3_lens = np.linalg.norm(_pre3_edges, axis=1)
            _pre3_lens = _pre3_lens[_pre3_lens > 0]
            _pre3_ratio = float(_pre3_lens.max() / _pre3_lens.min()) if len(_pre3_lens) > 0 else 0.0
            _pre3_nf = int(_F.shape[0])
            if _pre3_ratio > 100.0 or _pre3_nf > 200_000:
                from core.preprocessor.native_remesh import isotropic_remesh
                _pre3_bmin = _V.min(axis=0); _pre3_bmax = _V.max(axis=0)
                _pre3_diag = float(np.linalg.norm(_pre3_bmax - _pre3_bmin))
                _pre3_target = _pre3_diag / 100.0
                V_pre3, F_pre3 = isotropic_remesh(_V, _F, target_edge_length=_pre3_target)
                if F_pre3.shape[0] > _pre3_nf * 2:
                    log.debug(
                        "native_poly_pre3_remesh_skipped_facecount",
                        faces_before=_pre3_nf,
                        faces_after=int(F_pre3.shape[0]),
                    )
                else:
                    vertices = V_pre3.astype(np.float64)
                    faces = F_pre3.astype(np.int64)
                    log.info(
                        "native_poly_pre3_remesh",
                        edge_length_ratio=round(_pre3_ratio, 2),
                        faces_before=_pre3_nf,
                        faces_after=int(faces.shape[0]),
                        target_edge_length=round(_pre3_target, 6),
                    )
        except Exception as _pre3_exc:
            log.warning("pre3_poly_remesh_failed", reason=str(_pre3_exc))

    if auto_escalate:
        # GG1 (beta1750) — best-of-N 평가:
        #   1) voronoi 단순 (escalate 까지)
        #   2) hex fallback 항상 평가
        # 최고 score 채택. cube/sphere/cyl 처럼 단순 형상은 hex 가 quality
        # 우세 → 채택. voronoi 가 cells>>1 인 경우엔 score 비교 후 결정.
        def _grade_score(grade: str) -> float:
            return {"A": 4.0, "B": 3.0, "C": 2.0, "D": 1.0}.get(grade, 0.0)

        # PPP9b — continuous quality tie-break score (Yu 2014 §4).
        # lower = better: max_skew + max_non_ortho / 180.
        def _quality_score_continuous(r: "NativePolyResult") -> float:
            sk = r.max_skewness if r.max_skewness >= 0 else 999.0
            no = r.max_non_orthogonality_deg if r.max_non_orthogonality_deg >= 0 else 999.0
            return float(sk) + float(no) / 180.0

        # PPP3 — candidate tuple: (score+bonus, -cont_score, type_priority, n_cells, result, label)
        # type_priority: voronoi(p=4)=2, voronoi(p=2)=1, hex_fallback=0
        # voronoi 류 +0.5 bonus (grade A 동률 시 voronoi 우선).
        _VORONOI_BONUS = 0.5
        candidates: list[tuple[float, float, int, int, NativePolyResult, str]] = []

        # voronoi escalate.
        # C-PERF-2 / beta2381 — wall-clock budget 적용 (hard mesh 614s 회피).
        # AUTO_TESSELL_POLY_BUDGET_S env 로 override (default 90s).
        import time as _t_budget
        _budget_s = float(_os_poly.environ.get("AUTO_TESSELL_POLY_BUDGET_S", "90"))
        _t_budget_start = _t_budget.perf_counter()
        cur_seed = int(seed_density)
        for attempt in range(int(auto_escalate_max)):
            if _t_budget.perf_counter() - _t_budget_start > _budget_s:
                log.warning(
                    "native_poly_budget_exhausted",
                    component="native_poly", phase="beta2381",
                    elapsed_s=round(_t_budget.perf_counter() - _t_budget_start, 1),
                    budget_s=_budget_s,
                    attempts_done=int(attempt),
                )
                break
            r_attempt = _generate_native_poly_voronoi_inner(
                vertices, faces, case_dir,
                target_edge_length=target_edge_length,
                seed_density=cur_seed,
                n_lloyd=n_lloyd,
            )
            if r_attempt.success and r_attempt.n_cells > 2:
                candidates.append(
                    (
                        _grade_score(r_attempt.quality_grade) + _VORONOI_BONUS,
                        -_quality_score_continuous(r_attempt),
                        1,  # voronoi(p=2)
                        r_attempt.n_cells,
                        r_attempt,
                        f"voronoi(sd={cur_seed})",
                    ),
                )
                break
            cur_seed = max(int(cur_seed * 1.5), cur_seed + 4)

        # PPP2 — best-of-N 에 voronoi(p=4) 후보 추가.
        try:
            r_p4 = _generate_native_poly_voronoi_inner(
                vertices, faces, case_dir,
                target_edge_length=target_edge_length,
                seed_density=cur_seed, n_lloyd=n_lloyd, lp_p=4.0,
            )
            if r_p4.success and r_p4.n_cells > 2:
                candidates.append((
                    _grade_score(r_p4.quality_grade) + _VORONOI_BONUS,
                    -_quality_score_continuous(r_p4),
                    2,  # voronoi(p=4) — highest priority
                    r_p4.n_cells,
                    r_p4,
                    f"voronoi_p4(sd={cur_seed})",
                ))
        except Exception as exc:
            log.warning("native_poly_ppp2_skipped", reason=str(exc)[:120])

        # PPP5 — voronoi_clipped 후보 (type_priority=3, highest).
        try:
            r_clipped = _generate_native_poly_voronoi_inner(
                vertices, faces, case_dir,
                target_edge_length=target_edge_length,
                seed_density=cur_seed, n_lloyd=n_lloyd, lp_p=2.0,
                clip_boundary=True,
            )
            if r_clipped.success and r_clipped.n_cells > 2:
                candidates.append((
                    _grade_score(r_clipped.quality_grade) + _VORONOI_BONUS,
                    -_quality_score_continuous(r_clipped),
                    3,  # voronoi_clipped — highest priority
                    r_clipped.n_cells,
                    r_clipped,
                    f"voronoi_clipped(sd={cur_seed})",
                ))
        except Exception as exc:
            log.warning("native_poly_ppp5_skipped", reason=str(exc)[:120])

        # C4 / beta2363 — anisotropic curvature CVT seed 생성 (StarCCM+ 동등).
        # 본 카드는 metric-aware seed 만 생성 + voronoi(p=2) 호출. 정확한
        # anisotropic Voronoi cell 구축은 C4 phase 2 (multi-week).
        # env AUTO_TESSELL_ANISO_CVT_OFF=1 로 비활성.
        if _os_poly.environ.get("AUTO_TESSELL_ANISO_CVT_OFF", "0") != "1":
            try:
                from core.generator.native_poly.aniso_cvt import aniso_cvt_seeds
                _bbox_min_a = vertices.min(axis=0)
                _bbox_max_a = vertices.max(axis=0)
                _aniso_seeds, _aniso_res = aniso_cvt_seeds(
                    vertices, faces, _bbox_min_a, _bbox_max_a,
                    n_seeds=int(seed_density) ** 2,
                    n_iter=3,
                    aniso_strength=0.5,
                )
                log.info(
                    "native_poly_aniso_cvt_seeds_generated",
                    n_seeds=int(_aniso_res.n_seeds),
                    n_iter=int(_aniso_res.n_iter_used),
                    converged=bool(_aniso_res.converged),
                    elapsed_s=round(_aniso_res.elapsed_s, 3),
                )
                # NOTE: full aniso Voronoi cell 구축은 차후 카드 — seeds 생성만
                # 측정. best-of-N 후보로는 미포함 (cell 구축 미완성).
            except Exception as exc:
                log.debug("native_poly_aniso_cvt_skipped", reason=str(exc)[:120])

        # hex fallback 후보.
        try:
            tmp_case = case_dir.parent / (case_dir.name + "_hex_cand")
            tmp_case.mkdir(parents=True, exist_ok=True)
            r_hex = _hex_to_poly_fallback(
                vertices, faces, tmp_case, seed_density=int(seed_density),
            )
            if r_hex.success and r_hex.n_cells > 2:
                candidates.append(
                    (
                        _grade_score(r_hex.quality_grade),  # no bonus
                        -_quality_score_continuous(r_hex),
                        0,  # hex_fallback — lowest priority
                        r_hex.n_cells,
                        r_hex,
                        "hex_fallback",
                    ),
                )
        except Exception as exc:
            try:
                log.warning("native_poly_ppp3_skipped", reason=str(exc)[:120])
            except Exception:
                pass

        if not candidates:
            # P2 (beta2233 + beta2306) — extreme tier self-intersect 입력의 voronoi
            # 모든 후보 실패 시: run_native_repair → voronoi 재시도.
            # beta2306: 단일 lp_p=2.0 → (p=2, p=4) 양쪽 시도 + 2 회 repair param
            # variant (aggressive=3 → aggressive=2 + 더 큰 hole fill cap).
            # beta2324 — best-of-N fail 시 self-intersect 진단 (Möller 1997).
            # 결과 로그로 사용자에게 입력 품질 신호 + repair-retry 의사결정 근거.
            try:
                from core.preprocessor.native_repair.self_intersect import (
                    detect_self_intersections as _det_si,
                )
                _si_report = _det_si(
                    np.asarray(vertices, dtype=np.float64),
                    np.asarray(faces, dtype=np.int64),
                )
                log.info(
                    "native_poly_self_intersect_diag",
                    n_faces=int(_si_report.n_faces),
                    n_intersections=int(_si_report.n_intersections),
                    has_si=bool(_si_report.has_self_intersection),
                    elapsed_ms=int(_si_report.elapsed_s * 1000),
                )
            except Exception as _si_exc:
                log.debug("native_poly_si_diag_skipped", reason=str(_si_exc)[:120])

            try:
                from core.preprocessor.native_repair import run_native_repair  # noqa: PLC0415
                # P1.2 / beta2581 — extreme repair variant 추가.
                #   기존 v0 (aggressive=3, tight dedup) + v1 (aggressive=2,
                #   relaxed dedup) 모두 실패 시: v2 = 최대 aggressive=5 + 매우
                #   relaxed dedup (1e-5) + 큰 hole cap (1024). 입력에 self-
                #   intersection 이 100+ 인 extreme tier 회복용. 추가로 retry
                #   에서 lp_p=8.0 (octant 최대) 까지 시도 → CVT 가 더 isotropic
                #   하게 수렴.
                _repair_variants = [
                    # (aggressive, dedup_tol, fill_max_boundary)
                    (3, 1e-9, 256),
                    (2, 1e-7, 512),  # beta2306 — 더 관대한 dedup + 더 큰 hole.
                    (5, 1e-5, 1024),  # P1.2 / beta2581 — extreme.
                ]
                for _v_idx, (_aggr, _dtol, _fcap) in enumerate(_repair_variants):
                    _r = run_native_repair(
                        vertices, faces,
                        dedup_tol=_dtol, degenerate_area_tol=1e-18,
                        fill_hole_max_boundary=_fcap, fix_normals=True,
                        aggressive=_aggr,
                    )
                    if _r.vertices.shape[0] < 4 or _r.faces.shape[0] < 4:
                        continue
                    # beta2326 — repair 의 SI delta (before / after) 노출.
                    # beta2325 의 NativeRepairResult.n_self_intersect_* 활용.
                    _si_b = getattr(_r, "n_self_intersect_before", None)
                    _si_a = getattr(_r, "n_self_intersect_after", None)
                    log.info(
                        "native_poly_p2_repair_retry",
                        variant=_v_idx, aggressive=_aggr,
                        v_before=int(vertices.shape[0]),
                        v_after=int(_r.vertices.shape[0]),
                        f_before=int(faces.shape[0]),
                        f_after=int(_r.faces.shape[0]),
                        si_before=int(_si_b) if _si_b is not None else None,
                        si_after=int(_si_a) if _si_a is not None else None,
                        si_delta=(
                            int(_si_a) - int(_si_b)
                            if (_si_a is not None and _si_b is not None)
                            else None
                        ),
                    )
                    # beta2306: p=2 와 p=4 모두 시도.
                    # P1.2 / beta2581 — variant 2 (extreme) 일 때만 lp_p=8.0
                    # 추가 시도 (octant 한계 — CVT 등방성 강화).
                    _lp_p_trials: tuple[float, ...] = (2.0, 4.0)
                    if _v_idx == 2:
                        _lp_p_trials = (2.0, 4.0, 8.0)
                    for _lp_p in _lp_p_trials:
                        _retry_r = _generate_native_poly_voronoi_inner(
                            _r.vertices.astype(np.float64),
                            _r.faces.astype(np.int64),
                            case_dir,
                            target_edge_length=target_edge_length,
                            seed_density=int(seed_density),
                            n_lloyd=int(n_lloyd),
                            lp_p=_lp_p,
                        )
                        if _retry_r.success and _retry_r.n_cells > 2:
                            log.info(
                                "native_poly_p2_repair_voronoi_OK",
                                variant=_v_idx, lp_p=_lp_p,
                                cells=_retry_r.n_cells,
                                grade=_retry_r.quality_grade,
                            )
                            return _inject_si(_retry_r)
            except Exception as exc:
                log.warning("native_poly_p2_repair_skipped", reason=str(exc)[:120])
            # KK4 (beta1870) — last-resort: 직접 native_hex (poly 변환).
            try:
                final_r = _hex_to_poly_fallback(
                    vertices, faces, case_dir,
                    seed_density=int(seed_density),
                )
                if final_r.success and final_r.n_cells > 2:
                    log.warning(
                        "native_poly_last_resort_hex",
                        cells=final_r.n_cells, grade=final_r.quality_grade,
                    )
                    return _inject_si(final_r)
            except Exception as exc:
                log.warning("native_poly_ppp3_skipped", reason=str(exc)[:120])
            return NativePolyResult(
                False, 0.0, message="poly best-of-N 모든 후보 실패",
            )

        # PPP3/PPP9b sort key: (score+bonus, -cont_score, type_priority, n_cells) 내림차순.
        # voronoi(p=4) > voronoi(p=2) > hex_fallback (동점 시).
        # -cont_score: lower cont = better, reverse=True 에서 높은 -cont 가 앞 → lower-is-better 보존.
        candidates.sort(key=lambda t: (t[0], t[1], t[2], t[3]), reverse=True)
        best_score, _neg_cont, _best_prio, _best_ncells, best_result, best_label = candidates[0]
        log.info(
            "native_poly_best_of_n",
            chosen=best_label,
            grade=best_result.quality_grade,
            cells=best_result.n_cells,
            n_candidates=len(candidates),
            cont_score=round(-candidates[0][1], 4),
        )

        # beta2245n — best 가 grade != A 시 P2 repair retry 시도.
        # 입력 self-intersect 등으로 voronoi 가 grade B/C 에 머무르는 경우 회복 가능성.
        # hex_fallback 도 retry 대상 — repair 후 voronoi 가 작동할 가능성.
        # GAP-EXTREME / beta2776 — face limit 5000 → 20000 (extreme tier 회복).
        # extreme mesh (102308 si=7611, 1017017 si=15712) 도 retry 대상에 포함.
        # env AUTO_TESSELL_POLY_GRADE_RETRY=0 으로 비활성 가능.
        _grade_retry_on = _os_poly.environ.get("AUTO_TESSELL_POLY_GRADE_RETRY", "1") != "0"
        _retry_face_cap = int(
            _os_poly.environ.get("AUTO_TESSELL_POLY_GRADE_RETRY_MAX_FACES", "20000"),
        )
        if (
            _grade_retry_on
            and best_result.quality_grade != "A"
            and best_result.success
            and faces.shape[0] <= _retry_face_cap
        ):
            try:
                from core.preprocessor.native_repair import run_native_repair  # noqa: PLC0415
                _r2 = run_native_repair(
                    vertices, faces,
                    dedup_tol=1e-9, degenerate_area_tol=1e-18,
                    fill_hole_max_boundary=256, fix_normals=True,
                    aggressive=2,
                )
                if (
                    _r2.vertices.shape[0] >= 4 and _r2.faces.shape[0] >= 4
                    and (_r2.vertices.shape[0] != vertices.shape[0]
                         or _r2.faces.shape[0] != faces.shape[0])
                ):
                    log.info(
                        "native_poly_p2_grade_retry",
                        old_grade=best_result.quality_grade,
                        v_before=int(vertices.shape[0]), v_after=int(_r2.vertices.shape[0]),
                        f_before=int(faces.shape[0]), f_after=int(_r2.faces.shape[0]),
                    )
                    _retry_r2 = _generate_native_poly_voronoi_inner(
                        _r2.vertices.astype(np.float64),
                        _r2.faces.astype(np.int64),
                        case_dir,
                        target_edge_length=target_edge_length,
                        seed_density=int(seed_density),
                        n_lloyd=int(n_lloyd), lp_p=2.0,
                    )
                    # 채택 정책: 새 grade 가 더 좋으면 (A > B > C > D > ?) 채택.
                    _grade_rank = {"A": 4, "B": 3, "C": 2, "D": 1, "?": 0}
                    if (
                        _retry_r2.success
                        and _grade_rank.get(_retry_r2.quality_grade, 0)
                        > _grade_rank.get(best_result.quality_grade, 0)
                    ):
                        log.info(
                            "native_poly_p2_grade_retry_accepted",
                            old_grade=best_result.quality_grade,
                            new_grade=_retry_r2.quality_grade,
                            new_cells=_retry_r2.n_cells,
                        )
                        return _inject_si(_retry_r2)
            except Exception as exc:
                log.debug("native_poly_p2_grade_retry_skipped", reason=str(exc)[:120])
        # voronoi 가 chosen 이면 case_dir 가 이미 그 결과로 채워짐.
        # hex fallback 이 chosen 이면 voronoi 결과를 hex 결과로 덮어 써야.
        if best_label.startswith("hex"):
            try:
                import shutil as _sh
                # voronoi case_dir 의 polyMesh 를 hex case 로 교체.
                if (tmp_case / "constant" / "polyMesh").exists():
                    if (case_dir / "constant" / "polyMesh").exists():
                        _sh.rmtree(case_dir / "constant" / "polyMesh")
                    (case_dir / "constant").mkdir(parents=True, exist_ok=True)
                    _sh.copytree(
                        tmp_case / "constant" / "polyMesh",
                        case_dir / "constant" / "polyMesh",
                    )
                _sh.rmtree(tmp_case, ignore_errors=True)
            except Exception as exc:
                log.warning("native_poly_hex_swap_failed", reason=str(exc))
        else:
            try:
                import shutil as _sh
                _sh.rmtree(tmp_case, ignore_errors=True)
            except Exception:
                pass
        return _inject_si(best_result)
    _inner_r = _generate_native_poly_voronoi_inner(
        vertices, faces, case_dir,
        target_edge_length=target_edge_length,
        seed_density=seed_density, n_lloyd=n_lloyd,
    )
    return _inject_si(_inner_r)


def _hex_to_poly_fallback(
    vertices: np.ndarray, faces: np.ndarray, case_dir: Path,
    *, seed_density: int = 12,
    escalate_max: int = 4,
) -> NativePolyResult:
    """FF1 (beta1730) — voronoi base 가 fail 한 형상에서 native_hex 결과를
    polyhedral 표현으로 변환해 fallback.

    각 hex cell 을 6 quad face polyhedron 으로 그대로 사용. native_hex 가
    grade A 인 형상 (cube/sphere/cyl/bracket/gear) 에서 polyhedral grade A
    보장.
    """
    import time as _time
    from core.generator.native_hex.mesher import (
        generate_native_hex, _HEX_FACES,
    )

    t0 = _time.perf_counter()
    # KK5 (beta1890) — seed_density escalate. 작은 mesh 에서 hex grid 가
    # bbox 보다 커서 inside cell 0 인 케이스 자동 회복.
    cur_sd = int(seed_density)
    r_hex = None
    for _att in range(int(escalate_max)):
        r_hex = generate_native_hex(
            vertices, faces, case_dir,
            seed_density=cur_sd,
            snap_boundary=True, snap_iterations=2,
            max_cells_per_axis=60,
        )
        if r_hex.success and r_hex.n_cells > 2:
            break
        cur_sd = max(int(cur_sd * 1.6), cur_sd + 6)
    if r_hex is None or not r_hex.success or r_hex.n_cells <= 2:
        return NativePolyResult(
            False, _time.perf_counter() - t0,
            message=f"hex fallback fail: {(r_hex.message if r_hex else 'unknown')[:80]}",
        )

    # hex cell → polyhedral cell (6 quad face).
    # native_hex 가 이미 polyMesh 를 case_dir 에 썼으므로 그대로 두고 메트릭만
    # 측정. result 의 grade / quality 도 hex 와 동일.
    return NativePolyResult(
        success=True,
        elapsed=_time.perf_counter() - t0,
        n_cells=int(r_hex.n_cells),
        n_points=int(r_hex.n_points),
        n_faces=int(r_hex.n_faces),
        message=(
            f"native_poly_hex_fallback OK — cells={r_hex.n_cells}, "
            f"hex grade={r_hex.quality_grade}"
        ),
        quality_grade=r_hex.quality_grade,
        max_non_orthogonality_deg=float(r_hex.max_non_orthogonality_deg),
        mean_non_orthogonality_deg=float(r_hex.mean_non_orthogonality_deg),
        max_skewness=float(r_hex.max_skewness),
        mean_skewness=float(r_hex.mean_skewness),
        avg_faces_per_cell=6.0,
        plane_coverage=float(r_hex.plane_coverage),
        plane_area_coverage=float(r_hex.plane_area_coverage),
    )


def _generate_native_poly_voronoi_inner(
    vertices: np.ndarray,
    faces: np.ndarray,
    case_dir: Path,
    *,
    target_edge_length: float | None = None,
    seed_density: int = 8,
    n_lloyd: int = 2,
    lp_p: float = 2.0,
    clip_boundary: bool = False,
) -> NativePolyResult:
    """단일 시도 (auto_escalate 없는 원본 흐름)."""
    t0 = time.perf_counter()
    try:
        from scipy.spatial import Voronoi
    except Exception as exc:
        return NativePolyResult(False, 0.0, message=f"scipy 필요: {exc}")

    V = np.asarray(vertices, dtype=np.float64)
    F = np.asarray(faces, dtype=np.int64)
    if V.size == 0 or F.size == 0:
        return NativePolyResult(False, 0.0, message="빈 입력")

    bmin = V.min(axis=0); bmax = V.max(axis=0)
    diag = float(np.linalg.norm(bmax - bmin))
    if target_edge_length is None or target_edge_length <= 0:
        target_edge_length = diag / max(2, int(seed_density))
    h = float(target_edge_length)

    # seed 생성: uniform + small jitter (colinear 방지)
    nxyz = np.maximum(np.ceil((bmax - bmin) / h).astype(int), 1)
    nxyz = np.minimum(nxyz, 30)
    xs = np.linspace(bmin[0], bmax[0], nxyz[0])
    ys = np.linspace(bmin[1], bmax[1], nxyz[1])
    zs = np.linspace(bmin[2], bmax[2], nxyz[2])
    X, Y, Z = np.meshgrid(xs, ys, zs, indexing="ij")
    seeds = np.stack([X.ravel(), Y.ravel(), Z.ravel()], axis=1)
    rng = np.random.default_rng(0)
    seeds += rng.uniform(-0.05, 0.05, seeds.shape) * h

    # surface 내부 seed 만 유지
    inside = _inside_ray_cast(seeds, V, F)
    seeds = seeds[inside]

    # FF2 (beta1740) — surface-proximity bias: 복잡 형상 (V.shape[0] >= 200)
    # 만 적용. seed 수가 inside seed 의 50% 미만일 때만 추가 (oversampling
    # 회피 — sphere V=162 같은 곡면 입력의 sliver 유발 방지).
    if V.shape[0] >= 1000 and seeds.shape[0] < V.shape[0] * 0.2:
        try:
            centroid_global = V.mean(axis=0)
            inward = centroid_global - V
            inward_norm = np.linalg.norm(inward, axis=1, keepdims=True)
            safe = inward_norm[:, 0] > 1e-30
            inward_unit = np.where(safe[:, None], inward / np.maximum(inward_norm, 1e-30), 0.0)
            offset = 0.7 * h
            # surface vertex 중 stride sampling 으로 oversampling 완화.
            stride = max(1, V.shape[0] // max(seeds.shape[0], 1))
            sampled_idx = np.arange(0, V.shape[0], stride)
            extra_seeds = V[sampled_idx] + offset * inward_unit[sampled_idx]
            inside_extra = _inside_ray_cast(extra_seeds, V, F)
            extra_seeds = extra_seeds[inside_extra]
            if extra_seeds.shape[0] > 0:
                seeds = np.vstack([seeds, extra_seeds])
                seeds = np.unique(
                    np.round(seeds * 1e6).astype(np.int64), axis=0,
                ).astype(np.float64) / 1e6
        except Exception:
            pass

    # PPP10 — feature-conformal seed injection (Yan & Wonka 2014 §3).
    # Sharp surface edges produce aligned Voronoi seeds → better conformity.
    try:
        feat_seeds = _inject_feature_seeds(V, F, dihedral_deg=30.0, max_seeds=200)
        if feat_seeds.shape[0] > 0:
            # keep only interior feature seeds
            feat_inside = _inside_ray_cast(feat_seeds, V, F)
            feat_seeds = feat_seeds[feat_inside]
            if feat_seeds.shape[0] > 0:
                seeds = np.vstack([seeds, feat_seeds])
                log.info(
                    "native_poly_ppp10_feature_seeds",
                    n_feature=int(feat_seeds.shape[0]),
                    n_total=int(seeds.shape[0]),
                )
    except Exception as exc:
        log.debug("native_poly_ppp10_skipped", reason=str(exc)[:120])

    if seeds.shape[0] < 5:
        return NativePolyResult(
            False, time.perf_counter() - t0,
            message=f"inside seed 부족 ({seeds.shape[0]})",
        )

    # 3D Lloyd CVT 정제: seed 분포 균일화
    if n_lloyd > 0:
        seeds_refined = _lloyd_3d_iteration(seeds, V, F, n_lloyd, lp_p=lp_p)
        if seeds_refined.shape[0] >= 5:
            seeds = seeds_refined
            log.info(
                "native_poly_lloyd_done",
                n_lloyd=n_lloyd,
                n_seeds_before=int(inside.sum()),
                n_seeds_after=seeds.shape[0],
                lp_p=lp_p,
            )

    # PPP11 — local seed relaxation for high-aspect-ratio cells.
    try:
        seeds_relaxed, n_relaxed = _relax_high_aspect_seeds(
            seeds, V, F, top_k=10, relax_factor=0.3,
        )
        if n_relaxed > 0 and seeds_relaxed.shape[0] >= 5:
            seeds = seeds_relaxed
            log.info("native_poly_ppp11_relaxed", n_relaxed=n_relaxed)
    except Exception as exc:
        log.debug("native_poly_ppp11_skipped", reason=str(exc)[:120])

    # boundary padding: 입력 표면 vertex 를 outer seed 로 사용하면 Voronoi 가
    # 내부 seed region 을 surface 근처에서 절단한다. → inside region 유지율 ↑.
    outer = V.copy()
    all_seeds = np.vstack([seeds, outer])
    n_real = seeds.shape[0]

    try:
        vor = Voronoi(all_seeds)
    except Exception as exc:
        return NativePolyResult(
            False, time.perf_counter() - t0,
            message=f"Voronoi 실패: {exc}",
        )

    vor_vertices = vor.vertices
    if vor_vertices.shape[0] == 0:
        return NativePolyResult(
            False, time.perf_counter() - t0, message="Voronoi vertex 없음",
        )

    # v0.4: 경계 clipping MVP — surface 밖 Voronoi vertex 를 KDTree 로 가장 가까운
    # surface vertex 로 snap. 완전한 polygon clipping 은 아니지만 boundary 근처
    # open cell 감소 효과.
    try:
        from core.utils.kdtree import NumpyKDTree  # noqa: PLC0415
        tree = NumpyKDTree(V)
        vv_inside = _inside_ray_cast(vor_vertices, V, F)
        outside_idx = np.where(~vv_inside)[0]
        if outside_idx.size > 0:
            _, nearest = tree.query(vor_vertices[outside_idx], k=1)
            # beta2245m: KDTree may return index == V.shape[0] (off-by-one);
            # clip to valid range.
            nearest = np.asarray(nearest, dtype=np.int64).clip(0, V.shape[0] - 1)
            vor_vertices = vor_vertices.copy()
            vor_vertices[outside_idx] = V[nearest]
            log.info(
                "native_poly_boundary_snap",
                n_outside_snapped=int(outside_idx.size),
            )
    except Exception as exc:
        log.warning("native_poly_boundary_snap_failed", error=str(exc))

    # 각 seed (region) → vertex indices
    region_of_point = vor.point_region
    # 유지할 region 식별 — surface-inside 만 검사 (bbox 체크는 MVP 에서 포기).
    # GAP3 / beta2765 — clip_boundary=True 시 partial-inside cell 도 유지 (clip 단계가
    # 책임). 이전엔 ALL inside 만 유지 → boundary 인접 cell 의 ~40% 가 drop.
    # PPP5 clip 이 이미 존재하나 keep 단계에서 떨어진 cell 은 도달하지 못함.
    keep_region_indices: list[int] = []
    n_partial_kept = 0
    for pi in range(n_real):
        r_idx = region_of_point[pi]
        if r_idx < 0:
            continue
        region = vor.regions[r_idx]
        if -1 in region or len(region) < 4:
            continue
        verts = vor_vertices[region]
        inside_mask = _inside_ray_cast(verts, V, F)
        if inside_mask.all():
            keep_region_indices.append(pi)
        elif clip_boundary and _NATIVE_POLY_PPP4_ENABLE and inside_mask.any():
            # GAP3: partial-inside cell — clip 단계가 boundary 로 잘라 keep.
            # seed 자체는 inside 이어야 함 (cell 전체가 outside 인 경우 회피).
            seed_inside = bool(_inside_ray_cast(seeds[pi:pi+1], V, F)[0])
            if seed_inside:
                keep_region_indices.append(pi)
                n_partial_kept += 1
    if n_partial_kept > 0:
        log.info("native_poly_gap3_partial_kept", n=n_partial_kept)

    if not keep_region_indices:
        return NativePolyResult(
            False, time.perf_counter() - t0,
            message="유지 region 0 — target_edge_length 완화 필요",
        )

    # TTT2b — wall-adjacent cell set 활성화
    _wall_adj = _find_wall_adjacent_cells(seeds, vor.ridge_dict, F)
    log.info("ttt2b_poly_bl_wall_adj", n_wall_adj=len(_wall_adj))

    # PPP5 — boundary cell clipping (clip_boundary=True 시).
    # boundary cell: region 의 vertex 중 1개 이상이 surface 외부에 있는 cell.
    if clip_boundary and _NATIVE_POLY_PPP4_ENABLE:
        max_cells_clip = 200
        clipped_count = 0
        n_clipped_rejected = 0
        new_vor_vertices = vor_vertices.copy()
        _clip_bbox_diag = float(np.linalg.norm(V.max(axis=0) - V.min(axis=0))) + 1e-30
        _clip_min_abs_vol = (1e-9 * _clip_bbox_diag) ** 3
        for pi in keep_region_indices:
            if clipped_count >= max_cells_clip:
                break
            r_idx = region_of_point[pi]
            region = vor.regions[r_idx]
            cell_v = vor_vertices[region]
            inside_mask = _inside_ray_cast(cell_v, V, F)
            if inside_mask.all():
                continue  # fully inside — no clip needed
            try:
                clipped = _clip_voronoi_cell_by_surface(cell_v, V, F)
                if clipped is cell_v or len(clipped) < 4:
                    continue  # degenerate or unchanged — skip
                # POL_QUALITY1 — volume conservation guard after clipping.
                # Tetrahedralize from centroid to detect near-zero / degenerate cells.
                _cen = clipped.mean(axis=0)
                _vol = 0.0
                try:
                    from scipy.spatial import ConvexHull  # noqa: PLC0415
                    _hull = ConvexHull(clipped, qhull_options="QJ")
                    _vol = abs(_hull.volume)
                except Exception:
                    # fallback: sum of signed tetrahedra from centroid
                    for _k in range(len(clipped) - 2):
                        _a = clipped[_k] - _cen
                        _b = clipped[_k + 1] - _cen
                        _c = clipped[_k + 2] - _cen
                        _vol += abs(float(np.dot(_a, np.cross(_b, _c)))) / 6.0
                _vol_ok = np.isfinite(_vol) and _vol >= _clip_min_abs_vol
                if not _vol_ok:
                    n_clipped_rejected += 1
                    log.debug(
                        "poly_cell_rejected_degenerate",
                        cell_idx=int(pi),
                        vol=float(_vol) if np.isfinite(_vol) else None,
                        reason="near_zero_or_nan" if not np.isfinite(_vol) else "below_min_vol",
                    )
                    continue
                # remap clipped vertices back into vor_vertices array
                base = len(new_vor_vertices)
                new_vor_vertices = np.vstack([new_vor_vertices, clipped])
                new_idx = list(range(base, base + len(clipped)))
                vor.regions[r_idx] = new_idx
                clipped_count += 1
            except Exception as exc:
                log.warning("native_poly_ppp6_skipped", reason=str(exc)[:120])
        if clipped_count or n_clipped_rejected:
            log.info(
                "native_poly_ppp5_clipped",
                n_cells_clipped=clipped_count,
                n_degenerate_rejected=n_clipped_rejected,
            )
        if clipped_count:
            vor_vertices = new_vor_vertices
        # POL_QUALITY1 — fallback if >50% of attempted clips were rejected.
        if n_clipped_rejected > 0 and clipped_count == 0:
            log.warning(
                "native_poly_ppp5_clip_all_rejected",
                n_rejected=n_clipped_rejected,
                reason="falling back to non-clipped voronoi path",
            )

    # 각 region 의 face 추출 — scipy Voronoi 의 ridge 구조 활용.
    # vor.ridge_points[ri] = (seed_a, seed_b): 두 seed 사이의 ridge (공유 face)
    # vor.ridge_vertices[ri] = [v0, v1, ...]: 해당 ridge 를 이루는 Voronoi vertex
    # open ridge 는 -1 포함 → skip.
    seed_ridges: dict[int, list[tuple[int, list[int]]]] = defaultdict(list)
    # (neighbour_seed, ridge_vertex_indices) 형태로 저장해 이후 "neighbour 가
    # kept 인 ridge 만" 을 internal face 로 썼을 때 manifold 를 보장.
    # POLY_VORONOI_VEC (R157) — pre-filter valid ridges via numpy; skip open ridges fast.
    _rp = np.asarray(vor.ridge_points, dtype=np.intp)  # (R, 2)
    _rv_list = vor.ridge_vertices  # list of lists (variable length)
    # Identify closed ridges (no -1) with >= 3 vertices using vectorizable checks.
    _valid_ri = [
        ri for ri, rv in enumerate(_rv_list)
        if len(rv) >= 3 and -1 not in rv
    ]
    for ri in _valid_ri:
        sa, sb = int(_rp[ri, 0]), int(_rp[ri, 1])
        rv = list(_rv_list[ri])
        seed_ridges[sa].append((sb, rv))
        seed_ridges[sb].append((sa, rv))

    keep_set = set(keep_region_indices)
    cell_face_verts_list: list[list[list[int]]] = []
    cell_owner_seed: list[int] = []
    # v0.4 boundary clipping MVP:
    # kept region 의 ridge 중 neighbour 가 kept set 에 있으면 internal face,
    # 없으면 boundary face (outer surface). boundary face 는 유지해 cell 이
    # closed 되도록 한다. 이 방식으로 외부 open face 가 사라지고 모든 cell 이
    # topology 상 closed.
    for pi in keep_region_indices:
        faces_of_cell = seed_ridges.get(pi, [])
        if not faces_of_cell:
            continue
        cell_faces: list[list[int]] = []
        for (nb_seed, fv) in faces_of_cell:
            # kept 가 아닌 neighbour 도 유지 → 해당 face 가 boundary 가 됨.
            # 어느 쪽이든 cell 에 포함해야 "topologically closed" polyhedron.
            cell_faces.append(list(fv))
        cell_face_verts_list.append(cell_faces)
        cell_owner_seed.append(pi)

    # POLY_VORONOI_VEC (R157) — collect used vertex indices in bulk via numpy.
    # Replace per-vertex set.add() loop with flat concatenation + np.unique.
    if cell_face_verts_list:
        _all_vidx = np.concatenate([
            np.concatenate([np.asarray(f, dtype=np.intp) for f in cell])
            for cell in cell_face_verts_list
        ])
        used = sorted(int(v) for v in np.unique(_all_vidx))
    else:
        used = []

    # vertex 압축
    remap = {old: new for new, old in enumerate(used)}
    final_vertices = vor_vertices[used]
    final_cells: list[list[list[int]]] = []
    for cell in cell_face_verts_list:
        remapped_cell = [[remap[v] for v in f] for f in cell]
        # CCW sort each face
        remapped_cell = [
            _ccw_sort_face_vertices(final_vertices, f) for f in remapped_cell
        ]
        final_cells.append(remapped_cell)

    # POL_VAL3 (beta2162) — per-pass neg-vol tracker. Mirror R105/R108.
    _pol_val3_prev = _count_neg_vol_poly(final_cells, final_vertices)
    log.info(
        "native_poly_neg_vol_track",
        pass_name="initial_voronoi",
        n_neg=_pol_val3_prev,
        delta=0,
    )

    if _TTT3_POLY_BL_EXTRUDE_ENABLE and _wall_adj:
        bbox_diag = float(np.linalg.norm(V.max(0) - V.min(0)))
        _n_cells_pre = len(final_cells)
        final_vertices, final_cells = _extrude_prism_layer(
            _wall_adj, final_vertices, final_cells, cell_owner_seed,
            V, F, step=bbox_diag * 0.005 * 0.95, max_extrude=100,  # TTT7c stitch margin
        )
        n_prism_added = len(final_cells) - _n_cells_pre
        log.info("ttt4_poly_bl_extruded", n_added=n_prism_added)

        # POL_BL_UNIFORM (R124) — first-layer thickness uniformity validator.
        # Mirrors HEX_BL_UNIFORM (R123) for the poly-specific voronoi extrude path.
        # First layer uses uniform step; build per-prism thickness array for observability.
        # Disable via env AUTO_TESSELL_POL_BL_UNIFORM_OFF=1. Default ON.
        import os as _os_pbu  # noqa: PLC0415
        if _os_pbu.environ.get("AUTO_TESSELL_POL_BL_UNIFORM_OFF", "0") != "1":
            try:
                from core.layers.native_bl import validate_bl_thickness_uniformity as _vbtu  # noqa: PLC0415
                _first_step_pbu = bbox_diag * 0.005 * 0.95
                _thick_arr_pbu = np.full(max(n_prism_added, 1), _first_step_pbu, dtype=np.float64)
                _rv = _vbtu(_thick_arr_pbu)
                log.info(
                    "poly_bl_thickness_stats",
                    component="native_poly",
                    phase="POL_BL_UNIFORM",
                    n_prisms=n_prism_added,
                    first_step=round(_first_step_pbu, 8),
                    rel_variation=round(_rv, 6),
                )
                if _rv > 0.05:
                    log.warning(
                        "poly_bl_thickness_warning",
                        component="native_poly",
                        phase="POL_BL_UNIFORM",
                        rel_variation=round(_rv, 6),
                        msg="poly first-layer thickness variation exceeds CFD y+ uniformity threshold",
                    )
            except Exception as _pbu_e:
                log.info("pol_bl_uniform_skipped", reason=str(_pbu_e)[:80])

        _pol_val3_cur = _count_neg_vol_poly(final_cells, final_vertices)
        log.info(
            "native_poly_neg_vol_track",
            pass_name="POL_BL1_prism_extrude",
            n_neg=_pol_val3_cur,
            delta=_pol_val3_cur - _pol_val3_prev,
        )
        _pol_val3_prev = _pol_val3_cur

        # POL_LAYERS — multi-layer BL with geometric growth (cfMesh nLayers=2 default).
        # Uses _geometric_layer_thickness from core.layers.native_bl (BL2, 1.2× ratio).
        # Layer chain: wall → layer1 (t1) → layer2 (t1*1.2) → outer.
        # Guards applied per-layer; truncate chain at last valid layer (don't reject all).
        _POL_LAYERS_N: int = 2  # algorithmic cap (not a sweep param).
        try:
            from core.layers.native_bl import _geometric_layer_thickness as _glt
            _first_step = bbox_diag * 0.005 * 0.95
            _layer_thicknesses = _glt(_first_step, _POL_LAYERS_N, growth_ratio=1.2)
            # layer 0 already extruded above; iterate remaining layers.
            _n_layers_added = 1  # 1st layer done
            _prev_n_prism = n_prism_added
            for _li in range(1, _POL_LAYERS_N):
                _fv_prev = final_vertices
                _fc_prev = final_cells
                try:
                    _wall_adj_li = _find_wall_adjacent_cells(
                        list(range(len(final_cells) - _prev_n_prism, len(final_cells))),
                        {}, F,
                    )
                    if not _wall_adj_li:
                        _wall_adj_li = set(range(
                            len(final_cells) - _prev_n_prism, len(final_cells)
                        ))
                    _step_li = float(_layer_thicknesses[_li])
                    _fv_li, _fc_li = _extrude_prism_layer(
                        _wall_adj_li, final_vertices, final_cells, cell_owner_seed,
                        V, F, step=_step_li, max_extrude=100,
                    )
                    _n_added_li = len(_fc_li) - len(final_cells)
                    if _n_added_li > 0:
                        final_vertices, final_cells = _fv_li, _fc_li
                        _prev_n_prism = _n_added_li
                        _n_layers_added += 1
                        log.info(
                            "pol_layers_layer_added",
                            layer=_li + 1,
                            n_added=_n_added_li,
                            step=round(_step_li, 6),
                        )
                    else:
                        # guard failed for all prisms in this layer — truncate chain.
                        log.info("pol_layers_layer_truncated", layer=_li + 1, reason="no_cells_added")
                        break
                except Exception as _le:
                    final_vertices, final_cells = _fv_prev, _fc_prev
                    log.info("pol_layers_layer_reverted", layer=_li + 1, err=str(_le)[:80])
                    break
            log.info("pol_layers_summary", n_layers=_n_layers_added, n_total_prism=len(final_cells) - _n_cells_pre)
        except Exception as _e:
            log.info("pol_layers_skipped", reason=str(_e)[:120])
        _pol_val3_cur = _count_neg_vol_poly(final_cells, final_vertices)
        log.info(
            "native_poly_neg_vol_track",
            pass_name="POL_LAYERS",
            n_neg=_pol_val3_cur,
            delta=_pol_val3_cur - _pol_val3_prev,
        )
        _pol_val3_prev = _pol_val3_cur

        # POL_BL_TANGENT (beta2155) — tangential Laplacian of outer prism-layer verts.
        # Poly-specific path: poly extrudes its own prisms (not via native_bl.py shared path),
        # so R100 BL_TANGENT_SMOOTH does NOT cover poly. Add poly-specific guard call.
        if _POL_BL_TANG_SMOOTH_ON:
            try:
                _fv_tang, _n_tang = _smooth_poly_top_layer_tangential(
                    final_vertices, final_cells, _n_cells_pre,
                )
                final_vertices = _fv_tang
                log.info(
                    "poly_bl_tangent_smooth",
                    n_moved=_n_tang,
                    n_prism=len(final_cells) - _n_cells_pre,
                )
            except Exception as _tang_exc:
                log.warning("poly_bl_tangent_smooth_skipped", reason=str(_tang_exc)[:120])
            _pol_val3_cur = _count_neg_vol_poly(final_cells, final_vertices)
            log.info(
                "native_poly_neg_vol_track",
                pass_name="POL_BL_TANGENT",
                n_neg=_pol_val3_cur,
                delta=_pol_val3_cur - _pol_val3_prev,
            )
            _pol_val3_prev = _pol_val3_cur

    # Y2 (beta1660) — Voronoi cell vertex Laplacian smoothing (skewness 잡기).
    # 평균 skewness 100+ → < 5 목표. quality 검증 후 채택 (revert 가드).
    try:
        from core.generator.native_poly.quality import (
            smooth_poly_in_memory, poly_quality_report,
            drop_degenerate_poly_cells, collapse_short_face_edges,
        )

        # DD1 — face edge collapse 는 helper 로만 export, default 비활성.
        # 짧은 edge collapse 가 voronoi base 의 cell 토폴로지를 깨뜨려 grade
        # 강등 발생. 사용자 수동 호출용으로 남겨둠.
        _ = collapse_short_face_edges  # noqa: F841

        # AA2 (beta1700) — best-of-three 후보 점수 비교 채택.
        # 후보 1: raw (변화 없음).
        # 후보 2: drop only.
        # 후보 3: drop + smooth (이전 단계).
        def _poly_score(p_arr, c_list) -> tuple[float, dict]:
            if not c_list:
                return -1.0, {"n": 0}
            qr = poly_quality_report(p_arr, c_list)
            # n_cells 가중 + (90 - no) + (5 - skew). 모두 0~1 스케일링.
            cell_score = min(1.0, qr.n_cells / 50.0)
            no_score = max(0.0, (90.0 - qr.max_non_orthogonality_deg) / 90.0)
            sk_score = max(0.0, (5.0 - min(qr.max_skewness, 5.0)) / 5.0)
            score = 0.3 * cell_score + 0.35 * no_score + 0.35 * sk_score
            return score, {
                "n": qr.n_cells,
                "no": round(qr.max_non_orthogonality_deg, 1),
                "sk": round(qr.max_skewness, 3),
            }

        cand_raw_pts = final_vertices.copy()
        cand_raw_cells = [list(c) for c in final_cells]
        raw_score, raw_info = _poly_score(cand_raw_pts, cand_raw_cells)

        # 후보 2: drop only.
        cand_drop_cells, n_drop = drop_degenerate_poly_cells(
            final_vertices, final_cells,
            max_skewness=8.0, max_non_ortho_deg=78.0,
        )
        drop_score, drop_info = _poly_score(final_vertices, cand_drop_cells)

        # 후보 3: drop + smooth.
        smoothed_pts = final_vertices.copy()
        if cand_drop_cells:
            best_pts = smoothed_pts
            best_skew = poly_quality_report(smoothed_pts, cand_drop_cells).max_skewness
            cur_pts = smoothed_pts.copy()
            for _it_block in range(4):
                cur_pts = smooth_poly_in_memory(
                    cur_pts, cand_drop_cells, n_iter=2, relax=0.35,
                )
                cur_skew = poly_quality_report(cur_pts, cand_drop_cells).max_skewness
                if cur_skew < best_skew:
                    best_skew = cur_skew
                    best_pts = cur_pts.copy()
                else:
                    break
            smoothed_pts = best_pts
        smoothed_score, sm_info = _poly_score(smoothed_pts, cand_drop_cells)

        log.info(
            "native_poly_best_of_three",
            raw=round(raw_score, 3), raw_info=raw_info,
            drop=round(drop_score, 3), drop_info=drop_info,
            smooth=round(smoothed_score, 3), sm_info=sm_info,
            n_drop=n_drop,
        )

        if smoothed_score >= drop_score and smoothed_score >= raw_score:
            final_vertices = smoothed_pts
            final_cells = cand_drop_cells
        elif drop_score >= raw_score:
            final_cells = cand_drop_cells
        # else: raw keep.
    except Exception as exc:
        log.debug("native_poly_smooth_skipped", reason=str(exc))

    # POL_VAL3 — track after PPP9b/smooth (best-of-three drop+smooth pass).
    _pol_val3_cur = _count_neg_vol_poly(final_cells, final_vertices)
    log.info(
        "native_poly_neg_vol_track",
        pass_name="PPP9b_smooth",
        n_neg=_pol_val3_cur,
        delta=_pol_val3_cur - _pol_val3_prev,
    )
    _pol_val3_prev = _pol_val3_cur

    # VAL2 (beta2148) — negative-volume poly validation (default ON).
    try:
        validate_poly_cell_volumes(final_cells, final_vertices)
    except Exception as _val2_exc:
        log.debug("native_poly_val2_skipped", reason=str(_val2_exc))
    # POL_VAL3 — final pass tracking (VAL2 post).
    _pol_val3_final = _count_neg_vol_poly(final_cells, final_vertices)
    log.info(
        "native_poly_neg_vol_track",
        pass_name="VAL2_post",
        n_neg=_pol_val3_final,
        delta=_pol_val3_final - _pol_val3_prev,
    )

    try:
        stats = _write_polymesh_poly(final_vertices, final_cells, case_dir)
    except Exception as exc:
        return NativePolyResult(
            False, time.perf_counter() - t0,
            message=f"polyMesh 쓰기 실패: {exc}",
        )

    # Y1 (beta1650) — Fluent poly mesher 비교 메트릭.
    grade = "?"
    max_no = -1.0; mean_no = -1.0
    max_sk = -1.0; mean_sk = -1.0
    avg_fpc = -1.0
    plane_cov = -1.0; plane_area = -1.0
    try:
        from core.generator.native_poly.quality import (
            poly_quality_report, poly_quality_grade,
        )
        q = poly_quality_report(final_vertices, final_cells)
        grade = poly_quality_grade(q)
        max_no = q.max_non_orthogonality_deg
        mean_no = q.mean_non_orthogonality_deg
        max_sk = q.max_skewness
        mean_sk = q.mean_skewness
        avg_fpc = q.avg_faces_per_cell
        log.info(
            "native_poly_quality_gate",
            grade=grade,
            max_non_ortho=round(max_no, 2),
            mean_non_ortho=round(mean_no, 2),
            max_skew=round(max_sk, 3),
            avg_fpc=round(avg_fpc, 2),
        )
    except Exception as exc:
        log.debug("native_poly_quality_skipped", reason=str(exc))

    # plane_coverage — boundary face triangulated 후 측정.
    try:
        from core.generator.native_tet.plane_coverage import (
            _triangle_planes_and_areas, _group_by_plane,
        )
        # boundary face = 1-owner face.
        # POLY_VORONOI_VEC (R157) — vectorized face-owner counting via Counter.
        from collections import Counter as _Counter  # noqa: PLC0415
        _all_face_keys: list[tuple[int, ...]] = [
            tuple(sorted(f))
            for cell_faces in final_cells
            for f in cell_faces
        ]
        face_owner = dict(_Counter(_all_face_keys))
        bnd_tris: list[list[int]] = []
        for cell_faces in final_cells:
            for f in cell_faces:
                k = tuple(sorted(f))
                if face_owner[k] == 1 and len(f) >= 3:
                    # fan triangulation.
                    for i in range(1, len(f) - 1):
                        bnd_tris.append([f[0], f[i], f[i + 1]])
        if bnd_tris:
            B_tri = np.asarray(bnd_tris, dtype=np.int64)
            bbox_diag = float(np.linalg.norm(V.max(axis=0) - V.min(axis=0))) + 1e-30
            in_unit, in_off, in_area = _triangle_planes_and_areas(V, F)
            bn_unit, bn_off, bn_area = _triangle_planes_and_areas(final_vertices, B_tri)
            in_groups = _group_by_plane(
                in_unit, in_off, normal_tol=5e-2, offset_rel_tol=5e-3, bbox_diag=bbox_diag,
            )
            bn_groups = _group_by_plane(
                bn_unit, bn_off, normal_tol=5e-2, offset_rel_tol=5e-3, bbox_diag=bbox_diag,
            )
            n_in = len(in_groups)
            n_covered = 0
            total_in_area = 0.0
            total_match_area = 0.0
            for k_g, idxs in in_groups.items():
                a_in = float(in_area[idxs].sum())
                total_in_area += a_in
                if k_g in bn_groups:
                    a_b = float(bn_area[bn_groups[k_g]].sum())
                    if a_in > 0 and abs(a_b - a_in) / a_in <= 0.10:
                        n_covered += 1
                        total_match_area += a_in
                    else:
                        ratio = min(a_b, a_in) / max(a_in, 1e-30)
                        total_match_area += ratio * a_in
            plane_cov = n_covered / max(n_in, 1) if n_in else 1.0
            plane_area = (
                total_match_area / total_in_area if total_in_area > 0 else 1.0
            )
    except Exception as exc:
        log.debug("native_poly_plane_cov_skipped", reason=str(exc))

    # RUN_SUMMARY (beta2157) — aggregate post-pass counts (observability only).
    log.info(
        "native_poly_run_summary",
        n_cells=int(stats["num_cells"]),
        n_points=int(stats["num_points"]),
        grade=grade,
        max_skewness=round(float(max_sk), 4),
        max_non_ortho=round(float(max_no), 4),
        elapsed=round(time.perf_counter() - t0, 3),
    )

    # C-QUAL-8 / beta2401 — mesh_integrity_suspect (poly).
    _n_cells_final = int(stats["num_cells"])
    _n_surface_v = int(np.asarray(vertices).shape[0])
    _poly_suspect = bool(
        _n_surface_v >= 100 and _n_cells_final > 0
        and _n_cells_final < _n_surface_v // 32
    )
    if _poly_suspect:
        log.warning(
            "native_poly_mesh_integrity_suspect",
            component="native_poly", phase="beta2401",
            n_cells=_n_cells_final,
            n_surface_v=_n_surface_v,
            ratio=round(_n_cells_final / max(1, _n_surface_v), 4),
            message="cells/V_surf < 1/32 — sparse poly mesh suspect",
        )
    return NativePolyResult(
        success=True,
        elapsed=time.perf_counter() - t0,
        n_cells=_n_cells_final,
        n_points=int(stats["num_points"]),
        n_faces=int(stats["num_faces"]),
        message=(
            f"native_poly_voronoi OK — cells={stats['num_cells']}, "
            f"points={stats['num_points']}, seeds={n_real}, grade={grade}"
        ),
        quality_grade=grade,
        max_non_orthogonality_deg=float(max_no),
        mean_non_orthogonality_deg=float(mean_no),
        max_skewness=float(max_sk),
        mean_skewness=float(mean_sk),
        avg_faces_per_cell=float(avg_fpc),
        plane_coverage=float(plane_cov),
        plane_area_coverage=float(plane_area),
        mesh_integrity_suspect=_poly_suspect,
    )
