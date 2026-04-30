"""U4 / beta2705 — ML model inference warmup + cache.

torch model 의 첫 inference 는 cudnn benchmark / kernel cache miss 로 지연.
warmup() 으로 dummy input 한 번 통과 → 이후 latency 안정화.
+ 모델 cache (path → loaded model) — 같은 .pt 반복 load 회피.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


_MODEL_CACHE: dict[str, Any] = {}


def warmup_model(
    model: Any,
    input_dim: int,
    *,
    n_iter: int = 3,
    batch: int = 4,
    use_cuda: bool = False,
) -> dict:
    """dummy forward 으로 model warmup.

    Args:
        model: torch.nn.Module.
        input_dim: input feature dim.
        n_iter: warmup iterations.
        batch: dummy batch size.
        use_cuda: True 면 device='cuda'.

    Returns:
        {"warm_iters": int, "device": str, "dummy_out_shape": tuple}.
    """
    import time
    try:
        import torch
    except ImportError:
        return {"warm_iters": 0, "device": "n/a", "skipped": True}

    device = "cuda" if (use_cuda and torch.cuda.is_available()) else "cpu"
    model = model.to(device).eval()
    out_shape: tuple = ()
    t0 = time.perf_counter()
    with torch.no_grad():
        for _ in range(int(n_iter)):
            x = torch.randn(batch, input_dim, device=device)
            y = model(x)
            out_shape = tuple(y.shape)
    dt = time.perf_counter() - t0
    return {
        "warm_iters": int(n_iter),
        "device": device,
        "elapsed_s": dt,
        "dummy_out_shape": out_shape,
    }


def cached_load(model_path: str | Path) -> Any | None:
    """path → torch.load (1회만), repeat call 은 cache 반환.

    Returns:
        loaded checkpoint dict or None.
    """
    key = str(Path(model_path).resolve())
    if key in _MODEL_CACHE:
        return _MODEL_CACHE[key]
    try:
        import torch
        ckpt = torch.load(key, map_location="cpu", weights_only=False)
    except Exception:
        return None
    _MODEL_CACHE[key] = ckpt
    return ckpt


def cache_clear() -> int:
    """cache 초기화. 반환값: 비운 항목 수."""
    n = len(_MODEL_CACHE)
    _MODEL_CACHE.clear()
    return n


def cache_size() -> int:
    return len(_MODEL_CACHE)
