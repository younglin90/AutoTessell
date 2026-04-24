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
    # Round 70 확장.
    mean_aspect: float = 0.0
    min_dihedral_deg: float = 0.0
    median_dihedral_deg: float = 0.0
    # Round 75: volume-weighted metrics (큰 tet 이 영향 큼).
    vol_weighted_mean_q: float = 0.0
    p10_q: float = 0.0             # worst 10% quality (percentile).
    p10_dihedral_deg: float = 0.0


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


def tet_aspect_ratio(pts: np.ndarray, tets: np.ndarray) -> np.ndarray:
    """Aspect ratio = circumradius / inradius (1 = regular, ∞ = degenerate)."""
    tets = np.asarray(tets, dtype=np.int64)
    if tets.size == 0:
        return np.zeros(0)
    v = pts[tets]
    a, b, c, d = v[:, 0], v[:, 1], v[:, 2], v[:, 3]

    # volume.
    vol6 = np.abs(np.einsum("ij,ij->i", b - a, np.cross(c - a, d - a)))
    vol = vol6 / 6.0

    # face areas.
    def _area(p, q, r):
        return 0.5 * np.linalg.norm(np.cross(q - p, r - p), axis=1)
    A1 = _area(a, b, c)
    A2 = _area(a, b, d)
    A3 = _area(a, c, d)
    A4 = _area(b, c, d)
    surf_sum = A1 + A2 + A3 + A4

    # inradius = 3V / surface_area.
    inrad = np.where(surf_sum > 1e-30, 3.0 * vol / surf_sum, 0.0)

    # circumradius via formula: R = |det(M)| / (2 * |det(vectors)|) 복잡 →
    # 근사 edge-max based: R ≈ sqrt(max edge^2) * correction.
    e1 = np.linalg.norm(b - a, axis=1)
    e2 = np.linalg.norm(c - a, axis=1)
    e3 = np.linalg.norm(d - a, axis=1)
    e4 = np.linalg.norm(c - b, axis=1)
    e5 = np.linalg.norm(d - b, axis=1)
    e6 = np.linalg.norm(d - c, axis=1)
    rmax = np.maximum.reduce([e1, e2, e3, e4, e5, e6]) / 2.0

    safe_inrad = np.where(inrad > 1e-30, inrad, 1.0)
    ratio = rmax / safe_inrad
    return np.where(inrad > 1e-30, ratio, 1e6)


def tet_min_dihedral_deg(pts: np.ndarray, tets: np.ndarray) -> np.ndarray:
    """각 tet 의 6 dihedral angle 중 최소 (degrees). 정사면체 ≈ 70.5°."""
    tets = np.asarray(tets, dtype=np.int64)
    if tets.size == 0:
        return np.zeros(0)
    v = pts[tets]
    a, b, c, d = v[:, 0], v[:, 1], v[:, 2], v[:, 3]

    # 4 face normals (positive orient 가정).
    def _n(p, q, r):
        n = np.cross(q - p, r - p)
        norm = np.linalg.norm(n, axis=1, keepdims=True)
        return n / np.where(norm > 1e-30, norm, 1.0)

    n_abc = _n(a, b, c)
    n_abd = _n(a, b, d)
    n_acd = _n(a, c, d)
    n_bcd = _n(b, c, d)

    # dihedral between faces sharing edge = π - angle(face normals).
    def _dih(n1, n2):
        dot = np.clip(np.einsum("ij,ij->i", n1, n2), -1.0, 1.0)
        return np.rad2deg(np.arccos(dot))

    dh1 = 180.0 - _dih(n_abc, n_abd)   # edge ab
    dh2 = 180.0 - _dih(n_abc, n_acd)   # edge ac
    dh3 = 180.0 - _dih(n_abd, n_acd)   # edge ad
    dh4 = 180.0 - _dih(n_abc, n_bcd)   # edge bc
    dh5 = 180.0 - _dih(n_abd, n_bcd)   # edge bd
    dh6 = 180.0 - _dih(n_acd, n_bcd)   # edge cd

    return np.minimum.reduce([dh1, dh2, dh3, dh4, dh5, dh6])


def snapshot(pts: np.ndarray, tets: np.ndarray) -> QualitySnapshot:
    q = tet_shape_quality(pts, tets)
    if q.size == 0:
        return QualitySnapshot(0, 0.0, 0.0, 0.0, 0.0)
    aspect = tet_aspect_ratio(pts, tets)
    dih = tet_min_dihedral_deg(pts, tets)

    # volume weight.
    tets_arr = np.asarray(tets, dtype=np.int64)
    v = pts[tets_arr]
    vol6 = np.abs(np.einsum(
        "ij,ij->i",
        v[:, 1] - v[:, 0],
        np.cross(v[:, 2] - v[:, 0], v[:, 3] - v[:, 0]),
    ))
    w_sum = float(vol6.sum())
    vol_weighted_mean_q = (
        float((q * vol6).sum() / w_sum) if w_sum > 0 else 0.0
    )

    return QualitySnapshot(
        n_tets=int(q.size),
        min_q=float(q.min()),
        mean_q=float(q.mean()),
        median_q=float(np.median(q)),
        max_aspect=float(aspect.max()),
        mean_aspect=float(aspect.mean()),
        min_dihedral_deg=float(dih.min()),
        median_dihedral_deg=float(np.median(dih)),
        vol_weighted_mean_q=vol_weighted_mean_q,
        p10_q=float(np.percentile(q, 10)),
        p10_dihedral_deg=float(np.percentile(dih, 10)),
    )


def should_stop(
    history: list[QualitySnapshot],
    *,
    target_min_q: float = 0.3,
    target_min_dihedral_deg: float | None = None,
    improvement_eps: float = 0.005,
    window: int = 3,
) -> tuple[bool, str]:
    """iteration 을 더 돌릴지 판단.

    중단 조건:
        - 최신 min_q ≥ target_min_q: "target"
        - target_min_dihedral_deg 설정 시 min_dihedral 이 threshold 이상: "dihedral_target"
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
    if (
        target_min_dihedral_deg is not None
        and last.min_dihedral_deg >= float(target_min_dihedral_deg)
    ):
        return True, "dihedral_target"
    if len(history) >= window:
        recent = [h.min_q for h in history[-window:]]
        if max(recent) - min(recent) < improvement_eps:
            return True, "plateau"
    return False, ""
