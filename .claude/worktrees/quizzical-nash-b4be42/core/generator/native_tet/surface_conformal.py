"""U1 — Surface conformal pass: 입력 face 강제 회복.

cube / cylinder 같은 평면 surface 입력에서 결과 mesh boundary 가 입력 F 의
모든 triangle 을 정확히 face 로 갖고 있지 않은 경우 강제 회복.

전략
    1) 입력 F 의 각 triangle 이 결과 tet mesh 의 face 로 존재하는지 검사.
    2) missing face 마다 그 triangle 의 centroid 를 신규 점으로 삽입.
    3) 전체 re-Delaunay.
    4) face 수가 줄면 채택, 아니면 종료.
    5) 진전이 있는 동안 반복.

centroid 삽입 → 새 tet 들이 그 centroid 를 fan apex 로 사용 → 자연스럽게
원본 triangle 이 boundary 가 아니라 internal face 로 남거나 분할 sub-face 로
나타남. 분할된 sub-face 의 합집합이 원본 face 영역을 덮어 conformal.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class SurfaceConformalResult:
    iterations: int
    n_inserted: int
    face_ratio_before: float
    face_ratio_after: float
    n_missing_faces_before: int
    n_missing_faces_after: int


def _input_faces_present_set(F_surf: np.ndarray) -> set[tuple[int, int, int]]:
    out: set[tuple[int, int, int]] = set()
    for ti in range(F_surf.shape[0]):
        a, b, c = (int(x) for x in F_surf[ti])
        s = tuple(sorted((a, b, c)))
        out.add(s)
    return out


def _tet_faces_set(tets: np.ndarray) -> set[tuple[int, int, int]]:
    if tets.size == 0:
        return set()
    faces = np.stack([
        tets[:, [0, 1, 2]], tets[:, [0, 1, 3]],
        tets[:, [0, 2, 3]], tets[:, [1, 2, 3]],
    ], axis=1).reshape(-1, 3)
    sf = np.sort(faces, axis=1)
    return {(int(sf[i, 0]), int(sf[i, 1]), int(sf[i, 2])) for i in range(sf.shape[0])}


def _face_ratio(F_surf: np.ndarray, tets: np.ndarray) -> tuple[float, list[tuple[int, int, int]]]:
    inp = _input_faces_present_set(F_surf)
    tf = _tet_faces_set(tets)
    if not inp:
        return 1.0, []
    missing = [f for f in inp if f not in tf]
    return float(len(inp) - len(missing)) / float(len(inp)), missing


def surface_conformal_pass(
    pts: np.ndarray,
    tets: np.ndarray,
    V_surf: np.ndarray,
    F_surf: np.ndarray,
    *,
    max_iter: int = 4,
    points_budget: int = 500,
    target_ratio: float = 0.95,
) -> tuple[np.ndarray, np.ndarray, SurfaceConformalResult]:
    """입력 F 의 face 가 결과 mesh 에 모두 face 로 존재하도록 점 강제 삽입.

    Args:
        pts: 현재 모든 점 (앞쪽이 V_surf 와 동일 좌표 가정).
        tets: 현재 tet 배열 (V_surf indexing 기준).
        V_surf, F_surf: 입력 surface.
        max_iter: 삽입+re-Delaunay 반복 한도.
        points_budget: iteration 당 최대 추가 점 수.
        target_ratio: 이 비율 도달하면 조기 종료.

    Returns:
        (new_pts, new_tets, info).
    """
    from scipy.spatial import Delaunay

    pts = np.asarray(pts, dtype=np.float64)
    tets = np.asarray(tets, dtype=np.int64)
    F_surf = np.asarray(F_surf, dtype=np.int64)
    V_surf = np.asarray(V_surf, dtype=np.float64)

    ratio0, _missing0 = _face_ratio(F_surf, tets)
    if ratio0 >= target_ratio or F_surf.shape[0] == 0:
        return pts, tets, SurfaceConformalResult(
            0, 0, ratio0, ratio0, len(_missing0), len(_missing0),
        )

    cur_pts = pts.copy()
    cur_tets = tets.copy()
    n_inserted = 0
    iters = 0
    n_miss_before = len(_missing0)

    for it in range(int(max_iter)):
        ratio_cur, missing = _face_ratio(F_surf, cur_tets)
        if ratio_cur >= target_ratio:
            break
        if not missing:
            break

        candidates: list[list[float]] = []
        for (a, b, c) in missing[:points_budget]:
            cen = (V_surf[a] + V_surf[b] + V_surf[c]) / 3.0
            d = np.linalg.norm(cur_pts - cen, axis=1).min() \
                if cur_pts.shape[0] else 1.0
            if d > 1e-7:
                candidates.append(cen.tolist())
            if len(candidates) >= int(points_budget):
                break

        if not candidates:
            break

        new_pts = np.vstack([cur_pts, np.asarray(candidates, dtype=np.float64)])
        try:
            D = Delaunay(new_pts)
            new_tets = np.asarray(D.simplices, dtype=np.int64)
        except Exception:
            break

        ratio_after, _missing_after = _face_ratio(F_surf, new_tets)
        if ratio_after > ratio_cur + 1e-6:
            cur_pts = new_pts
            cur_tets = new_tets
            n_inserted += len(candidates)
            iters = it + 1
        else:
            break

    ratio_final, missing_final = _face_ratio(F_surf, cur_tets)
    return cur_pts, cur_tets, SurfaceConformalResult(
        iterations=int(iters),
        n_inserted=int(n_inserted),
        face_ratio_before=float(ratio0),
        face_ratio_after=float(ratio_final),
        n_missing_faces_before=int(n_miss_before),
        n_missing_faces_after=int(len(missing_final)),
    )
