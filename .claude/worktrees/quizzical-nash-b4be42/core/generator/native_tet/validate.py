"""Phase J1 — Inverted tet detection + swap repair.

Local operation (flip/collapse/smooth) 이후 signed volume 이 음수로 뒤집힌
tet 은 invalid mesh 를 만든다. 본 모듈은:
    1. 각 tet 의 signed volume 계산.
    2. 음수인 tet 의 last 2 vertex swap 으로 양수 복구.
    3. 복구 불가능한 degenerate (|vol| < eps) 는 리포트.

정상 Delaunay 직후에는 문제없지만 split/collapse/flip 반복 후 numerical
edge case 에서 발생 가능. 대규모 안전판.

레퍼런스
    - Shewchuk 1997, "Adaptive Precision Floating-Point Arithmetic and Fast
      Robust Geometric Predicates" — signed volume robustness.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class ValidateResult:
    n_tets: int
    n_inverted_before: int
    n_fixed_by_swap: int
    n_degenerate: int


def signed_volume6(pts: np.ndarray, tets: np.ndarray) -> np.ndarray:
    """per-tet signed (6 × volume). 양수 = 양의 방향."""
    tets = np.asarray(tets, dtype=np.int64)
    if tets.size == 0:
        return np.zeros(0)
    v = pts[tets]
    return np.einsum(
        "ij,ij->i",
        v[:, 1] - v[:, 0],
        np.cross(v[:, 2] - v[:, 0], v[:, 3] - v[:, 0]),
    )


def orientation_signs(
    pts: np.ndarray, tets: np.ndarray, *, tol: float = 1e-14,
) -> np.ndarray:
    """predicates.orient3d_batch 위임. 각 tet 부호 (int8)."""
    from core.utils.predicates import orient3d_batch

    tets = np.asarray(tets, dtype=np.int64)
    if tets.size == 0:
        return np.zeros(0, dtype=np.int8)
    v = pts[tets]
    return orient3d_batch(v[:, 0], v[:, 1], v[:, 2], v[:, 3], tol=tol)


def drop_extreme_slivers(
    pts: np.ndarray,
    tets: np.ndarray,
    *,
    min_dihedral_deg: float = 0.5,
    min_aspect_regular: float = 10000.0,
) -> tuple[np.ndarray, int]:
    """dihedral 이 극단적으로 작거나 (대략 공면) aspect 가 비정상적으로 큰 tet 제거.

    boundary 보호: surface triangle 이 유지되는지는 caller 가 별도 체크 필요.
    본 함수는 단순히 "수치적으로 무의미한" tet 만 제거.
    """
    tets = np.asarray(tets, dtype=np.int64)
    if tets.size == 0:
        return tets, 0
    # 간단: signed vol 이 거의 0 이거나, dihedral 최소가 threshold 미만인 tet 탈락.
    from core.generator.native_tet.quality import (
        tet_aspect_ratio, tet_min_dihedral_deg,
    )

    dih = tet_min_dihedral_deg(pts, tets)
    asp = tet_aspect_ratio(pts, tets)
    drop = (dih < float(min_dihedral_deg)) | (asp > float(min_aspect_regular))
    n_drop = int(drop.sum())
    return tets[~drop], n_drop


def smooth_then_drop_slivers(
    pts: np.ndarray,
    tets: np.ndarray,
    *,
    locked_vertex_ids: np.ndarray | None = None,
    min_dihedral_deg: float = 0.5,
    min_aspect_regular: float = 10000.0,
    n_smooth_iter: int = 2,
    relax: float = 0.3,
) -> tuple[np.ndarray, np.ndarray, int, int]:
    """beta1130 (R110) — drop 대신 sliver 주변 vertex smoothing 으로 complete.

    1) 극단 sliver 감지.
    2) sliver 가 포함하는 non-locked interior vertex 를 1-ring 평균 방향으로
       relax × n_smooth_iter 이동.
    3) 그래도 여전히 sliver 인 tet 만 drop.

    Returns: (pts_new, tets_new, n_smooth_moved, n_dropped).
    """
    from core.generator.native_tet.quality import (
        tet_aspect_ratio, tet_min_dihedral_deg,
    )
    from core.generator.native_tet.smooth import _build_edge_rows

    pts = np.asarray(pts, dtype=np.float64).copy()
    tets = np.asarray(tets, dtype=np.int64)
    if tets.size == 0:
        return pts, tets, 0, 0

    locked_mask = np.zeros(pts.shape[0], dtype=bool)
    if locked_vertex_ids is not None and len(locked_vertex_ids) > 0:
        locked_mask[np.asarray(locked_vertex_ids, dtype=np.int64)] = True

    dih = tet_min_dihedral_deg(pts, tets)
    asp = tet_aspect_ratio(pts, tets)
    bad = (dih < float(min_dihedral_deg)) | (asp > float(min_aspect_regular))
    if not bad.any():
        return pts, tets, 0, 0

    affected = np.zeros(pts.shape[0], dtype=bool)
    for ti in np.where(bad)[0]:
        for vi in tets[ti]:
            affected[int(vi)] = True
    affected &= ~locked_mask
    n_moved = 0
    if affected.any():
        rows, cols = _build_edge_rows(tets)
        for _ in range(int(n_smooth_iter)):
            sum_nbr = np.zeros_like(pts)
            count = np.zeros(pts.shape[0], dtype=np.int64)
            np.add.at(sum_nbr, rows, pts[cols])
            np.add.at(count, rows, 1)
            valid = affected & (count > 0)
            if not valid.any():
                break
            centroid = np.zeros_like(pts)
            centroid[valid] = sum_nbr[valid] / count[valid, None]
            step = float(relax) * (centroid[valid] - pts[valid])
            pts[valid] = pts[valid] + step
            n_moved += int(valid.sum())

    # re-evaluate.
    dih = tet_min_dihedral_deg(pts, tets)
    asp = tet_aspect_ratio(pts, tets)
    drop = (dih < float(min_dihedral_deg)) | (asp > float(min_aspect_regular))
    n_drop = int(drop.sum())
    tets_out = tets[~drop]
    return pts, tets_out, n_moved, n_drop


def count_boundary_faces(tets: np.ndarray) -> int:
    """beta1280 (R101) — 1-owner face (= surface) 개수.

    validate / fix_inverted 후 surface 가 온전히 유지됐는지 caller 가 비교.
    """
    tets = np.asarray(tets, dtype=np.int64)
    if tets.size == 0:
        return 0
    faces = np.stack([
        tets[:, [0, 1, 2]], tets[:, [0, 1, 3]],
        tets[:, [0, 2, 3]], tets[:, [1, 2, 3]],
    ], axis=1).reshape(-1, 3)
    faces = np.sort(faces, axis=1)
    max_id = int(faces.max()) + 1 if faces.size else 1
    key = (
        faces[:, 0].astype(np.int64) * max_id * max_id
        + faces[:, 1].astype(np.int64) * max_id
        + faces[:, 2].astype(np.int64)
    )
    _, counts = np.unique(key, return_counts=True)
    return int((counts == 1).sum())


def fix_inverted_tets(
    pts: np.ndarray,
    tets: np.ndarray,
    *,
    degenerate_eps: float = 1e-20,
    use_exact_for_uncertain: bool = True,
) -> tuple[np.ndarray, ValidateResult]:
    """음수 signed vol tet 은 마지막 두 vertex swap 으로 양수화.

    Returns:
        (fixed_tets, ValidateResult).
    """
    tets = np.asarray(tets, dtype=np.int64).copy()
    pts = np.asarray(pts, dtype=np.float64)
    if tets.size == 0:
        return tets, ValidateResult(0, 0, 0, 0)

    vol6 = signed_volume6(pts, tets)
    inverted = vol6 < -float(degenerate_eps)
    degenerate = np.abs(vol6) < float(degenerate_eps)

    # beta510 → beta540: uncertain (|vol6| near tol) tet 은 staged predicate 로
    # 재판정. staged 는 Stage 1 double 이 불확실하면 float128 → Fraction 으로
    # drop, 평균 속도 유지하며 정확성 확보.
    if use_exact_for_uncertain and degenerate.any():
        uncertain_idx = np.where(degenerate)[0]
        try:
            from core.utils.predicates_staged import orient3d_staged

            for ti in uncertain_idx.tolist():
                a, b, c, d = tets[ti]
                s = orient3d_staged(pts[a], pts[b], pts[c], pts[d])
                if s < 0:
                    inverted[ti] = True
                    degenerate[ti] = False
                elif s > 0:
                    degenerate[ti] = False
        except Exception:
            pass

    n_before = int(inverted.sum())
    n_degen = int(degenerate.sum())

    # swap (v2, v3) — signed volume sign 뒤집힘.
    if n_before > 0:
        idx = np.where(inverted)[0]
        tmp = tets[idx, 2].copy()
        tets[idx, 2] = tets[idx, 3]
        tets[idx, 3] = tmp

    vol6_after = signed_volume6(pts, tets)
    still = int((vol6_after < -float(degenerate_eps)).sum())
    fixed = n_before - still

    return tets, ValidateResult(
        n_tets=int(tets.shape[0]),
        n_inverted_before=n_before,
        n_fixed_by_swap=int(fixed),
        n_degenerate=n_degen,
    )
