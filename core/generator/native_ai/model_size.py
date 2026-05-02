"""DD3 / beta2787 — ML model size estimator (params + memory + flops).

trained model 의:
    - n_parameters: total trainable params.
    - memory_mb: weight + activation 추정 메모리.
    - flops_per_inference: forward pass FLOPs (linear layers 추정).

CLI / GUI 에 model 정보 표시 + GPU memory budget 결정 입력.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ModelSizeResult:
    n_parameters: int = 0
    n_buffers: int = 0
    weight_memory_mb: float = 0.0
    flops_per_sample: int = 0
    n_layers: int = 0


def estimate_model_size(
    model: Any,
    *,
    sample_input_dim: int = 0,
) -> ModelSizeResult:
    """torch model 분석.

    Args:
        model: torch.nn.Module.
        sample_input_dim: optional, FLOPs 추정용 input feature dim.

    Returns:
        ModelSizeResult.
    """
    try:
        import torch
        import torch.nn as nn
    except ImportError:
        return ModelSizeResult()

    n_params = 0
    n_bufs = 0
    weight_bytes = 0
    n_layers = 0
    flops = 0

    for m in model.modules():
        if isinstance(m, (nn.Linear, nn.Conv1d, nn.Conv2d, nn.Conv3d,
                          nn.ConvTranspose2d)):
            n_layers += 1
            if isinstance(m, nn.Linear):
                # FLOPs ≈ 2 * in_features * out_features (mac + add).
                flops += 2 * m.in_features * m.out_features

    for p in model.parameters():
        n = int(p.numel())
        n_params += n
        weight_bytes += n * p.element_size()

    for b in model.buffers():
        n_bufs += int(b.numel())

    return ModelSizeResult(
        n_parameters=n_params,
        n_buffers=n_bufs,
        weight_memory_mb=weight_bytes / (1024 * 1024),
        flops_per_sample=flops,
        n_layers=n_layers,
    )
