"""BB3 / beta2753 — ML training resume from checkpoint.

장시간 학습 중단/재개 지원. checkpoint = (model_state, optimizer_state,
epoch, scheduler_state, history).

torch 의존. 기존 train_history (BETA2718) + model_version (BETA2739) 와 통합.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ResumeInfo:
    epoch: int = 0
    best_val_loss: float = float("inf")
    history_path: str = ""
    found: bool = False
    message: str = ""


def save_checkpoint(
    path: str | Path,
    model: Any,
    optimizer: Any,
    epoch: int,
    *,
    best_val_loss: float = float("inf"),
    scheduler: Any = None,
    extra: dict | None = None,
) -> bool:
    """training checkpoint 저장.

    Returns:
        성공 여부.
    """
    try:
        import torch
        ckpt = {
            "epoch": int(epoch),
            "model_state_dict": model.state_dict(),
            "optimizer_state_dict": optimizer.state_dict(),
            "best_val_loss": float(best_val_loss),
        }
        if scheduler is not None:
            ckpt["scheduler_state_dict"] = scheduler.state_dict()
        if extra:
            ckpt.update(extra)
        # version stamp.
        try:
            from core.generator.native_ai.model_version import stamp_version
            ckpt = stamp_version(ckpt)
        except Exception:
            pass

        Path(path).parent.mkdir(parents=True, exist_ok=True)
        torch.save(ckpt, str(path))
        return True
    except Exception:
        return False


def load_checkpoint(
    path: str | Path,
    model: Any,
    optimizer: Any,
    *,
    scheduler: Any = None,
    map_location: str = "cpu",
) -> ResumeInfo:
    """checkpoint 로드 → model/optimizer state 복원.

    Returns:
        ResumeInfo (found=True 면 epoch, best_val_loss 복원됨).
    """
    p = Path(path)
    if not p.exists():
        return ResumeInfo(found=False, message=f"missing: {p}")

    try:
        import torch
        ckpt = torch.load(str(p), map_location=map_location, weights_only=False)
    except Exception as exc:
        return ResumeInfo(found=False, message=f"load error: {exc}")

    if not isinstance(ckpt, dict):
        return ResumeInfo(found=False, message="not dict")

    try:
        if "model_state_dict" in ckpt:
            model.load_state_dict(ckpt["model_state_dict"])
        if "optimizer_state_dict" in ckpt:
            optimizer.load_state_dict(ckpt["optimizer_state_dict"])
        if scheduler is not None and "scheduler_state_dict" in ckpt:
            scheduler.load_state_dict(ckpt["scheduler_state_dict"])
    except Exception as exc:
        return ResumeInfo(found=False, message=f"state load error: {exc}")

    return ResumeInfo(
        epoch=int(ckpt.get("epoch", 0)),
        best_val_loss=float(ckpt.get("best_val_loss", float("inf"))),
        history_path=str(ckpt.get("history_path", "")),
        found=True,
        message=f"resumed at epoch {ckpt.get('epoch', 0)}",
    )
