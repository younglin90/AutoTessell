"""C8-2.1.2 — GPU point-to-triangle accurate distance kernel.

기존 gpu_envelope.py 는 point-to-vertex 최소거리만 (approx). 정확한
envelope check 는 point-to-triangle 거리 필요.

Algorithm: Eberly's "Distance Between Point and Triangle in 3D" — 7-region
case分.

현재 (skeleton): torch tensor batch 구현 (CPU/CUDA). 진짜 .cu kernel 은
별도 카드 (다월).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class GPUPointToTriResult:
    success: bool
    n_query: int = 0
    n_inside: int = 0
    elapsed: float = 0.0
    backend: str = ""
    speedup_estimate: float = 1.0
    message: str = ""


def gpu_point_to_tri_distance(
    query_pts: np.ndarray,
    surf_pts: np.ndarray,
    surf_faces: np.ndarray,
    *,
    use_cuda: bool = True,
    batch_size: int = 4096,
) -> tuple[np.ndarray, GPUPointToTriResult]:
    """Per-query 최소 point-to-triangle distance.

    torch.cdist 는 vertex 거리만; 본 함수는 모든 triangle 에 대해 정확한
    point-on-triangle projection distance.

    Args:
        query_pts: (N, 3).
        surf_pts: (M, 3).
        surf_faces: (F, 3).
        use_cuda: CUDA 시도.
        batch_size: query batching.

    Returns:
        (min_dist: (N,), GPUPointToTriResult).
    """
    import time
    t0 = time.perf_counter()
    N = int(query_pts.shape[0])
    F = int(surf_faces.shape[0])

    try:
        import torch
        device_str = "cuda" if (use_cuda and torch.cuda.is_available()) else "cpu"
        device = torch.device(device_str)
    except Exception:
        return (
            np.full(N, np.inf, dtype=np.float64),
            GPUPointToTriResult(
                success=False, n_query=N, backend="skip",
                message="torch unavailable",
                elapsed=time.perf_counter() - t0,
            ),
        )

    if F == 0:
        return (
            np.full(N, np.inf, dtype=np.float64),
            GPUPointToTriResult(
                success=False, n_query=N, backend=f"torch_{device_str}",
                message="empty faces", elapsed=time.perf_counter() - t0,
            ),
        )

    surf_t = torch.tensor(surf_pts, dtype=torch.float32, device=device)
    faces_t = torch.tensor(surf_faces, dtype=torch.int64, device=device)
    A = surf_t[faces_t[:, 0]]  # (F, 3)
    B = surf_t[faces_t[:, 1]]
    C = surf_t[faces_t[:, 2]]
    AB = B - A
    AC = C - A

    out = np.full(N, np.inf, dtype=np.float64)
    # Eberly 7-region precompute
    a_dot = (AB * AB).sum(-1)                # (F,)
    b_dot = (AB * AC).sum(-1)
    c_dot = (AC * AC).sum(-1)
    det_F = a_dot * c_dot - b_dot * b_dot     # (F,)
    det_safe = torch.clamp(det_F, min=1e-30)
    inv_det = 1.0 / det_safe
    for batch_s in range(0, N, batch_size):
        batch_e = min(batch_s + batch_size, N)
        q_t = torch.tensor(query_pts[batch_s:batch_e], dtype=torch.float32, device=device)
        # AP = (B, F, 3) = query - A
        AP = q_t[:, None, :] - A[None, :, :]
        d_pa_ab = (AP * AB[None, :, :]).sum(-1)             # (B, F)
        d_pa_ac = (AP * AC[None, :, :]).sum(-1)
        # signed -d / -e from Eberly: s = b·d - a·e, t = b·e - c·d → use simpler form
        s = (b_dot[None, :] * d_pa_ac - c_dot[None, :] * d_pa_ab) * (-inv_det[None, :])
        t = (b_dot[None, :] * d_pa_ab - a_dot[None, :] * d_pa_ac) * (-inv_det[None, :])
        # Initialize w/ projection params (region 0: inside triangle)
        u = torch.zeros_like(s)
        v = torch.zeros_like(t)
        inside = (s >= 0) & (t >= 0) & (s + t <= 1)
        u = torch.where(inside, s, u)
        v = torch.where(inside, t, v)
        # Region edges: clamp to triangle boundary.
        # Region 1: s < 0, t < 0 → vertex A
        v_A = (s < 0) & (t < 0)
        u = torch.where(v_A, torch.zeros_like(u), u)
        v = torch.where(v_A, torch.zeros_like(v), v)
        # Region 2: s >= 0, t < 0 → edge AB. clamp s to [0,1], v=0
        e_AB = (~inside) & (~v_A) & (t < 0)
        u_AB = torch.clamp(d_pa_ab / torch.clamp(a_dot[None, :], min=1e-30), 0.0, 1.0)
        u = torch.where(e_AB, u_AB, u)
        v = torch.where(e_AB, torch.zeros_like(v), v)
        # Region 3: s < 0, t >= 0 → edge AC. clamp t to [0,1], u=0
        e_AC = (~inside) & (~v_A) & (~e_AB) & (s < 0)
        v_AC = torch.clamp(d_pa_ac / torch.clamp(c_dot[None, :], min=1e-30), 0.0, 1.0)
        u = torch.where(e_AC, torch.zeros_like(u), u)
        v = torch.where(e_AC, v_AC, v)
        # Region 4: s + t > 1 → edge BC.
        # parameterize edge BC by r ∈ [0,1]: P(r) = B + r*(C-B). Closest r:
        # r = (CmB · (Q - B)) / (CmB·CmB)
        rest = (~inside) & (~v_A) & (~e_AB) & (~e_AC)
        if rest.any():
            CmB = AC - AB                              # (F, 3)
            BP = q_t[:, None, :] - (A[None, :, :] + AB[None, :, :])  # = Q - B
            r = (BP * CmB[None, :, :]).sum(-1) / torch.clamp(
                (CmB * CmB).sum(-1)[None, :], min=1e-30,
            )
            r = torch.clamp(r, 0.0, 1.0)
            u_BC = 1.0 - r
            v_BC = r
            u = torch.where(rest, u_BC, u)
            v = torch.where(rest, v_BC, v)
        closest = A[None, :, :] + u[..., None] * AB[None, :, :] + v[..., None] * AC[None, :, :]
        d_sq = ((q_t[:, None, :] - closest) ** 2).sum(-1)
        min_d, _ = d_sq.min(dim=1)
        out[batch_s:batch_e] = torch.sqrt(min_d).cpu().numpy()

    return (
        out,
        GPUPointToTriResult(
            success=True,
            n_query=N,
            backend=f"torch_{device_str}",
            speedup_estimate=20.0 if device_str == "cuda" else 3.0,
            message=f"point-to-tri batch via torch ({device_str})",
            elapsed=time.perf_counter() - t0,
        ),
    )
