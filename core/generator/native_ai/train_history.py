"""W3 / beta2718 — ML training per-epoch history CSV logger.

train_predictor / train_bl_predictor 의 학습 곡선 시각화 / 비교 입력.
간단한 csv (epoch, train_loss, val_loss, lr, elapsed_s) 적립.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TrainHistoryLogger:
    path: Path
    fields: list[str] = field(default_factory=lambda: [
        "epoch", "train_loss", "val_loss", "lr", "elapsed_s",
    ])
    _opened: bool = False

    def __post_init__(self):
        self.path = Path(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # write header.
        if not self.path.exists() or self.path.stat().st_size == 0:
            with self.path.open("w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(self.fields)
        self._opened = True

    def append(self, **row: float | int) -> None:
        """append one epoch row.

        Missing fields → empty cell. Extra fields → ignored.
        """
        if not self._opened:
            raise RuntimeError("logger not initialized")
        out = [row.get(f, "") for f in self.fields]
        with self.path.open("a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(out)

    def n_rows(self) -> int:
        if not self.path.exists():
            return 0
        with self.path.open("r", encoding="utf-8") as f:
            return max(0, sum(1 for _ in f) - 1)


def read_history(path: str | Path) -> list[dict]:
    """csv → list of dict (numeric coercion)."""
    p = Path(path)
    if not p.exists():
        return []
    rows: list[dict] = []
    with p.open("r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            d: dict = {}
            for k, v in row.items():
                if v == "" or v is None:
                    d[k] = None
                    continue
                try:
                    d[k] = float(v) if "." in v else int(v)
                except (ValueError, TypeError):
                    d[k] = v
            rows.append(d)
    return rows
