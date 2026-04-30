"""Y3 / beta2732 — ML batch evaluation utility.

trained model 의 inference 를 batch 로 효율적으로 실행.
batch 크기 자동 조절 + GPU OOM fallback + timing 측정.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray


@dataclass
class EvalBatchResult:
    n_samples: int = 0
    batch_size: int = 0
    n_batches: int = 0
    elapsed_s: float = 0.0
    samples_per_s: float = 0.0
    device: str = "cpu"
    oom_fallbacks: int = 0


def predict_batch(
    model: Any,
    X: NDArray[np.float64],
    *,
    batch_size: int = 256,
    use_cuda: bool = False,
    auto_oom_fallback: bool = True,
) -> tuple[NDArray[np.float64], EvalBatchResult]:
    """torch model 에 X (N, D) → predictions (N, 1).

    Args:
        model: torch.nn.Module (eval 가능).
        X: (N, D) 입력 array.
        batch_size: 초기 batch 크기. OOM 시 절반.
        use_cuda: True 면 cuda 시도.
        auto_oom_fallback: OOM 시 batch 절반 + retry.

    Returns:
        (preds (N, 1), EvalBatchResult).
    """
    import time
    try:
        import torch
    except ImportError:
        return np.zeros((X.shape[0], 1), dtype=np.float64), EvalBatchResult(
            n_samples=int(X.shape[0]),
            elapsed_s=0.0,
            device="n/a",
        )

    X = np.asarray(X, dtype=np.float32)
    n = int(X.shape[0])
    if n == 0:
        return np.zeros((0, 1), dtype=np.float64), EvalBatchResult()

    device = "cuda" if (use_cuda and torch.cuda.is_available()) else "cpu"
    model = model.to(device).eval()

    bs = int(batch_size)
    n_oom = 0
    out_chunks: list[np.ndarray] = []
    n_batches = 0

    t0 = time.perf_counter()
    i = 0
    while i < n:
        j = min(i + bs, n)
        try:
            with torch.no_grad():
                xt = torch.from_numpy(X[i:j]).to(device)
                yt = model(xt)
                out_chunks.append(yt.cpu().numpy())
            n_batches += 1
            i = j
        except RuntimeError as exc:
            msg = str(exc)
            if auto_oom_fallback and ("out of memory" in msg or "OOM" in msg):
                n_oom += 1
                if device == "cuda":
                    torch.cuda.empty_cache()
                bs = max(bs // 2, 1)
                if bs < 1:
                    raise
                # retry same i.
                continue
            raise

    elapsed = time.perf_counter() - t0
    preds = np.concatenate(out_chunks, axis=0).astype(np.float64) \
        if out_chunks else np.zeros((0, 1), dtype=np.float64)

    return preds, EvalBatchResult(
        n_samples=n,
        batch_size=bs,
        n_batches=n_batches,
        elapsed_s=elapsed,
        samples_per_s=float(n / max(elapsed, 1e-30)),
        device=device,
        oom_fallbacks=n_oom,
    )
