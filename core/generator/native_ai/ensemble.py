"""AA3 / beta2746 — ML model ensemble averager.

여러 trained model 의 prediction 을 평균 → 단일 결과.
- variance 감소.
- uncertainty estimate (std across models).

simple equal-weight average / weighted (by val_loss inverse) 두 모드.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass
class EnsembleResult:
    n_models: int = 0
    n_samples: int = 0
    mean: NDArray[np.float64] | None = None
    std: NDArray[np.float64] | None = None
    weights: NDArray[np.float64] | None = None


def ensemble_predictions(
    preds_list: list[NDArray[np.float64]],
    *,
    weights: list[float] | None = None,
    val_losses: list[float] | None = None,
) -> EnsembleResult:
    """N model 의 prediction 평균.

    Args:
        preds_list: each (M, K) array. shape consistency 필수.
        weights: explicit weight (sum=1 강제 안 함, normalize 함).
        val_losses: weights None 일 때, 1/val_loss 비례 weight.

    Returns:
        EnsembleResult (mean, std, weights).
    """
    if not preds_list:
        return EnsembleResult()

    arrs = [np.asarray(p, dtype=np.float64) for p in preds_list]
    shapes = {a.shape for a in arrs}
    if len(shapes) != 1:
        raise ValueError(f"shape mismatch: {shapes}")

    n_models = len(arrs)
    stacked = np.stack(arrs, axis=0)  # (N, M, K).

    if weights is not None:
        w = np.asarray(weights, dtype=np.float64)
    elif val_losses is not None:
        w = 1.0 / np.maximum(np.asarray(val_losses, dtype=np.float64), 1e-12)
    else:
        w = np.ones(n_models, dtype=np.float64)

    if w.shape[0] != n_models:
        raise ValueError(f"weights len {w.shape[0]} != n_models {n_models}")
    w = w / w.sum()

    # weighted mean along axis 0.
    mean = (stacked * w[:, None, None]).sum(axis=0)  # (M, K).
    # std (unweighted across models — uncertainty estimate).
    std = stacked.std(axis=0)

    return EnsembleResult(
        n_models=n_models,
        n_samples=int(arrs[0].shape[0]),
        mean=mean,
        std=std,
        weights=w,
    )
