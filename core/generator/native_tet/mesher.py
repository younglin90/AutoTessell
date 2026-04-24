"""native_tet MVP 메쉬 생성기."""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from core.utils.logging import get_logger

log = get_logger(__name__)


@dataclass
class NativeTetResult:
    success: bool
    elapsed: float
    n_cells: int = 0
    n_points: int = 0
    message: str = ""
    # v0.4: dual 변환 등 downstream 사용을 위해 tet array 와 points 를 함께 반환.
    tet_points: np.ndarray | None = None
    tets: np.ndarray | None = None


def _seed_points_uniform(
    bbox_min: np.ndarray, bbox_max: np.ndarray, spacing: float,
) -> np.ndarray:
    """bbox 내부 uniform grid 시드. spacing 이 bbox 보다 크면 빈 array."""
    diag = float(np.linalg.norm(bbox_max - bbox_min))
    if spacing <= 0 or diag == 0:
        return np.zeros((0, 3))
    # safety: 한 축 당 최대 60 개 (grid size 제한)
    nxyz = np.maximum(
        np.ceil((bbox_max - bbox_min) / spacing).astype(int),
        1,
    )
    nxyz = np.minimum(nxyz, 60)
    xs = np.linspace(bbox_min[0], bbox_max[0], nxyz[0])
    ys = np.linspace(bbox_min[1], bbox_max[1], nxyz[1])
    zs = np.linspace(bbox_min[2], bbox_max[2], nxyz[2])
    X, Y, Z = np.meshgrid(xs, ys, zs, indexing="ij")
    return np.stack([X.ravel(), Y.ravel(), Z.ravel()], axis=1)


from core.utils.geometry import inside_winding_number as _inside_winding_number


