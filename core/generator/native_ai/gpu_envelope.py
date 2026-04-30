"""C8 (2.1) — GPU envelope check kernel skeleton.

fTetWild envelope check (point-to-surface distance) 의 GPU 가속화.
현재 (CPU): scipy.spatial.cKDTree + per-query distance. 100k point ~5s.
target (GPU): torch tensor batch + cuda kernel. 100k point ~50ms (100× speedup).

현재 (skeleton, 2026-04): torch tensor migration only — graceful CPU fallback.
실제 CUDA kernel 은 별도 카드:
    C8-2.1.1: torch.cdist tensor batch (CPU+GPU) — 본 카드 (10-20× CPU on torch)
    C8-2.1.2: custom CUDA kernel (triton or .cu) — 50-100× GPU
    C8-2.1.3: KD-tree GPU build (gpu-octree research) — 200-500×

CLAUDE.md 정책 준수:
    - torch (이미 의존) 만 사용
    - cuda 없으면 graceful CPU fallback
    - 외부 lib 신규 의존 0
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


_TORCH_AVAILABLE: bool | None = None


def _torch_available() -> bool:
    global _TORCH_AVAILABLE
    if _TORCH_AVAILABLE is not None:
        return _TORCH_AVAILABLE
    try:
        import torch  # noqa: F401
        _TORCH_AVAILABLE = True
    except ImportError:
        _TORCH_AVAILABLE = False
    return _TORCH_AVAILABLE


@dataclass
class GPUEnvelopeResult:
    """GPU envelope check result."""

    success: bool
    n_query: int = 0
    n_inside: int = 0
    n_outside: int = 0
    elapsed: float = 0.0
    backend: str = ""               # "torch_cuda" / "torch_cpu" / "skip"
    speedup_vs_cpu_estimate: float = 1.0
    message: str = ""


def gpu_envelope_check(
    query_pts: np.ndarray,
    surf_pts: np.ndarray,
    surf_faces: np.ndarray,
    eps: float,
    *,
    use_cuda: bool = True,
    batch_size: int = 8192,
) -> tuple[np.ndarray, GPUEnvelopeResult]:
    """Per-query envelope inside-check (GPU-accelerated when available).

    현재 (skeleton): torch.cdist 기반 batched distance compute.
    실제 CUDA kernel 은 C8-2.1.2 카드.

    Args:
        query_pts: (N, 3) query 점.
        surf_pts: (M, 3) surface vertex.
        surf_faces: (F, 3) surface face index.
        eps: envelope thickness.
        use_cuda: CUDA 시도 여부.
        batch_size: query batching size (메모리 한계).

    Returns:
        (inside: (N,) bool, GPUEnvelopeResult)
    """
    import time
    t0 = time.perf_counter()

    N = int(query_pts.shape[0])

    if not _torch_available():
        # torch 없음 — graceful skip, return all-True (envelope 통과 가정).
        return (
            np.ones(N, dtype=bool),
            GPUEnvelopeResult(
                success=False,
                n_query=N,
                backend="skip",
                message="torch not available — fallback to CPU envelope path",
                elapsed=time.perf_counter() - t0,
            ),
        )

    try:
        import torch
        device_str = "cuda" if (use_cuda and torch.cuda.is_available()) else "cpu"
        device = torch.device(device_str)
    except Exception as exc:
        return (
            np.ones(N, dtype=bool),
            GPUEnvelopeResult(
                success=False,
                n_query=N,
                backend="skip",
                message=f"torch error: {exc!s:.80}",
                elapsed=time.perf_counter() - t0,
            ),
        )

    # Skeleton: simple point-to-vertex 최소거리 ≤ eps check.
    # Real implementation in C8-2.1.2: point-to-triangle 정확 거리 (CUDA kernel).
    surf_t = torch.tensor(surf_pts, dtype=torch.float32, device=device)
    inside = np.zeros(N, dtype=bool)
    n_in = 0
    eps_sq = float(eps) ** 2

    for s in range(0, N, batch_size):
        e = min(s + batch_size, N)
        q_t = torch.tensor(query_pts[s:e], dtype=torch.float32, device=device)
        # (B, M) pairwise squared distance
        d_sq = torch.cdist(q_t, surf_t, p=2.0) ** 2
        # min over surface vertices
        min_d_sq, _ = d_sq.min(dim=1)
        inside_b = (min_d_sq <= eps_sq).cpu().numpy()
        inside[s:e] = inside_b
        n_in += int(inside_b.sum())

    speedup_estimate = 10.0 if device_str == "cuda" else 2.0

    return (
        inside,
        GPUEnvelopeResult(
            success=True,
            n_query=N,
            n_inside=n_in,
            n_outside=N - n_in,
            backend=f"torch_{device_str}",
            speedup_vs_cpu_estimate=speedup_estimate,
            message=f"GPU envelope check via torch.cdist ({device_str})",
            elapsed=time.perf_counter() - t0,
        ),
    )
