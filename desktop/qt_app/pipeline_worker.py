"""QThread 기반 백그라운드 파이프라인 실행 워커."""
from __future__ import annotations

import logging
import traceback
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from desktop.qt_app.main_window import QualityLevel


# ---------------------------------------------------------------------------
# Log bridge — structlog/logging 출력을 worker.progress 시그널로 전달
# ---------------------------------------------------------------------------


class _QtLogHandler(logging.Handler):
    """root logger 의 record 를 worker.progress 시그널로 forward.

    주의 — 이 handler 는 worker thread 에서 호출되지만 progress.emit() 는 main thread
    의 signal queue 로 queued connection 으로 들어간다. 메쉬 빌드 단계에서 DEBUG 로그가
    초당 수천 건 발생하면 GUI thread 가 signal flood 를 처리하느라 마우스 입력이 막힌다.
    → 기본 INFO 레벨 + 동일 메시지 burst 무시 (단순 rate limit).
    """

    def __init__(self, worker: object) -> None:
        # GUI 에 노출할 가치가 있는 INFO 이상만 forward. DEBUG 는 콘솔/파일 logger 가
        # 받음 (root logger 는 level 그대로 유지).
        super().__init__(level=logging.INFO)
        self._worker = worker
        self._last_msg = ""
        self._last_msg_count = 0

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
        except Exception:
            msg = record.getMessage()
        # 초당 수천 회 동일/유사 메시지 폭주를 단순 압축.
        if msg == self._last_msg:
            self._last_msg_count += 1
            # 같은 줄이 16번 연속이면 그 다음부터는 16배수마다만 emit.
            if self._last_msg_count & (self._last_msg_count - 1):
                return
        else:
            self._last_msg = msg
            self._last_msg_count = 1
        level = record.levelname
        tag = {"WARNING": "WARN", "CRITICAL": "ERR", "ERROR": "ERR"}.get(level, level)
        try:
            self._worker.progress.emit(f"[{tag}] {msg}")  # type: ignore[attr-defined]
        except Exception:
            pass


def _attach_log_bridge(worker: object) -> _QtLogHandler:
    """워커가 돌아가는 동안 root logger에 QtLogHandler를 추가한다."""
    handler = _QtLogHandler(worker)
    # structlog 메시지의 타임스탬프/이벤트는 이미 포매팅되어 있으므로 message만 사용
    handler.setFormatter(logging.Formatter("%(message)s"))
    logging.getLogger().addHandler(handler)
    return handler


