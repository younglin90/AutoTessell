"""X4 / beta2726 — ML model JSON descriptor exporter.

trained .pt 의 metadata 를 단순 JSON 으로 추출 → 모델 카드 / API 응답 / Web SaaS.
weight 는 export 하지 않음 (보안 + 크기). architecture / hparam / metric 만.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass
class ModelDescriptor:
    name: str = ""
    architecture: str = ""
    input_dim: int = 0
    output_dim: int = 1
    n_parameters: int = 0
    val_loss: float = 0.0
    train_loss: float = 0.0
    n_train: int = 0
    n_val: int = 0
    epochs: int = 0
    batch_size: int = 0
    lr: float = 0.0
    seed: int = 0
    dataset_path: str = ""
    dataset_sha256_short: str = ""
    trained_at: str = ""
    backend: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, ensure_ascii=False)


def export_descriptor(model_path: str | Path) -> ModelDescriptor | None:
    """torch.load → metadata 추출 + n_parameters 계산.

    Returns:
        ModelDescriptor or None on failure.
    """
    p = Path(model_path)
    if not p.exists():
        return None

    try:
        import torch
        ckpt = torch.load(str(p), map_location="cpu", weights_only=False)
    except Exception:
        return None

    if not isinstance(ckpt, dict):
        return None

    desc = ModelDescriptor(
        name=p.stem,
        architecture=str(ckpt.get("architecture", "?")),
        input_dim=int(ckpt.get("input_dim", 0) or 0),
        output_dim=int(ckpt.get("output_dim", 1) or 1),
        val_loss=float(ckpt.get("final_val_loss", 0.0) or 0.0),
        train_loss=float(ckpt.get("final_train_loss", 0.0) or 0.0),
        n_train=int(ckpt.get("n_train", 0) or 0),
        n_val=int(ckpt.get("n_val", 0) or 0),
        epochs=int(ckpt.get("epochs", 0) or 0),
        batch_size=int(ckpt.get("batch_size", 0) or 0),
        lr=float(ckpt.get("lr", 0.0) or 0.0),
        seed=int(ckpt.get("seed", 0) or 0),
        dataset_path=str(ckpt.get("dataset_path", "")),
        dataset_sha256_short=str(ckpt.get("dataset_sha256_short", "")),
        trained_at=str(ckpt.get("trained_at", "")),
        backend=str(ckpt.get("backend", "")),
    )

    # n_parameters from state_dict.
    sd = ckpt.get("model_state_dict", {})
    if isinstance(sd, dict):
        desc.n_parameters = sum(
            int(getattr(t, "numel", lambda: 0)()) for t in sd.values()
            if hasattr(t, "numel")
        )

    return desc


def export_descriptor_to_file(model_path: str | Path, out_json: str | Path) -> bool:
    desc = export_descriptor(model_path)
    if desc is None:
        return False
    Path(out_json).write_text(desc.to_json(), encoding="utf-8")
    return True
