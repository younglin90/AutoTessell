"""V4 / beta2712 — ML feature standardizer (z-score).

train/test 일관된 정규화 적용 — mean / std 저장 → predict 시 동일 변환.
ML 모델 input 의 numerical stability 향상 + 학습 수렴 가속.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from numpy.typing import NDArray


@dataclass
class FeatureScaler:
    mean: NDArray[np.float64] = field(default_factory=lambda: np.zeros(0))
    std: NDArray[np.float64] = field(default_factory=lambda: np.zeros(0))
    n_features: int = 0

    @classmethod
    def fit(cls, X: NDArray[np.float64], *, eps: float = 1e-8) -> "FeatureScaler":
        """X (N, D) 의 column-wise mean/std 계산. std<eps → 1.0 으로 대체."""
        X = np.asarray(X, dtype=np.float64)
        if X.ndim != 2:
            raise ValueError(f"X must be 2D, got {X.ndim}D")
        mean = X.mean(axis=0)
        std = X.std(axis=0)
        std = np.where(std < eps, 1.0, std)
        return cls(mean=mean, std=std, n_features=int(X.shape[1]))

    def transform(self, X: NDArray[np.float64]) -> NDArray[np.float64]:
        X = np.asarray(X, dtype=np.float64)
        if X.shape[-1] != self.n_features:
            raise ValueError(
                f"feature dim {X.shape[-1]} != fitted {self.n_features}"
            )
        return (X - self.mean) / self.std

    def inverse_transform(self, X: NDArray[np.float64]) -> NDArray[np.float64]:
        X = np.asarray(X, dtype=np.float64)
        return X * self.std + self.mean

    def fit_transform(self, X: NDArray[np.float64]) -> NDArray[np.float64]:
        sc = FeatureScaler.fit(X)
        self.mean = sc.mean
        self.std = sc.std
        self.n_features = sc.n_features
        return self.transform(X)

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps({
            "mean": self.mean.tolist(),
            "std": self.std.tolist(),
            "n_features": self.n_features,
        }, indent=2))

    @classmethod
    def load(cls, path: str | Path) -> "FeatureScaler":
        d = json.loads(Path(path).read_text())
        return cls(
            mean=np.asarray(d["mean"], dtype=np.float64),
            std=np.asarray(d["std"], dtype=np.float64),
            n_features=int(d["n_features"]),
        )
