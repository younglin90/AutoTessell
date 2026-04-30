"""K4 / beta2636 — Progress callback API.

long-running mesh ops 의 진행 상황을 콜백으로 전달.
GUI / CLI / log 의 progress bar 와 호환.

API:
    progress = ProgressTracker(total=100, callback=cb)
    progress.update(10, "phase A done")
    progress.advance("phase B")
    progress.set_total(200)  # 동적 total 변경.
    progress.finish()

callback signature: cb(event: ProgressEvent) -> None.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class ProgressEvent:
    """단일 progress 이벤트."""

    current: int
    total: int
    phase: str = ""
    message: str = ""
    elapsed_s: float = 0.0
    rate_per_s: float = 0.0       # current / elapsed.
    eta_s: float = 0.0            # 추정 남은 시간 (rate 기반).
    extra: dict = field(default_factory=dict)


ProgressCallback = Callable[[ProgressEvent], None]


class ProgressTracker:
    """Progress callback 추적기.

    multiple callback 등록 가능 (GUI + log + CLI 동시).
    thread-safe 아님 (single thread 가정).
    """

    def __init__(
        self,
        total: int = 100,
        *,
        callback: ProgressCallback | None = None,
        callbacks: list[ProgressCallback] | None = None,
        phase: str = "",
    ) -> None:
        import time
        self._total = max(1, int(total))
        self._current = 0
        self._phase = phase
        self._t_start = time.perf_counter()
        self._callbacks: list[ProgressCallback] = list(callbacks or [])
        if callback is not None:
            self._callbacks.append(callback)

    def add_callback(self, cb: ProgressCallback) -> None:
        self._callbacks.append(cb)

    def set_total(self, total: int) -> None:
        self._total = max(1, int(total))

    def set_phase(self, phase: str) -> None:
        self._phase = phase

    def update(
        self,
        current: int | None = None,
        message: str = "",
        *,
        increment: int | None = None,
        **extra,
    ) -> None:
        """Progress 갱신 + 모든 callback 호출."""
        import time
        if current is not None:
            self._current = int(current)
        elif increment is not None:
            self._current += int(increment)
        else:
            self._current += 1

        elapsed = time.perf_counter() - self._t_start
        rate = self._current / max(elapsed, 1e-9)
        remaining = max(0, self._total - self._current)
        eta = remaining / max(rate, 1e-9)
        evt = ProgressEvent(
            current=self._current,
            total=self._total,
            phase=self._phase,
            message=message,
            elapsed_s=elapsed,
            rate_per_s=rate,
            eta_s=eta,
            extra=extra,
        )
        for cb in self._callbacks:
            try:
                cb(evt)
            except Exception:
                pass  # callback 실패 무시 (mesh op 차단 방지).

    def advance(self, message: str = "", **extra) -> None:
        """1 step 증가."""
        self.update(increment=1, message=message, **extra)

    def finish(self, message: str = "done", **extra) -> None:
        """완료 — current = total + 알림."""
        self.update(current=self._total, message=message, **extra)

    @property
    def current(self) -> int:
        return self._current

    @property
    def total(self) -> int:
        return self._total

    @property
    def fraction(self) -> float:
        return min(1.0, self._current / max(self._total, 1))


def stdout_callback(prefix: str = "[PROGRESS]") -> ProgressCallback:
    """간단 stdout printer callback."""
    def _cb(evt: ProgressEvent) -> None:
        pct = 100.0 * evt.current / max(evt.total, 1)
        eta_s = evt.eta_s
        msg = f" — {evt.message}" if evt.message else ""
        phase = f" [{evt.phase}]" if evt.phase else ""
        print(
            f"{prefix}{phase} {evt.current}/{evt.total} "
            f"({pct:.1f}%) ETA {eta_s:.1f}s{msg}",
            flush=True,
        )
    return _cb


def silent_callback() -> ProgressCallback:
    """no-op callback."""
    def _cb(evt: ProgressEvent) -> None:  # noqa: ARG001
        pass
    return _cb


def collect_callback(into: list[ProgressEvent]) -> ProgressCallback:
    """Test 용 — list 에 모든 이벤트 누적."""
    def _cb(evt: ProgressEvent) -> None:
        into.append(evt)
    return _cb
