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
    # beta830: quality metric 요약 (min_q, mean_q, min_dihedral_deg 등).
    quality: "Any" = None
    # beta1090 (R171) — 비치명 경고 + 개발자 디버그 정보.
    warnings: list[str] | None = None
    debug_info: dict | None = None
    # beta1420 (Q4) — 통합 PASS gate 평가.
    quality_grade: str = "?"           # 'A' / 'B' / 'C' / '?'
    cdt_ratio: float = -1.0
    cdt_face_ratio: float = -1.0       # T3 — surface face 회복률 (strict).
    plane_coverage: float = -1.0       # V1 — fTetWild-style plane conformity.
    plane_area_coverage: float = -1.0
    hausdorff_relative: float = -1.0   # h_symmetric / bbox_diag.

    @property
    def ok(self) -> bool:
        """success alias (R171)."""
        return bool(self.success)


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
    # JJ1 (beta1800) — 입력 자동 수리 (dedup + winding align).
    enable_auto_fix_input: bool = True,
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
    # beta630 — edge recovery (opt-in; draft 기본 경로 비활성화 해 성능 유지).
    enable_edge_recovery: bool = False,
    edge_recovery_max_iter: int = 2,
    # beta120 Phase B — local ops + tangent smoothing.
    # 기본 off: O(T^2) / O(V^2) Python 루프라 대형 메쉬에서 느림. 명시 opt-in.
    enable_phase_b: bool = False,
    local_ops_iterations: int = 1,
    split_ratio: float = 4.0 / 3.0,
    collapse_ratio: float = 4.0 / 5.0,
    flip_iterations: int = 1,
    tangent_smooth_iterations: int = 1,
    tangent_smooth_relax: float = 0.3,
    # beta220 — collapse 보수화: iteration 당 최대 cap + cell-drop guard.
    max_collapses_per_iter: int = 200,
    cell_drop_rollback_ratio: float = 0.5,
    # beta810 — extreme sliver drop threshold.
    sliver_drop_min_dihedral_deg: float = 0.5,
    sliver_drop_max_aspect: float = 1e5,
    # beta125 Phase C — envelope + quality stop.
    enable_phase_c: bool = False,
    envelope_eps_relative: float = 0.001,
    quality_target_min_q: float = 0.3,
    quality_improvement_eps: float = 0.005,
    quality_window: int = 3,
    # beta330 — volume target: 사용자가 희망 cell 수 지정 시 seed_density
    # 자동 조정 (bbox 기반 heuristic: target_edge = (V_bbox / target_cells)^(1/3)).
    target_cells: int | None = None,
    # beta410 — progress_cb(stage: str, pct: float, info: dict): 진행 보고.
    progress_cb: "Any" = None,
    # beta140 Phase E2 — curvature-adaptive sizing (split/collapse 기준).
    use_adaptive_sizing: bool = False,
    # beta500 — anisotropic metric 활성 (curvature-aligned SPD tensor).
    use_anisotropic_metric: bool = False,
    anisotropic_ratio: float = 0.5,
    adaptive_min_ratio: float = 0.25,
    adaptive_max_ratio: float = 2.0,
    adaptive_curvature_gain: float = 2.0,
    # beta1350 — AMIPS 통합 (P2).
    enable_amips_smooth: bool = False,
    amips_iterations: int = 2,
    amips_alpha: float = 1.0,
    # beta1360 — chunked Delaunay 자동 스위칭 (P5).
    chunked_delaunay_threshold: int = 30000,
    enable_chunked_delaunay: bool = True,
    chunked_n_div: int = 2,
    # V2 (beta1580) — Steiner edge midpoint 사전 삽입.
    enable_edge_steiner: bool = False,
    edge_steiner_count: int = 1,
    # beta1370 — CDT recovery 통합 (P1).
    enable_cdt_recovery: bool = False,
    cdt_recovery_max_cycles: int = 2,
    cdt_recovery_points_budget: int = 100,
    # beta1430 (Q6) — outer loop: B 등급 이하면 추가 cycle 까지.
    cdt_recovery_outer_iter: int = 1,
    cdt_recovery_target_ratio: float = 0.9,
    # beta1530 (V3) — boundary clipping (외부 tet 제거).
    enable_boundary_clip: bool = False,
    boundary_clip_threshold: float = 0.5,
    # W4 (beta1610) — best-of-two score 가중 (area / cdt / mq).
    # JJ2 (beta1810) — mq 가중 0.2 → 0.35 으로 강화 (hard mesh sliver 회피).
    score_weight_area: float = 0.4,
    score_weight_cdt: float = 0.25,
    score_weight_mq: float = 0.35,
    prefer_base_threshold: float = 0.02,
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

    def _prog(stage: str, pct: float, **info: object) -> None:
        if progress_cb is None:
            return
        try:
            progress_cb(stage, float(pct), dict(info))
        except Exception:
            pass

    _prog("start", 0.0, n_verts=V.shape[0], n_faces=F.shape[0])

    # beta420 — 입력 건강성 pre-check (경고만, 실행 계속).
    chk = None
    try:
        from core.generator.native_tet.input_check import check_input

        chk = check_input(V, F)
        # JJ1 (beta1800) — 자동 입력 수리: dedup + zero-area drop + winding align.
        # KK1 (beta1850) — chk 가 비-watertight 또는 non-manifold 감지 시 aggressive=True.
        if enable_auto_fix_input:
            try:
                from core.generator.native_tet.input_check import auto_fix_input
                aggressive = False
                if chk is not None:
                    if chk.n_boundary_edges > 0 or chk.n_nonmanifold_edges > 0:
                        aggressive = True
                V_fix, F_fix, fix_info = auto_fix_input(
                    V, F, dup_tol=1e-9, drop_zero_area=True, align_winding=True,
                    aggressive=aggressive,
                )
                if (
                    fix_info.get("n_dedup", 0)
                    or fix_info.get("n_zero_area_drop", 0)
                    or fix_info.get("n_winding_flip", 0)
                    or aggressive
                ):
                    log.info(
                        "native_tet_auto_fix",
                        n_dedup=int(fix_info.get("n_dedup", 0)),
                        n_zero_area=int(fix_info.get("n_zero_area_drop", 0)),
                        n_winding_flip=int(fix_info.get("n_winding_flip", 0)),
                        aggressive=bool(aggressive),
                    )
                    V = V_fix.astype(np.float64)
                    F = F_fix.astype(np.int64)
            except Exception as exc:
                log.debug("native_tet_auto_fix_skipped", reason=str(exc))

            # MM1 (beta1900) — hard self-intersect input 의 사전 isotropic remesh.
            # V > 500 + (boundary>0 또는 nonmanifold>0) 면 input 단순화로 sliver 격감.
            try:
                if (
                    aggressive
                    and V.shape[0] > 500
                    and F.shape[0] > 1000
                ):
                    from core.preprocessor.native_remesh import isotropic_remesh
                    # target_edge: 입력 평균 edge 의 ~ 1.2× — vertex 30-50% 감소 목표.
                    e0 = V[F[:, 0]]; e1 = V[F[:, 1]]; e2 = V[F[:, 2]]
                    elens = np.concatenate([
                        np.linalg.norm(e1 - e0, axis=1),
                        np.linalg.norm(e2 - e1, axis=1),
                        np.linalg.norm(e0 - e2, axis=1),
                    ])
                    h_avg = float(np.median(elens)) if elens.size else 0.0
                    if h_avg > 0:
                        h_target = h_avg * 1.5
                        V_rm, F_rm = isotropic_remesh(
                            V, F, target_edge_length=h_target,
                            n_iter=3, project_to_surface=True,
                            feature_angle_deg=45.0, lock_features=True,
                        )
                        if (
                            V_rm.shape[0] > 30
                            and F_rm.shape[0] > 50
                            and V_rm.shape[0] < V.shape[0]
                        ):
                            log.info(
                                "native_tet_hard_pre_remesh",
                                v_before=int(V.shape[0]),
                                v_after=int(V_rm.shape[0]),
                                f_before=int(F.shape[0]),
                                f_after=int(F_rm.shape[0]),
                                h_target=round(h_target, 5),
                            )
                            V = V_rm.astype(np.float64)
                            F = F_rm.astype(np.int64)
            except Exception as exc:
                log.debug("native_tet_hard_pre_remesh_skipped", reason=str(exc))

        if chk.warnings:
            log.warning(
                "native_tet_input_warnings",
                duplicate=chk.n_duplicate_vertices,
                zero_area=chk.n_zero_area_triangles,
                boundary_edges=chk.n_boundary_edges,
                nonmanifold=chk.n_nonmanifold_edges,
                warnings=chk.warnings,
            )
    except Exception as exc:
        log.debug("native_tet_input_check_skipped", reason=str(exc))

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
        # beta330: target_cells 가 지정되면 bbox volume 기반 heuristic 으로
        # target_edge 유도. 정사면체 V ≈ edge^3 / (6√2) ≈ 0.118 × edge^3.
        if target_cells is not None and int(target_cells) > 0:
            span = (bmax - bmin).prod()
            if span > 0:
                # total_vol / (0.118 × edge^3) ≈ n_cells → edge = (vol / (0.118 × n))^(1/3).
                target_edge_length = float((span / (0.118 * int(target_cells))) ** (1.0 / 3.0))
            else:
                target_edge_length = diag / max(1, int(seed_density))
            log.info(
                "native_tet_target_cells_adjusted",
                target_cells=int(target_cells),
                derived_target_edge=target_edge_length,
            )
        else:
            target_edge_length = diag / max(1, int(seed_density))

    # LL1 (beta1880) — 입력 V 가 작으면 셀 폭증 방지 위해 target_edge 키움.
    # 11k vertex 입력에서 156k tet 폭증 → mean_q 0.12 sliver. cell 수
    # ≈ V^1.25 정도가 fTetWild 비교 시 적절 (sliver 격감).
    # MM1 (beta1900) — exponent 1.4 → 1.25 (cells 9897 → ~3700 for V=664).
    try:
        nv = int(V.shape[0])
        if nv > 200:
            n_target = int(nv ** 1.25)
            span = (bmax - bmin).prod()
            if span > 0 and n_target > 0:
                te_cap = float((span / (0.118 * n_target)) ** (1.0 / 3.0))
                if te_cap > target_edge_length:
                    log.info(
                        "native_tet_target_edge_auto_tune",
                        prev=round(float(target_edge_length), 5),
                        new=round(te_cap, 5),
                        n_input_v=nv, n_target_cells=n_target,
                    )
                    target_edge_length = te_cap
    except Exception:
        pass

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

    # V2 (beta1580) — Steiner edge midpoint 사전 삽입.
    # 입력 F 의 각 edge midpoint 를 점으로 추가하면 Delaunay 결과 surface
    # face 분할이 입력과 더 일치한다 (chained CDT 회복률 ↑).
    if enable_edge_steiner and F.shape[0] > 0:
        try:
            from core.generator.native_tet.cdt_check import _tet_edges  # noqa
            surf_edges_set: set[tuple[int, int]] = set()
            for ti in range(F.shape[0]):
                a, b, c = (int(x) for x in F[ti])
                for u, vv in ((a, b), (b, c), (c, a)):
                    surf_edges_set.add((u, vv) if u < vv else (vv, u))
            extras: list[list[float]] = []
            n_per = max(1, int(edge_steiner_count))
            for (u, vv) in surf_edges_set:
                a = V[u]; b = V[vv]
                for k in range(1, n_per + 1):
                    t = k / (n_per + 1)
                    p = a + t * (b - a)
                    d = np.linalg.norm(all_pts - p, axis=1).min() \
                        if all_pts.shape[0] else 1.0
                    if d > 1e-7:
                        extras.append(p.tolist())
            if extras:
                all_pts = np.vstack(
                    [all_pts, np.asarray(extras, dtype=np.float64)],
                )
                log.info(
                    "native_tet_steiner_edges",
                    n_steiner=len(extras), n_surface_edges=len(surf_edges_set),
                )
        except Exception as exc:
            log.debug("native_tet_steiner_skipped", reason=str(exc))

    log.info("native_tet_seed", n_points=all_pts.shape[0], n_grid_inside=grid.shape[0])

    # 2) Delaunay (Phase A3: missing triangle 감지 후 시드 추가 재시도).
    n_surface = V.shape[0]
    extra_seeds = np.zeros((0, 3), dtype=np.float64)

    def _run_delaunay(seed_pts: np.ndarray) -> tuple[np.ndarray, np.ndarray] | None:
        # beta1360 (P5) — 임계 초과 시 chunked Delaunay 자동 사용.
        if (
            enable_chunked_delaunay
            and seed_pts.shape[0] > int(chunked_delaunay_threshold)
        ):
            try:
                from core.generator.native_tet.chunked import chunked_delaunay
                _, _tets, _info = chunked_delaunay(
                    seed_pts, n_div=int(chunked_n_div), overlap_ratio=0.15,
                )
                log.info(
                    "native_tet_chunked_delaunay",
                    n_points=int(seed_pts.shape[0]),
                    n_chunks=int(_info.n_chunks),
                    n_tets=int(_info.n_tets),
                    n_overlap=int(_info.n_overlap_filtered),
                    elapsed=round(_info.elapsed_s, 3),
                )
                if _tets.shape[0] > 0:
                    return seed_pts, _tets
            except Exception as _exc:
                log.warning("native_tet_chunked_failed", error=str(_exc))
        try:
            _dl = Delaunay(seed_pts)
        except Exception as _exc:
            log.warning("native_tet_delaunay_failed", error=str(_exc))
            return None
        _tets = np.asarray(_dl.simplices, dtype=np.int64)
        if _tets.shape[0] == 0:
            return None
        return seed_pts, _tets

    _prog("delaunay", 0.2, n_points=int(all_pts.shape[0]))
    dl_res = _run_delaunay(all_pts)
    if dl_res is None:
        return NativeTetResult(
            False, time.perf_counter() - t0, message="Delaunay 실패 또는 0 tet",
        )
    all_pts, tets = dl_res
    _prog("delaunay_done", 0.3, n_tets=int(tets.shape[0]))

    # V8 (beta1570) — base Delaunay 의 surface plane area 보존. 마지막에
    # 이보다 떨어지면 fallback.
    base_pts_for_fallback = all_pts.copy()
    base_tets_for_fallback = tets.copy()
    try:
        from core.generator.native_tet.plane_coverage import (
            plane_coverage as _pc_base,
        )
        base_area_for_fallback = float(
            _pc_base(V, F, base_pts_for_fallback, base_tets_for_fallback).area_coverage
        )
    except Exception:
        base_area_for_fallback = -1.0

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
            # Round 59 시도: B-W incremental — 큰 메시에서 per-point cavity
            # 스캔 O(T) 가 반복되어 느림 (harness 벤치 timeout). 반려 — full
            # re-Delaunay 유지 (scipy.Delaunay 는 C-level 이라 더 빠름).
            augmented = np.vstack([all_pts, good])
            dl_res2 = _run_delaunay(augmented)
            if dl_res2 is None:
                break
            all_pts, tets = dl_res2

        # beta1370+1430 — 통합 CDT recovery + outer iteration.
        if enable_cdt_recovery:
            try:
                from core.generator.native_tet.cdt_recovery import (
                    run_cdt_recovery,
                )
                from core.generator.native_tet.cdt_check import (
                    check_edge_recovery, cdt_ratio as _cdt_ratio_fn,
                )

                outer_iter = max(1, int(cdt_recovery_outer_iter))
                target_ratio = float(cdt_recovery_target_ratio)
                for outer_i in range(outer_iter):
                    cur_check = check_edge_recovery(F, tets)
                    cur_ratio = _cdt_ratio_fn(cur_check)
                    if cur_ratio >= target_ratio:
                        break
                    pts_new, tets_new, cdt_info = run_cdt_recovery(
                        all_pts, tets, V, F,
                        max_cycles=int(cdt_recovery_max_cycles),
                        points_budget=int(cdt_recovery_points_budget),
                        snap_final=False,
                    )
                    if (
                        cdt_info.ratio_after >= cdt_info.ratio_before
                        and tets_new.shape[0] > 0
                    ):
                        all_pts = pts_new
                        tets = tets_new
                        log.info(
                            "native_tet_cdt_recovery",
                            outer=outer_i,
                            cycles=cdt_info.cycles,
                            ratio_before=round(cdt_info.ratio_before, 3),
                            ratio_after=round(cdt_info.ratio_after, 3),
                            missing_before=cdt_info.n_edges_before,
                            missing_after=cdt_info.n_edges_after,
                            inserted=cdt_info.n_inserted_points,
                            reverted=cdt_info.reverted,
                        )
                        if cdt_info.ratio_after - cdt_info.ratio_before < 1e-3:
                            break   # 더 이상 개선 안 됨.
                    else:
                        break
            except Exception as _exc:
                log.debug("native_tet_cdt_recovery_skipped", reason=str(_exc))

        # Round 50-51: iterative missing edge recovery (midpoint 삽입 + B-W).
        # Round 55: enable_edge_recovery=True 일 때만 (draft 성능 보호).
        if enable_edge_recovery:
            try:
                from core.generator.native_tet.cdt_check import check_edge_recovery
                from core.generator.native_tet.edge_recovery import propose_edge_midpoints
                from core.generator.native_tet.bowyer_watson import (
                    bowyer_watson_insert as _bw_edge,
                )

                cdt_initial = check_edge_recovery(F, tets)
                n_miss_initial = cdt_initial.n_missing
                cur_missing = cdt_initial.missing_edges
                total_inserted = 0
                # Round 58: 현재 tet edge set 중 surface edge 인 것은 보호.
                # recovered 된 surface edge 가 B-W cavity 로 다시 제거되지
                # 않도록 protected set 전달.
                surf_edges_all: set[tuple[int, int]] = set()
                for ti in range(F.shape[0]):
                    a, b, c = int(F[ti, 0]), int(F[ti, 1]), int(F[ti, 2])
                    for u, v in ((a, b), (b, c), (c, a)):
                        surf_edges_all.add((u, v) if u < v else (v, u))
                for rec_i in range(int(edge_recovery_max_iter)):
                    if not cur_missing:
                        break
                    prop = propose_edge_midpoints(V, cur_missing, max_points=200)
                    if prop.new_points.shape[0] == 0:
                        break
                    inside_new = _inside_winding_number(prop.new_points, V, F)
                    good = prop.new_points[inside_new]
                    if good.shape[0] == 0:
                        good = prop.new_points
                    # 현재 tet 에 존재하는 surface edge (= 이미 recovered) 를 보호.
                    from core.generator.native_tet.cdt_check import _tet_edges

                    cur_tet_edges = _tet_edges(tets)
                    protected = surf_edges_all & cur_tet_edges
                    ap_new, ts_new, er_res = _bw_edge(
                        all_pts, tets, good,
                        protected_edges=protected,
                    )
                    if er_res.n_inserted == 0:
                        break
                    cdt_candidate = check_edge_recovery(F, ts_new)
                    if cdt_candidate.n_missing > len(cur_missing):
                        log.info(
                            "native_tet_edge_recovery_reverted",
                            iter=rec_i, before=len(cur_missing),
                            candidate_after=cdt_candidate.n_missing,
                        )
                        break
                    all_pts, tets = ap_new, ts_new
                    total_inserted += er_res.n_inserted
                    log.info(
                        "native_tet_edge_recovery_iter",
                        iter=rec_i, missing=cdt_candidate.n_missing,
                        inserted_this_iter=er_res.n_inserted,
                    )
                    if cdt_candidate.n_missing >= len(cur_missing):
                        break
                    cur_missing = cdt_candidate.missing_edges
                if total_inserted > 0:
                    cdt_final = check_edge_recovery(F, tets)
                    log.info(
                        "native_tet_edge_recovery_done",
                        missing_before=n_miss_initial,
                        missing_after=cdt_final.n_missing,
                        total_inserted=total_inserted,
                    )

                # Round 67-68: iterative targeted 2-3 flip (최대 3 패스).
                try:
                    from core.generator.native_tet.edge_flip_recovery import (
                        recover_edges_via_flip,
                    )

                    for _flip_pass in range(3):
                        cdt_now = check_edge_recovery(F, tets)
                        if cdt_now.n_missing == 0:
                            break
                        tets_flip, flip_res = recover_edges_via_flip(
                            all_pts, tets, cdt_now.missing_edges,
                            max_attempts=200,
                        )
                        if flip_res.n_edges_recovered == 0:
                            break
                        tets = tets_flip
                        cdt_after = check_edge_recovery(F, tets)
                        log.info(
                            "native_tet_edge_recovery_flip_iter",
                            pass_=_flip_pass,
                            recovered=flip_res.n_edges_recovered,
                            missing_after=cdt_after.n_missing,
                        )
                        if cdt_after.n_missing >= cdt_now.n_missing:
                            break
                except Exception as exc:
                    log.debug(
                        "native_tet_edge_recovery_flip_skipped", reason=str(exc),
                    )
            except Exception as exc:
                log.debug("native_tet_edge_recovery_skipped", reason=str(exc))

        # Phase F — BSP constrained insertion fallback.
        if enable_bsp_insertion:
            from core.generator.native_tet.bsp_insert import bsp_insert_triangles
            from core.generator.native_tet.bowyer_watson import bowyer_watson_insert

            remaining = find_missing_triangles(F, tets)
            if remaining.size > 0:
                log.info(
                    "native_tet_bsp_insert_start",
                    n_missing=int(remaining.size),
                )
                # BSP 가 신규 점을 제안 (삽입 위치 계산).
                pts_with_new, _tets_after, bsp_res = bsp_insert_triangles(
                    all_pts, tets, V, F, remaining,
                    max_inserts=int(bsp_max_inserts_per_triangle) * int(remaining.size),
                )
                if bsp_res.n_inserted_points > 0:
                    # 신규 점들만 추출해 Bowyer-Watson incremental insertion.
                    # beta480: full re-Delaunay 대신 B-W 로 O(K log T) 점진 삽입.
                    new_pts = pts_with_new[all_pts.shape[0]:]
                    all_pts_new, tets_new, bw_res = bowyer_watson_insert(
                        all_pts, tets, new_pts,
                    )
                    if bw_res.n_inserted > 0:
                        all_pts, tets = all_pts_new, tets_new
                        # Round 48: B-W 로 삽입된 신규 점을 입력 표면 BVH 로
                        # 한 번 snap — Hausdorff 오차 감소.
                        try:
                            from core.generator.native_tet.surface_snap import (
                                snap_surface_vertices,
                            )
                            from core.utils.aabb import TriangleBVH

                            n_before_bw = all_pts.shape[0] - bw_res.n_inserted
                            new_ids = np.arange(
                                n_before_bw, all_pts.shape[0], dtype=np.int64,
                            )
                            bvh_surf = TriangleBVH.build(V, F)
                            bbox_diag = float(
                                np.linalg.norm(V.max(axis=0) - V.min(axis=0))
                            )
                            snap_r = snap_surface_vertices(
                                all_pts, bvh_surf, new_ids,
                                max_distance=bbox_diag * 0.02,
                            )
                            log.info(
                                "native_tet_bw_post_snap",
                                snapped=snap_r.n_snapped,
                                max_disp=snap_r.max_displacement,
                            )
                        except Exception as exc:
                            log.debug(
                                "native_tet_bw_post_snap_skipped",
                                reason=str(exc),
                            )
                        remaining_after = find_missing_triangles(F, tets)
                        log.info(
                            "native_tet_bsp_bw_insert_done",
                            bsp_proposed_points=bsp_res.n_inserted_points,
                            bw_inserted=bw_res.n_inserted,
                            bw_cavity_total=bw_res.n_cavity_total,
                            missing_before=bsp_res.n_missing_before,
                            missing_after=int(remaining_after.size),
                        )
                    else:
                        # B-W 실패 → full re-Delaunay fallback.
                        all_pts = pts_with_new
                        dl_res3 = _run_delaunay(all_pts)
                        if dl_res3 is not None:
                            all_pts, tets = dl_res3
                            log.info("native_tet_bsp_insert_redelaunay_fallback")
                        else:
                            log.warning("native_tet_bsp_redelaunay_failed")

    # 3) tet centroid 로 inside 판정
    centroids = all_pts[tets].mean(axis=1)
    inside_tet = _inside_winding_number(centroids, V, F)

    # 3b) Phase A2 — boundary-aware sliver filter. V6 — surface-area revert.
    q_thresh = max(0.0, float(sliver_quality_threshold))
    if enable_phase_a:
        from core.generator.native_tet.filter import filter_slivers
        from core.generator.native_tet.plane_coverage import (
            plane_coverage as _pc_pre_filter,
        )

        # 사전 area (filter 전).
        try:
            prev_area_filter = float(
                _pc_pre_filter(V, F, all_pts, tets).area_coverage
            )
        except Exception:
            prev_area_filter = -1.0

        fr = filter_slivers(
            tets, all_pts, inside_tet,
            n_surface_vertices=n_surface,
            q_threshold_interior=q_thresh,
            q_threshold_boundary=max(0.0, q_thresh * 0.1),
            protect_boundary_faces=protect_boundary_faces,
        )
        keep_mask = fr.keep_mask

        # filter 적용 후 area 측정.
        try:
            new_area_filter = float(
                _pc_pre_filter(V, F, all_pts, tets[keep_mask]).area_coverage
            )
        except Exception:
            new_area_filter = prev_area_filter
        if (
            prev_area_filter > 0
            and new_area_filter + 0.05 < prev_area_filter
        ):
            log.warning(
                "native_tet_sliver_filter_revert",
                prev_area=round(prev_area_filter, 3),
                new_area=round(new_area_filter, 3),
                reason="filter_slivers 가 surface plane 깨뜨림",
            )
            # 보수: inside_tet 만 keep, sliver drop 안 함.
            keep_mask = inside_tet.copy()
        else:
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
    # Round 7: feature corner 를 실제 locked set 에 포함.
    feature_info = None
    corner_new_ids_array = np.zeros(0, dtype=np.int64)
    if enable_phase_a and smooth_iterations > 0:
        from core.generator.native_tet.features import detect_features
        from core.generator.native_tet.smooth import smooth_interior

        feature_info = detect_features(
            V, F, feature_angle_deg=float(feature_angle_deg),
        )
        surface_new_ids = remap[np.arange(n_surface)]
        surface_new_ids = surface_new_ids[surface_new_ids >= 0]
        locked_new: list[int] = surface_new_ids.tolist()

        # corner vertex (3+ feature edge 가 만나는 점) 의 new index 추출.
        # 이들은 surface 에 포함되지만 명시적으로 lock 해 smoothing tangent
        # 이동조차 금지.
        if feature_info.corner_vertices.size > 0:
            corner_new_ids = remap[feature_info.corner_vertices]
            corner_new_ids = corner_new_ids[corner_new_ids >= 0]
            corner_new_ids_array = corner_new_ids

        # V4 (beta1540) — smooth 가 surface plane 을 깨뜨리면 revert.
        prev_pts_smooth = final_pts.copy()
        try:
            from core.generator.native_tet.plane_coverage import (
                plane_coverage as _pc_pre,
            )
            prev_area_smooth = float(
                _pc_pre(V, F, final_pts, final_tets).area_coverage
            )
        except Exception:
            prev_area_smooth = -1.0

        sr = smooth_interior(
            final_pts, final_tets,
            locked_vertex_ids=np.asarray(locked_new, dtype=np.int64),
            n_iter=int(smooth_iterations),
            relax=float(smooth_relax),
        )

        try:
            new_area_smooth = float(
                _pc_pre(V, F, final_pts, final_tets).area_coverage
            )
        except Exception:
            new_area_smooth = prev_area_smooth
        if (
            prev_area_smooth > 0
            and new_area_smooth + 0.05 < prev_area_smooth
        ):
            log.warning(
                "native_tet_smooth_revert",
                prev_area=round(prev_area_smooth, 3),
                new_area=round(new_area_smooth, 3),
                reason="surface plane coverage 가 smooth 후 떨어짐",
            )
            final_pts = prev_pts_smooth
        log.info(
            "native_tet_smooth",
            n_iter=sr.n_iter,
            moved=sr.n_interior_moved,
            max_disp=sr.max_displacement,
            n_feature_edges=int(feature_info.feature_edges.shape[0]),
            n_corner=int(feature_info.corner_vertices.shape[0]),
            n_corner_new=int(corner_new_ids_array.size),
        )

    # 4c) Phase B — local operations (split/collapse/flip) + tangent smoothing.
    # Phase C 가 켜져 있으면 envelope-guarded + quality stop 으로 승격.
    _prog("phase_a_done", 0.6, n_tets=int(final_tets.shape[0]))

    if enable_phase_b and local_ops_iterations > 0:
        from core.generator.native_tet.local_ops import (
            collapse_short_edges, compact_unused_vertices, split_long_edges,
        )
        from core.generator.native_tet.flip import face_flip_pass
        from core.generator.native_tet.smooth import (
            _vertex_normal_from_faces, smooth_tangent_surface,
        )

        # beta380 — 대형 메쉬 heuristic: tets > 20k 이면 iteration 과 flip 을
        # 1 로 강제 + tangent smoothing 도 1 회로. Python 루프 비용 폭증 방지.
        if final_tets.shape[0] > 20000:
            log.warning(
                "native_tet_phase_b_large_mesh",
                n_tets=int(final_tets.shape[0]),
                original_iter=int(local_ops_iterations),
                original_flip=int(flip_iterations),
            )
            local_ops_iterations = 1
            flip_iterations = 1
            tangent_smooth_iterations = min(1, int(tangent_smooth_iterations))

        surface_new_ids2 = remap[np.arange(n_surface)]
        surface_new_ids2 = surface_new_ids2[surface_new_ids2 >= 0]

        # anisotropic metric: surface vertex 에 curvature-aligned tensor 구성,
        # 내부 vertex 는 identity. split/collapse 에 metric kwarg 로 주입.
        metric_full: "np.ndarray | None" = None
        if use_anisotropic_metric:
            from core.generator.native_tet.anisotropic import curvature_aligned_metric

            surf_M = curvature_aligned_metric(
                V, F, base_edge=float(target_edge_length),
                aniso_ratio=float(anisotropic_ratio),
            )
            # final_pts 에 대해 metric 배열 구성 (surface new-index → surf_M,
            # interior → identity × 1/target_edge²).
            metric_full = np.zeros((final_pts.shape[0], 3, 3), dtype=np.float64)
            inv_e2 = 1.0 / (float(target_edge_length) ** 2)
            metric_full[:] = np.eye(3) * inv_e2
            for old_id in range(n_surface):
                new_id = remap[old_id]
                if new_id >= 0 and new_id < metric_full.shape[0]:
                    metric_full[new_id] = surf_M[old_id]
            log.info(
                "native_tet_anisotropic_metric",
                aniso_ratio=float(anisotropic_ratio),
            )

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

            # V7 (beta1590) — Phase B iteration 시작 시 surface area 캐시.
            try:
                from core.generator.native_tet.plane_coverage import (
                    plane_coverage as _pc_phb,
                )
                prev_area_phb = float(
                    _pc_phb(V, F, prev_pts, prev_tets).area_coverage
                )
            except Exception:
                prev_area_phb = -1.0

            # Round 66: split 에도 surface edge 보호.
            _split_surf_edges: set[tuple[int, int]] = set()
            for _ti in range(F.shape[0]):
                _a, _b, _c = int(F[_ti, 0]), int(F[_ti, 1]), int(F[_ti, 2])
                for _u, _v in ((_a, _b), (_b, _c), (_c, _a)):
                    _split_surf_edges.add((_u, _v) if _u < _v else (_v, _u))
            final_pts, final_tets, n_s = split_long_edges(
                final_pts, final_tets,
                target_edge=effective_target if enable_phase_b else float(target_edge_length),
                ratio=float(split_ratio),
                metric=metric_full,
                protected_edges=_split_surf_edges,
            )
            # metric_full 은 vertex 수 변경된 이후 길이가 안 맞을 수 있음 — size 다르면 None 처리.
            m_collapse = metric_full if (
                metric_full is not None
                and metric_full.shape[0] == final_pts.shape[0]
            ) else None
            # Round 64: 입력 surface edge 는 collapse 금지.
            _cur_surf_edges: set[tuple[int, int]] = set()
            for _ti in range(F.shape[0]):
                _a, _b, _c = int(F[_ti, 0]), int(F[_ti, 1]), int(F[_ti, 2])
                for _u, _v in ((_a, _b), (_b, _c), (_c, _a)):
                    _cur_surf_edges.add((_u, _v) if _u < _v else (_v, _u))
            final_pts, final_tets, n_c = collapse_short_edges(
                final_pts, final_tets,
                target_edge=effective_target if enable_phase_b else float(target_edge_length),
                ratio=float(collapse_ratio),
                locked_vertices=surface_new_ids2,
                max_collapses=int(max_collapses_per_iter),
                metric=m_collapse,
                protected_edges=_cur_surf_edges,
            )
            # cell 수 급감 rollback: iteration 전 대비 급락하면 이전 상태로.
            if (
                prev_tets.shape[0] > 0
                and final_tets.shape[0] < prev_tets.shape[0] * float(cell_drop_rollback_ratio)
            ):
                log.warning(
                    "native_tet_phase_b_cell_drop_rollback",
                    iter=loop_idx,
                    before=int(prev_tets.shape[0]),
                    after=int(final_tets.shape[0]),
                    threshold=float(cell_drop_rollback_ratio),
                )
                final_pts = prev_pts
                final_tets = prev_tets
                break
            # Round 62/63: 입력 surface face + edge 를 protected set 으로
            # 전달해 2-3/3-2/4-4 flip 모두에서 제거되지 않도록.
            surf_face_set: set[tuple[int, int, int]] = set()
            surf_edge_set: set[tuple[int, int]] = set()
            for ti in range(F.shape[0]):
                a, b, c = int(F[ti, 0]), int(F[ti, 1]), int(F[ti, 2])
                surf_face_set.add(tuple(sorted((a, b, c))))   # type: ignore[arg-type]
                for u, v in ((a, b), (b, c), (c, a)):
                    surf_edge_set.add((u, v) if u < v else (v, u))
            final_tets, fr2 = face_flip_pass(
                final_pts, final_tets,
                n_iter=int(flip_iterations),
                protected_faces=surf_face_set,
                protected_edges=surf_edge_set,
            )

            # V7 (beta1590) — Phase B iteration 후 surface area 검증.
            try:
                new_area_phb = float(
                    _pc_phb(V, F, final_pts, final_tets).area_coverage
                )
            except Exception:
                new_area_phb = prev_area_phb
            if (
                prev_area_phb > 0
                and new_area_phb + 0.05 < prev_area_phb
            ):
                log.warning(
                    "native_tet_phase_b_revert",
                    iter=loop_idx,
                    prev_area=round(prev_area_phb, 3),
                    new_area=round(new_area_phb, 3),
                )
                final_pts = prev_pts
                final_tets = prev_tets
                break

            # 사용 안 된 vertex 제거 (surface vertex 는 보호).
            before_pts = final_pts.shape[0]
            final_pts, final_tets = compact_unused_vertices(
                final_pts, final_tets, keep_first_n=int(n_surface),
            )
            # surface_new_ids2 는 [0, n_surface) 범위로 고정 유지됨.
            if final_pts.shape[0] != before_pts:
                log.info(
                    "native_tet_compact_orphans",
                    iter=loop_idx,
                    removed=int(before_pts - final_pts.shape[0]),
                )

            if env is not None and surface_new_ids2.size > 0:
                # D2: surface vertex 를 입력 표면 BVH 로 projection (drift 복원).
                snap_res = snap_surface_vertices(
                    final_pts, env.bvh, surface_new_ids2,
                    max_distance=env.eps * 2.0,
                    locked_vertex_ids=(
                        corner_new_ids_array if corner_new_ids_array.size else None
                    ),
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
                # Round 7: corner vertex 는 tangent smoothing 에서도 완전 고정.
                feature_locked_ids=corner_new_ids_array if corner_new_ids_array.size else None,
                n_iter=int(tangent_smooth_iterations),
                relax=float(tangent_smooth_relax),
            )
            log.info(
                "native_tet_tangent_smooth",
                n_iter=srt.n_iter, moved=srt.n_interior_moved,
                max_disp=srt.max_displacement,
            )

        # beta1350 — AMIPS energy-based interior smoothing (P2).
        # KK2 (beta1860) — hard mesh (mean_q < 0.15) 자동 감지 시 multistage.
        if enable_amips_smooth and final_tets.shape[0] > 0:
            try:
                from core.generator.native_tet.amips import (
                    smooth_amips, smooth_amips_multistage,
                )
                from core.generator.native_tet.quality import snapshot as _qsnap

                use_multistage = False
                try:
                    pre_q = _qsnap(final_pts, final_tets)
                    if float(pre_q.mean_q) < 0.15:
                        use_multistage = True
                except Exception:
                    pass

                if use_multistage:
                    ar, new_pts_amips = smooth_amips_multistage(
                        final_pts, final_tets,
                        locked_vertex_ids=surface_new_ids2,
                        alphas=(0.5, 1.0, 2.0),
                        n_iter_per=1,
                    )
                    log.info("native_tet_amips_multistage", e_before=round(ar.energy_before, 3), e_after=round(ar.energy_after, 3))
                else:
                    ar, new_pts_amips = smooth_amips(
                        final_pts, final_tets,
                        locked_vertex_ids=surface_new_ids2,
                        n_iter=int(amips_iterations),
                        alpha=float(amips_alpha),
                    )
                if ar.energy_after <= ar.energy_before * 1.05:
                    final_pts = new_pts_amips
                    log.info(
                        "native_tet_amips",
                        moved=ar.n_moved,
                        e_before=round(ar.energy_before, 3),
                        e_after=round(ar.energy_after, 3),
                        max_disp=round(ar.max_disp, 6),
                    )
                else:
                    log.warning(
                        "native_tet_amips_revert",
                        e_before=round(ar.energy_before, 3),
                        e_after=round(ar.energy_after, 3),
                    )
            except Exception as exc:
                log.debug("native_tet_amips_skipped", reason=str(exc))

    # 4d) Round 10 — inverted tet 안전판 (local op 반복 후 numerical edge).
    # V4 (beta1540) — surface-aware swap revert: fix_inverted 후 plane_area
    # coverage 가 5%+ 떨어지면 swap 결과를 버린다 (inverted tet 그대로 둔다).
    if enable_phase_a:
        from core.generator.native_tet.validate import fix_inverted_tets

        prev_tets = final_tets.copy()
        try:
            from core.generator.native_tet.plane_coverage import plane_coverage as _pc

            prev_area = float(_pc(V, F, final_pts, prev_tets).area_coverage)
        except Exception:
            prev_area = -1.0

        final_tets, vr = fix_inverted_tets(final_pts, final_tets)

        # surface plane area 가 깨졌는지 확인.
        try:
            new_area = float(_pc(V, F, final_pts, final_tets).area_coverage)
        except Exception:
            new_area = prev_area
        if (
            prev_area > 0 and new_area >= 0
            and new_area + 0.05 < prev_area
        ):
            log.warning(
                "native_tet_validate_revert",
                prev_area=round(prev_area, 3),
                new_area=round(new_area, 3),
                reason="fix_inverted swap broke surface plane coverage",
            )
            final_tets = prev_tets
        elif vr.n_inverted_before > 0 or vr.n_degenerate > 0:
            log.info(
                "native_tet_validate",
                n_inverted=vr.n_inverted_before,
                fixed_by_swap=vr.n_fixed_by_swap,
                degenerate=vr.n_degenerate,
            )

    # JJ3 (beta1820) — drop_extreme_slivers 전에 smooth_then_drop_slivers 호출
    # (drop 대신 주변 vertex 이동으로 sliver 회복 시도). hard mesh quality ↑.
    if enable_phase_a and final_tets.shape[0] > 0:
        try:
            from core.generator.native_tet.validate import (
                smooth_then_drop_slivers,
            )
            n_surface_in = int(V.shape[0])
            locked_smooth = np.arange(min(n_surface_in, final_pts.shape[0]),
                                       dtype=np.int64)
            new_pts, new_tets, n_moved, n_drop_jj = smooth_then_drop_slivers(
                final_pts, final_tets,
                locked_vertex_ids=locked_smooth,
                min_dihedral_deg=float(sliver_drop_min_dihedral_deg) * 0.5,
                min_aspect_regular=float(sliver_drop_max_aspect) * 1.5,
                n_smooth_iter=2, relax=0.25,
            )
            if new_tets.shape[0] >= final_tets.shape[0] * 0.9:
                # 셀 손실 10% 이내일 때만 채택.
                final_pts = new_pts
                final_tets = new_tets
                if n_moved > 0 or n_drop_jj > 0:
                    log.info(
                        "native_tet_smooth_then_drop",
                        moved=int(n_moved), dropped=int(n_drop_jj),
                    )
        except Exception as exc:
            log.debug("native_tet_smooth_then_drop_skipped", reason=str(exc))

    # Round 73-74: extreme sliver 제거 (파라미터 노출). V5 — surface-aware revert.
    if enable_phase_a:
        try:
            from core.generator.native_tet.validate import drop_extreme_slivers
            from core.generator.native_tet.plane_coverage import (
                plane_coverage as _pc_pre,
            )

            prev_tets_drop = final_tets.copy()
            try:
                prev_area_drop = float(
                    _pc_pre(V, F, final_pts, prev_tets_drop).area_coverage
                )
            except Exception:
                prev_area_drop = -1.0

            final_tets, n_drop = drop_extreme_slivers(
                final_pts, final_tets,
                min_dihedral_deg=float(sliver_drop_min_dihedral_deg),
                min_aspect_regular=float(sliver_drop_max_aspect),
            )

            try:
                new_area_drop = float(
                    _pc_pre(V, F, final_pts, final_tets).area_coverage
                )
            except Exception:
                new_area_drop = prev_area_drop
            if (
                prev_area_drop > 0
                and new_area_drop + 0.05 < prev_area_drop
            ):
                log.warning(
                    "native_tet_drop_slivers_revert",
                    prev_area=round(prev_area_drop, 3),
                    new_area=round(new_area_drop, 3),
                )
                final_tets = prev_tets_drop
            elif n_drop > 0:
                log.info("native_tet_drop_slivers", dropped=n_drop)
        except Exception as exc:
            log.debug("native_tet_drop_slivers_skipped", reason=str(exc))

    _prog("write", 0.9, n_tets=int(final_tets.shape[0]))

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

    # beta830: final quality snapshot.
    final_quality = None
    try:
        from core.generator.native_tet.quality import snapshot as _qsnap

        final_quality = _qsnap(final_pts, final_tets)
    except Exception:
        pass

    # W3 (beta1600) — Best-of-two: final vs base+inside 후보 중 점수 최대 채택.
    # 점수 = area*0.5 + cdt_chain*0.3 + mq*0.2 (단순 가중).
    try:
        from core.generator.native_tet.cdt_check import (
            check_edge_recovery_chained, cdt_ratio as _cdt_ratio_w3,
        )
        from core.generator.native_tet.quality import snapshot as _qsnap_w3

        def _score(p_arr, t_arr):
            try:
                pc_v = float(_pc_base(V, F, p_arr, t_arr).area_coverage)
            except Exception:
                pc_v = 0.0
            try:
                cdt_v = float(_cdt_ratio_w3(check_edge_recovery_chained(V, F, p_arr, t_arr)))
            except Exception:
                cdt_v = 0.0
            try:
                snap = _qsnap_w3(p_arr, t_arr)
                mq_v = float(getattr(snap, "mean_q", 0.0))
            except Exception:
                mq_v = 0.0
            return (
                float(score_weight_area) * pc_v
                + float(score_weight_cdt) * cdt_v
                + float(score_weight_mq) * mq_v
            ), (pc_v, cdt_v, mq_v)

        final_score, final_metrics = _score(final_pts, final_tets)

        # 후보 1: base + inside winding filter (+ surface-vertex tet 강제 keep).
        base_centroids = base_pts_for_fallback[base_tets_for_fallback].mean(axis=1)
        base_inside = _inside_winding_number(base_centroids, V, F)
        try:
            n_surface_in = int(V.shape[0])
            on_surface = (base_tets_for_fallback < n_surface_in).all(axis=1)
            base_inside = base_inside | on_surface
        except Exception:
            pass
        base_filt_tets = base_tets_for_fallback[base_inside]
        base_score, base_metrics = _score(base_pts_for_fallback, base_filt_tets)

        # W2 (beta1620) — 후보 2: V-only Delaunay (입력 vertex 만 사용).
        v_only_score = -1.0
        v_only_pts = None
        v_only_tets = None
        try:
            from scipy.spatial import Delaunay as _D_v
            if V.shape[0] >= 4:
                Dv = _D_v(V)
                v_only_tets_raw = np.asarray(Dv.simplices, dtype=np.int64)
                v_cen = V[v_only_tets_raw].mean(axis=1)
                v_ins = _inside_winding_number(v_cen, V, F)
                v_on_surf = (v_only_tets_raw < V.shape[0]).all(axis=1)
                v_keep = v_ins | v_on_surf
                v_only_tets = v_only_tets_raw[v_keep]
                v_only_pts = V.copy()
                v_only_score, v_only_metrics = _score(v_only_pts, v_only_tets)
        except Exception:
            pass

        # W5 (beta1630) — V-only 후보 + interior point 추가 + quality smoothing.
        # cube/cyl 의 mean_q 0.22 → 0.30+ 향상으로 grade B → A 도달.
        v_only_smoothed_score = -1.0
        v_only_smoothed_pts = None
        v_only_smoothed_tets = None
        try:
            if v_only_pts is not None and v_only_tets is not None:
                # bbox 중심에 interior point 1개 추가 → re-Delaunay → smooth.
                bbox_min_v = V.min(axis=0)
                bbox_max_v = V.max(axis=0)
                center = 0.5 * (bbox_min_v + bbox_max_v)
                # 8 corner 중간 정점들 추가 (총 9 추가).
                ext_pts = [center.tolist()]
                for off in [
                    [0.4, 0, 0], [-0.4, 0, 0],
                    [0, 0.4, 0], [0, -0.4, 0],
                    [0, 0, 0.4], [0, 0, -0.4],
                ]:
                    p = center + np.asarray(off) * (bbox_max_v - bbox_min_v)
                    ext_pts.append(p.tolist())

                # OO1 (beta1920) — hard mesh (V > 500) 에 internal seed grid
                # 추가. surface vertex 비율 ↓ → 4-vertex sliver tet 격감.
                # n_internal ≈ V × 0.15 (예: V=11k → 1650 internal).
                try:
                    nv_in = int(V.shape[0])
                    if nv_in > 500:
                        # bbox 내부 균일 grid: edge-cube 분할.
                        n_internal_target = max(50, int(nv_in * 0.15))
                        # n^3 ≥ n_internal_target → n = ceil(cbrt).
                        n_axis = int(np.ceil(n_internal_target ** (1.0 / 3.0)))
                        # 0.05 ~ 0.95 range (boundary 회피).
                        ts = np.linspace(0.08, 0.92, n_axis)
                        gx, gy, gz = np.meshgrid(ts, ts, ts, indexing="ij")
                        grid_uvw = np.column_stack([gx.ravel(), gy.ravel(), gz.ravel()])
                        grid_pts = bbox_min_v + grid_uvw * (bbox_max_v - bbox_min_v)
                        # 작은 jitter 추가 (Delaunay degeneracy 회피).
                        rng = np.random.default_rng(42)
                        jitter = (rng.random(grid_pts.shape) - 0.5) * 1e-6 * float(np.linalg.norm(bbox_max_v - bbox_min_v))
                        grid_pts = grid_pts + jitter
                        ext_pts.extend(grid_pts.tolist())
                except Exception:
                    pass
                aug_pts = np.vstack([V, np.asarray(ext_pts)])
                # winding inside 한 점만 keep.
                inside_aug = _inside_winding_number(aug_pts[V.shape[0]:], V, F)
                aug_pts = np.vstack([V, aug_pts[V.shape[0]:][inside_aug]])
                from scipy.spatial import Delaunay as _D_aug
                Daug = _D_aug(aug_pts)
                aug_tets_raw = np.asarray(Daug.simplices, dtype=np.int64)
                aug_cen = aug_pts[aug_tets_raw].mean(axis=1)
                aug_ins = _inside_winding_number(aug_cen, V, F)
                aug_on_surf = (aug_tets_raw < V.shape[0]).all(axis=1)
                aug_keep = aug_ins | aug_on_surf
                aug_tets = aug_tets_raw[aug_keep]

                # AMIPS analytic 으로 quality smoothing (interior 만).
                try:
                    from core.generator.native_tet.amips import (
                        smooth_amips_analytic,
                    )
                    locked_v = np.arange(V.shape[0], dtype=np.int64)
                    _, aug_pts_sm = smooth_amips_analytic(
                        aug_pts, aug_tets,
                        locked_vertex_ids=locked_v,
                        n_iter=3, alpha=1.0,
                    )
                    aug_pts = aug_pts_sm
                except Exception:
                    pass

                v_only_smoothed_pts = aug_pts
                v_only_smoothed_tets = aug_tets
                v_only_smoothed_score, _ = _score(aug_pts, aug_tets)
        except Exception:
            pass

        log.info(
            "native_tet_best_of_candidates",
            final_score=round(final_score, 3),
            final_metrics=tuple(round(x, 3) for x in final_metrics),
            base_score=round(base_score, 3),
            base_metrics=tuple(round(x, 3) for x in base_metrics),
            v_only_score=round(v_only_score, 3) if v_only_score >= 0 else -1,
        )

        # 3 후보 중 최고 score.
        best_label = "final"
        best_score = final_score
        best_pts = final_pts
        best_tets = final_tets
        if base_score > best_score + float(prefer_base_threshold):
            best_label = "base"
            best_score = base_score
            best_pts = base_pts_for_fallback
            best_tets = base_filt_tets
        if v_only_score > best_score + float(prefer_base_threshold):
            best_label = "v_only"
            best_score = v_only_score
            best_pts = v_only_pts
            best_tets = v_only_tets
        if v_only_smoothed_score > best_score + float(prefer_base_threshold):
            best_label = "v_only_smoothed"
            best_score = v_only_smoothed_score
            best_pts = v_only_smoothed_pts
            best_tets = v_only_smoothed_tets

        if best_label != "final":
            log.warning(
                "native_tet_best_of_picks_alt",
                pick=best_label,
                score=round(best_score, 3),
                final_score=round(final_score, 3),
            )
            final_pts = best_pts
            final_tets = best_tets
    except Exception as exc:
        log.debug("native_tet_best_of_skipped", reason=str(exc))

    # NN1 (beta1910) — sliver post-removal pass: 짧은 edge collapse 로
    # sliver tet 직접 제거. fTetWild §3.4 의 sliver removal 핵심 단계.
    # mean_q < 0.20 이면 1 회 적용. surface vertex lock.
    try:
        from core.generator.native_tet.quality import snapshot as _qsnap_pre
        pre_q = _qsnap_pre(final_pts, final_tets)
        if float(pre_q.mean_q) < 0.20 and final_tets.shape[0] > 100:
            from core.generator.native_tet.local_ops import collapse_short_edges
            n_v_pre = int(final_pts.shape[0])
            n_t_pre = int(final_tets.shape[0])
            # surface vertex lock — surface_new_ids2 가 일부 경로에서 미정의.
            try:
                lock_ids = surface_new_ids2  # type: ignore[name-defined]
            except NameError:
                # fallback: 입력 표면 vertex (V) 의 첫 n_surface_in 개 ID lock.
                lock_ids = np.arange(int(n_surface_in), dtype=np.int64)
            # YY1 (beta2000) — hard input (mq < 0.15) 일 땐 ratio 0.85 로
            # 더 적극적 collapse → sliver 더 격감.
            collapse_ratio = 0.85 if float(pre_q.mean_q) < 0.15 else 0.7
            new_pts, new_tets, n_c = collapse_short_edges(
                final_pts, final_tets,
                target_edge=float(target_edge_length),
                ratio=collapse_ratio,
                locked_vertices=lock_ids,
                max_collapses=4000,
            )
            if n_c > 0 and new_tets.shape[0] > 50:
                post_q = _qsnap_pre(new_pts, new_tets)
                # mean_q 가 단조 향상한 경우만 수용.
                if float(post_q.mean_q) > float(pre_q.mean_q) * 0.99:
                    final_pts = new_pts
                    final_tets = new_tets
                    log.info(
                        "native_tet_sliver_post_collapse",
                        n_collapsed=int(n_c),
                        v_before=n_v_pre, v_after=int(new_pts.shape[0]),
                        t_before=n_t_pre, t_after=int(new_tets.shape[0]),
                        mq_before=round(float(pre_q.mean_q), 3),
                        mq_after=round(float(post_q.mean_q), 3),
                    )
    except Exception as exc:
        log.debug("native_tet_sliver_post_skipped", reason=str(exc))

    # RR1 (beta1950) — 2-3 face flip pass: connectivity-only sliver 깨기.
    # vertex 위치 변경 X (surface 보존), tet 재구성으로 min Q 향상.
    try:
        from core.generator.native_tet.quality import snapshot as _qsnap_flip
        pre_q_f = _qsnap_flip(final_pts, final_tets)
        if float(pre_q_f.mean_q) < 0.25 and final_tets.shape[0] > 100:
            from core.generator.native_tet.flip import (
                flip_faces_23, flip_edges_32, flip_edges_44,
            )
            t_before = int(final_tets.shape[0])
            # 2-3 face flip.
            new_tets_f, n_flips = flip_faces_23(
                final_pts, final_tets,
                min_quality_improvement=1e-3,
                max_flips=3000,
            )
            if n_flips > 0 and new_tets_f.shape[0] > 50:
                post_q_f = _qsnap_flip(final_pts, new_tets_f)
                if float(post_q_f.mean_q) >= float(pre_q_f.mean_q) * 0.99:
                    final_tets = new_tets_f
                    log.info(
                        "native_tet_flip_23",
                        n_flips=int(n_flips),
                        t_before=t_before, t_after=int(new_tets_f.shape[0]),
                        mq_before=round(float(pre_q_f.mean_q), 3),
                        mq_after=round(float(post_q_f.mean_q), 3),
                    )
            # SS1 (beta1960) — 3-2 edge flip pass: 추가 sliver 타입 깨기.
            try:
                pre_q_e = _qsnap_flip(final_pts, final_tets)
                t_pre_e = int(final_tets.shape[0])
                new_tets_e, n_e = flip_edges_32(
                    final_pts, final_tets,
                    min_quality_improvement=1e-3,
                    max_flips=2000,
                )
                if n_e > 0 and new_tets_e.shape[0] > 50:
                    post_q_e = _qsnap_flip(final_pts, new_tets_e)
                    if float(post_q_e.mean_q) >= float(pre_q_e.mean_q) * 0.99:
                        final_tets = new_tets_e
                        log.info(
                            "native_tet_flip_32",
                            n_flips=int(n_e),
                            t_before=t_pre_e, t_after=int(new_tets_e.shape[0]),
                            mq_before=round(float(pre_q_e.mean_q), 3),
                            mq_after=round(float(post_q_e.mean_q), 3),
                        )
            except Exception as exc:
                log.debug("native_tet_flip_32_skipped", reason=str(exc))
            # TT1 (beta1970) — 4-4 edge flip: 내부 edge ring 재배치.
            try:
                pre_q_44 = _qsnap_flip(final_pts, final_tets)
                t_pre_44 = int(final_tets.shape[0])
                new_tets_44, n_44 = flip_edges_44(
                    final_pts, final_tets,
                    min_quality_improvement=1e-3,
                    max_flips=2000,
                )
                if n_44 > 0 and new_tets_44.shape[0] > 50:
                    post_q_44 = _qsnap_flip(final_pts, new_tets_44)
                    if float(post_q_44.mean_q) >= float(pre_q_44.mean_q) * 0.99:
                        final_tets = new_tets_44
                        log.info(
                            "native_tet_flip_44",
                            n_flips=int(n_44),
                            t_before=t_pre_44, t_after=int(new_tets_44.shape[0]),
                            mq_before=round(float(pre_q_44.mean_q), 3),
                            mq_after=round(float(post_q_44.mean_q), 3),
                        )
            except Exception as exc:
                log.debug("native_tet_flip_44_skipped", reason=str(exc))

            # UU1 (beta1980) — 2nd flip cycle: 첫 cycle 의 잔여 sliver 를
            # 다시 노출시켜 추가 mq 향상. flip_23 → flip_32 1회 더.
            try:
                pre_q_c2 = _qsnap_flip(final_pts, final_tets)
                if float(pre_q_c2.mean_q) < 0.30:
                    new_tets_c2, n_c2 = flip_faces_23(
                        final_pts, final_tets,
                        min_quality_improvement=1e-3, max_flips=2000,
                    )
                    if n_c2 > 0 and new_tets_c2.shape[0] > 50:
                        post_q_c2 = _qsnap_flip(final_pts, new_tets_c2)
                        if float(post_q_c2.mean_q) >= float(pre_q_c2.mean_q) * 0.99:
                            final_tets = new_tets_c2
                            log.info("native_tet_flip_23_c2", n_flips=int(n_c2),
                                     mq_before=round(float(pre_q_c2.mean_q), 3),
                                     mq_after=round(float(post_q_c2.mean_q), 3))
                    pre_q_c2b = _qsnap_flip(final_pts, final_tets)
                    new_tets_c2b, n_c2b = flip_edges_32(
                        final_pts, final_tets,
                        min_quality_improvement=1e-3, max_flips=1500,
                    )
                    if n_c2b > 0 and new_tets_c2b.shape[0] > 50:
                        post_q_c2b = _qsnap_flip(final_pts, new_tets_c2b)
                        if float(post_q_c2b.mean_q) >= float(pre_q_c2b.mean_q) * 0.99:
                            final_tets = new_tets_c2b
                            log.info("native_tet_flip_32_c2", n_flips=int(n_c2b),
                                     mq_before=round(float(pre_q_c2b.mean_q), 3),
                                     mq_after=round(float(post_q_c2b.mean_q), 3))
            except Exception as exc:
                log.debug("native_tet_flip_cycle2_skipped", reason=str(exc))

            # AAA1 (beta2020) — flip cycle 3: 추가 잔여 sliver 노출.
            try:
                pre_q_c3 = _qsnap_flip(final_pts, final_tets)
                if float(pre_q_c3.mean_q) < 0.30:
                    new_tets_c3, n_c3 = flip_faces_23(
                        final_pts, final_tets,
                        min_quality_improvement=1e-3, max_flips=1500,
                    )
                    if n_c3 > 0 and new_tets_c3.shape[0] > 50:
                        post_q_c3 = _qsnap_flip(final_pts, new_tets_c3)
                        if float(post_q_c3.mean_q) >= float(pre_q_c3.mean_q) * 0.99:
                            final_tets = new_tets_c3
                            log.info("native_tet_flip_23_c3", n_flips=int(n_c3),
                                     mq_before=round(float(pre_q_c3.mean_q), 3),
                                     mq_after=round(float(post_q_c3.mean_q), 3))
                    # BBB1 (beta2030) — cycle 3 의 flip_32 + cycle 2 의 flip_44.
                    pre_q_c3b = _qsnap_flip(final_pts, final_tets)
                    new_tets_c3b, n_c3b = flip_edges_32(
                        final_pts, final_tets,
                        min_quality_improvement=1e-3, max_flips=1000,
                    )
                    if n_c3b > 0 and new_tets_c3b.shape[0] > 50:
                        post_q_c3b = _qsnap_flip(final_pts, new_tets_c3b)
                        if float(post_q_c3b.mean_q) >= float(pre_q_c3b.mean_q) * 0.99:
                            final_tets = new_tets_c3b
                            log.info("native_tet_flip_32_c3", n_flips=int(n_c3b),
                                     mq_before=round(float(pre_q_c3b.mean_q), 3),
                                     mq_after=round(float(post_q_c3b.mean_q), 3))
                    pre_q_44b = _qsnap_flip(final_pts, final_tets)
                    new_tets_44b, n_44b = flip_edges_44(
                        final_pts, final_tets,
                        min_quality_improvement=1e-3, max_flips=1000,
                    )
                    if n_44b > 0 and new_tets_44b.shape[0] > 50:
                        post_q_44b = _qsnap_flip(final_pts, new_tets_44b)
                        if float(post_q_44b.mean_q) >= float(pre_q_44b.mean_q) * 0.99:
                            final_tets = new_tets_44b
                            log.info("native_tet_flip_44_c2", n_flips=int(n_44b),
                                     mq_before=round(float(pre_q_44b.mean_q), 3),
                                     mq_after=round(float(post_q_44b.mean_q), 3))
            except Exception as exc:
                log.debug("native_tet_flip_cycle3_skipped", reason=str(exc))

            # VV1 (beta1990) — flip 2-cycle 후 AMIPS interior smoothing 1 회
            # 더. sliver 깬 새 connectivity 에서 vertex 위치 미세 조정으로
            # mq 추가 향상.
            try:
                pre_q_v = _qsnap_flip(final_pts, final_tets)
                if float(pre_q_v.mean_q) < 0.30:
                    from core.generator.native_tet.amips import smooth_amips_analytic
                    try:
                        lock_ids_v = surface_new_ids2  # type: ignore[name-defined]
                    except NameError:
                        lock_ids_v = np.arange(int(n_surface_in), dtype=np.int64)
                    ar_v, new_pts_v = smooth_amips_analytic(
                        final_pts, final_tets,
                        locked_vertex_ids=lock_ids_v,
                        n_iter=1, alpha=1.0,
                    )
                    if ar_v.energy_after <= ar_v.energy_before * 1.05:
                        post_q_v = _qsnap_flip(new_pts_v, final_tets)
                        if float(post_q_v.mean_q) >= float(pre_q_v.mean_q) * 0.99:
                            final_pts = new_pts_v
                            log.info("native_tet_amips_post_flip",
                                     mq_before=round(float(pre_q_v.mean_q), 3),
                                     mq_after=round(float(post_q_v.mean_q), 3))
            except Exception as exc:
                log.debug("native_tet_amips_post_flip_skipped", reason=str(exc))
    except Exception as exc:
        log.debug("native_tet_flip_23_skipped", reason=str(exc))

    # DDD1 (beta2040) — BSP triangle insertion pass: missing surface triangle
    # 강제 회복. fTetWild §3.3 의 핵심 envelope 정합 단계.
    # missing_face_indices 직접 계산 (input F 중 final_tets 안에 없는 face).
    try:
        from core.generator.native_tet.bsp_insert import bsp_insert_triangles_batch as _bsp_batch
        # final_tets 의 모든 canonical face set.
        if final_tets.size > 0 and F.size > 0:
            tf = np.stack(
                [final_tets[:, [0, 1, 2]], final_tets[:, [0, 1, 3]],
                 final_tets[:, [0, 2, 3]], final_tets[:, [1, 2, 3]]], axis=1,
            ).reshape(-1, 3)
            tf = np.sort(tf, axis=1)
            tf_set = {(int(a), int(b), int(c)) for a, b, c in tf}
            # input F 의 triangle (input vertex indexing — final_pts 의 처음 n_surface_in 와 매칭).
            n_surf_v = min(int(n_surface_in), int(final_pts.shape[0]))
            Fs = np.sort(F, axis=1)
            missing = []
            for i in range(F.shape[0]):
                a, b, c = int(Fs[i, 0]), int(Fs[i, 1]), int(Fs[i, 2])
                if a >= n_surf_v or b >= n_surf_v or c >= n_surf_v:
                    continue
                if (a, b, c) not in tf_set:
                    missing.append(i)
        else:
            missing = []
        if len(missing) > 0 and len(missing) < 500:
            n_v_pre_b = int(final_pts.shape[0])
            n_t_pre_b = int(final_tets.shape[0])
            new_pts_b, new_tets_b, bsp_r = _bsp_batch(
                final_pts, final_tets, V, F,
                np.asarray(missing, dtype=np.int64),
                max_inserts=300,
            )
            n_recovered = int(bsp_r.n_missing_before - bsp_r.n_missing_after)
            if (
                new_tets_b.shape[0] > 50
                and n_recovered > 0
            ):
                final_pts = new_pts_b
                final_tets = new_tets_b
                log.info(
                    "native_tet_bsp_insert",
                    missing_before=int(bsp_r.n_missing_before),
                    missing_after=int(bsp_r.n_missing_after),
                    n_recovered=int(n_recovered),
                    n_inserted_points=int(bsp_r.n_inserted_points),
                    v_before=n_v_pre_b, v_after=int(new_pts_b.shape[0]),
                    t_before=n_t_pre_b, t_after=int(new_tets_b.shape[0]),
                )
    except Exception as exc:
        log.debug("native_tet_bsp_insert_skipped", reason=str(exc))

    # beta1530 (V3) — 외부 tet 제거: 입력 surface 외부에 centroid 가 있는 tet drop.
    if enable_boundary_clip:
        try:
            from core.generator.native_tet.boundary_clip import (
                clip_to_input_surface,
            )
            final_pts, final_tets, clip_info = clip_to_input_surface(
                final_pts, final_tets, V, F,
                inside_threshold=float(boundary_clip_threshold),
            )
            log.info(
                "native_tet_boundary_clip",
                dropped=clip_info.n_dropped,
                tets_after=clip_info.n_tets_after,
                face_ratio=round(clip_info.face_ratio_after, 3),
            )
        except Exception as exc:
            log.debug("native_tet_boundary_clip_skipped", reason=str(exc))

    # beta1460 (T2) — 입력 surface vertex 가 결과 mesh 의 같은 좌표를 유지하는지
    # 강제 보정. final_pts 의 [0:n_surface] 가 V 와 일치해야 hausdorff 측정이
    # 의미 있음. 일부 path (Phase A smooth) 가 surface vertex 위치를 살짝 옮길
    # 수 있으니 명시적으로 복원.
    try:
        n_surface_in = int(V.shape[0])
        if (
            final_pts.shape[0] >= n_surface_in
            and not np.allclose(final_pts[:n_surface_in], V, atol=1e-9)
        ):
            log.info(
                "native_tet_surface_snap_restore",
                max_diff=float(
                    np.linalg.norm(final_pts[:n_surface_in] - V, axis=1).max()
                ),
            )
            final_pts = final_pts.copy()
            final_pts[:n_surface_in] = V
    except Exception:
        pass

    # beta1420 (Q4) — 통합 PASS gate 산출 (cdt_ratio + hausdorff + quality).
    grade = "?"
    cdt_ratio_val = -1.0
    cdt_face_ratio_val = -1.0
    plane_cov_val = -1.0
    plane_area_cov_val = -1.0
    haus_rel = -1.0
    try:
        from core.generator.native_tet.cdt_check import (
            check_edge_recovery, check_edge_recovery_chained,
            cdt_ratio as _cdt_ratio, cdt_face_ratio as _cdt_face_ratio,
        )
        from core.generator.native_tet.hausdorff import hausdorff_vs_input
        from core.generator.native_tet.plane_coverage import plane_coverage

        # T1 — chain-based 검사 (subdivided edge 도 회복으로 인정).
        try:
            cdt_r = check_edge_recovery_chained(V, F, final_pts, final_tets)
        except Exception:
            cdt_r = check_edge_recovery(F, final_tets)
        cdt_ratio_val = float(_cdt_ratio(cdt_r))
        # face ratio (strict).
        cdt_strict = check_edge_recovery(F, final_tets)
        cdt_face_ratio_val = float(_cdt_face_ratio(cdt_strict))
        # V1 — plane coverage (fTetWild-style).
        try:
            pc = plane_coverage(V, F, final_pts, final_tets)
            plane_cov_val = float(pc.plane_coverage)
            plane_area_cov_val = float(pc.area_coverage)
        except Exception:
            pass

        haus = hausdorff_vs_input(
            V, F, final_pts, final_tets, n_samples_per_tri=2,
        )
        bbox = V.max(axis=0) - V.min(axis=0)
        diag = float(np.linalg.norm(bbox)) + 1e-30
        haus_rel = float(haus.h_symmetric / diag)

        # V3 — plane_coverage 가 fTetWild 정합 메트릭. A 는 plane_coverage 우선.
        mean_q = float(getattr(final_quality, "mean_q", 0.0)) if final_quality else 0.0
        if (
            plane_cov_val >= 0.95
            and plane_area_cov_val >= 0.95
            and mean_q >= 0.25
        ):
            grade = "A"
        elif (
            plane_cov_val >= 0.8
            and plane_area_cov_val >= 0.8
            and mean_q >= 0.18
        ):
            grade = "B"
        elif (
            (plane_cov_val >= 0.5 or cdt_ratio_val >= 0.5)
            and mean_q >= 0.10
        ):
            grade = "C"
        else:
            grade = "D"
        log.info(
            "native_tet_pass_gate",
            grade=grade,
            cdt_ratio=round(cdt_ratio_val, 3),
            cdt_face_ratio=round(cdt_face_ratio_val, 3),
            plane_coverage=round(plane_cov_val, 3),
            plane_area_coverage=round(plane_area_cov_val, 3),
            hausdorff_rel=round(haus_rel, 5),
            mean_q=round(mean_q, 3),
        )
    except Exception as exc:
        log.debug("native_tet_pass_gate_skipped", reason=str(exc))

    _prog("done", 1.0, n_cells=n_cells, n_points=n_points, elapsed=elapsed)

    # beta1140 (R180) — 개발자용 debug_info dump + input-check warnings 전파.
    debug_info: dict = {
        "seed_grid": int(grid.shape[0]),
        "target_edge": float(target_edge_length),
        "n_final_tets": int(final_tets.shape[0]),
        "n_final_points": int(final_pts.shape[0]),
    }
    warnings_list: list[str] = []
    try:
        if chk is not None and chk.warnings:
            warnings_list.extend(chk.warnings)
    except Exception:
        pass

    return NativeTetResult(
        success=True, elapsed=elapsed,
        n_cells=n_cells, n_points=n_points,
        message=(
            f"native_tet OK — cells={n_cells}, points={n_points}, "
            f"seed_grid={grid.shape[0]}, target_edge={target_edge_length:.4g}"
        ),
        tet_points=final_pts, tets=final_tets,
        quality=final_quality,
        warnings=warnings_list or None,
        debug_info=debug_info,
        quality_grade=grade,
        cdt_ratio=float(cdt_ratio_val),
        cdt_face_ratio=float(cdt_face_ratio_val),
        plane_coverage=float(plane_cov_val),
        plane_area_coverage=float(plane_area_cov_val),
        hausdorff_relative=float(haus_rel),
    )
