"""D6 / beta2596 — BL collision predictor train + 배포.

D5 (collect_bl_dataset.py) 가 만든 npz 로 학습 → assets/models/bl_predictor.pt.
이후 AUTO_TESSELL_BL_PREDICT_MODEL=assets/models/bl_predictor.pt 로 활성화 (native_bl 의 _compute_collision_distance fast-path).

Usage:
    python3 scripts/train_bl_predictor.py
    python3 scripts/train_bl_predictor.py --epochs 100
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="assets/models/bl_dataset.npz")
    ap.add_argument("--output", default="assets/models/bl_predictor.pt")
    ap.add_argument("--epochs", type=int, default=50)
    ap.add_argument("--batch-size", type=int, default=64)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--cpu", action="store_true")
    args = ap.parse_args()

    repo = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo))

    from core.generator.native_ai.train_bl_predictor import train_bl_collision_predictor

    ds = repo / args.dataset
    out = repo / args.output
    if not ds.exists():
        print(f"[ERR] dataset not found: {ds}", file=sys.stderr)
        return 1

    out.parent.mkdir(parents=True, exist_ok=True)
    print(f"[INFO] training {ds} → {out}")
    print(f"       epochs={args.epochs} batch_size={args.batch_size}")

    r = train_bl_collision_predictor(
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
    print(f"[NEXT] 활성화: export AUTO_TESSELL_BL_PREDICT_MODEL={out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
