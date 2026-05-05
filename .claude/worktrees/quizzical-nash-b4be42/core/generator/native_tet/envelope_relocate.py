"""
envelope_relocate.py — fTetWild §3.5 envelope-bounded surface vertex relocation (SSS1 skeleton).

_SSS1_ENVELOPE_RELOCATE = False  →  호출처 미연결, 기능 OFF.
"""

import numpy as np
from numpy.typing import NDArray

_SSS1_ENVELOPE_RELOCATE = False


def _tangent_project(
    pt: NDArray[np.float64],
    normal: NDArray[np.float64],
    target: NDArray[np.float64],
) -> NDArray[np.float64]:
    """normal 성분을 제거하여 tangent 평면 상의 이동 후보 좌표를 반환한다.

    Parameters
    ----------
    pt:     현재 표면 정점 위치 (3,)
    normal: 단위 법선 벡터 (3,)
    target: 이동 목표 위치 (3,)  — smoothing 계산값 등

    Returns
    -------
    tangent-projected candidate position (3,)
    """
    n = normal / (np.linalg.norm(normal) + 1e-300)
    delta = target - pt
    delta_tangent = delta - np.dot(delta, n) * n
    return pt + delta_tangent


def _envelope_bounded_relocate(
    pts: NDArray[np.float64],
    surface_idx: NDArray[np.intp],
    target_pts: NDArray[np.float64],
    vertex_normals: NDArray[np.float64],
    envelope,
) -> NDArray[np.float64]:
    """surface vertex 마다 tangent projection 후보를 생성하고
    envelope.contains_points 검증을 통과하면 채택, 실패하면 원위치를 유지한다.

    Parameters
    ----------
    pts:            전체 정점 배열 (N, 3)
    surface_idx:    표면 정점 인덱스 배열 (S,)
    target_pts:     각 surface_idx 정점에 대응하는 이동 목표 (S, 3)
    vertex_normals: 각 surface_idx 정점의 단위 법선 (S, 3)
    envelope:       contains_points(pts_Mx3) -> (M,) bool 을 지원하는 객체

    Returns
    -------
    updated pts (N, 3) — surface vertex 중 envelope 통과한 정점만 이동.
    """
    result = pts.copy()

    candidates = np.empty((len(surface_idx), 3), dtype=np.float64)
    for k, idx in enumerate(surface_idx):
        candidates[k] = _tangent_project(pts[idx], vertex_normals[k], target_pts[k])

    inside = envelope.contains_points(candidates)

    for k, idx in enumerate(surface_idx):
        if inside[k]:
            result[idx] = candidates[k]
        # else: 원위치 유지 (result[idx] 이미 pts[idx] 복사)

    return result
