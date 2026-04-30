"""AI-V1.3 — ML-based swap candidate scoring.

Klingner 2008 §4 swap-based sliver removal: 2-3 / 3-2 / 4-4 swap 후보들 중
quality 향상이 큰 것 우선 적용. 기존: 모든 후보 enumerate + Klingner 평가
(per-candidate O(K) 시간).

ML 접근: trained quality predictor 로 swap 후보 score 빠르게 평가, top-K 만
실제 enumeration. ~20-50× speedup target.

API:
    score_swap_candidates(model, swap_candidates) → np.ndarray (N,) score
    select_top_k_swaps(scores, k=10) → indices

현재 (skeleton): API + ranking algorithm. inference 는 ml_tet_smoothing_apply
의 model_pt 와 통합.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class SwapCandidate:
    """Single swap candidate metadata."""

    swap_type: str       # "2-3" | "3-2" | "4-4"
    pre_tets: np.ndarray  # (K, 4) before swap
    post_tets: np.ndarray  # (M, 4) after swap (K_new = different)
    edge_or_face: tuple   # edge (i, j) for 2-3/4-4, face (i, j, k) for 3-2


@dataclass
class SwapScoreResult:
    success: bool
    n_candidates: int = 0
    scores: np.ndarray | None = None
    top_k_indices: np.ndarray | None = None
    elapsed: float = 0.0
    backend: str = ""
    message: str = ""


def score_swap_candidates(
    model,
    pts: np.ndarray,
    candidates: list[SwapCandidate],
    *,
    use_cuda: bool = True,
) -> SwapScoreResult:
    """Score swap candidates using trained predictor.

    Algorithm:
        1. For each candidate: extract features for post_tets
        2. Predict per-tet quality
        3. Aggregate: min/mean over post_tets → swap score
        4. Higher score = better expected quality post-swap

    Args:
        model: load_trained_predictor 결과 (None → graceful skip).
        pts: (N, 3) all vertices.
        candidates: list of SwapCandidate.
        use_cuda: CUDA 시도.

    Returns:
        SwapScoreResult.
    """
    import time
    t0 = time.perf_counter()

    if model is None or len(candidates) == 0:
        return SwapScoreResult(
            success=False,
            n_candidates=len(candidates),
            backend="skip",
            message="model is None or empty candidates",
            elapsed=time.perf_counter() - t0,
        )

    try:
        from .training_data import extract_features_batch
    except ImportError:
        return SwapScoreResult(
            success=False,
            n_candidates=len(candidates),
            backend="skip",
            message="training_data unavailable",
            elapsed=time.perf_counter() - t0,
        )

    try:
        from .ml_tet_smoothing import predict_quality_batch
    except ImportError:
        return SwapScoreResult(
            success=False,
            n_candidates=len(candidates),
            backend="skip",
            message="predict_quality_batch unavailable",
            elapsed=time.perf_counter() - t0,
        )

    # For each candidate: predict post_tets quality, aggregate → score (min)
    scores = np.zeros(len(candidates), dtype=np.float32)
    for i, cand in enumerate(candidates):
        post = cand.post_tets
        if post.shape[0] == 0:
            scores[i] = 0.0
            continue
        try:
            c12, c8, _q_true = extract_features_batch(pts, post)
            preds = predict_quality_batch(model, c12, c8)
            scores[i] = float(preds.min())  # 최악 tet 의 quality
        except Exception:
            scores[i] = 0.0

    return SwapScoreResult(
        success=True,
        n_candidates=len(candidates),
        scores=scores,
        elapsed=time.perf_counter() - t0,
        backend="torch_predicted",
        message=f"scored {len(candidates)} candidates",
    )


def select_top_k_swaps(
    scores: np.ndarray,
    *,
    k: int = 10,
    min_score: float = 0.0,
) -> np.ndarray:
    """Select top-K swap candidates by score.

    Args:
        scores: (N,) per-candidate score.
        k: top count.
        min_score: 최소 score threshold (이 미만은 제외).

    Returns:
        (M,) top-K indices, M ≤ k.
    """
    if scores.size == 0:
        return np.zeros(0, dtype=np.int64)
    valid = scores >= min_score
    valid_idx = np.where(valid)[0]
    if valid_idx.size == 0:
        return np.zeros(0, dtype=np.int64)
    valid_scores = scores[valid_idx]
    sort_order = np.argsort(-valid_scores)  # descending
    top_idx = valid_idx[sort_order][:k]
    return top_idx.astype(np.int64)
