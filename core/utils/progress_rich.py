"""W6 / beta2721 — minimal progress callback wrapper.

CLI / GUI 가 mesh pipeline 의 진행을 표시할 수 있도록 stage / pct 가벼운 API.
rich 가 있으면 컬러 출력, 없으면 plain text fallback.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class ProgressTracker:
    callback: Callable[[str, float], None] | None = None
    history: list[tuple[str, float]] = field(default_factory=list)
    use_rich: bool = False

    def __post_init__(self):
        if self.callback is None and self.use_rich:
            try:
                from rich.console import Console
                self._console = Console()
                self._has_rich = True
            except ImportError:
                self._console = None
                self._has_rich = False
        else:
            self._console = None
            self._has_rich = False

    def report(self, stage: str, pct: float) -> None:
        """report progress.

        Args:
            stage: 단계 이름 (e.g., "Analyzer", "Generator/native_tet").
            pct: 0-100 progress.
        """
        pct = float(max(0.0, min(100.0, pct)))
        self.history.append((stage, pct))
        if self.callback is not None:
            self.callback(stage, pct)
            return
        # default print.
        bar_w = 20
        filled = int(bar_w * pct / 100)
        bar = "█" * filled + "░" * (bar_w - filled)
        line = f"  [{bar}] {pct:5.1f}%  {stage}"
        if self._has_rich and self._console is not None:
            self._console.print(line)
        else:
            print(line)

    def stage_count(self) -> int:
        return len(self.history)

    def last(self) -> tuple[str, float] | None:
        return self.history[-1] if self.history else None
