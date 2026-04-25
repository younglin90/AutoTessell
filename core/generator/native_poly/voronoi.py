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


def _lloyd_3d_iteration(
    seeds: np.ndarray,
    V: np.ndarray,
    F: np.ndarray,
    n_lloyd: int,
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
                centroid = vor.vertices[region].mean(axis=0)
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
        last_result: NativePolyResult | None = None
        cur_seed = int(seed_density)
        for attempt in range(int(auto_escalate_max)):
            r_attempt = _generate_native_poly_voronoi_inner(
                vertices, faces, case_dir,
                target_edge_length=target_edge_length,
                seed_density=cur_seed,
                n_lloyd=n_lloyd,
            )
            if r_attempt.success and r_attempt.n_cells > 0:
                return r_attempt
            last_result = r_attempt
            cur_seed = max(int(cur_seed * 1.5), cur_seed + 4)
        return last_result if last_result is not None else NativePolyResult(
            False, 0.0, message="auto_escalate 모든 시도 실패",
        )
    return _generate_native_poly_voronoi_inner(
        vertices, faces, case_dir,
        target_edge_length=target_edge_length,
        seed_density=seed_density, n_lloyd=n_lloyd,
    )


def _generate_native_poly_voronoi_inner(
    vertices: np.ndarray,
    faces: np.ndarray,
    case_dir: Path,
    *,
    target_edge_length: float | None = None,
    seed_density: int = 8,
    n_lloyd: int = 2,
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
    if seeds.shape[0] < 5:
        return NativePolyResult(
            False, time.perf_counter() - t0,
            message=f"inside seed 부족 ({seeds.shape[0]})",
        )

    # 3D Lloyd CVT 정제: seed 분포 균일화
    if n_lloyd > 0:
        seeds_refined = _lloyd_3d_iteration(seeds, V, F, n_lloyd)
        if seeds_refined.shape[0] >= 5:
            seeds = seeds_refined
            log.info(
                "native_poly_lloyd_done",
                n_lloyd=n_lloyd,
                n_seeds_before=int(inside.sum()),
                n_seeds_after=seeds.shape[0],
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
