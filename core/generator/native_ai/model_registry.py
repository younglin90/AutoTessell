"""T5 / beta2699 — ML model registry.

models/ 디렉터리의 trained .pt 파일을 자동 검색 + metadata 등록.
multi-version 모델 관리 + 자동 best-of-N 선택.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RegisteredModel:
    """단일 model 등록 정보."""

    path: Path
    name: str
    architecture: str = "v1"
    val_loss: float = 1.0
    n_train: int = 0
    trained_at: str = ""
    dataset_sha256_short: str = ""
    metadata: dict = field(default_factory=dict)


def discover_models(
    model_dir: str | Path = "models",
    *,
    pattern: str = "*.pt",
) -> list[RegisteredModel]:
    """models/ 디렉터리의 .pt 파일 → RegisteredModel list.

    각 .pt 파일을 torch.load 로 metadata 추출.

    Args:
        model_dir: 검색 디렉터리.
        pattern: glob pattern.

    Returns:
        list of RegisteredModel.
    """
    pdir = Path(model_dir)
    if not pdir.exists():
        return []

    try:
        import torch
    except ImportError:
        return []

    out: list[RegisteredModel] = []
    for f in sorted(pdir.glob(pattern)):
        if f.name.startswith("."):
            continue
        try:
            ckpt = torch.load(str(f), map_location="cpu", weights_only=False)
        except Exception:
            continue

        if not isinstance(ckpt, dict):
            continue

        out.append(RegisteredModel(
            path=f,
            name=f.stem,
            architecture=str(ckpt.get("architecture", "v1")),
            val_loss=float(ckpt.get("final_val_loss", 1.0)),
            n_train=int(ckpt.get("n_train", 0)),
            trained_at=str(ckpt.get("trained_at", "")),
            dataset_sha256_short=str(ckpt.get("dataset_sha256_short", "")),
            metadata={
                k: v for k, v in ckpt.items()
                if k not in ("state_dict",) and not k.startswith("_")
            },
        ))

    return out


def select_best_model(
    model_dir: str | Path = "models",
    *,
    metric: str = "val_loss",
    direction: str = "lower",
    architecture_filter: str | None = None,
) -> RegisteredModel | None:
    """등록된 모델 중 best 1 선택.

    Args:
        model_dir: 검색 디렉터리.
        metric: "val_loss" (default).
        direction: "lower" 또는 "higher".
        architecture_filter: 특정 architecture 만 ("v1" / "v3").

    Returns:
        RegisteredModel 또는 None.
    """
    models = discover_models(model_dir)
    if architecture_filter is not None:
        models = [m for m in models if m.architecture == architecture_filter]
    if not models:
        return None

    if metric == "val_loss":
        if direction == "lower":
            return min(models, key=lambda m: m.val_loss)
        return max(models, key=lambda m: m.val_loss)
    return models[0]