def _detach_log_bridge(handler: _QtLogHandler | None) -> None:
    if handler is None:
        return
    try:
        logging.getLogger().removeHandler(handler)
    except Exception:
        pass


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
        mesh_type: str = "auto",
        max_iterations: int = 3,
        auto_retry: str = "off",
        prefer_native: bool = False,
        prefer_native_tier: bool = False,
        dry_run: bool = False,
        element_size: float | None = None,
        max_cells: int | None = None,
        tier_specific_params: dict[str, Any] | None = None,
        no_repair: bool = False,
        surface_remesh: bool = False,
        remesh_engine: str = "auto",
        allow_ai_fallback: bool = False,
        validator_engine: str = "checkmesh",
        strict_tier: bool = False,
        # GUI-FIX / beta2811 — beta2299 호환: GUI cross_engine_fallback 통과.
        cross_engine_fallback: bool = False,
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
                mesh_type: str = "auto",
                max_iterations: int = 3,
                auto_retry: str = "off",
                prefer_native: bool = False,
                prefer_native_tier: bool = False,
                dry_run: bool = False,
                element_size: float | None = None,
                max_cells: int | None = None,
                tier_specific_params: dict[str, Any] | None = None,
                no_repair: bool = False,
                surface_remesh: bool = False,
                remesh_engine: str = "auto",
                allow_ai_fallback: bool = False,
                validator_engine: str = "checkmesh",
                strict_tier: bool = False,
                # beta2299: GUI cross_engine_fallback 체크박스 → orchestrator.
                cross_engine_fallback: bool = False,
            ) -> None:
                super().__init__()
                self._input_path = input_path
                self._quality_level = quality_level
                self._output_dir = output_dir
                self._tier_hint = tier_hint
                self._mesh_type = mesh_type
                self._max_iterations = max_iterations
                self._auto_retry = auto_retry
                self._prefer_native = bool(prefer_native)
                self._prefer_native_tier = bool(prefer_native_tier)
                self._dry_run = dry_run
                self._element_size = element_size
                self._max_cells = max_cells
                self._tier_specific_params = tier_specific_params or {}
                self._no_repair = no_repair
                self._surface_remesh = surface_remesh
                self._remesh_engine = remesh_engine
                self._allow_ai_fallback = allow_ai_fallback
                self._validator_engine = validator_engine
                self._strict_tier = strict_tier
                self._cross_engine_fallback = bool(cross_engine_fallback)

            def run(self) -> None:
                """파이프라인을 실행하고 결과를 finished 시그널로 emit."""
                # GUI 로그와 콘솔 로그를 일치시키기 위해 structlog/logging 출력을
                # progress 시그널로도 전달하는 핸들러를 설치한다.
                log_bridge = _attach_log_bridge(self)
                try:
                    from core.pipeline.orchestrator import PipelineOrchestrator

                    orchestrator = PipelineOrchestrator()
                    output_dir = self._output_dir or (self._input_path.parent / "output")
                    output_dir = output_dir.expanduser().resolve()
                    output_dir.mkdir(parents=True, exist_ok=True)

                    self.progress.emit(
                        f"파이프라인 시작: input={self._input_path.name} "
                        f"quality={self._quality_level.value} "
                        f"mesh_type={self._mesh_type} "
                        f"tier={self._tier_hint} "
                        f"auto_retry={self._auto_retry} "
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
                        mesh_type=self._mesh_type,
                        tier_hint=self._tier_hint,
                        max_iterations=self._max_iterations,
                        auto_retry=self._auto_retry,
                        prefer_native=self._prefer_native,
                        prefer_native_tier=self._prefer_native_tier,
                        dry_run=self._dry_run,
                        element_size=self._element_size,
                        max_cells=self._max_cells,
                        tier_specific_params=self._tier_specific_params,
                        no_repair=self._no_repair,
                        surface_remesh=self._surface_remesh,
                        remesh_engine=self._remesh_engine,
                        allow_ai_fallback=self._allow_ai_fallback,
                        validator_engine=self._validator_engine,
                        strict_tier=self._strict_tier,
                        cross_engine_fallback=self._cross_engine_fallback,
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
                finally:
                    # 로그 브리지 제거 — 이 워커가 끝난 뒤에도 로그가 전파되면 곤란하다.
                    try:
                        _detach_log_bridge(log_bridge)
                    except Exception:
                        pass

        instance = _Worker.__new__(_Worker)
        instance.__init__(
            input_path,
            quality_level,
            output_dir,
            tier_hint=tier_hint,
            mesh_type=mesh_type,
            max_iterations=max_iterations,
            auto_retry=auto_retry,
            prefer_native=prefer_native,
            prefer_native_tier=prefer_native_tier,
            dry_run=dry_run,
            element_size=element_size,
            max_cells=max_cells,
            tier_specific_params=tier_specific_params,
            no_repair=no_repair,
            surface_remesh=surface_remesh,
            remesh_engine=remesh_engine,
            allow_ai_fallback=allow_ai_fallback,
            validator_engine=validator_engine,
            strict_tier=strict_tier,
            cross_engine_fallback=cross_engine_fallback,
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
    """파이프라인 완료 결과에서 quality_report 메트릭을 emit.

    BETA2872 — 이전 구현이 quality_report 를 dict 로 가정해 isinstance(qr, dict)
    가 항상 False (실제 type 은 QualityReport pydantic model) → quality_update
    signal 한 번도 발화되지 않아 GUI Quality 탭이 영원히 0 으로 남았다.
    이제 evaluation_summary.checkmesh / additional_metrics 직접 추출.
    """
    metrics: dict = {}
    try:
        qr = getattr(result, "quality_report", None)
        if qr is None:
            return
        es = getattr(qr, "evaluation_summary", None)
        cm = getattr(es, "checkmesh", None) if es is not None else None
        if cm is not None:
            for src_attr, dst_key in (
                ("max_non_orthogonality", "max_non_ortho"),
                ("max_skewness", "max_skewness"),
                ("max_aspect_ratio", "max_aspect_ratio"),
                ("negative_volumes", "negative_volumes"),
                ("cells", "n_cells"),
                ("min_face_area", "min_face_area"),
                ("min_cell_volume", "min_vol"),
            ):
                v = getattr(cm, src_attr, None)
                if v is not None:
                    metrics[dst_key] = v
        am = getattr(es, "additional_metrics", None) if es is not None else None
        if am is not None:
            for src_attr, dst_key in (
                ("max_aspect_ratio", "max_aspect_ratio"),
            ):
                v = getattr(am, src_attr, None)
                if v is not None:
                    metrics[dst_key] = v
        if metrics:
            worker.quality_update.emit(metrics)  # type: ignore[union-attr]
    except Exception as exc:
        try:
            worker.progress.emit(  # type: ignore[union-attr]
                f"[DBG] quality emit 실패: {type(exc).__name__}: {exc}"
            )
        except Exception:
            pass
