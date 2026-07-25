"""P1 — CDT (Constrained Delaunay) boundary recovery 통합 루틴.

현재 한계 (2026-04-25 기준)
    cube 같은 대각선 toplogy edge 는 B-W insert 만으로 회복이 어렵다 —
    삽입 후보점이 기존 cavity 바깥에 있으면 모든 시도가 revert. 진짜 해결은
    (a) 2-3 flip 기반 edge recovery (edge_flip_recovery.recover_edges_via_flip),
    (b) cavity re-triangulation (R95) 에서 surface 정렬 대각선 선택.
    본 모듈은 두 전략의 뼈대를 제공하고, 악화 방지 (revert) 를 엄격히 보장한다.



기존 기능 (edge_recovery.propose_edge_midpoints, recursive_midpoint,
bowyer_watson_insert, surface_snap) 를 한 cycle 루프로 묶어 실제 recovery
ratio 가 수렴할 때까지 반복한다.

cycle
    1) check_edge_recovery → missing_edges.
    2) propose_recursive_midpoint(depth=cycle) → 후보 점.
    3) bowyer_watson_insert(protected_edges=surface_edges) 로 삽입.
    4) 결과가 악화되면 revert, 그렇지 않으면 반복.
    5) 최종 surface vertex 를 BVH snap 으로 재-projection (R99).

본 모듈은 MVP — 완전한 CDT 이론 (Shewchuk, Si) 의 근사 파이프라인.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class CDTRecoveryResult:
    cycles: int
    n_edges_before: int
    n_edges_after: int
    ratio_before: float
    ratio_after: float
    n_inserted_points: int
    reverted: int


def _surface_edge_set(F: np.ndarray) -> set[tuple[int, int]]:
    """C-PERF-28 / beta2479 — vectorize via lexsort+pack-unique."""
    if F.size == 0:
        return set()
    src = F[:, [0, 1, 2]].reshape(-1).astype(np.int64)
    dst = F[:, [1, 2, 0]].reshape(-1).astype(np.int64)
    u = np.minimum(src, dst); v = np.maximum(src, dst)
    n_max = int(F.max()) + 1
    pack = u * n_max + v
    uniq = np.unique(pack)
    return set(zip((uniq // n_max).tolist(), (uniq % n_max).tolist()))


def run_cdt_recovery(
    pts: np.ndarray, tets: np.ndarray,
    V_surf: np.ndarray, F_surf: np.ndarray,
    *,
    max_cycles: int = 4,
    points_budget: int = 200,
    snap_final: bool = True,
) -> tuple[np.ndarray, np.ndarray, CDTRecoveryResult]:
    """cycle-driven CDT recovery.

    각 cycle 은 (i) missing edge 감지 → (ii) recursive midpoint 후보 →
    (iii) constrained B-W insert → (iv) ratio 체크 + revert.
    """
    from core.generator.native_tet.cdt_check import (
        check_edge_recovery, cdt_ratio,
    )
    from core.generator.native_tet.edge_recovery import (
        propose_recursive_midpoint,
    )
    from core.generator.native_tet.bowyer_watson import bowyer_watson_insert

    pts = np.asarray(pts, dtype=np.float64).copy()
    tets = np.asarray(tets, dtype=np.int64).copy()
    F_surf = np.asarray(F_surf, dtype=np.int64)

    protected = _surface_edge_set(F_surf)

    r0 = check_edge_recovery(F_surf, tets)
    n_before = r0.n_missing
    ratio0 = cdt_ratio(r0)
    if n_before == 0:
        return pts, tets, CDTRecoveryResult(
            0, 0, 0, ratio0, ratio0, 0, 0,
        )

    n_inserted_total = 0
    reverted = 0
    cycles_done = 0

    # (a) flip-기반 edge recovery 1회 — 대각선 topology 회복.
    try:
        from core.generator.native_tet.edge_flip_recovery import (
            recover_edges_via_flip,
        )
        r_cur = check_edge_recovery(F_surf, tets)
        if r_cur.n_missing > 0:
            pts_before = pts.copy(); tets_before = tets.copy()
            out = recover_edges_via_flip(
                pts, tets, r_cur.missing_edges,
            )
            if isinstance(out, tuple):
                tets_new = out[0] if len(out) >= 1 else tets
            else:
                tets_new = out
            r_try = check_edge_recovery(F_surf, tets_new)
            if r_try.n_missing < r_cur.n_missing:
                tets = tets_new
                cycles_done = 1
            else:
                pts = pts_before; tets = tets_before
                reverted += 1
    except Exception:
        pass

    # (a2) Q2 cavity re-triangulation — surface-aligned diagonal 선택.
    try:
        from core.generator.native_tet.cavity_retri import (
            cavity_retri_for_missing_edges,
        )
        r_cur = check_edge_recovery(F_surf, tets)
        if r_cur.n_missing > 0:
            tets_before = tets.copy()
            tets_new, retri_info = cavity_retri_for_missing_edges(
                pts, tets, r_cur.missing_edges,
            )
            r_try = check_edge_recovery(F_surf, tets_new)
            if r_try.n_missing < r_cur.n_missing:
                tets = tets_new
                cycles_done = max(cycles_done, 1)
            elif retri_info.n_recovered > 0:
                # 같거나 더 많아지면 revert (보수).
                tets = tets_before
                reverted += 1
    except Exception:
        pass

    # (b) insertion-기반 cycle 반복.
    #
    # PERF (dual_torus plateau) — profiling showed this loop dominating
    # run_cdt_recovery's cost (bowyer_watson_insert against a large cavity
    # is ~13-15s/cycle here) while producing inserted=0 for every cycle on
    # structurally-unrecoverable geometry (coplanar flat-on-surface wedges,
    # see tests/test_native_tet_dual_torus_limit.py). Two fixes:
    #   1) Plateau exit — once a cycle reverts (net-zero insertion), `tets`
    #      is restored to exactly the state it was in before that cycle, so
    #      the missing-edge set cannot have changed either. Cache that
    #      check_edge_recovery result across reverted cycles instead of
    #      recomputing the full edge/cavity search from scratch every time;
    #      only invalidate the cache when a cycle actually keeps its insert.
    #   2) After N consecutive zero-progress (reverted) cycles, stop
    #      retrying rather than burning the rest of max_cycles — a fixed
    #      candidate mechanism repeating on an unchanged mesh is very
    #      unlikely to suddenly start succeeding.
    _PLATEAU_N = 3
    _consec_zero = 0
    _cached_check: object | None = None
    for cycle in range(1, int(max_cycles) + 1):
        if _cached_check is not None:
            r_cur = _cached_check
        else:
            r_cur = check_edge_recovery(F_surf, tets)
            _cached_check = r_cur
        if r_cur.n_missing == 0:
            break
        prop = propose_recursive_midpoint(
            V_surf, r_cur.missing_edges,
            max_depth=cycle, max_points=points_budget,
        )
        if prop.new_points.shape[0] == 0:
            break

        pts_before = pts.copy()
        tets_before = tets.copy()

        new_pts, new_tets, _ins = bowyer_watson_insert(
            pts, tets, prop.new_points,
            protected_edges=protected,
        )
        if new_tets.shape[0] == 0:
            # tets 불변 — 캐시된 r_cur 는 다음 cycle 에도 여전히 유효.
            reverted += 1
            _consec_zero += 1
            if _consec_zero >= _PLATEAU_N:
                break
            continue

        r_after = check_edge_recovery(F_surf, new_tets)
        if r_after.n_missing >= r_cur.n_missing:
            # 악화: revert. tets 가 revert 전 상태로 그대로 복원되므로
            # 캐시된 r_cur 는 계속 유효 (무효화 불필요).
            pts = pts_before
            tets = tets_before
            reverted += 1
            _consec_zero += 1
            if _consec_zero >= _PLATEAU_N:
                break
            continue

        pts = new_pts
        tets = new_tets
        n_inserted_total += int(prop.new_points.shape[0])
        cycles_done = cycle
        _consec_zero = 0
        _cached_check = None  # tets 실제 변경 — 캐시 무효화, 다음 cycle 재계산.

    # R99 — 최종 surface vertex 재-projection.
    if snap_final and V_surf.shape[0] > 0:
        try:
            from core.utils.aabb import TriangleBVH

            bvh = TriangleBVH.build(V_surf, F_surf)
            surf_ids = np.arange(min(V_surf.shape[0], pts.shape[0]), dtype=np.int64)
            snapped, _ = bvh.snap_to_surface(pts[surf_ids])
            pts[surf_ids] = snapped
        except Exception:
            pass

    r_final = check_edge_recovery(F_surf, tets)
    return pts, tets, CDTRecoveryResult(
        cycles=int(cycles_done),
        n_edges_before=int(n_before),
        n_edges_after=int(r_final.n_missing),
        ratio_before=float(ratio0),
        ratio_after=float(cdt_ratio(r_final)),
        n_inserted_points=int(n_inserted_total),
        reverted=int(reverted),
    )
