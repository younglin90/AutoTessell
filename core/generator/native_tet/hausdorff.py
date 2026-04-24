"""R134 — 결과 tet boundary vs 입력 surface 간 Hausdorff 거리.

output tet mesh 의 외곽 triangle 과 input surface F 사이의 2-sided
Hausdorff / mean / p95 거리 계산. BVH 기반 closest-point.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from core.utils.aabb import TriangleBVH


@dataclass
class HausdorffReport:
    h_forward: float          # sup_{p ∈ tet_boundary} d(p, input_surface)
    h_backward: float         # sup_{q ∈ input_surface} d(q, tet_boundary)
    h_symmetric: float        # max(forward, backward)
    mean_forward: float
    p95_forward: float
    n_sample_points_forward: int
    n_sample_points_backward: int


def _tet_boundary_faces(tets: np.ndarray) -> np.ndarray:
    """1-owner face 만 추출 (boundary)."""
    tets = np.asarray(tets, dtype=np.int64)
    if tets.size == 0:
        return np.zeros((0, 3), dtype=np.int64)
    faces = np.stack([
        tets[:, [0, 1, 2]], tets[:, [0, 1, 3]],
        tets[:, [0, 2, 3]], tets[:, [1, 2, 3]],
    ], axis=1).reshape(-1, 3)
    sorted_f = np.sort(faces, axis=1)
    # 1-owner 찾기.
    max_id = int(sorted_f.max()) + 1 if sorted_f.size else 1
    key = (
        sorted_f[:, 0].astype(np.int64) * max_id * max_id
        + sorted_f[:, 1].astype(np.int64) * max_id
        + sorted_f[:, 2].astype(np.int64)
    )
    _, inv, counts = np.unique(key, return_inverse=True, return_counts=True)
    is_boundary = counts[inv] == 1
    return faces[is_boundary]


def _sample_triangle_barycentric(
    V: np.ndarray, F: np.ndarray, *, n_per_triangle: int = 3,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """각 triangle 에서 barycentric 난수 샘플링."""
    if rng is None:
        rng = np.random.default_rng(0)
    if F.shape[0] == 0:
        return np.zeros((0, 3), dtype=np.float64)
    u = rng.random((F.shape[0], n_per_triangle))
    v = rng.random((F.shape[0], n_per_triangle))
    # barycentric mapping.
    over = (u + v) > 1
    u = np.where(over, 1 - u, u)
    v = np.where(over, 1 - v, v)
    w = 1.0 - u - v
    A = V[F[:, 0]][:, None, :]
    B = V[F[:, 1]][:, None, :]
    C = V[F[:, 2]][:, None, :]
    P = u[..., None] * A + v[..., None] * B + w[..., None] * C
    return P.reshape(-1, 3)


def hausdorff_vs_input(
    V_input: np.ndarray, F_input: np.ndarray,
    pts: np.ndarray, tets: np.ndarray,
    *,
    n_samples_per_tri: int = 2,
) -> HausdorffReport:
    """입력 표면 vs tet boundary 간 2-sided Hausdorff.

    샘플링 + BVH closest-point 로 근사. 정밀도는 n_samples_per_tri 조절.
    """
    V_input = np.asarray(V_input, dtype=np.float64)
    F_input = np.asarray(F_input, dtype=np.int64)
    pts = np.asarray(pts, dtype=np.float64)
    tets = np.asarray(tets, dtype=np.int64)

    B = _tet_boundary_faces(tets)
    if B.shape[0] == 0 or F_input.shape[0] == 0:
        return HausdorffReport(0.0, 0.0, 0.0, 0.0, 0.0, 0, 0)

    # forward: 샘플 on tet boundary → distance to input surface.
    P_f = _sample_triangle_barycentric(pts, B, n_per_triangle=n_samples_per_tri)
    bvh_in = TriangleBVH.build(V_input, F_input)
    d_f = bvh_in.unsigned_distances(P_f)

    # backward: 샘플 on input surface → distance to tet boundary.
    P_b = _sample_triangle_barycentric(
        V_input, F_input, n_per_triangle=n_samples_per_tri,
    )
    bvh_out = TriangleBVH.build(pts, B)
    d_b = bvh_out.unsigned_distances(P_b)

    h_f = float(d_f.max()) if d_f.size else 0.0
    h_b = float(d_b.max()) if d_b.size else 0.0
    mean_f = float(d_f.mean()) if d_f.size else 0.0
    p95_f = float(np.percentile(d_f, 95)) if d_f.size else 0.0

    return HausdorffReport(
        h_forward=h_f,
        h_backward=h_b,
        h_symmetric=max(h_f, h_b),
        mean_forward=mean_f,
        p95_forward=p95_f,
        n_sample_points_forward=int(P_f.shape[0]),
        n_sample_points_backward=int(P_b.shape[0]),
    )
