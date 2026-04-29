"""Phase Q — 입력 표면 pre-check.

generate_native_tet 진입 전에 입력의 degenerate / self-intersection 가능성을
감지해 경고 (failure 아님, 계속 진행 가능). 사용자가 입력 품질을 인지하도록.

레퍼런스
    - Möller 1997, "A Fast Triangle-Triangle Intersection Test".
    - Botsch et al. 2010 §1.4 consistency checks.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class InputCheckResult:
    n_duplicate_vertices: int
    n_zero_area_triangles: int
    n_boundary_edges: int          # 1 owner edge (non-watertight)
    n_nonmanifold_edges: int       # 3+ owner edge
    min_triangle_area: float
    min_dihedral_deg: float
    warnings: list[str]


def _tri_aabb_overlap(tmin, tmax, i, j) -> bool:
    return (
        tmin[j, 0] <= tmax[i, 0] and tmax[j, 0] >= tmin[i, 0]
        and tmin[j, 1] <= tmax[i, 1] and tmax[j, 1] >= tmin[i, 1]
        and tmin[j, 2] <= tmax[i, 2] and tmax[j, 2] >= tmin[i, 2]
    )


def _moller_tri_intersect(A, B, C, D, E, F) -> bool:
    """beta1290 (R102) — Möller 1997 triangle-triangle intersection test.

    두 triangle (A,B,C), (D,E,F) 의 실제 교차 여부 반환. 공유 vertex 또는
    공면 coplanar 는 False (false positive 최소화).
    """
    import numpy as _np

    A = _np.asarray(A); B = _np.asarray(B); C = _np.asarray(C)
    D = _np.asarray(D); E = _np.asarray(E); F = _np.asarray(F)

    n2 = _np.cross(E - D, F - D)
    d2 = -_np.dot(n2, D)
    d_a = _np.dot(n2, A) + d2
    d_b = _np.dot(n2, B) + d2
    d_c = _np.dot(n2, C) + d2
    if (d_a > 0 and d_b > 0 and d_c > 0) or (d_a < 0 and d_b < 0 and d_c < 0):
        return False
    if abs(d_a) < 1e-20 and abs(d_b) < 1e-20 and abs(d_c) < 1e-20:
        return False  # coplanar 무시.

    n1 = _np.cross(B - A, C - A)
    d1 = -_np.dot(n1, A)
    d_d = _np.dot(n1, D) + d1
    d_e = _np.dot(n1, E) + d1
    d_f = _np.dot(n1, F) + d1
    if (d_d > 0 and d_e > 0 and d_f > 0) or (d_d < 0 and d_e < 0 and d_f < 0):
        return False
    if abs(d_d) < 1e-20 and abs(d_e) < 1e-20 and abs(d_f) < 1e-20:
        return False

    # 두 plane 의 교선 방향.
    D_line = _np.cross(n1, n2)
    axis = int(_np.argmax(_np.abs(D_line)))

    def _interval(P1, P2, P3, dP1, dP2, dP3):
        # 부호가 다른 vertex 찾기.
        if dP1 * dP2 > 0:
            # P3 는 반대 부호.
            t1 = P1[axis] + (P3[axis] - P1[axis]) * dP1 / (dP1 - dP3)
            t2 = P2[axis] + (P3[axis] - P2[axis]) * dP2 / (dP2 - dP3)
        elif dP1 * dP3 > 0:
            t1 = P1[axis] + (P2[axis] - P1[axis]) * dP1 / (dP1 - dP2)
            t2 = P3[axis] + (P2[axis] - P3[axis]) * dP3 / (dP3 - dP2)
        else:
            t1 = P2[axis] + (P1[axis] - P2[axis]) * dP2 / (dP2 - dP1)
            t2 = P3[axis] + (P1[axis] - P3[axis]) * dP3 / (dP3 - dP1)
        return (min(t1, t2), max(t1, t2))

    i1 = _interval(A, B, C, d_a, d_b, d_c)
    i2 = _interval(D, E, F, d_d, d_e, d_f)
    return i1[1] >= i2[0] and i2[1] >= i1[0]


def exact_self_intersection_check(
    V: np.ndarray, F: np.ndarray, *, max_checks: int = 20000,
) -> int:
    """beta1290 (R102) — AABB sweep 후 Möller 정확 테스트로 self-intersection.

    AABB overlap 후보 쌍만 정확 체크. 공유 vertex 있는 쌍은 제외.
    Returns: 실제 교차 쌍 수 (over-estimate 아님).
    """
    V = np.asarray(V, dtype=np.float64)
    F = np.asarray(F, dtype=np.int64)
    if F.shape[0] < 2:
        return 0
    tri_pts = V[F]
    tmin = tri_pts.min(axis=1)
    tmax = tri_pts.max(axis=1)
    order = np.argsort(tmin[:, 0])
    n_hit = 0
    n_checks = 0
    for ii in range(order.size):
        i = int(order[ii])
        for jj in range(ii + 1, order.size):
            j = int(order[jj])
            if tmin[j, 0] > tmax[i, 0]:
                break
            if not _tri_aabb_overlap(tmin, tmax, i, j):
                continue
            if set(F[i].tolist()) & set(F[j].tolist()):
                continue
            n_checks += 1
            if n_checks > max_checks:
                return n_hit
            if _moller_tri_intersect(
                V[F[i, 0]], V[F[i, 1]], V[F[i, 2]],
                V[F[j, 0]], V[F[j, 1]], V[F[j, 2]],
            ):
                n_hit += 1
    return n_hit


def auto_fix_input(
    V: np.ndarray, F: np.ndarray,
    *,
    dup_tol: float = 1e-9,
    drop_zero_area: bool = True,
    align_winding: bool = True,
    aggressive: bool = False,
) -> tuple[np.ndarray, np.ndarray, dict]:
    """beta1110 (R174/R175) — 간단한 입력 자동 수리.

    - dup_tol 그리드 기준 vertex merge + F 재매핑.
    - drop_zero_area=True 이면 |area| < 1e-20 triangle 제거.
    - align_winding=True 이면 bbox centroid 기준 전체 face 의 바깥 방향 통일
      (flood-fill 이 아닌 centroid-direction heuristic — MVP).

    Returns: (V_new, F_new, info_dict).
    """
    V = np.asarray(V, dtype=np.float64)
    F = np.asarray(F, dtype=np.int64)
    info: dict = {}

    if V.shape[0] == 0 or F.shape[0] == 0:
        return V, F, info

    # 1) vertex dedup.
    scale = 1.0 / max(dup_tol, 1e-30)
    q = np.round(V * scale).astype(np.int64)
    # 해시용 view.
    view = np.ascontiguousarray(q).view(
        np.dtype((np.void, q.dtype.itemsize * 3))
    ).ravel()
    _, first_idx, inv = np.unique(view, return_index=True, return_inverse=True)
    V2 = V[first_idx]
    F2 = inv[F]
    info["n_dedup"] = int(V.shape[0] - V2.shape[0])

    # 2) zero-area drop.
    if drop_zero_area:
        e1 = V2[F2[:, 1]] - V2[F2[:, 0]]
        e2 = V2[F2[:, 2]] - V2[F2[:, 0]]
        area = 0.5 * np.linalg.norm(np.cross(e1, e2), axis=1)
        keep = area > 1e-20
        info["n_zero_area_drop"] = int((~keep).sum())
        F2 = F2[keep]

    # 3) winding align (centroid-heuristic).
    if align_winding and F2.shape[0] > 0:
        centroid = V2.mean(axis=0)
        tri_centroid = V2[F2].mean(axis=1)
        outward = tri_centroid - centroid
        e1 = V2[F2[:, 1]] - V2[F2[:, 0]]
        e2 = V2[F2[:, 2]] - V2[F2[:, 0]]
        face_n = np.cross(e1, e2)
        dot = np.einsum("ij,ij->i", face_n, outward)
        flip = dot < 0
        # swap v1 ↔ v2.
        F2_flip = F2.copy()
        F2_flip[flip, 1] = F2[flip, 2]
        F2_flip[flip, 2] = F2[flip, 1]
        F2 = F2_flip
        info["n_winding_flip"] = int(flip.sum())

    # KK1 (beta1850) — aggressive=True 면 native_repair 의 hole fill +
    # non-manifold edge 제거까지 추가 수행.
    if aggressive:
        try:
            from core.preprocessor.native_repair import run_native_repair
            r = run_native_repair(
                V2, F2,
                dedup_tol=float(dup_tol),
                degenerate_area_tol=1e-18,
                fill_hole_max_boundary=128,
                fix_normals=True,
            )
            info["aggressive_steps"] = r.steps
            info["aggressive_watertight"] = r.watertight
            info["aggressive_manifold"] = r.manifold
            return r.vertices.astype(np.float64), r.faces.astype(np.int64), info
        except Exception as exc:
            info["aggressive_error"] = str(exc)[:120]

    return V2, F2, info


def check_input(
    V: np.ndarray, F: np.ndarray,
    *,
    dup_tol: float = 1e-12,
    zero_area_tol: float = 1e-20,
) -> InputCheckResult:
    """입력 surface mesh 의 기본 건강성 리포트."""
    V = np.asarray(V, dtype=np.float64)
    F = np.asarray(F, dtype=np.int64)
    warnings: list[str] = []

    # 1) 중복 vertex.
    n_dup = 0
    if V.shape[0] > 0:
        # round to tol grid + unique.
        scale = 1.0 / max(dup_tol, 1e-30)
        q = np.round(V * scale).astype(np.int64)
        _, counts = np.unique(
            q.view([("", q.dtype)] * 3),
            return_counts=True,
        )
        n_dup = int((counts > 1).sum())
        if n_dup > 0:
            warnings.append(
                f"duplicate vertices: {n_dup} (tolerance={dup_tol:.2e})"
            )

    # 2) triangle area.
    min_area = 0.0
    n_zero = 0
    if F.shape[0] > 0:
        e1 = V[F[:, 1]] - V[F[:, 0]]
        e2 = V[F[:, 2]] - V[F[:, 0]]
        area = 0.5 * np.linalg.norm(np.cross(e1, e2), axis=1)
        n_zero = int((area < zero_area_tol).sum())
        min_area = float(area.min()) if area.size else 0.0
        if n_zero > 0:
            warnings.append(
                f"zero-area triangles: {n_zero} (< {zero_area_tol:.2e})"
            )

    # 3) edge topology.
    # C-PERF-47 / beta2498 — vectorize edge owners + boundary/nm count.
    n_boundary = 0; n_nonmanifold = 0
    min_dih = 180.0
    if F.shape[0] > 0:
        src_eo = F[:, [0, 1, 2]].reshape(-1).astype(np.int64)
        dst_eo = F[:, [1, 2, 0]].reshape(-1).astype(np.int64)
        u_eo = np.minimum(src_eo, dst_eo)
        v_eo = np.maximum(src_eo, dst_eo)
        order_eo = np.lexsort((v_eo, u_eo))
        u_s = u_eo[order_eo]; v_s = v_eo[order_eo]
        diff_eo = np.r_[True, (u_s[1:] != u_s[:-1]) | (v_s[1:] != v_s[:-1])]
        starts_eo = np.where(diff_eo)[0]
        sizes_eo = np.diff(np.r_[starts_eo, len(u_s)])
        n_boundary = int((sizes_eo == 1).sum())
        n_nonmanifold = int((sizes_eo >= 3).sum())
        if n_boundary > 0:
            warnings.append(f"non-watertight: {n_boundary} boundary edges")
        if n_nonmanifold > 0:
            warnings.append(
                f"non-manifold: {n_nonmanifold} edges with 3+ owners"
            )

    # 4) AABB 기반 빠른 self-intersection 후보 탐지.
    #    정확한 체크는 비싸므로 AABB overlap 있는 쌍만 카운트 (over-estimate).
    n_aabb_overlaps = 0
    if F.shape[0] > 2 and F.shape[0] < 20000:
        try:
            tri_pts = V[F]                  # (T, 3, 3)
            tmin = tri_pts.min(axis=1)
            tmax = tri_pts.max(axis=1)
            # 순진 O(T^2) 는 피하고 sorted-sweep 으로 대체.
            order = np.argsort(tmin[:, 0])
            n_over = 0
            for idx_i in range(order.size):
                i = int(order[idx_i])
                for idx_j in range(idx_i + 1, order.size):
                    j = int(order[idx_j])
                    if tmin[j, 0] > tmax[i, 0]:
                        break
                    # AABB overlap 3D.
                    if (tmin[j, 1] <= tmax[i, 1] and tmax[j, 1] >= tmin[i, 1]
                        and tmin[j, 2] <= tmax[i, 2] and tmax[j, 2] >= tmin[i, 2]):
                        # 공유 vertex 있으면 정상 adjacency (over-count 제외).
                        if set(F[i].tolist()) & set(F[j].tolist()):
                            continue
                        n_over += 1
                        if n_over >= 500:
                            break
                if n_over >= 500:
                    break
            n_aabb_overlaps = n_over
            if n_over > 0:
                warnings.append(
                    f"possible self-intersection candidates: {n_over} "
                    "(AABB overlap heuristic — manual check 권장)"
                )
        except Exception:
            pass

    # beta1100 (R172/R173) — degenerate 크기 / 빈 입력 처리.
    if V.shape[0] < 4:
        warnings.append(
            f"insufficient vertices: {V.shape[0]} (tet 생성에 최소 4 필요)"
        )
    if F.shape[0] == 0:
        warnings.append("empty face list (빈 surface)")

    return InputCheckResult(
        n_duplicate_vertices=n_dup,
        n_zero_area_triangles=n_zero,
        n_boundary_edges=n_boundary,
        n_nonmanifold_edges=n_nonmanifold,
        min_triangle_area=min_area,
        min_dihedral_deg=min_dih,
        warnings=warnings,
    )