def generate_native_tet(
    vertices: np.ndarray,
    faces: np.ndarray,
    case_dir: Path,
    *,
    target_edge_length: float | None = None,
    seed_density: int = 12,
    sliver_quality_threshold: float = 0.05,
    max_input_vertices: int = 100000,
    # beta104 Phase A — TetWild-lite 1 단계.
    enable_phase_a: bool = True,
    feature_angle_deg: float = 30.0,
    recovery_iterations: int = 2,
    protect_boundary_faces: bool = True,
    smooth_iterations: int = 2,
    smooth_relax: float = 0.5,
    # beta160 Phase F — BSP constrained triangle insertion (opt-in fallback).
    enable_bsp_insertion: bool = False,
    bsp_max_inserts_per_triangle: int = 50,
    # beta120 Phase B — local ops + tangent smoothing.
    # 기본 off: O(T^2) / O(V^2) Python 루프라 대형 메쉬에서 느림. 명시 opt-in.
    enable_phase_b: bool = False,
    local_ops_iterations: int = 1,
    split_ratio: float = 4.0 / 3.0,
    collapse_ratio: float = 4.0 / 5.0,
    flip_iterations: int = 1,
    tangent_smooth_iterations: int = 1,
    tangent_smooth_relax: float = 0.3,
    # beta125 Phase C — envelope + quality stop.
    enable_phase_c: bool = False,
    envelope_eps_relative: float = 0.001,
    quality_target_min_q: float = 0.3,
    quality_improvement_eps: float = 0.005,
    quality_window: int = 3,
    # beta140 Phase E2 — curvature-adaptive sizing (split/collapse 기준).
    use_adaptive_sizing: bool = False,
    adaptive_min_ratio: float = 0.25,
    adaptive_max_ratio: float = 2.0,
    adaptive_curvature_gain: float = 2.0,
) -> NativeTetResult:
    """입력 표면 메쉬 → tet polyMesh (MVP).

    Args:
        vertices: (V, 3) 표면 점.
        faces: (F, 3) 표면 triangles (watertight 가정).
        case_dir: OpenFOAM case 디렉터리 (constant/polyMesh 생성됨).
        target_edge_length: 내부 grid spacing. None 이면 bbox_diag / seed_density.
        seed_density: target_edge_length 가 None 일 때 bbox_diag 분할 수.
        sliver_quality_threshold: shape quality (정사면체≈1, sliver≈0) 하한. 이
            값 미만 tet 은 제거. beta62: 0.05 기본이었으나 복잡 형상에서 모든 tet
            이 탈락해 harness 수렴 실패 → 기본값을 quality 별로 조정 가능하게 노출.

    Returns:
        NativeTetResult.
    """
    t0 = time.perf_counter()
    try:
        from scipy.spatial import Delaunay
    except Exception as exc:
        return NativeTetResult(False, 0.0, message=f"scipy 필요: {exc}")

    try:
        from core.generator.polymesh_writer import PolyMeshWriter
    except Exception as exc:
        return NativeTetResult(False, 0.0, message=f"polymesh_writer import 실패: {exc}")

    V = np.asarray(vertices, dtype=np.float64)
    F = np.asarray(faces, dtype=np.int64)
    if V.size == 0 or F.size == 0:
        return NativeTetResult(False, 0.0, message="빈 입력 mesh")

    # beta77: large input guardrail — scipy.Delaunay 가 100k+ vertex 에서 OOM.
    cap = max(1, int(max_input_vertices))
    if V.shape[0] > cap:
        log.warning(
            "native_tet_input_too_large",
            n_vertices=V.shape[0], cap=cap,
            hint="max_input_vertices 늘리거나 표면 리메쉬로 decimation 권장",
        )
        return NativeTetResult(
            False, 0.0,
            message=(
                f"입력 mesh 가 너무 큽니다: {V.shape[0]} vertices > "
                f"max_input_vertices={cap}. "
                "표면 리메쉬(--force-remesh) 또는 max_input_vertices 상향 권장."
            ),
        )

    bmin = V.min(axis=0); bmax = V.max(axis=0)
    diag = float(np.linalg.norm(bmax - bmin))
    if target_edge_length is None or target_edge_length <= 0:
        target_edge_length = diag / max(1, int(seed_density))

    log.info(
        "native_tet_start",
        n_surf_verts=V.shape[0], n_surf_faces=F.shape[0],
        bbox_diag=diag, target_edge_length=float(target_edge_length),
    )

    # 1) 시드 = 표면 vertex + 내부 uniform grid
    grid = _seed_points_uniform(bmin, bmax, float(target_edge_length))
    # grid 중 outside 제거 (아니면 bbox 밖으로 tet 이 많이 생김)
    if grid.shape[0] > 0:
        inside_mask = _inside_winding_number(grid, V, F)
        grid = grid[inside_mask]

    all_pts = np.vstack([V, grid]) if grid.shape[0] else V.copy()
    log.info("native_tet_seed", n_points=all_pts.shape[0], n_grid_inside=grid.shape[0])

    # 2) Delaunay (Phase A3: missing triangle 감지 후 시드 추가 재시도).
    n_surface = V.shape[0]
    extra_seeds = np.zeros((0, 3), dtype=np.float64)

    def _run_delaunay(seed_pts: np.ndarray) -> tuple[np.ndarray, np.ndarray] | None:
        try:
            _dl = Delaunay(seed_pts)
        except Exception as _exc:
            log.warning("native_tet_delaunay_failed", error=str(_exc))
            return None
        _tets = np.asarray(_dl.simplices, dtype=np.int64)
        if _tets.shape[0] == 0:
            return None
        return seed_pts, _tets

    dl_res = _run_delaunay(all_pts)
    if dl_res is None:
        return NativeTetResult(
            False, time.perf_counter() - t0, message="Delaunay 실패 또는 0 tet",
        )
    all_pts, tets = dl_res

    if enable_phase_a and recovery_iterations > 0:
        from core.generator.native_tet.insertion import (
            find_missing_triangles, recovery_seeds,
        )

        for it in range(int(recovery_iterations)):
            rec = recovery_seeds(
                all_pts, F, tets,
                bump_distance=0.05 * float(target_edge_length),
                max_seeds=2000,
            )
            if rec.n_missing == 0:
                log.info(
                    "native_tet_recovery_complete",
                    iter=it, n_input=rec.n_input_triangles,
                )
                break
            log.info(
                "native_tet_recovery_iter",
                iter=it, n_missing=rec.n_missing,
                n_new_seeds=int(rec.extra_seeds.shape[0]),
            )
            if rec.extra_seeds.shape[0] == 0:
                break
            inside_new = _inside_winding_number(rec.extra_seeds, V, F)
            good = rec.extra_seeds[inside_new]
            if good.shape[0] == 0:
                break
            extra_seeds = np.vstack([extra_seeds, good])
            augmented = np.vstack([all_pts, good])
            dl_res2 = _run_delaunay(augmented)
            if dl_res2 is None:
                break
            all_pts, tets = dl_res2

        # Phase F — BSP constrained insertion fallback.
        if enable_bsp_insertion:
            from core.generator.native_tet.bsp_insert import bsp_insert_triangles

            remaining = find_missing_triangles(F, tets)
            if remaining.size > 0:
                log.info(
                    "native_tet_bsp_insert_start",
                    n_missing=int(remaining.size),
                )
                all_pts, _tets_after, bsp_res = bsp_insert_triangles(
                    all_pts, tets, V, F, remaining,
                    max_inserts=int(bsp_max_inserts_per_triangle) * int(remaining.size),
                )
                if bsp_res.n_inserted_points > 0:
                    # 신규 점 추가 후 전체 재-Delaunay.
                    dl_res3 = _run_delaunay(all_pts)
                    if dl_res3 is not None:
                        all_pts, tets = dl_res3
                        remaining_after = find_missing_triangles(F, tets)
                        log.info(
                            "native_tet_bsp_insert_done",
                            inserted_points=bsp_res.n_inserted_points,
                            subdivided_tets=bsp_res.n_subdivided_tets,
                            missing_before=bsp_res.n_missing_before,
                            missing_after=int(remaining_after.size),
                        )
                    else:
                        log.warning("native_tet_bsp_redelaunay_failed")

    # 3) tet centroid 로 inside 판정
    centroids = all_pts[tets].mean(axis=1)
    inside_tet = _inside_winding_number(centroids, V, F)

    # 3b) Phase A2 — boundary-aware sliver filter.
    q_thresh = max(0.0, float(sliver_quality_threshold))
    if enable_phase_a:
        from core.generator.native_tet.filter import filter_slivers

        fr = filter_slivers(
            tets, all_pts, inside_tet,
            n_surface_vertices=n_surface,
            q_threshold_interior=q_thresh,
            q_threshold_boundary=max(0.0, q_thresh * 0.1),
            protect_boundary_faces=protect_boundary_faces,
        )
        keep_mask = fr.keep_mask
        log.info(
            "native_tet_sliver_filter_phase_a",
            kept=int(keep_mask.sum()),
            dropped_total=fr.n_dropped,
            interior_dropped=fr.n_interior_dropped,
            boundary_protected=fr.n_boundary_protected,
            q_thresh_interior=fr.q_thresh_interior,
            q_thresh_boundary=fr.q_thresh_boundary,
        )
    else:
        # legacy: 일괄 q_thresh 적용.
        v = all_pts[tets]
        e01 = np.linalg.norm(v[:, 1] - v[:, 0], axis=1)
        e02 = np.linalg.norm(v[:, 2] - v[:, 0], axis=1)
        e03 = np.linalg.norm(v[:, 3] - v[:, 0], axis=1)
        e12 = np.linalg.norm(v[:, 2] - v[:, 1], axis=1)
        e13 = np.linalg.norm(v[:, 3] - v[:, 1], axis=1)
        e23 = np.linalg.norm(v[:, 3] - v[:, 2], axis=1)
        edge_max = np.maximum.reduce([e01, e02, e03, e12, e13, e23])
        vol6 = np.abs(
            np.einsum(
                "ij,ij->i",
                v[:, 1] - v[:, 0],
                np.cross(v[:, 2] - v[:, 0], v[:, 3] - v[:, 0]),
            )
        )
        safe = edge_max > 1e-30
        q = np.zeros_like(edge_max)
        q[safe] = (8.48 * (vol6[safe] / 6.0)) / (edge_max[safe] ** 3)
        keep_mask = inside_tet & (q >= q_thresh)
        log.info(
            "native_tet_sliver_filter",
            kept=int(keep_mask.sum()),
            dropped_sliver=int(inside_tet.sum() - keep_mask.sum()),
            q_threshold=q_thresh,
        )
    kept = tets[keep_mask]
    if kept.shape[0] == 0:
        return NativeTetResult(
            False, time.perf_counter() - t0,
            message="inside tet 0 — target_edge_length 조정 필요",
        )

    # 4) 사용된 vertex 만 추출 + 인덱스 압축.
    #    v0.4.0-beta5: Hausdorff 보존을 위해 모든 surface vertex (V) 는 사용
    #    여부와 무관하게 최종 mesh 에 강제 포함.
    used_set = set(np.unique(kept.ravel()).tolist())
    surface_vert_ids = set(range(V.shape[0]))
    used_set |= surface_vert_ids
    used = np.array(sorted(used_set), dtype=np.int64)
    remap = -np.ones(all_pts.shape[0], dtype=np.int64)
    remap[used] = np.arange(used.shape[0])
    final_tets = remap[kept].astype(np.int64)
    final_pts = all_pts[used].copy()

    # 4b) Phase A1 + A4 — feature 잠금 + interior Laplacian smoothing.
    if enable_phase_a and smooth_iterations > 0:
        from core.generator.native_tet.features import detect_features
        from core.generator.native_tet.smooth import smooth_interior

        feat = detect_features(V, F, feature_angle_deg=float(feature_angle_deg))
        # surface vertex 의 new-index: remap[surface_id] (0..n_surface-1 중 used).
        surface_new_ids = remap[np.arange(n_surface)]
        surface_new_ids = surface_new_ids[surface_new_ids >= 0]
        locked_new: list[int] = surface_new_ids.tolist()
        # feature_locked 는 원래 surface vertex 의 부분집합 → 이미 surface 로 잠김.
        # (추가 lock 이 필요하면 여기서 확장.)
        _ = feat   # 향후 anisotropic smoothing 등에 활용.

        sr = smooth_interior(
            final_pts, final_tets,
            locked_vertex_ids=np.asarray(locked_new, dtype=np.int64),
            n_iter=int(smooth_iterations),
            relax=float(smooth_relax),
        )
        log.info(
            "native_tet_smooth",
            n_iter=sr.n_iter,
            moved=sr.n_interior_moved,
            max_disp=sr.max_displacement,
            n_feature_edges=int(feat.feature_edges.shape[0]),
            n_corner=int(feat.corner_vertices.shape[0]),
        )

    # 4c) Phase B — local operations (split/collapse/flip) + tangent smoothing.
    # Phase C 가 켜져 있으면 envelope-guarded + quality stop 으로 승격.
    if enable_phase_b and local_ops_iterations > 0:
        from core.generator.native_tet.local_ops import (
            collapse_short_edges, split_long_edges,
        )
        from core.generator.native_tet.flip import face_flip_pass
        from core.generator.native_tet.smooth import (
            _vertex_normal_from_faces, smooth_tangent_surface,
        )

        surface_new_ids2 = remap[np.arange(n_surface)]
        surface_new_ids2 = surface_new_ids2[surface_new_ids2 >= 0]

        # adaptive sizing: vertex 별 target 계산 후 split/collapse 에 사용할
        # scalar target 을 곡률 영향 받은 평균으로 조정.
        effective_target = float(target_edge_length)
        if use_adaptive_sizing:
            from core.generator.native_tet.adaptive import curvature_sizing

            per_v = curvature_sizing(
                V, F,
                target_edge=effective_target if enable_phase_b else float(target_edge_length),
                min_ratio=float(adaptive_min_ratio),
                max_ratio=float(adaptive_max_ratio),
                curvature_gain=float(adaptive_curvature_gain),
            )
            effective_target = float(per_v.mean())
            log.info(
                "native_tet_adaptive_sizing",
                base_target=float(target_edge_length),
                adaptive_mean=effective_target,
                adaptive_min=float(per_v.min()),
                adaptive_max=float(per_v.max()),
            )

        env = None
        q_hist: list = []
        if enable_phase_c:
            from core.generator.native_tet.envelope import Envelope, check_operation
            from core.generator.native_tet.quality import snapshot, should_stop
            from core.generator.native_tet.surface_snap import snap_surface_vertices

            env = Envelope.build(V, F, eps_relative=float(envelope_eps_relative))
            q_hist.append(snapshot(final_pts, final_tets))
            log.info(
                "native_tet_phase_c_init_quality",
                n_tets=q_hist[0].n_tets, min_q=q_hist[0].min_q,
                mean_q=q_hist[0].mean_q, max_aspect=q_hist[0].max_aspect,
                envelope_eps=env.eps,
            )

        for loop_idx in range(int(local_ops_iterations)):
            # 이전 상태 스냅샷 (envelope reject 시 복원용).
            prev_pts = final_pts.copy()
            prev_tets = final_tets.copy()

            final_pts, final_tets, n_s = split_long_edges(
                final_pts, final_tets,
                target_edge=effective_target if enable_phase_b else float(target_edge_length),
                ratio=float(split_ratio),
            )
            final_pts, final_tets, n_c = collapse_short_edges(
                final_pts, final_tets,
                target_edge=effective_target if enable_phase_b else float(target_edge_length),
                ratio=float(collapse_ratio),
                locked_vertices=surface_new_ids2,
            )
            final_tets, fr2 = face_flip_pass(
                final_pts, final_tets,
                n_iter=int(flip_iterations),
            )

            if env is not None and surface_new_ids2.size > 0:
                # D2: surface vertex 를 입력 표면 BVH 로 projection (drift 복원).
                snap_res = snap_surface_vertices(
                    final_pts, env.bvh, surface_new_ids2,
                    max_distance=env.eps * 2.0,
                )
                log.info(
                    "native_tet_surface_snap",
                    iter=loop_idx, snapped=snap_res.n_snapped,
                    max_disp=snap_res.max_displacement,
                )
                ok, max_d = check_operation(env, final_pts[surface_new_ids2])
                if not ok:
                    # envelope 이탈 → 이전 상태로 복원.
                    final_pts = prev_pts
                    final_tets = prev_tets
                    log.warning(
                        "native_tet_phase_c_envelope_reject",
                        iter=loop_idx, max_surf_distance=max_d,
                        envelope_eps=env.eps,
                    )
                    break

            log.info(
                "native_tet_phase_b_iter",
                iter=loop_idx, splits=n_s, collapses=n_c,
                flips_23=fr2.n_flip_23,
                q_before=fr2.min_quality_before,
                q_after=fr2.min_quality_after,
            )

            if enable_phase_c:
                from core.generator.native_tet.quality import snapshot, should_stop

                q_hist.append(snapshot(final_pts, final_tets))
                stop, reason = should_stop(
                    q_hist,
                    target_min_q=float(quality_target_min_q),
                    improvement_eps=float(quality_improvement_eps),
                    window=int(quality_window),
                )
                if stop:
                    log.info(
                        "native_tet_phase_c_stop",
                        iter=loop_idx, reason=reason,
                        min_q=q_hist[-1].min_q,
                    )
                    break

            if n_s == 0 and n_c == 0 and fr2.n_flip_23 == 0:
                break

        # 4) tangent-plane surface smoothing.
        if tangent_smooth_iterations > 0 and surface_new_ids2.size > 0:
            # new index 공간에서 surface V/F 재구성.
            vn_old = _vertex_normal_from_faces(V, F)
            # remap 으로 new-index 기반 법선 재매핑.
            vn_new = np.zeros((final_pts.shape[0], 3), dtype=np.float64)
            for old_id in range(n_surface):
                new_id = remap[old_id]
                if new_id >= 0:
                    vn_new[new_id] = vn_old[old_id]
            srt = smooth_tangent_surface(
                final_pts, final_tets,
                surface_vertex_ids=surface_new_ids2,
                vertex_normals=vn_new,
                feature_locked_ids=None,   # 간이: 전체 lock 은 smooth_interior 에서 담당.
                n_iter=int(tangent_smooth_iterations),
                relax=float(tangent_smooth_relax),
            )
            log.info(
                "native_tet_tangent_smooth",
                n_iter=srt.n_iter, moved=srt.n_interior_moved,
                max_disp=srt.max_displacement,
            )

    # 5) polyMesh 쓰기
    try:
        stats = PolyMeshWriter().write(final_pts, final_tets, case_dir)
    except Exception as exc:
        return NativeTetResult(
            False, time.perf_counter() - t0,
            message=f"polyMesh 쓰기 실패: {exc}",
        )

    elapsed = time.perf_counter() - t0
    n_cells = int(stats.get("num_cells", final_tets.shape[0]))
    n_points = int(stats.get("num_points", final_pts.shape[0]))
    return NativeTetResult(
        success=True, elapsed=elapsed,
        n_cells=n_cells, n_points=n_points,
        message=(
            f"native_tet OK — cells={n_cells}, points={n_points}, "
            f"seed_grid={grid.shape[0]}, target_edge={target_edge_length:.4g}"
        ),
        tet_points=final_pts, tets=final_tets,
    )
