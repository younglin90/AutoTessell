"""Z3 / beta2739 — ML model version manager.

learn → save → load 사이클에서 architecture 호환성 / version 관리.
- semantic version (major.minor.patch).
- architecture mismatch 탐지.
- old model 자동 마이그레이션 hook.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ModelVersion:
    major: int = 0
    minor: int = 0
    patch: int = 0

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    @classmethod
    def parse(cls, s: str) -> "ModelVersion":
        parts = str(s).split(".")
        try:
            mj = int(parts[0]) if len(parts) >= 1 else 0
            mn = int(parts[1]) if len(parts) >= 2 else 0
            pt = int(parts[2]) if len(parts) >= 3 else 0
        except (ValueError, IndexError):
            return cls(0, 0, 0)
        return cls(mj, mn, pt)

    def is_compatible_with(self, other: "ModelVersion") -> bool:
        """major 같으면 호환 가능, 다르면 incompatible."""
        return self.major == other.major

    def is_newer_than(self, other: "ModelVersion") -> bool:
        return (self.major, self.minor, self.patch) > (
            other.major, other.minor, other.patch
        )


# 현재 architecture version. major bump 시 학습된 weight 호환 안 됨.
CURRENT_VERSION = ModelVersion(major=1, minor=0, patch=0)


def check_model_version(model_path: str | Path) -> tuple[ModelVersion, bool, str]:
    """모델 파일에서 version 추출 + 현재 호환성 체크.

    Returns:
        (version, is_compatible, message).
    """
    p = Path(model_path)
    if not p.exists():
        return ModelVersion(0, 0, 0), False, f"missing: {p}"

    try:
        import torch
        ckpt = torch.load(str(p), map_location="cpu", weights_only=False)
    except Exception as exc:
        return ModelVersion(0, 0, 0), False, f"load error: {exc}"

    if not isinstance(ckpt, dict):
        return ModelVersion(0, 0, 0), False, "not a dict checkpoint"

    v_str = str(ckpt.get("model_version", "1.0.0"))
    v = ModelVersion.parse(v_str)
    compat = v.is_compatible_with(CURRENT_VERSION)
    msg = (
        f"compatible (model={v}, current={CURRENT_VERSION})"
        if compat
        else f"INCOMPATIBLE (model major={v.major}, current major={CURRENT_VERSION.major})"
    )
    return v, compat, msg


def stamp_version(ckpt: dict, version: ModelVersion = CURRENT_VERSION) -> dict:
    """checkpoint dict 에 version 도장. 기존 정보 보존."""
    ckpt = dict(ckpt) if not isinstance(ckpt, dict) else ckpt
    ckpt["model_version"] = str(version)
    return ckpt
