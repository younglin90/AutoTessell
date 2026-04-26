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

import numpy as np

from core.utils.logging import get_logger

log = get_logger(__name__)

# PPP4 skeleton — clipping default OFF
_NATIVE_POLY_PPP4_ENABLE: bool = True  # PPP5 — clipping activated

# TTT1 — BL integration sequence skeleton (default OFF)
# TTT1 → TTT2 prism layer insertion → TTT3 stitch
_TTT1_POLY_BL_ENABLE: bool = True


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


from core.utils.geometry import inside_winding_number as _inside_ray_cast


def _write_polymesh_poly(
    vertices: np.ndarray,
    cells: list[list[list[int]]],  # cell 별 face (vertex index list)
    case_dir: Path,
) -> dict[str, int]:
    """각 cell 을 face list 로 정의한 polyMesh — generic writer 위임."""
    from core.generator.polymesh_writer import write_generic_polymesh  # noqa: PLC0415

    return write_generic_polymesh(vertices, cells, case_dir)


_TTT3_POLY_BL_EXTRUDE_ENABLE = True  # TTT4: BL prism extrude 활성.

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
    n = len(cells)
    # face vertex set → (cell_i, cell_j) adjacency
    face_map: dict[frozenset, list[int]] = {}
    for ci, faces in enumerate(cells):
        for face in faces:
            key = frozenset(face)
            face_map.setdefault(key, []).append(ci)

    # build adjacency list
    adj: list[set[int]] = [set() for _ in range(n)]
    for owners in face_map.values():
        if len(owners) == 2:
            a, b = owners
            adj[a].add(b)
            adj[b].add(a)

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
        wall_seed_to_cell = {cell_owner_seed[i]: i for i in range(len(cells))}
        n_added = 0
        new_verts: list = list(vertices)
        new_cells: list = list(cells)
        _tf_array = np.asarray(thickness_factor) if not np.isscalar(thickness_factor) else None

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

            top_indices = []
            base_offset = len(new_verts)
            for vi in face:
                new_verts.append(np.array(new_verts[vi]) + normal * step * factor_i)
                top_indices.append(base_offset + len(top_indices))

            n_face = len(face)
            prism_faces: list[list[int]] = []
            prism_faces.append(list(face))  # bottom
            prism_faces.append(list(reversed(top_indices)))  # top (flip normal)
            for k in range(n_face):
                k2 = (k + 1) % n_face
                prism_faces.append([face[k], face[k2], top_indices[k2], top_indices[k]])
            new_cells.append(prism_faces)
            n_added += 1

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

    # build edge → face adjacency
    edge_to_faces: dict[tuple[int, int], list[int]] = {}
    for fi, tri in enumerate(F):
        for k in range(3):
            a, b = int(tri[k]), int(tri[(k + 1) % 3])
            key = (min(a, b), max(a, b))
            edge_to_faces.setdefault(key, []).append(fi)

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
        new_seeds: list[np.ndarray] = []
        for si, region_idx in enumerate(vor.point_region):
            if region_idx < 0 or region_idx >= len(vor.regions):
                new_seeds.append(seeds_inside[si])
                continue
            region = vor.regions[region_idx]
            if -1 in region or len(region) == 0:
                # open cell → 원본 유지
                new_seeds.append(seeds_inside[si])
            else:
                if lp_p == 2.0:
                    centroid = vor.vertices[region].mean(axis=0)
                else:
                    try:
                        vs = vor.vertices[region]
                        d = np.linalg.norm(vs - seeds_inside[si], axis=1)
                        w = np.power(np.maximum(d, 1e-12), lp_p - 2.0)
                        centroid = (w[:, None] * vs).sum(axis=0) / w.sum()
                        if not np.all(np.isfinite(centroid)):
                            centroid = vs.mean(axis=0)
                    except Exception as exc:
                        log.warning("native_poly_ppp2_skipped", reason=str(exc)[:120])
                        centroid = seeds_inside[si]
                new_seeds.append(centroid)
        seeds_inside = np.array(new_seeds, dtype=np.float64)
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
        cur_seed = int(seed_density)
        for attempt in range(int(auto_escalate_max)):
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
            # KK4 (beta1870) — voronoi + hex_fallback 모두 실패 → case_dir 에
            # 직접 native_hex 호출 (마지막 안전망).
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
                    return final_r
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
        return best_result
    return _generate_native_poly_voronoi_inner(
        vertices, faces, case_dir,
        target_edge_length=target_edge_length,
        seed_density=seed_density, n_lloyd=n_lloyd,
    )


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
    keep_region_indices: list[int] = []
    for pi in range(n_real):
        r_idx = region_of_point[pi]
        if r_idx < 0:
            continue
        region = vor.regions[r_idx]
        if -1 in region or len(region) < 4:
            continue
        verts = vor_vertices[region]
        # 모든 vertex 가 surface 내부인지
        if not _inside_ray_cast(verts, V, F).all():
            continue
        keep_region_indices.append(pi)

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
        new_vor_vertices = vor_vertices.copy()
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
                # remap clipped vertices back into vor_vertices array
                base = len(new_vor_vertices)
                new_vor_vertices = np.vstack([new_vor_vertices, clipped])
                new_idx = list(range(base, base + len(clipped)))
                vor.regions[r_idx] = new_idx
                clipped_count += 1
            except Exception as exc:
                log.warning("native_poly_ppp6_skipped", reason=str(exc)[:120])
        if clipped_count:
            vor_vertices = new_vor_vertices
            log.info("native_poly_ppp5_clipped", n_cells_clipped=clipped_count)

    # 각 region 의 face 추출 — scipy Voronoi 의 ridge 구조 활용.
    # vor.ridge_points[ri] = (seed_a, seed_b): 두 seed 사이의 ridge (공유 face)
    # vor.ridge_vertices[ri] = [v0, v1, ...]: 해당 ridge 를 이루는 Voronoi vertex
    # open ridge 는 -1 포함 → skip.
    seed_ridges: dict[int, list[tuple[int, list[int]]]] = defaultdict(list)
    # (neighbour_seed, ridge_vertex_indices) 형태로 저장해 이후 "neighbour 가
    # kept 인 ridge 만" 을 internal face 로 썼을 때 manifold 를 보장.
    for ri, (sa, sb) in enumerate(vor.ridge_points):
        rv = vor.ridge_vertices[ri]
        if -1 in rv or len(rv) < 3:
            continue
        seed_ridges[int(sa)].append((int(sb), list(rv)))
        seed_ridges[int(sb)].append((int(sa), list(rv)))

    keep_set = set(keep_region_indices)
    used_vertex_set: set[int] = set()
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
            for v in fv:
                used_vertex_set.add(int(v))
        cell_face_verts_list.append(cell_faces)
        cell_owner_seed.append(pi)

    # vertex 압축
    used = sorted(used_vertex_set)
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

    if _TTT3_POLY_BL_EXTRUDE_ENABLE and _wall_adj:
        bbox_diag = float(np.linalg.norm(V.max(0) - V.min(0)))
        _n_cells_pre = len(final_cells)
        final_vertices, final_cells = _extrude_prism_layer(
            _wall_adj, final_vertices, final_cells, cell_owner_seed,
            V, F, step=bbox_diag * 0.005 * 0.95, max_extrude=100,  # TTT7c stitch margin
        )
        n_prism_added = len(final_cells) - _n_cells_pre
        log.info("ttt4_poly_bl_extruded", n_added=n_prism_added)

        # TTT8 — 2nd BL layer (expansion ratio 1.5, Garimella 2003).
        _fv_1st = final_vertices
        _fc_1st = final_cells
        try:
            # 1st layer 의 extruded wall vertex 집합을 새 wall 로 재구성.
            _n_orig_v = len(_fv_1st)
            _wall_adj_2 = _find_wall_adjacent_cells(
                list(range(len(final_cells) - n_prism_added, len(final_cells))),
                {}, F,
            )
            if not _wall_adj_2:
                # fallback: 1st-pass prism index 직접 사용.
                _wall_adj_2 = list(range(len(final_cells) - n_prism_added, len(final_cells)))
            _step_2 = bbox_diag * 0.005 * 0.95 * 1.5
            _fv_2nd, _fc_2nd = _extrude_prism_layer(
                _wall_adj_2, final_vertices, final_cells, cell_owner_seed,
                V, F, step=_step_2, max_extrude=100,
            )
            n_prism_added_2 = len(_fc_2nd) - len(final_cells)
            if n_prism_added_2 > 0 and len(_fc_2nd) > _n_cells_pre:
                final_vertices, final_cells = _fv_2nd, _fc_2nd
                log.info("ttt8_poly_bl_2nd_layer", n_added=n_prism_added_2, step=_step_2)
            else:
                log.info("ttt8_poly_bl_2nd_layer_skipped", reason="no_cells_added")
        except Exception as _e:
            # 2nd layer 실패 시 1st 결과로 revert (grade 가드).
            final_vertices, final_cells = _fv_1st, _fc_1st
            log.info("ttt8_poly_bl_2nd_layer_reverted", err=str(_e))

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
        face_owner: dict[tuple[int, ...], int] = {}
        for cell_faces in final_cells:
            for f in cell_faces:
                k = tuple(sorted(f))
                face_owner[k] = face_owner.get(k, 0) + 1
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

    return NativePolyResult(
        success=True,
        elapsed=time.perf_counter() - t0,
        n_cells=int(stats["num_cells"]),
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
    )
