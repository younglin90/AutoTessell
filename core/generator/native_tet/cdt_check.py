"""Round 49 — Conformal CDT constraint check.

TetGen (Si 2015) §4 가 보장하는 "boundary recovery" 의 부분 검증. 입력
surface 의 모든 edge 가 tet mesh 에도 edge 로 (혹은 edge 들의 체인으로)
존재하는지 확인.

현 native_tet 은 BSP + B-W 로 triangle recovery 는 수행하지만 edge 레벨
conformal 성을 엄격히 보장하지 않는다. 본 모듈은 검사만 제공하고 이후
라운드에서 missing edge 를 recovery 할 기반이 된다.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class CDTCheckResult:
    n_surface_edges: int
    n_present_as_tet_edges: int
    n_missing: int
    missing_edges: list[tuple[int, int]]   # input surface indexing.
    # beta970 (R94): triangle 회복률.
    n_surface_faces: int = 0
    n_present_as_tet_faces: int = 0
    n_missing_faces: int = 0


def _tet_triangles(tets: np.ndarray) -> set[tuple[int, int, int]]:
    """tet 배열의 모든 face (canonical sorted).

    C-PERF-34 / beta2485 — vectorized via np.unique on packed key.
    """
    tets = np.asarray(tets, dtype=np.int64)
    if tets.size == 0:
        return set()
    faces = np.stack(
        [tets[:, [0, 1, 2]], tets[:, [0, 1, 3]],
         tets[:, [0, 2, 3]], tets[:, [1, 2, 3]]],
        axis=1,
    ).reshape(-1, 3)
    faces = np.sort(faces, axis=1)
    n_max = int(tets.max()) + 1 if tets.size > 0 else 1
    pack = (
        faces[:, 0].astype(np.int64) * (n_max * n_max)
        + faces[:, 1].astype(np.int64) * n_max
        + faces[:, 2].astype(np.int64)
    )
    uniq = np.unique(pack)
    a = (uniq // (n_max * n_max)).tolist()
    b = ((uniq // n_max) % n_max).tolist()
    c = (uniq % n_max).tolist()
    return set(zip(a, b, c))


def _tet_edges(tets: np.ndarray) -> set[tuple[int, int]]:
    """tet 배열의 모든 edge (canonical sorted).

    C-PERF-35 / beta2486 — vectorize via packed-key np.unique.
    """
    tets = np.asarray(tets, dtype=np.int64)
    if tets.size == 0:
        return set()
    pair_idx = np.array(
        [[0, 1], [0, 2], [0, 3], [1, 2], [1, 3], [2, 3]], dtype=np.int64,
    )
    edges = np.stack(
        [tets[:, pair_idx[:, 0]], tets[:, pair_idx[:, 1]]], axis=2,
    ).reshape(-1, 2)
    edges.sort(axis=1)
    n_max = int(tets.max()) + 1
    pack = edges[:, 0].astype(np.int64) * n_max + edges[:, 1].astype(np.int64)
    uniq = np.unique(pack)
    a = (uniq // n_max).tolist()
    b = (uniq % n_max).tolist()
    return set(zip(a, b))


def check_edge_recovery_chained(
    V_surf: np.ndarray, F_surf: np.ndarray,
    pts: np.ndarray, tets: np.ndarray,
    *, snap_tol: float = 1e-6,
) -> "CDTCheckResult":
    """beta1450 (T1) — chain-based edge recovery 검사.

    surface edge (u, v) 가 다음 중 하나면 recovered:
        (a) (u, v) 가 tet edge 로 직접 존재.
        (b) u-v 선분 위에 놓인 다른 점 w 들이 있어, (u, w_1), (w_1, w_2),
            ..., (w_k, v) 가 모두 tet edge 로 존재 (segment chain).

    (b) 검사: u-v 선분 위 (snap_tol 이내) 에 있는 모든 점들의 매개변수 t 를
    정렬, 인접 segment 가 모두 tet edge 면 chain 성립.
    """
    V_surf = np.asarray(V_surf, dtype=np.float64)
    F_surf = np.asarray(F_surf, dtype=np.int64)
    pts = np.asarray(pts, dtype=np.float64)
    tets = np.asarray(tets, dtype=np.int64)

    # 모든 surface edge.  C-PERF-36 / beta2487 — vectorized via packed-key.
    if F_surf.size == 0:
        surf_edges: set[tuple[int, int]] = set()
    else:
        src_se = F_surf[:, [0, 1, 2]].reshape(-1).astype(np.int64)
        dst_se = F_surf[:, [1, 2, 0]].reshape(-1).astype(np.int64)
        u_se = np.minimum(src_se, dst_se)
        v_se = np.maximum(src_se, dst_se)
        n_max_se = int(F_surf.max()) + 1
        pack_se = u_se * n_max_se + v_se
        uniq_se = np.unique(pack_se)
        a_se = (uniq_se // n_max_se).tolist()
        b_se = (uniq_se % n_max_se).tolist()
        surf_edges = set(zip(a_se, b_se))

    tet_edges = _tet_edges(tets)

    missing: list[tuple[int, int]] = []
    for (u, v) in surf_edges:
        if (u, v) in tet_edges:
            continue
        # chain 검사: u-v 선분 위 점들 (snap_tol 이내) 의 인덱스 + t 파라미터.
        if pts.shape[0] == 0:
            missing.append((u, v))
            continue
        a = V_surf[u] if u < V_surf.shape[0] else pts[u]
        b = V_surf[v] if v < V_surf.shape[0] else pts[v]
        d = b - a
        d_norm = float(np.linalg.norm(d))
        if d_norm < 1e-30:
            continue
        d_unit = d / d_norm
        rel = pts - a                                       # (N, 3)
        t_vals = rel @ d_unit                               # 매개변수.
        proj = t_vals[:, None] * d_unit + a
        residual = np.linalg.norm(pts - proj, axis=1)
        on_seg = (residual < snap_tol) & (t_vals > -snap_tol) & (t_vals < d_norm + snap_tol)
        if not on_seg.any():
            missing.append((u, v))
            continue
        chain_pts = np.where(on_seg)[0]
        # u, v 자체도 포함 (있으면).
        ts = t_vals[chain_pts]
        order = np.argsort(ts)
        chain_sorted = chain_pts[order]
        # u 가 시작인지 v 가 끝인지 확인 — 정렬된 chain 의 첫/끝이 u/v 와 일치해야.
        first = int(chain_sorted[0])
        last = int(chain_sorted[-1])
        if first != u and first != v:
            missing.append((u, v))
            continue
        if last != u and last != v:
            missing.append((u, v))
            continue
        # 인접 segment 가 모두 tet edge?
        ok = True
        for i in range(len(chain_sorted) - 1):
            p, q = int(chain_sorted[i]), int(chain_sorted[i + 1])
            key = (p, q) if p < q else (q, p)
            if key not in tet_edges:
                ok = False
                break
        if not ok:
            missing.append((u, v))

    n_present = len(surf_edges) - len(missing)
    return CDTCheckResult(
        n_surface_edges=len(surf_edges),
        n_present_as_tet_edges=n_present,
        n_missing=len(missing),
        missing_edges=missing,
    )


def cdt_ratio(result: "CDTCheckResult") -> float:
    """beta1120 (R156) — edge 회복률 (0.0~1.0)."""
    if result.n_surface_edges == 0:
        return 1.0
    return float(result.n_present_as_tet_edges) / float(result.n_surface_edges)


def cdt_face_ratio(result: "CDTCheckResult") -> float:
    """face 회복률 (0.0~1.0)."""
    if result.n_surface_faces == 0:
        return 1.0
    return float(result.n_present_as_tet_faces) / float(result.n_surface_faces)


def missing_edge_report(
    V: np.ndarray, F: np.ndarray, tets: np.ndarray,
) -> list[dict]:
    """beta980 (R100) — 각 missing edge 에 대한 상세 (midpoint/length)."""
    V = np.asarray(V, dtype=np.float64)
    r = check_edge_recovery(F, tets)
    out: list[dict] = []
    for (u, v) in r.missing_edges:
        if u < 0 or v < 0 or u >= V.shape[0] or v >= V.shape[0]:
            continue
        mid = 0.5 * (V[u] + V[v])
        length = float(np.linalg.norm(V[u] - V[v]))
        out.append({
            "u": int(u), "v": int(v),
            "midpoint": mid.tolist(),
            "length": length,
        })
    return out


def check_edge_recovery(
    F: np.ndarray, tets: np.ndarray,
) -> CDTCheckResult:
    """입력 surface F 의 edge 가 tet mesh 에 그대로 존재하는지 검사.

    Args:
        F: (m, 3) surface triangles (tets 와 동일 vertex indexing 기준).
        tets: (T, 4).

    Returns:
        CDTCheckResult.
    """
    F = np.asarray(F, dtype=np.int64)
    if F.size == 0:
        return CDTCheckResult(0, 0, 0, [], 0, 0, 0)
    # surface edge set.  C-PERF-37 / beta2488 — vectorized via packed-key.
    src_se = F[:, [0, 1, 2]].reshape(-1).astype(np.int64)
    dst_se = F[:, [1, 2, 0]].reshape(-1).astype(np.int64)
    u_se = np.minimum(src_se, dst_se)
    v_se = np.maximum(src_se, dst_se)
    n_max_se = int(F.max()) + 1
    pack_se = u_se * n_max_se + v_se
    uniq_se = np.unique(pack_se)
    surf_edges: set[tuple[int, int]] = set(zip(
        (uniq_se // n_max_se).tolist(),
        (uniq_se % n_max_se).tolist(),
    ))

    tet_edges = _tet_edges(tets)

    missing = [e for e in surf_edges if e not in tet_edges]

    # beta970 (R94): face 회복 집계.
    tet_faces = _tet_triangles(tets)
    surf_faces: set[tuple[int, int, int]] = set()
    for ti in range(F.shape[0]):
        tri = sorted((int(F[ti, 0]), int(F[ti, 1]), int(F[ti, 2])))
        surf_faces.add((tri[0], tri[1], tri[2]))
    n_face_present = sum(1 for t in surf_faces if t in tet_faces)
    n_face_missing = len(surf_faces) - n_face_present

    return CDTCheckResult(
        n_surface_edges=len(surf_edges),
        n_present_as_tet_edges=len(surf_edges) - len(missing),
        n_missing=len(missing),
        missing_edges=missing,
        n_surface_faces=len(surf_faces),
        n_present_as_tet_faces=n_face_present,
        n_missing_faces=n_face_missing,
    )
