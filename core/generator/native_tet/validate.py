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
    void_free: bool = True,
) -> tuple[np.ndarray, int]:
    """극단 sliver (거의 공면이거나 aspect 비정상) 를 센다. 기본값은 제거하지 않는다.

    Args:
        void_free: True (기본) 면 **세기만 하고 지우지 않는다**.

            사면체 분할에서 tet 을 삭제하면 그 face 들이 경계에 편입되지만 입력
            표면에 속하지 않는다 ⇒ void 벽이고, 아무도 그 구멍을 메우지 않는다
            (BETA2822 가 ``filter.py`` 에 세운 불변식). 이 함수의 원래 docstring 은
            *"boundary 보호: surface triangle 이 유지되는지는 caller 가 별도 체크
            필요"* 라고 적어 두었으나 어떤 caller 도 그 체크를 하지 않았고, 부피
            내부 구멍은 애초에 surface triangle 체크로는 잡히지 않는다.

            실측 (cube/draft/N=2000/P4C=0): 이 함수가 5 회 호출에 **260 개**를
            삭제해 (한 호출에 300 개 중 51 개 = 17%) 남은 void 벽 면적의 최대
            기여자였다.

            fTetWild 는 sliver 를 삭제하지 않고 위상 보존 국소 연산 (split /
            collapse / swap / smooth) 으로 제거한다 (Hu et al. 2020 §3.4).
            반환하는 count 는 그 국소 연산이 갚아야 할 부채다.
            False 면 legacy 동작 (실제 삭제) — A/B 용.

    Returns: (tets, n_extreme_slivers). ``void_free`` 면 tets 는 입력 그대로.
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
    if void_free:
        return tets, n_drop
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
    void_free: bool = True,
) -> tuple[np.ndarray, np.ndarray, int, int]:
    """beta1130 (R110) — drop 대신 sliver 주변 vertex smoothing 으로 complete.

    1) 극단 sliver 감지.
    2) sliver 가 포함하는 non-locked interior vertex 를 1-ring 평균 방향으로
       relax × n_smooth_iter 이동.
    3) ``void_free=False`` 면 그래도 여전히 sliver 인 tet 을 drop.

    Args:
        void_free: True (기본) 면 3) 의 drop 을 하지 않는다 — smoothing 만 하고
            남은 sliver 는 그대로 안고 간다.

            근거는 BETA2822 가 ``filter.py`` 에 세운 것과 **동일한 void 정리**:
            사면체 분할에서 tet 을 삭제하면 그 face 들이 경계에 편입되지만 입력
            표면에 속하지 않는다 ⇒ void 벽. 아무도 그 구멍을 메우지 않는다.
            그 불변식이 이 호출에는 적용돼 있지 않았다.

            특히 경계 정점을 올바르게 lock 하면 (BETA2823) 이 결함이 **드러난다**:
            line 128 의 ``affected &= ~locked_mask`` 때문에 lock 된 경계 sliver 는
            smoothing 으로 빠져나갈 수 없고 → 전부 drop 으로 떨어진다.
            실측 (cube/draft/N=2000): n_drop/call 4 → ~50 (12배), 경계면 446 → 574
            (한 호출에 +128 = 내부 void). 부피는 정확히 1.0 인데 면적만 1.32x 인
            것이 증거 — 부피 0 인 내부 균열이라 발산정리엔 안 잡히고 면적에만 잡힌다.

            fTetWild 는 sliver 를 삭제하지 않고 위상 보존 국소 연산 (split /
            collapse / swap / smooth) 으로 제거한다 (Hu et al. 2020 §3.4).
            False 면 legacy 동작 — A/B 용.

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

    # C-PERF-78 / beta2529 — vectorized: gather all bad-tet verts in one shot.
    affected = np.zeros(pts.shape[0], dtype=bool)
    bad_verts = tets[bad].ravel()
    if bad_verts.size > 0:
        affected[bad_verts] = True
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
    if void_free:
        # 삭제하지 않는다 (void 정리 — docstring 참고). 남은 sliver 수는 계속
        # 보고해 국소 연산이 갚아야 할 부채로 가시화한다.
        return pts, tets, n_moved, 0
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
