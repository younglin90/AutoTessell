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


def snapshot_to_dict(snap: "QualitySnapshot | None") -> dict:
    """QualitySnapshot → JSON-serializable dict. 로그/리포트/bench 파일 공용."""
    if snap is None:
        return {}
    return {
        "n_tets": int(snap.n_tets),
        "min_q": round(float(snap.min_q), 6),
        "mean_q": round(float(snap.mean_q), 6),
        "median_q": round(float(snap.median_q), 6),
        "max_aspect": round(float(snap.max_aspect), 3),
        "mean_aspect": round(float(snap.mean_aspect), 3),
        "min_dihedral_deg": round(float(snap.min_dihedral_deg), 3),
        "median_dihedral_deg": round(float(snap.median_dihedral_deg), 3),
        "vol_weighted_mean_q": round(float(snap.vol_weighted_mean_q), 6),
        "p10_q": round(float(snap.p10_q), 6),
        "p10_dihedral_deg": round(float(snap.p10_dihedral_deg), 3),
    }


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


def tet_radius_edge_ratio(pts: np.ndarray, tets: np.ndarray) -> np.ndarray:
    """beta990 (R111) — Shewchuk "radius-edge quality": circumradius / shortest edge.

    Sliver 검출에 강한 지표. 정사면체 ≈ 0.612, sliver → ∞.
    """
    tets = np.asarray(tets, dtype=np.int64)
    if tets.size == 0:
        return np.zeros(0)
    v = pts[tets]
    a, b, c, d = v[:, 0], v[:, 1], v[:, 2], v[:, 3]
    e1 = np.linalg.norm(b - a, axis=1)
    e2 = np.linalg.norm(c - a, axis=1)
    e3 = np.linalg.norm(d - a, axis=1)
    e4 = np.linalg.norm(c - b, axis=1)
    e5 = np.linalg.norm(d - b, axis=1)
    e6 = np.linalg.norm(d - c, axis=1)
    emin = np.minimum.reduce([e1, e2, e3, e4, e5, e6])
    # circumradius 근사: max edge / (2 sin(min_dihedral)) 는 비싸니 emax/2 사용.
    emax = np.maximum.reduce([e1, e2, e3, e4, e5, e6])
    R = emax / 2.0  # 근사 (정사면체 기준).
    return np.where(emin > 1e-30, R / emin, 1e6)


def tet_min_solid_angle_sr(pts: np.ndarray, tets: np.ndarray) -> np.ndarray:
    """beta1000 (R112) — 각 tet 의 4 vertex 중 최소 solid angle (steradian).

    정사면체 ≈ 0.551 sr, degenerate → 0.
    Van Oosterom–Strackee 공식.
    """
    tets = np.asarray(tets, dtype=np.int64)
    if tets.size == 0:
        return np.zeros(0)
    v = pts[tets]

    def _sa(o, p1, p2, p3):
        a = p1 - o; b = p2 - o; c = p3 - o
        na = np.linalg.norm(a, axis=1)
        nb = np.linalg.norm(b, axis=1)
        nc = np.linalg.norm(c, axis=1)
        num = np.abs(np.einsum("ij,ij->i", a, np.cross(b, c)))
        ab = np.einsum("ij,ij->i", a, b)
        bc = np.einsum("ij,ij->i", b, c)
        ca = np.einsum("ij,ij->i", c, a)
        denom = (
            na * nb * nc + ab * nc + bc * na + ca * nb
        )
        return 2.0 * np.arctan2(num, np.where(np.abs(denom) > 1e-30, denom, 1e-30))

    sa0 = _sa(v[:, 0], v[:, 1], v[:, 2], v[:, 3])
    sa1 = _sa(v[:, 1], v[:, 0], v[:, 2], v[:, 3])
    sa2 = _sa(v[:, 2], v[:, 0], v[:, 1], v[:, 3])
    sa3 = _sa(v[:, 3], v[:, 0], v[:, 1], v[:, 2])
    return np.minimum.reduce([sa0, sa1, sa2, sa3])


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
    target_max_aspect: float | None = None,
    improvement_eps: float = 0.005,
    window: int = 3,
    require_all: bool = False,
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
    # beta1040 (R113): multi-metric AND / OR.
    q_ok = last.min_q >= target_min_q
    dih_ok = (
        target_min_dihedral_deg is None
        or last.min_dihedral_deg >= float(target_min_dihedral_deg)
    )
    asp_ok = (
        target_max_aspect is None
        or last.max_aspect <= float(target_max_aspect)
    )
    if require_all:
        if q_ok and dih_ok and asp_ok:
            return True, "multi_target"
    else:
        if q_ok:
            return True, "target"
        if target_min_dihedral_deg is not None and dih_ok:
            return True, "dihedral_target"
        if target_max_aspect is not None and asp_ok:
            return True, "aspect_target"
    if len(history) >= window:
        recent = [h.min_q for h in history[-window:]]
        if max(recent) - min(recent) < improvement_eps:
            return True, "plateau"
    return False, ""


# ---------------------------------------------------------------------------
# RRR1 — quality histogram percentile helper (스켈레톤, default OFF)
# ---------------------------------------------------------------------------

_RRR1_QUALITY_HISTOGRAM: bool = False


def _quality_percentiles(pts: np.ndarray, tets: np.ndarray) -> dict:
    """Klingner 2008 §3.5 — quality histogram percentile helper.

    Returns
    -------
    dict with keys "shape_q", "aspect", "min_dihedral_deg", each mapping to
    a sub-dict {"p50", "p90", "p95", "p99"}.

    Note: called only when _RRR1_QUALITY_HISTOGRAM is True (RRR2 에서 활성).
    현재 호출 경로 없음 (스켈레톤).
    """
    pcts = [50, 90, 95, 99]

    sq = tet_shape_quality(pts, tets)
    asp = tet_aspect_ratio(pts, tets)
    dih = tet_min_dihedral_deg(pts, tets)

    def _pct_dict(arr: np.ndarray) -> dict:
        vals = np.percentile(arr, pcts)
        return {"p50": float(vals[0]), "p90": float(vals[1]),
                "p95": float(vals[2]), "p99": float(vals[3])}

    return {
        "shape_q": _pct_dict(sq),
        "aspect": _pct_dict(asp),
        "min_dihedral_deg": _pct_dict(dih),
    }
