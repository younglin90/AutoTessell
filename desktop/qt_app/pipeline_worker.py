"""QThread 기반 백그라운드 파이프라인 실행 워커."""
from __future__ import annotations

import traceback
from pathlib import Path
from typing import TYPE_CHECKING, Any

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

    def __new__(
        cls,
        input_path: Path,
        quality_level: QualityLevel,
        output_dir: Path | None = None,
        *,
        tier_hint: str = "auto",
        max_iterations: int = 3,
        dry_run: bool = False,
        element_size: float | None = None,
        max_cells: int | None = None,
        tier_specific_params: dict[str, Any] | None = None,
        no_repair: bool = False,
        surface_remesh: bool = False,
        remesh_engine: str = "auto",
        allow_ai_fallback: bool = False,
    ) -> PipelineWorker:  # type: ignore[misc]
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
                progress_percent: Signal[int, str] = Signal(int, str)
                finished: Signal[object] = Signal(object)

                def __init__(
                    self,
                    input_path: Path,
                    quality_level: QualityLevel,
                    output_dir: Path | None = None,
                    tier_hint: str = "auto",
                    max_iterations: int = 3,
                    dry_run: bool = False,
                    element_size: float | None = None,
                    max_cells: int | None = None,
                    tier_specific_params: dict[str, Any] | None = None,
                    no_repair: bool = False,
                    surface_remesh: bool = False,
                    remesh_engine: str = "auto",
                    allow_ai_fallback: bool = False,
                ) -> None:
                    super().__init__()
                    self._input_path = input_path
                    self._quality_level = quality_level
                    self._output_dir = output_dir
                    self._tier_hint = tier_hint
                    self._max_iterations = max_iterations
                    self._dry_run = dry_run
                    self._element_size = element_size
                    self._max_cells = max_cells
                    self._tier_specific_params = tier_specific_params or {}
                    self._no_repair = no_repair
                    self._surface_remesh = surface_remesh
                    self._remesh_engine = remesh_engine
                    self._allow_ai_fallback = allow_ai_fallback

                def run(self) -> None:
                    """파이프라인을 실행하고 결과를 finished 시그널로 emit."""
                    try:
                        from core.pipeline.orchestrator import PipelineOrchestrator

                        orchestrator = PipelineOrchestrator()
                        output_dir = self._output_dir or (self._input_path.parent / "output")
                        output_dir = output_dir.expanduser().resolve()
                        output_dir.mkdir(parents=True, exist_ok=True)

                        self.progress.emit(
                            f"파이프라인 시작: input={self._input_path.name} "
                            f"quality={self._quality_level.value} "
                            f"tier={self._tier_hint} "
                            f"max_iter={self._max_iterations} "
                            f"element_size={self._element_size} "
                            f"max_cells={self._max_cells} "
                            f"no_repair={self._no_repair} "
                            f"surface_remesh={self._surface_remesh} "
                            f"remesh_engine={self._remesh_engine} "
                            f"allow_ai_fallback={self._allow_ai_fallback} "
                            f"output={output_dir}"
                        )

                        def _on_progress(percent: int, message: str) -> None:
                            # Stop 요청 시 중단 (subprocess kill 후 thread가 여기서 탈출)
                            if self.isInterruptionRequested():
                                raise InterruptedError("사용자가 메시 생성을 중단했습니다.")
                            self.progress_percent.emit(int(percent), str(message))
                            self.progress.emit(f"[진행 {int(percent)}%] {message}")

                        result = orchestrator.run(
                            input_path=self._input_path,
                            output_dir=output_dir,
                            quality_level=self._quality_level.value,
                            tier_hint=self._tier_hint,
                            max_iterations=self._max_iterations,
                            dry_run=self._dry_run,
                            element_size=self._element_size,
                            max_cells=self._max_cells,
                            tier_specific_params=self._tier_specific_params,
                            no_repair=self._no_repair,
                            surface_remesh=self._surface_remesh,
                            remesh_engine=self._remesh_engine,
                            allow_ai_fallback=self._allow_ai_fallback,
                            progress_callback=_on_progress,
                        )
                        self.progress.emit(
                            f"파이프라인 종료: success={result.success} "
                            f"iterations={result.iterations} "
                            f"time={result.total_time_seconds:.2f}s"
                        )
                        self.finished.emit(result)
                    except InterruptedError:
                        # 사용자 중단 — finished 시그널 emit 안 함
                        # (main_window._stopping=True가 무시하지만 emit 자체를 생략)
                        return
                    except Exception as exc:  # noqa: BLE001
                        tb = traceback.format_exc()
                        brief_tb = "\n".join(tb.strip().splitlines()[-8:])
                        # Stop 요청 시 subprocess kill로 발생한 예외는 조용히 종료
                        if self.isInterruptionRequested():
                            return
                        # 실패 시 success=False 결과 emit
                        try:
                            from core.pipeline.orchestrator import PipelineResult

                            self.progress.emit(
                                f"[오류] {exc.__class__.__name__}: {exc}"
                            )
                            self.progress.emit(f"[디버그]\n{brief_tb}")
                            self.finished.emit(
                                PipelineResult(
                                    success=False,
                                    error=(
                                        f"{exc.__class__.__name__}: {exc}\n"
                                        f"{brief_tb}"
                                    ),
                                )
                            )
                        except Exception:
                            self.progress.emit(
                                f"[오류] {exc.__class__.__name__}: {exc}"
                            )
                            self.progress.emit(f"[디버그]\n{brief_tb}")
                            self.finished.emit(None)

            cls._qt_class = _Worker

        instance = cls._qt_class.__new__(cls._qt_class)
        instance.__init__(
            input_path,
            quality_level,
            output_dir,
            tier_hint=tier_hint,
            max_iterations=max_iterations,
            dry_run=dry_run,
            element_size=element_size,
            max_cells=max_cells,
            tier_specific_params=tier_specific_params,
            no_repair=no_repair,
            surface_remesh=surface_remesh,
            remesh_engine=remesh_engine,
            allow_ai_fallback=allow_ai_fallback,
        )
        return instance  # type: ignore[return-value]
