"""CC3 / beta2760 — ML weight magnitude pruning.

trained model 의 |w| < threshold 인 weight 를 0 으로 → sparse model.
- 모델 size 감소 (weight zero 압축).
- inference 속도 향상 (sparse matmul 시 — torch.compile 로).

torch 의존. 학습 후 / inference 직전에 적용.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class PruneResult:
    n_layers: int = 0
    total_params: int = 0
    pruned_params: int = 0
    sparsity: float = 0.0
    threshold: float = 0.0


def prune_weights_by_magnitude(
    model: Any,
    *,
    threshold: float | None = None,
    sparsity: float | None = None,
) -> PruneResult:
    """|w| < threshold 인 weight → 0.

    Args:
        model: torch.nn.Module.
        threshold: 절대값 임계 (둘 중 하나만 사용).
        sparsity: 목표 sparsity (0.0 ~ 1.0). 자동으로 threshold 계산.

    Returns:
        PruneResult.
    """
    try:
        import torch
    except ImportError:
        return PruneResult()

    if threshold is None and sparsity is None:
        threshold = 1e-3   # default.

    # 모든 weight 모아서 절대값 분포 → threshold 결정.
    if sparsity is not None:
        all_w = []
        for p in model.parameters():
            if p.requires_grad and p.dim() >= 2:
                all_w.append(p.detach().abs().reshape(-1))
        if all_w:
            stacked = torch.cat(all_w)
            k = int(sparsity * stacked.numel())
            if 0 < k < stacked.numel():
                kth = torch.kthvalue(stacked, k).values.item()
                threshold = kth
            else:
                threshold = 0.0

    n_layers = 0
    total = 0
    pruned = 0

    for p in model.parameters():
        if not p.requires_grad or p.dim() < 2:
            continue
        n_layers += 1
        total += int(p.numel())
        with torch.no_grad():
            mask = p.abs() < threshold
            n_pruned_layer = int(mask.sum().item())
            p[mask] = 0
            pruned += n_pruned_layer

    return PruneResult(
        n_layers=n_layers,
        total_params=total,
        pruned_params=pruned,
        sparsity=float(pruned) / max(total, 1),
        threshold=float(threshold) if threshold else 0.0,
    )
