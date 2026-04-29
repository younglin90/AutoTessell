"""V1 — Plane coverage: 결과 boundary 가 입력 F 의 plane 분할을 덮는지.

cube / cyl 같은 평면 입력에서 결과 mesh boundary 가 입력 F 의 12/N
triangle 과 정확히 일치하지 않더라도, "같은 plane 위에 있는 boundary
triangle 들의 면적 합이 그 plane 위의 입력 face 면적 합과 같으면" 표면이
실질적으로 보존된다. fTetWild 도 이 정의로 surface conformity 평가.

본 모듈
    1) 입력 F 를 plane 별 (normal, offset) 단위로 그룹.
    2) 결과 boundary face 도 동일 그룹.
    3) 각 plane 그룹 별 면적 합 비교.

plane 매칭 tolerance 는 normal cosine 0.999 + offset 절대 1e-6 단위.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class PlaneCoverageResult:
    n_input_planes: int
    n_covered_planes: int
    plane_coverage: float          # 덮인 plane 비율.
    area_coverage: float           # 면적 가중 비율.
    extra_area: float              # 입력 plane 위에 없는 boundary 면적.


def _tet_boundary_faces(tets: np.ndarray) -> np.ndarray:
    if tets.size == 0:
        return np.zeros((0, 3), dtype=np.int64)
    faces = np.stack([
        tets[:, [0, 1, 2]], tets[:, [0, 1, 3]],
        tets[:, [0, 2, 3]], tets[:, [1, 2, 3]],
    ], axis=1).reshape(-1, 3)
    sf = np.sort(faces, axis=1)
    max_id = int(sf.max()) + 1 if sf.size else 1
    key = (
        sf[:, 0].astype(np.int64) * max_id * max_id
        + sf[:, 1].astype(np.int64) * max_id
        + sf[:, 2].astype(np.int64)
    )
    _, inv, counts = np.unique(key, return_inverse=True, return_counts=True)
    return faces[counts[inv] == 1]


def _triangle_planes_and_areas(
    V: np.ndarray, F: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (unit_normals (M,3), offsets (M,), areas (M,))."""
    A = V[F[:, 0]]; B = V[F[:, 1]]; C = V[F[:, 2]]
    n = np.cross(B - A, C - A)
    norm = np.linalg.norm(n, axis=1)
    safe = norm > 1e-30
    unit = np.zeros_like(n)
    unit[safe] = n[safe] / norm[safe, None]
    # canonical sign — z 가 양수, 같으면 y, 같으면 x.
    sign_axis = np.where(
        unit[:, 2] != 0, np.sign(unit[:, 2]),
        np.where(unit[:, 1] != 0, np.sign(unit[:, 1]), np.sign(unit[:, 0])),
    )
    sign_axis = np.where(sign_axis == 0, 1.0, sign_axis)
    unit *= sign_axis[:, None]
    offset = np.einsum("ij,ij->i", unit, A)
    area = 0.5 * norm
    return unit, offset, area


def _group_by_plane(
    unit: np.ndarray, offset: np.ndarray,
    *, normal_tol: float = 1e-3, offset_rel_tol: float = 1e-4,
    bbox_diag: float = 1.0,
) -> dict[tuple[int, int, int, int], list[int]]:
    """grid quantize 로 plane → triangle indices.

    C-PERF-72 / beta2523 — vectorize via lexsort + group-boundary.
    """
    if unit.shape[0] == 0:
        return {}
    qn = np.round(unit / normal_tol).astype(np.int64)
    abs_off_tol = max(offset_rel_tol * bbox_diag, 1e-9)
    qo = np.round(offset / abs_off_tol).astype(np.int64)
    keys = np.column_stack([qn[:, 0], qn[:, 1], qn[:, 2], qo])  # (N, 4)
    idx_arr = np.arange(unit.shape[0], dtype=np.int64)
    order = np.lexsort((keys[:, 3], keys[:, 2], keys[:, 1], keys[:, 0]))
    k_s = keys[order]; i_s = idx_arr[order]
    diff = np.r_[True, np.any(k_s[1:] != k_s[:-1], axis=1)]
    starts = np.where(diff)[0]
    ends = np.r_[starts[1:], len(k_s)]
    out: dict[tuple[int, int, int, int], list[int]] = {}
    for s, e in zip(starts.tolist(), ends.tolist()):
        kt = (int(k_s[s, 0]), int(k_s[s, 1]),
              int(k_s[s, 2]), int(k_s[s, 3]))
        out[kt] = i_s[s:e].tolist()
    return out


