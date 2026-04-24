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


def auto_fix_input(
    V: np.ndarray, F: np.ndarray,
    *,
    dup_tol: float = 1e-9,
    drop_zero_area: bool = True,
    align_winding: bool = True,
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
    n_boundary = 0; n_nonmanifold = 0
    min_dih = 180.0
    if F.shape[0] > 0:
        edge_owners: dict[tuple[int, int], list[int]] = {}
        for ti in range(F.shape[0]):
            a, b, c = int(F[ti, 0]), int(F[ti, 1]), int(F[ti, 2])
            for u, v in ((a, b), (b, c), (c, a)):
                key = (u, v) if u < v else (v, u)
                edge_owners.setdefault(key, []).append(ti)
        for key, lst in edge_owners.items():
            if len(lst) == 1:
                n_boundary += 1
            elif len(lst) >= 3:
                n_nonmanifold += 1
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
