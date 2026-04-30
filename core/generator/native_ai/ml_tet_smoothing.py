"""AI-V1 — ML-based tet quality smoothing skeleton.

ML-augmented tet quality optimization. 핵심 아이디어:

1. tet quality predictor (small MLP) — input: tet 4 vertex 3D coords (12-dim) +
   1-ring context features → output: predicted Klingner mean-ratio quality.
2. swap candidate scorer — 2-3 / 3-2 / 4-4 swap 후보의 expected quality
   향상을 ML 로 빠르게 score, top-K 만 실제 enumeration.
3. neural smoothing direction — vertex 의 optimal displacement 를 단일 forward
   pass 로 예측 (gradient descent 대체).

현재 (skeleton, 2026-04): TorchModule stub + integration point.
실제 trained model 은 별도 카드:
    AI-V1.1: 10k tet sample dataset 생성 + train (1주)
    AI-V1.2: predictor model save/load + inference 통합 (3일)
    AI-V1.3: swap candidate ML score + Klingner §4 path 통합 (1주)

CLAUDE.md 정책 준수:
    - torch (이미 의존) 만 사용
    - cpu/cuda 자동 감지, GPU 없으면 graceful skip
    - trained model 은 hash-checked download (별도 카드)
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


_TORCH_AVAILABLE: bool | None = None


def _torch_available() -> bool:
    """torch import 여부 lazy check."""
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
class MLTetSmoothingResult:
    """ML smoothing result."""

    success: bool
    n_smoothed: int = 0
    n_swap_attempted: int = 0
    n_swap_applied: int = 0
    avg_q_before: float = 0.0
    avg_q_after: float = 0.0
    elapsed: float = 0.0
    backend: str = ""              # "torch_cpu" / "torch_cuda" / "skip"
    message: str = ""


def load_trained_predictor(model_pt: str, device=None):
    """Trained quality predictor 로드 (AI-V1.2).

    O6 / beta2665 — architecture metadata detection (v1 vs v3 residual).
    checkpoint 의 'architecture' 필드 기반으로 적절한 model 빌드.

    Args:
        model_pt: trained .pt 파일 경로.
        device: torch device. None → auto.

    Returns:
        torch.nn.Module 또는 None (실패 시 — 로깅으로 reason 노출).
    """
    if not _torch_available():
        return None
    import torch
    from pathlib import Path
    if not Path(model_pt).exists():
        return None
    if device is None:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    try:
        ckpt = torch.load(model_pt, map_location=device, weights_only=False)
    except Exception:
        return None

    # O6: architecture detection.
    arch = "v1"
    if isinstance(ckpt, dict):
        arch = str(ckpt.get("architecture", "v1"))

    import torch.nn as nn
    if arch in ("v3", "residual"):
        try:
            from .train_predictor import _build_predictor_v3_residual
            model = _build_predictor_v3_residual(input_dim=20)
            if model is None:
                return None
            model = model.to(device)
        except Exception:
            return None
    else:
        model = nn.Sequential(
            nn.Linear(20, 64),
            nn.ReLU(),
            nn.Linear(64, 64),
            nn.ReLU(),
            nn.Linear(64, 1),
            nn.Sigmoid(),
        ).to(device)

    try:
        if isinstance(ckpt, dict) and "state_dict" in ckpt:
            model.load_state_dict(ckpt["state_dict"])
        else:
            model.load_state_dict(ckpt)
    except Exception:
        # state_dict mismatch — likely architecture diff.
        return None
    model.eval()
    return model


def predict_quality_batch(
    model,
    coords: np.ndarray,
    context: np.ndarray,
    *,
    use_cuda: bool = True,
) -> np.ndarray:
    """Trained predictor 를 사용해 quality 예측 (AI-V1.2).

    Args:
        model: load_trained_predictor 의 결과.
        coords: (K, 12).
        context: (K, 8).
        use_cuda: CUDA 시도.

    Returns:
        (K,) predicted quality ∈ (0, 1).
    """
    if model is None or not _torch_available():
        return np.zeros(coords.shape[0], dtype=np.float32)
    import torch
    device = next(model.parameters()).device
    X = np.concatenate([coords.astype(np.float32), context.astype(np.float32)], axis=1)
    X_t = torch.tensor(X, device=device)
    with torch.no_grad():
        y = model(X_t).cpu().numpy().reshape(-1)
    return y.astype(np.float32)


def ml_tet_smoothing_apply(
    pts: np.ndarray,
    tets: np.ndarray,
    *,
    quality_threshold: float = 0.1,
    max_iter: int = 5,
    use_cuda: bool = True,
    model_pt: str | None = None,
) -> tuple[np.ndarray, np.ndarray, MLTetSmoothingResult]:
    """ML-augmented tet smoothing entry point.

    현재 (skeleton): torch 없거나 trained model 미배치 → graceful skip.
    실제 ML 통합은 AI-V1.1~V1.3 카드에서.

    Args:
        pts: (N, 3) tet vertex coordinates.
        tets: (T, 4) tet topology.
        quality_threshold: 이 값 이하의 tet 만 smoothing 대상.
        max_iter: 외부 iteration 수.
        use_cuda: CUDA 사용 시도.

    Returns:
        (pts_out, tets_out, MLTetSmoothingResult)
    """
    import time
    t0 = time.perf_counter()

    if not _torch_available():
        return pts, tets, MLTetSmoothingResult(
            success=False,
            backend="skip",
            message="torch not available",
            elapsed=time.perf_counter() - t0,
        )

    try:
        import torch
        device_str = "cuda" if (use_cuda and torch.cuda.is_available()) else "cpu"
    except Exception:
        return pts, tets, MLTetSmoothingResult(
            success=False,
            backend="skip",
            message="torch import error",
            elapsed=time.perf_counter() - t0,
        )

    # AI-V1.C / beta2588 — production smoothing path (model_pt provided 시).
    # Algorithm: 1-ring Laplacian candidate displacement + ML quality predictor
    # 로 채택 여부 결정. monotone guard (worst quality 하락 ≤ 0.015) 가 final.
    import os as _os
    _model_path = model_pt or _os.environ.get("AUTO_TESSELL_ML_SMOOTH_MODEL", "")
    if not _model_path:
        return pts, tets, MLTetSmoothingResult(
            success=False,
            backend=f"torch_{device_str}_skeleton",
            message="model not provided (set AUTO_TESSELL_ML_SMOOTH_MODEL)",
            elapsed=time.perf_counter() - t0,
        )

    try:
        from .training_data import extract_features_batch
        from core.generator.native_tet.quality import tet_shape_quality
    except ImportError as exc:
        return pts, tets, MLTetSmoothingResult(
            success=False,
            backend=f"torch_{device_str}_skip",
            message=f"deps missing: {exc!s:.60}",
            elapsed=time.perf_counter() - t0,
        )

    model = load_trained_predictor(_model_path, device=device_str)
    if model is None:
        return pts, tets, MLTetSmoothingResult(
            success=False,
            backend=f"torch_{device_str}_skip",
            message=f"model load failed: {_model_path[:60]}",
            elapsed=time.perf_counter() - t0,
        )

    pts_cur = pts.copy()
    q_pre = tet_shape_quality(pts_cur, tets)
    pre_min = float(q_pre.min())
    pre_mean = float(q_pre.mean())

    # Candidate: interior vertex 1-ring centroid 평균 (Laplacian displacement).
    n_v = pts_cur.shape[0]
    flat_v = tets.reshape(-1)
    centroids = pts_cur[tets].mean(axis=1)
    flat_c = np.repeat(centroids, 4, axis=0)
    sums = np.zeros((n_v, 3), dtype=np.float64)
    counts = np.zeros(n_v, dtype=np.int64)
    np.add.at(sums, flat_v, flat_c)
    np.add.at(counts, flat_v, 1)
    nz = counts > 0
    targets = np.zeros_like(sums)
    targets[nz] = sums[nz] / counts[nz, None]
    pts_cand = pts_cur.copy()
    pts_cand[nz] = 0.5 * (pts_cur[nz] + targets[nz])

    # ML predictor query 후보 vs 현재. extract_features_batch returns
    # (coords (K,12), context (K,8), qualities (K,)).
    coords_cur, ctx_cur, _ = extract_features_batch(pts_cur, tets)
    coords_cand, ctx_cand, _ = extract_features_batch(pts_cand, tets)
    pred_cur = predict_quality_batch(model, coords_cur, ctx_cur, use_cuda=(device_str == "cuda"))
    pred_cand = predict_quality_batch(model, coords_cand, ctx_cand, use_cuda=(device_str == "cuda"))
    if pred_cur is None or pred_cand is None:
        return pts, tets, MLTetSmoothingResult(
            success=False,
            backend=f"torch_{device_str}_skip",
            message="predictor inference failed",
            elapsed=time.perf_counter() - t0,
        )
    # 예측이 향상되는 vertex 만 채택. 단순 majority vote.
    cand_better = (pred_cand >= pred_cur)
    n_smoothed = int(cand_better.sum())
    if n_smoothed == 0:
        return pts, tets, MLTetSmoothingResult(
            success=False, n_smoothed=0,
            avg_q_before=pre_mean, avg_q_after=pre_mean,
            backend=f"torch_{device_str}",
            message="no ML-improving vertex found",
            elapsed=time.perf_counter() - t0,
        )

    # apply: cand_better tets 의 vertex 만 cand 위치로 이동.
    move_mask = np.zeros(n_v, dtype=bool)
    move_mask[tets[cand_better]] = True
    pts_new = pts_cur.copy()
    pts_new[move_mask] = pts_cand[move_mask]
    q_post = tet_shape_quality(pts_new, tets)
    post_min = float(q_post.min())
    post_mean = float(q_post.mean())
    accepted = (pre_min - post_min <= 0.015) and (post_mean >= pre_mean - 1e-12)
    if not accepted:
        return pts, tets, MLTetSmoothingResult(
            success=False, n_smoothed=int(move_mask.sum()),
            avg_q_before=pre_mean, avg_q_after=post_mean,
            backend=f"torch_{device_str}",
            message="monotone guard rejected",
            elapsed=time.perf_counter() - t0,
        )
    return pts_new, tets, MLTetSmoothingResult(
        success=True,
        n_smoothed=int(move_mask.sum()),
        avg_q_before=pre_mean, avg_q_after=post_mean,
        backend=f"torch_{device_str}",
        message=f"ML smoothed {int(move_mask.sum())} verts, mean {pre_mean:.4f} → {post_mean:.4f}",
        elapsed=time.perf_counter() - t0,
    )


def build_quality_predictor_skeleton():
    """torch quality predictor stub (architecture sketch).

    Real implementation in AI-V1.1:
        - MLP: input (12-dim tet coords + 8-dim 1-ring stats) → 1-dim quality.
        - Train on 10k Klingner-evaluated tets from Thingi10K.
        - L1 loss, Adam, batch=512, 50 epochs.
    """
    if not _torch_available():
        return None
    import torch.nn as nn
    return nn.Sequential(
        nn.Linear(20, 64),
        nn.ReLU(),
        nn.Linear(64, 64),
        nn.ReLU(),
        nn.Linear(64, 1),
        nn.Sigmoid(),  # output ∈ (0, 1) matching Klingner mean-ratio range
    )