def plane_coverage(
    V_surf: np.ndarray, F_surf: np.ndarray,
    pts: np.ndarray, tets: np.ndarray,
    *,
    normal_tol: float = 5e-2,
    offset_rel_tol: float = 5e-3,
    area_match_tol: float = 0.10,
) -> PlaneCoverageResult:
    """입력 F 의 각 plane 이 결과 boundary face 들로 덮이는지.

    plane 그룹 매칭 tolerance:
        - normal_tol: unit-normal grid 양자화.
        - offset_rel_tol: offset / bbox_diag.
        - area_match_tol: 면적 합 비율 차이 (5%).
    """
    V_surf = np.asarray(V_surf, dtype=np.float64)
    F_surf = np.asarray(F_surf, dtype=np.int64)
    pts = np.asarray(pts, dtype=np.float64)
    tets = np.asarray(tets, dtype=np.int64)

    if F_surf.size == 0:
        return PlaneCoverageResult(0, 0, 1.0, 1.0, 0.0)

    bbox = V_surf.max(axis=0) - V_surf.min(axis=0)
    bbox_diag = float(np.linalg.norm(bbox)) + 1e-30

    # 입력 plane group.
    in_unit, in_off, in_area = _triangle_planes_and_areas(V_surf, F_surf)
    in_groups = _group_by_plane(
        in_unit, in_off,
        normal_tol=normal_tol, offset_rel_tol=offset_rel_tol,
        bbox_diag=bbox_diag,
    )

    # 결과 boundary face plane group.
    B = _tet_boundary_faces(tets)
    if B.shape[0] == 0:
        return PlaneCoverageResult(
            len(in_groups), 0, 0.0, 0.0, 0.0,
        )
    bn_unit, bn_off, bn_area = _triangle_planes_and_areas(pts, B)
    bn_groups = _group_by_plane(
        bn_unit, bn_off,
        normal_tol=normal_tol, offset_rel_tol=offset_rel_tol,
        bbox_diag=bbox_diag,
    )

    n_in = len(in_groups)
    n_covered = 0
    total_in_area = 0.0
    total_match_area = 0.0
    total_in_area_for_match = 0.0
    extra_area = 0.0

    for key, idxs in in_groups.items():
        a_in = float(in_area[idxs].sum())
        total_in_area += a_in
        if key in bn_groups:
            a_b = float(bn_area[bn_groups[key]].sum())
            # 매칭 — 면적 비율 차이가 area_match_tol 이내면 덮인 것.
            if a_in > 0 and abs(a_b - a_in) / a_in <= area_match_tol:
                n_covered += 1
                total_match_area += a_in
                total_in_area_for_match += a_in
            else:
                # 부분 덮음 — 면적 비율로 카운트.
                ratio = min(a_b, a_in) / max(a_in, 1e-30)
                total_match_area += ratio * a_in
                total_in_area_for_match += a_in

    # extra: 결과 boundary 중 입력 plane 에 없는 group 의 면적.
    for key, idxs in bn_groups.items():
        if key not in in_groups:
            extra_area += float(bn_area[idxs].sum())

    plane_cov = n_covered / max(n_in, 1)
    area_cov = (
        total_match_area / total_in_area if total_in_area > 0 else 1.0
    )
    return PlaneCoverageResult(
        n_input_planes=int(n_in),
        n_covered_planes=int(n_covered),
        plane_coverage=float(plane_cov),
        area_coverage=float(area_cov),
        extra_area=float(extra_area),
    )
