"""CYLSKEW1 (beta2822) — near-wall offset-ring Delaunay seed points.

Garimella & Shashkov 2003 §3 offset-surface node placement, adapted as a
*seeding-only* diagnostic: 각 surface vertex 를 각도가중 내향(outward-flip)
법선을 따라 안쪽으로 offset 시킨 후보를 winding-number inside test +
min-dist 가드로 걸러 Delaunay 시드 후보 목록을 만든다. default OFF —
`AUTO_TESSELL_TET_OFFSET_RING=1` 일 때만 mesher.py 훅에서 호출된다.
"""
from __future__ import annotations

import numpy as np

from core.utils.geometry import inside_generalized_winding_number


def offset_ring_seed_points(
    V: np.ndarray, F: np.ndarray, target_edge_length: float,
    depth_frac: float = 0.5,
    rel_dedup: float = 1e-3, surf_floor: float = 0.25,
) -> tuple[np.ndarray, dict[str, float]]:
    """표면정점마다 내향 offset 후보를 만들어 winding/min-dist 가드로 필터."""
    V = np.asarray(V, dtype=np.float64)
    F = np.asarray(F, dtype=np.int64)
    n_v = V.shape[0]
    if n_v == 0 or F.shape[0] == 0 or F.shape[1] != 3:
        return np.zeros((0, 3), dtype=np.float64), {
            "n_cand": 0, "n_inserted": 0, "min_dist": 0.0,
        }

    v0 = V[F[:, 0]]; v1 = V[F[:, 1]]; v2 = V[F[:, 2]]
    cross = np.cross(v1 - v0, v2 - v0)
    area2 = np.linalg.norm(cross, axis=1)
    safe = area2 >= 1e-30
    n_arr = np.zeros_like(cross)
    n_arr[safe] = cross[safe] / area2[safe, None]

    # outward sign 교정 — mesh centroid 기준 (내향법선은 이 outward 를 뒤집어 사용).
    centroid = V.mean(axis=0)
    face_centroid = (v0 + v1 + v2) / 3.0
    dot = np.einsum("ij,ij->i", face_centroid - centroid, n_arr)
    n_arr[dot < 0] *= -1.0

    def _ang(a: np.ndarray, b: np.ndarray) -> np.ndarray:
        den = np.maximum(np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1), 1e-30)
        cosv = np.clip(np.einsum("ij,ij->i", a, b) / den, -1.0, 1.0)
        return np.arccos(cosv)

    ang0 = _ang(v1 - v0, v2 - v0)
    ang1 = _ang(v0 - v1, v2 - v1)
    ang2 = _ang(v0 - v2, v1 - v2)
    accum = np.zeros((n_v, 3), dtype=np.float64)
    np.add.at(accum, F[:, 0], n_arr * ang0[:, None])
    np.add.at(accum, F[:, 1], n_arr * ang1[:, None])
    np.add.at(accum, F[:, 2], n_arr * ang2[:, None])
    norms = np.linalg.norm(accum, axis=1)
    valid = norms > 1e-12
    n_hat = np.zeros_like(accum)
    n_hat[valid] = accum[valid] / norms[valid, None]

    depth = float(depth_frac) * float(target_edge_length)
    dedup_thr = float(rel_dedup) * float(target_edge_length)
    cand = V - depth * n_hat  # outward n_hat 을 빼면 내향 offset.
    cand = cand[valid]
    n_cand = int(cand.shape[0])

    inside = inside_generalized_winding_number(cand, V, F)
    cand = cand[inside]

    accepted: list[np.ndarray] = []
    min_dist = float("inf")
    for p in cand:
        d_v = float(np.linalg.norm(V - p, axis=1).min()) if V.shape[0] else np.inf
        if d_v < float(surf_floor) * depth:
            continue
        d_a = float(np.linalg.norm(np.asarray(accepted) - p, axis=1).min()) if accepted else np.inf
        d = min(d_v, d_a)
        if d < dedup_thr:
            continue
        accepted.append(p)
        min_dist = min(min_dist, d)

    P = np.asarray(accepted, dtype=np.float64).reshape(-1, 3)
    info = {
        "n_cand": n_cand,
        "n_inserted": int(P.shape[0]),
        "min_dist": round(min_dist, 8) if P.shape[0] else 0.0,
        "dedup_thr": dedup_thr,
        "surf_floor": float(surf_floor),
    }
    return P, info


def select_offset_ring_variant(
    seeds: np.ndarray,
    off_metrics: dict[str, float],
    on_metrics: dict[str, float],
    skew_tol: float = 0.0,
    nonortho_tol: float = 2.0,
) -> tuple[np.ndarray, dict[str, object]]:
    """CYLSKEW3 — offset-ring seed 채택을 monotone dominance 로 결정하는 순수 helper.

    두 metric dict(`{"skew":.., "nonortho":..}`)를 비교해 seeds 를 그대로 채택할지
    빈 배열로 revert 할지 결정한다. **caller 미연결(스켈레톤) — default OFF 불변.**
    """

    def _get(m: dict[str, float] | None, key: str) -> float:
        if m is None:
            return float("nan")
        v = m.get(key)
        if v is None:
            return float("nan")
        return float(v)

    off_skew, off_nonortho = _get(off_metrics, "skew"), _get(off_metrics, "nonortho")
    on_skew, on_nonortho = _get(on_metrics, "skew"), _get(on_metrics, "nonortho")

    vals = (off_skew, off_nonortho, on_skew, on_nonortho)
    if any(np.isnan(vals)):
        keep = False
    else:
        keep = (on_skew <= off_skew + skew_tol) and (
            on_nonortho <= off_nonortho + nonortho_tol
        )

    if keep:
        return np.asarray(seeds, dtype=np.float64), {"decision": "keep"}
    return np.zeros((0, 3), dtype=np.float64), {"decision": "revert"}
