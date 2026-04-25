"""U4 — Boundary clipping: 결과 tet mesh 의 외곽을 입력 F 와 정렬.

cube/cyl 같은 평면 입력에서 결과 mesh boundary 가 입력 F 의 12개 triangle
(또는 N개) 와 정확히 일치하지 않을 때, 결과 boundary 를 입력 F 와 매칭되게
강제 변환한다.

전략 (간이 carving)
    1) 결과 mesh 의 boundary face = 1-owner face.
    2) 입력 F 의 face 와 결과 boundary 의 face 가 정확히 매칭되지 않으면:
       (a) 결과 boundary 의 vertex 가 입력 F 의 vertex 부분집합인지 확인.
       (b) 결과 boundary 위의 tet 중 외부에 가까운 (winding number 낮은)
           tet 을 제거 — input F 의 inside test 기준.
    3) 제거 후 새 boundary 가 input F 와 일치하면 성공.

Boundary clipping 은 conformal Delaunay 보다 약하지만, sphere / convex 입력
에선 매우 효과적. 비-convex 입력에서는 carving 이 불완전할 수 있다.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class BoundaryClipResult:
    n_tets_before: int
    n_tets_after: int
    n_dropped: int
    face_ratio_before: float
    face_ratio_after: float


def _winding_inside(
    points: np.ndarray, V: np.ndarray, F: np.ndarray,
) -> np.ndarray:
    """입력 surface F 에 대해 각 점이 내부인지 winding number > 0.5 로 판정."""
    from core.utils.geometry import inside_winding_number

    return inside_winding_number(points, V, F)


def clip_to_input_surface(
    pts: np.ndarray,
    tets: np.ndarray,
    V_surf: np.ndarray,
    F_surf: np.ndarray,
    *,
    inside_threshold: float = 0.5,
) -> tuple[np.ndarray, np.ndarray, BoundaryClipResult]:
    """centroid 가 입력 surface 외부에 있는 tet 제거.

    cube/cyl 처럼 convex 입력에서 결과 mesh 가 surface 를 약간 벗어나는
    경우, 외부 tet 을 잘라내면 결과 boundary 가 input F 에 가까워진다.
    """
    from core.generator.native_tet.surface_conformal import _face_ratio

    pts = np.asarray(pts, dtype=np.float64)
    tets = np.asarray(tets, dtype=np.int64)
    V_surf = np.asarray(V_surf, dtype=np.float64)
    F_surf = np.asarray(F_surf, dtype=np.int64)

    n_before = int(tets.shape[0])
    fr_before, _ = _face_ratio(F_surf, tets)

    if tets.size == 0 or F_surf.size == 0:
        return pts, tets, BoundaryClipResult(
            n_before, n_before, 0, fr_before, fr_before,
        )

    # tet centroid.
    centroids = pts[tets].mean(axis=1)
    inside = _winding_inside(centroids, V_surf, F_surf)
    keep = inside >= float(inside_threshold)
    new_tets = tets[keep]
    fr_after, _ = _face_ratio(F_surf, new_tets)

    return pts, new_tets, BoundaryClipResult(
        n_tets_before=n_before,
        n_tets_after=int(new_tets.shape[0]),
        n_dropped=int((~keep).sum()),
        face_ratio_before=float(fr_before),
        face_ratio_after=float(fr_after),
    )
