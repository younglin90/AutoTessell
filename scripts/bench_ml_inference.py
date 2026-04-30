"""N4 / beta2656 — ML inference benchmark.

trained model 의 inference throughput 측정 (samples/sec).
batch size scan + CUDA vs CPU 비교.

Usage:
    python3 scripts/bench_ml_inference.py
    python3 scripts/bench_ml_inference.py --model models/ml_smooth_model.pt
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="models/ml_smooth_model.pt")
    ap.add_argument("--n-samples", type=int, default=10000)
    ap.add_argument("--batch-sizes", type=str, default="64,256,1024,4096")
    args = ap.parse_args()

    repo = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo))

    import numpy as np

    model_path = repo / args.model
    if not model_path.exists():
        print(f"[ERR] model not found: {model_path}", file=sys.stderr)
        return 1

    try:
        from core.generator.native_ai.ml_tet_smoothing import (
            load_trained_predictor, predict_quality_batch,
        )
        import torch
    except Exception as exc:
        print(f"[ERR] torch unavailable: {exc}", file=sys.stderr)
        return 2

    K = args.n_samples
    batch_sizes = [int(b) for b in args.batch_sizes.split(",") if b.strip()]

    print(f"\n[ML INFERENCE BENCH] model={model_path.name}, n_samples={K}")
    print(f"  batch sizes: {batch_sizes}")
    print()

    rng = np.random.default_rng(42)
    coords = rng.random((K, 12)).astype(np.float32)
    ctx = rng.random((K, 8)).astype(np.float32)

    for device_str in ("cuda", "cpu"):
        if device_str == "cuda" and not torch.cuda.is_available():
            continue
        model = load_trained_predictor(str(model_path), device=device_str)
        if model is None:
            continue

        # warmup.
        try:
            _ = predict_quality_batch(model, coords[:64], ctx[:64], use_cuda=(device_str == "cuda"))
        except Exception:
            continue

        print(f"  [{device_str.upper()}]")
        print(f"  {'batch':>8} {'time (ms)':>12} {'samples/sec':>15}")
        for bs in batch_sizes:
            t0 = time.perf_counter()
            for s in range(0, K, bs):
                e = min(s + bs, K)
                _ = predict_quality_batch(
                    model, coords[s:e], ctx[s:e],
                    use_cuda=(device_str == "cuda"),
                )
            elapsed = time.perf_counter() - t0
            sps = K / max(elapsed, 1e-9)
            print(f"  {bs:>8} {elapsed * 1000:>12.1f} {sps:>15.1f}")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
