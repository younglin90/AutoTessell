"""파이프라인 성능 프로파일러.

각 단계별 소요 시간을 측정하고 병목을 식별한다.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Generator

from core.utils.logging import get_logger

log = get_logger(__name__)


@dataclass
class TimingRecord:
    """단일 단계 타이밍."""

    name: str
    elapsed: float = 0.0
    children: list["TimingRecord"] = field(default_factory=list)

    @property
    def total(self) -> float:
        return self.elapsed

    @property
    def pct(self) -> float:
        return 0.0  # root에서 계산


@dataclass
class ProfilingResult:
    """전체 프로파일링 결과."""

    stages: list[TimingRecord] = field(default_factory=list)
    total_time: float = 0.0

    def summary(self) -> str:
        """Rich 포맷 가능한 요약 문자열."""
        if self.total_time == 0:
            return "No profiling data"

        lines = ["Stage                    Time       %"]
        lines.append("-" * 45)
        for s in self.stages:
            pct = (s.elapsed / self.total_time * 100) if self.total_time > 0 else 0
            bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
            lines.append(f"{s.name:24s} {s.elapsed:>6.2f}s  {bar} {pct:>5.1f}%")
        lines.append("-" * 45)
        lines.append(f"{'Total':24s} {self.total_time:>6.2f}s")
        return "\n".join(lines)


class PipelineProfiler:
    """파이프라인 성능 프로파일러."""

    def __init__(self) -> None:
        self._stages: list[TimingRecord] = []
        self._start: float = 0.0

    def start(self) -> None:
        self._start = time.perf_counter()
        self._stages = []

    @contextmanager
    def stage(self, name: str) -> Generator[None, None, None]:
        """단계별 타이밍 컨텍스트 매니저."""
        t0 = time.perf_counter()
        try:
            yield
        finally:
            elapsed = time.perf_counter() - t0
            self._stages.append(TimingRecord(name=name, elapsed=elapsed))
            log.debug("profiler_stage", stage=name, elapsed=f"{elapsed:.3f}s")

    def result(self) -> ProfilingResult:
        total = time.perf_counter() - self._start if self._start > 0 else 0
        return ProfilingResult(stages=self._stages, total_time=total)
