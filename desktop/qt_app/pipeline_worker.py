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

        # _Worker 클래스를 호출마다 새로 생성해 Signal 정의를 항상 최신 상태로 유지.
        # (재사용 시 stale QMetaObject 문제 방지. 생성 비용은 무시할 수준.)

        # PipelineResult 임포트 시도 — 실패해도 object 를 fallback 으로 사용
        try:
            from core.pipeline.orchestrator import PipelineResult as _PR
        except Exception:
            _PR = object  # type: ignore[assignment,misc]

        class _Worker(QThread):
            progress: Signal[str] = Signal(str)
            progress_percent: Signal[int, str] = Signal(int, str)
            finished: Signal[object] = Signal(object)
            quality_update: Signal[dict] = Signal(dict)  # checkMesh 품질 메트릭
            # 중간 아티팩트 준비 완료 — (file_path, stage_label)
            # 예: ("/tmp/case/_work/preprocessed.stl", "Preprocessed Surface")
            #     ("/tmp/case/constant/polyMesh", "Iteration 1 Volume Mesh")
            intermediate_ready: Signal[str, str] = Signal(str, str)

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
                        # checkMesh 품질 힌트 — 메시지에서 메트릭 파싱 시도
                        _try_emit_quality(self, message)
                        # 중간 아티팩트 프리뷰 — 긴 실행 중 대기시간 줄이기
                        _try_emit_intermediate(self, message, output_dir)

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
                    # 완료 후 quality_report에서 메트릭 emit
                    _emit_quality_from_result(self, result)
                    self.finished.emit(result)
                except InterruptedError:
                    # 사용자 중단 — UI를 대기 상태로 복원하기 위해 finished emit
                    try:
                        from core.pipeline.orchestrator import PipelineResult

                        self.progress.emit("[중단됨] 사용자 요청으로 파이프라인 중단")
                        self.finished.emit(
                            PipelineResult(success=False, error="User cancelled")
                        )
                    except Exception:  # noqa: BLE001
                        pass
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

                        self.progress.emit(f"[오류] {exc.__class__.__name__}: {exc}")
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
                        self.progress.emit(f"[오류] {exc.__class__.__name__}: {exc}")
                        self.progress.emit(f"[디버그]\n{brief_tb}")
                        self.finished.emit(None)

        instance = _Worker.__new__(_Worker)
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


# ---------------------------------------------------------------------------
# 품질 메트릭 emit 헬퍼 (모듈 레벨)
# ---------------------------------------------------------------------------


def _try_emit_quality(worker: object, message: str) -> None:
    """progress 메시지에서 checkMesh 메트릭을 파싱해 quality_update emit."""
    import re
    try:
        metrics: dict = {}
        m = re.search(r"[Nn]on.?ortho[^\d]*(\d+\.?\d*)", message)
        if m:
            metrics["max_non_ortho"] = float(m.group(1))
        m = re.search(r"[Ss]kewness[^\d]*(\d+\.?\d*)", message)
        if m:
            metrics["max_skewness"] = float(m.group(1))
        m = re.search(r"[Aa]spect[^\d]*(\d+\.?\d*)", message)
        if m:
            metrics["max_aspect_ratio"] = float(m.group(1))
        m = re.search(r"[Nn]egative\s+(?:vol|cell)[^\d]*(\d+)", message)
        if m:
            metrics["negative_volumes"] = int(m.group(1))
        if metrics:
            worker.quality_update.emit(metrics)  # type: ignore[union-attr]
    except Exception:
        pass


def _try_emit_intermediate(worker: object, message: str, output_dir: Path) -> None:
    """progress 메시지가 stage 완료를 알리면 해당 artifact 경로를 emit.

    Fine 품질 30분+ 실행 중 사용자에게 중간 결과를 미리 보여주기 위함.
    """
    try:
        # "Preprocess 완료" → 수리된 표면 STL
        if "Preprocess 완료" in message:
            pre_stl = output_dir / "_work" / "preprocessed.stl"
            if pre_stl.exists() and pre_stl.stat().st_size > 0:
                worker.intermediate_ready.emit(  # type: ignore[union-attr]
                    str(pre_stl), "전처리된 표면"
                )
                return

        # "Generate 완료 N/M" → 중간 volume polyMesh
        import re
        m = re.search(r"Generate 완료 (\d+)/(\d+)", message)
        if m:
            iteration = int(m.group(1))
            total = int(m.group(2))
            polymesh = output_dir / "constant" / "polyMesh"
            if polymesh.exists() and (polymesh / "points").exists():
                # 마지막 iteration이면 최종이므로 intermediate_ready 불필요
                # (finished signal이 그 역할) → 중간 iteration만 emit
                if iteration < total:
                    worker.intermediate_ready.emit(  # type: ignore[union-attr]
                        str(output_dir), f"반복 {iteration}/{total} Volume"
                    )
    except Exception:
        pass


def _emit_quality_from_result(worker: object, result: object) -> None:
    """파이프라인 완료 결과에서 quality_report 메트릭을 emit."""
    try:
        qr = getattr(result, "quality_report", None) or {}
        if isinstance(qr, dict):
            metrics = qr.get("metrics", {})
            if metrics:
                worker.quality_update.emit(metrics)  # type: ignore[union-attr]
    except Exception:
        pass
