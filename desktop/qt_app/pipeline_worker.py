"""QThread 기반 백그라운드 파이프라인 실행 워커."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from desktop.qt_app.main_window import QualityLevel

# ---------------------------------------------------------------------------
# PipelineWorker
# ---------------------------------------------------------------------------


class PipelineWorker:
    """PipelineOrchestrator 를 별도 스레드에서 실행하는 QThread 워커.

    헤드리스 환경에서도 클래스 정의 임포트가 가능하도록
    QThread 상속 및 Signal 생성은 내부에서 지연 처리한다.
    """

    def __new__(cls, input_path: Path, quality_level: QualityLevel) -> PipelineWorker:  # type: ignore[misc]
        """QThread 를 동적으로 상속한 인스턴스를 반환한다."""
        from PySide6.QtCore import QThread, Signal

        # QThread 를 베이스로 하는 실제 클래스를 동적으로 생성
        if not hasattr(cls, "_qt_class"):
            # PipelineResult 임포트 시도 — 실패해도 object 를 fallback 으로 사용
            try:
                from core.pipeline.orchestrator import PipelineResult as _PR
            except Exception:
                _PR = object  # type: ignore[assignment,misc]

            class _Worker(QThread):
                progress: Signal[str] = Signal(str)
                finished: Signal[object] = Signal(object)

                def __init__(
                    self,
                    input_path: Path,
                    quality_level: QualityLevel,
                ) -> None:
                    super().__init__()
                    self._input_path = input_path
                    self._quality_level = quality_level

                def run(self) -> None:
                    """파이프라인을 실행하고 결과를 finished 시그널로 emit."""
                    try:
                        from core.pipeline.orchestrator import PipelineOrchestrator

                        orchestrator = PipelineOrchestrator()

                        # 진행 상황 콜백을 progress 시그널로 연결
                        def _on_progress(msg: str) -> None:
                            self.progress.emit(msg)

                        self.progress.emit(
                            f"파이프라인 시작: {self._input_path.name} "
                            f"[{self._quality_level.value}]"
                        )
                        result = orchestrator.run(
                            input_path=self._input_path,
                            output_dir=self._input_path.parent / "output",
                            quality_level=self._quality_level.value,
                        )
                        self.finished.emit(result)
                    except Exception as exc:  # noqa: BLE001
                        # 실패 시 success=False 결과 emit
                        try:
                            from core.pipeline.orchestrator import PipelineResult

                            self.finished.emit(
                                PipelineResult(success=False, error=str(exc))
                            )
                        except Exception:
                            self.progress.emit(f"[오류] {exc}")
                            self.finished.emit(None)

            cls._qt_class = _Worker

        instance = cls._qt_class.__new__(cls._qt_class)
        instance.__init__(input_path, quality_level)
        return instance  # type: ignore[return-value]
