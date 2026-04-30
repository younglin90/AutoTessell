"""S2 / beta2689 — ML model checksum verify utility.

trained .pt 파일의 metadata (sha256, dataset_path) 추출 → 학습 일관성 점검.
L4 (BETA2643) 의 metadata 활용.

Usage:
    python3 scripts/verify_model_checksum.py models/ml_smooth_model.pt
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("model_path", type=Path)
    ap.add_argument("--check-dataset", action="store_true",
                    help="dataset 파일 sha256 재계산 + 매칭 검증")
    args = ap.parse_args()

    if not args.model_path.exists():
        print(f"[ERR] model not found: {args.model_path}", file=sys.stderr)
        return 1

    try:
        import torch
    except ImportError:
        print("[ERR] torch not installed", file=sys.stderr)
        return 2

    try:
        ckpt = torch.load(str(args.model_path), map_location="cpu", weights_only=False)
    except Exception as exc:
        print(f"[ERR] load failed: {exc}", file=sys.stderr)
        return 3

    if not isinstance(ckpt, dict):
        print(f"[ERR] checkpoint 가 dict 가 아님 (legacy format)", file=sys.stderr)
        return 4

    print(f"\n=== Model: {args.model_path} ===\n")

    keys_show = (
        "model_version", "architecture", "input_dim",
        "trained_at", "dataset_path", "dataset_size_bytes",
        "dataset_sha256_short", "lr", "batch_size", "seed",
        "backend", "epochs", "n_train", "n_val",
        "final_train_loss", "final_val_loss",
    )
    for k in keys_show:
        if k in ckpt:
            v = ckpt[k]
            if isinstance(v, float):
                print(f"  {k:<22}: {v:.6f}")
            else:
                print(f"  {k:<22}: {v}")
        else:
            print(f"  {k:<22}: (missing)")

    if args.check_dataset:
        ds_path = ckpt.get("dataset_path", "")
        ds_sha = ckpt.get("dataset_sha256_short", "")
        if not ds_path or not ds_sha:
            print("\n[WARN] dataset metadata 부족 — 검증 불가")
            return 5
        ds = Path(ds_path)
        if not ds.exists():
            print(f"\n[ERR] dataset not found: {ds}")
            return 6
        import hashlib
        h = hashlib.sha256()
        with ds.open("rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        cur_sha = h.hexdigest()[:16]
        match = cur_sha == ds_sha
        print(f"\n  dataset_sha256 (current ): {cur_sha}")
        print(f"  dataset_sha256 (recorded): {ds_sha}")
        print(f"  match: {'✓' if match else '✗ STALE — dataset changed since training'}")
        return 0 if match else 7
    return 0


if __name__ == "__main__":
    sys.exit(main())
