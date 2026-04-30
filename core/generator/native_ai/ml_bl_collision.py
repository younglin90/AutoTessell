"""AI-V3 — ML-based BL collision predict skeleton.

Pointwise T-Rex 의 핵심 challenge: BL prism extrusion 시 prism 들이 좁은 gap
에서 충돌. 현재 native_bl 은 geometric collision distance 계산 (느림, O(n²)).

ML 접근: per-vertex feature (local curvature, neighbor distance, normal angle)
입력 → predict gap_distance / collision_risk. 빠르게 critical region 식별.

현재 (skeleton, 2026-04): TorchModule stub + integration point.
실제 trained model 은 별도 카드:
    AI-V3.1: 5k vertex sample dataset 생성 (1주)
    AI-V3.2: predictor train + save (3일)
    AI-V3.3: native_bl _compute_collision_distance ML fast-path 통합 (1주)

Use case:
    기존 _compute_collision_distance: O(n_wall_v × n_wall_face) per-vertex tri
    distance check. 100k mesh 에서 ~30s.
    ML predict: O(n_wall_v) feature extraction + 1 forward pass. ~200ms.
    20-50× speedup target.
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
class BLCollisionPredictResult:
    """ML BL collision predict result."""

    success: bool
    n_vertices: int = 0
    n_high_risk: int = 0
    elapsed: float = 0.0
    backend: str = ""
    message: str = ""


def predict_bl_collision_distances(
    points: np.ndarray,
    wall_vert_indices: np.ndarray,
    wall_face_indices: np.ndarray,
    wall_face_verts: np.ndarray,
    *,
    use_cuda: bool = True,
) -> tuple[np.ndarray, BLCollisionPredictResult]:
    """ML-based BL collision distance prediction.

    현재 (skeleton): graceful skip → infinity distance 반환 (geometric path 사용).
    AI-V3.1~V3.3 카드 후 실제 ML inference.

    Args:
        points: (N, 3) all mesh vertex coords.
        wall_vert_indices: (Nw,) wall vertex indices.
        wall_face_indices: (Nf,) wall face indices.
        wall_face_verts: (Nf, 3) wall face vertex indices.
        use_cuda: CUDA 사용 시도.

    Returns:
        (collision_distance: (Nw,), BLCollisionPredictResult)
    """
    import time
    t0 = time.perf_counter()

    Nw = int(wall_vert_indices.shape[0])

    if not _torch_available():
        return (
            np.full(Nw, np.inf, dtype=np.float64),
            BLCollisionPredictResult(
                success=False,
                n_vertices=Nw,
                backend="skip",
                message="torch not available",
                elapsed=time.perf_counter() - t0,
            ),
        )

    try:
        import torch
        device_str = "cuda" if (use_cuda and torch.cuda.is_available()) else "cpu"
    except Exception:
        return (
            np.full(Nw, np.inf, dtype=np.float64),
            BLCollisionPredictResult(
                success=False,
                n_vertices=Nw,
                backend="skip",
                message="torch import error",
                elapsed=time.perf_counter() - t0,
            ),
        )

    # Skeleton: trained model 미배치.
    return (
        np.full(Nw, np.inf, dtype=np.float64),
        BLCollisionPredictResult(
            success=False,
            n_vertices=Nw,
            backend=f"torch_{device_str}_skeleton",
            message="ML model not yet trained (AI-V3.1 pending)",
            elapsed=time.perf_counter() - t0,
        ),
    )


def build_collision_predictor_skeleton():
    """torch BL collision predictor stub.

    Real implementation in AI-V3.1:
        - Input: 12-dim per-vertex feature (3 normal, 3 mean curvature dir,
          3 nearest face dist, 1 valence, 1 mean edge length, 1 area)
        - Hidden: 2 layers × 64 ReLU
        - Output: 1-dim log(gap_distance) sigmoid-scaled
        - Train: 5k Thingi10K wall vertices, MSE on log(true_gap)
    """
    if not _torch_available():
        return None
    import torch.nn as nn
    return nn.Sequential(
        nn.Linear(12, 64),
        nn.ReLU(),
        nn.Linear(64, 64),
        nn.ReLU(),
        nn.Linear(64, 1),
    )
