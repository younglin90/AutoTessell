"""Phase C3 — Mesh quality metrics + stop criterion.

TetWild / fTetWild 는 iteration 별 min_quality 가 stop_quality 에 도달하거나
개선 폭이 threshold 미만이면 종료. 본 모듈은 quality 계산 + 종료 판정 helper.

레퍼런스
    - Parthasarathy, Graichen, Hathaway 1994, "A comparison of tetrahedron
      quality measures" — shape quality 8.48·V/edge_max^3 공식 출처.
    - fTetWild §3.3 stop criterion — 독립 Python 재구현.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class QualitySnapshot:
    n_tets: int
    min_q: float
    mean_q: float
    median_q: float
    max_aspect: float


def tet_shape_quality(pts: np.ndarray, tets: np.ndarray) -> np.ndarray:
    """per-tet shape quality ∈ [0,1]. 정사면체 ≈ 1."""
    tets = np.asarray(tets, dtype=np.int64)
    if tets.size == 0:
        return np.zeros(0)
    v = pts[tets]
    e01 = np.linalg.norm(v[:, 1] - v[:, 0], axis=1)
    e02 = np.linalg.norm(v[:, 2] - v[:, 0], axis=1)
    e03 = np.linalg.norm(v[:, 3] - v[:, 0], axis=1)
    e12 = np.linalg.norm(v[:, 2] - v[:, 1], axis=1)
    e13 = np.linalg.norm(v[:, 3] - v[:, 1], axis=1)
    e23 = np.linalg.norm(v[:, 3] - v[:, 2], axis=1)
    emax = np.maximum.reduce([e01, e02, e03, e12, e13, e23])
    vol = np.abs(
        np.einsum(
            "ij,ij->i",
            v[:, 1] - v[:, 0],
            np.cross(v[:, 2] - v[:, 0], v[:, 3] - v[:, 0]),
        )
    ) / 6.0
    safe = emax > 1e-30
    q = np.zeros_like(emax)
    q[safe] = 8.48 * vol[safe] / (emax[safe] ** 3)
    return q


def snapshot(pts: np.ndarray, tets: np.ndarray) -> QualitySnapshot:
    q = tet_shape_quality(pts, tets)
    if q.size == 0:
        return QualitySnapshot(0, 0.0, 0.0, 0.0, 0.0)
    # aspect ratio = 1/q 근사.
    aspect = np.where(q > 1e-6, 1.0 / q, 1e6)
    return QualitySnapshot(
        n_tets=int(q.size),
        min_q=float(q.min()),
        mean_q=float(q.mean()),
        median_q=float(np.median(q)),
        max_aspect=float(aspect.max()),
    )


def should_stop(
    history: list[QualitySnapshot],
    *,
    target_min_q: float = 0.3,
    improvement_eps: float = 0.005,
    window: int = 3,
) -> tuple[bool, str]:
    """iteration 을 더 돌릴지 판단.

    중단 조건:
        - 최신 min_q ≥ target_min_q: "target"
        - 최근 window iteration 의 min_q 개선폭 < improvement_eps: "plateau"
        - n_tets 이 0: "empty"

    Returns:
        (stop, reason).
    """
    if not history:
        return False, ""
    last = history[-1]
    if last.n_tets == 0:
        return True, "empty"
    if last.min_q >= target_min_q:
        return True, "target"
    if len(history) >= window:
        recent = [h.min_q for h in history[-window:]]
        if max(recent) - min(recent) < improvement_eps:
            return True, "plateau"
    return False, ""
