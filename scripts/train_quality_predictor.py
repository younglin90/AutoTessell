"""D2 / beta2594 — quality predictor train + 배포 스크립트.

D1 (collect_ml_dataset.py) 가 만든 npz 로 50-epoch 학습 → models/ml_smooth_model.pt 배포.
이후 AUTO_TESSELL_ML_SMOOTH_MODEL=models/ml_smooth_model.pt 로 활성화.

Usage:
    python3 scripts/train_quality_predictor.py
    python3 scripts/train_quality_predictor.py --epochs 100 --batch-size 128

Output: models/ml_smooth_model.pt (state_dict + meta).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="models/ml_dataset.npz")
    ap.add_argument("--output", default="models/ml_smooth_model.pt")
    ap.add_argument("--epochs", type=int, default=50)
    ap.add_argument("--batch-size", type=int, default=64)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--cpu", action="store_true", help="force CPU even when CUDA available")
    args = ap.parse_args()

    repo = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo))

    from core.generator.native_ai.train_predictor import train_quality_predictor

    ds = repo / args.dataset
    out = repo / args.output
    if not ds.exists():
        print(f"[ERR] dataset not found: {ds}", file=sys.stderr)
        print(f"      먼저 'python3 scripts/collect_ml_dataset.py' 실행 필요.", file=sys.stderr)
        return 1

    out.parent.mkdir(parents=True, exist_ok=True)
    print(f"[INFO] training {ds} → {out}")
    print(f"       epochs={args.epochs} batch_size={args.batch_size} lr={args.lr}")

    r = train_quality_predictor(
        str(ds), str(out),
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        use_cuda=not args.cpu,
    )

    if not r.success:
        print(f"[ERR] training failed: {r.message}", file=sys.stderr)
        return 2

    print(f"[DONE] {r.backend}")
    print(f"       train_loss = {r.final_train_loss:.5f}")
    print(f"       val_loss   = {r.final_val_loss:.5f}")
    print(f"       n_train={r.n_train_samples}  n_val={r.n_val_samples}")
    print(f"       elapsed {r.elapsed:.1f}s")
    print(f"")
    print(f"[NEXT] 활성화: export AUTO_TESSELL_ML_SMOOTH_MODEL={out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
