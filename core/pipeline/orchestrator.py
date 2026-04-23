"""전체 파이프라인 오케스트레이터.

Analyzer → Preprocessor → Strategist → Generator ↔ Evaluator (최대 N회 반복)
"""

from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from core.analyzer.geometry_analyzer import GeometryAnalyzer
from core.evaluator.fidelity import GeometryFidelityChecker
from core.evaluator.metrics import AdditionalMetricsComputer
from core.evaluator.quality_checker import MeshQualityChecker
from core.evaluator.report import EvaluationReporter
from core.generator.case_writer import FoamCaseWriter
from core.generator.pipeline import MeshGenerator
from core.preprocessor.pipeline import Preprocessor
from core.schemas import (
    GeneratorLog,
    GeometryReport,
    MeshStrategy,
    PreprocessedReport,
    QualityReport,
)
from core.strategist.strategy_planner import StrategyPlanner
from core.utils.bc_writer import write_boundary_conditions
from core.utils.boundary_classifier import classify_boundaries
from core.utils.logging import get_logger

log = get_logger(__name__)


@dataclass
class PipelineResult:
    """전체 파이프라인 실행 결과."""

    success: bool
    geometry_report: GeometryReport | None = None
    preprocessed_report: PreprocessedReport | None = None
    strategy: MeshStrategy | None = None
    generator_log: GeneratorLog | None = None
    quality_report: QualityReport | None = None
    iterations: int = 0
    total_time_seconds: float = 0.0
    error: str | None = None
    boundary_patches: list[dict[str, Any]] = field(default_factory=list)


class PipelineOrchestrator:
    """5-Agent 파이프라인을 순서대로 실행하고 재시도 루프를 관리한다."""

    def __init__(
        self,
        analyzer: GeometryAnalyzer | None = None,
        preprocessor: Preprocessor | None = None,
        planner: StrategyPlanner | None = None,
        generator: MeshGenerator | None = None,
        checker: MeshQualityChecker | None = None,
        metrics_computer: AdditionalMetricsComputer | None = None,
        reporter: EvaluationReporter | None = None,
        fidelity_checker: GeometryFidelityChecker | None = None,
    ) -> None:
        self._analyzer = analyzer or GeometryAnalyzer()
        self._preprocessor = preprocessor or Preprocessor()
        self._planner = planner or StrategyPlanner()
        self._generator = generator or MeshGenerator()
        self._checker = checker or MeshQualityChecker()
        self._metrics = metrics_computer or AdditionalMetricsComputer()
        self._reporter = reporter or EvaluationReporter()
        self._fidelity = fidelity_checker or GeometryFidelityChecker()

    def run(
        self,
        input_path: Path,
        output_dir: Path,
        *,
        quality_level: str = "standard",
        mesh_type: str = "auto",
        tier_hint: str = "auto",
        max_iterations: int = 3,
        auto_retry: str = "off",
        dry_run: bool = False,
        element_size: float | None = None,
        max_cells: int | None = None,
        tier_specific_params: dict[str, Any] | None = None,
        no_repair: bool = False,
        surface_remesh: bool = False,
        remesh_engine: str = "auto",
        allow_ai_fallback: bool = False,
        write_of_case: bool = True,
        strict_tier: bool = False,
        validator_engine: str = "auto",
        prefer_native: bool = False,
        prefer_native_tier: bool = False,
        cross_engine_fallback: bool = False,
        _cross_engine_retried: bool = False,
        flow_velocity: float = 1.0,
        turbulence_model: str = "kEpsilon",
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> PipelineResult:
        """전체 파이프라인을 실행한다.

        Args:
            input_path: 입력 CAD/메쉬 파일 경로.
            output_dir: OpenFOAM case 출력 디렉터리.
            quality_level: 품질 레벨 (draft/standard/fine).
            tier_hint: Tier 힌트 (auto/snappy/netgen/...).
            max_iterations: Generator↔Evaluator 최대 반복 횟수.
            dry_run: True이면 전략 수립까지만 수행.
            element_size: 셀 크기 override.
            max_cells: 최대 셀 수 제한 (초과 시 base_cell_size 자동 확대).
            tier_specific_params: Tier별 사용자 파라미터 override.
            no_repair: 표면 수리 건너뛰기.
            surface_remesh: 강제 리메쉬.
            remesh_engine: L2 표면 리메쉬 엔진 선택.
            allow_ai_fallback: L3 AI 수리 허용.
            write_of_case: True이면 Generator 완료 후 OpenFOAM 케이스 파일 자동 생성.
            strict_tier: True면 명시 tier(auto 아님)에서 fallback tier를 비활성화.
            progress_callback: (percent, message) 진행률 콜백.

        Returns:
            PipelineResult with all intermediate artifacts.
        """
        start = time.perf_counter()
        result = PipelineResult(success=False)
        max_iterations = max(1, int(max_iterations))
        stage = "init"

        # Tier 5 엔진 선택 (v0.4 native-first):
        #   "auto"    → NativeMeshChecker 기본, OpenFOAM 은 교차 검증용
        #   "native"  → NativeMeshChecker 강제
        #   "checkmesh" / "openfoam" → OpenFOAM checkMesh 우선 (없으면 native fallback)
        #   "disabled"→ 아직 verdict 스킵 미구현 → native fallback
        _v = str(validator_engine or "auto").lower()
        _prefer_native = _v in ("auto", "native", "disabled")
        try:
            self._checker.set_prefer_native(_prefer_native)
        except Exception:
            pass
        log.info(
            "validator_engine_selected",
            requested=validator_engine,
            prefer_native=_prefer_native,
        )

        def emit_progress(percent: int, message: str) -> None:
            if progress_callback is None:
                return
            p = max(0, min(100, int(percent)))
            try:
                progress_callback(p, message)
            except Exception as exc:  # noqa: BLE001
                log.debug("progress_callback_failed", error=str(exc))

        try:
            log.debug(
                "pipeline_run_params",
                input_path=str(input_path),
                output_dir=str(output_dir),
                quality_level=quality_level,
                tier_hint=tier_hint,
                max_iterations=max_iterations,
                dry_run=dry_run,
                element_size=element_size,
                max_cells=max_cells,
                no_repair=no_repair,
                surface_remesh=surface_remesh,
                remesh_engine=remesh_engine,
                allow_ai_fallback=allow_ai_fallback,
                write_of_case=write_of_case,
                strict_tier=strict_tier,
                tier_param_keys=sorted((tier_specific_params or {}).keys()),
            )
            emit_progress(1, "Analyze 시작")
            log.info(
                "retry_policy",
                max_iterations=max_iterations,
                rules=[
                    "failed_checks_or_cells0 -> tier fallback",
                    "quality_fail -> parameter relax + optional quality downgrade",
                    "max_cells_limit -> base_cell_size enlarge",
                ],
            )
            # ------ 1. Analyze ------
            stage = "analyze"
            log.info("Pipeline stage: Analyze", input=str(input_path))
            geometry_report = self._analyzer.analyze(input_path)
            result.geometry_report = geometry_report
            self._save_json(output_dir / "geometry_report.json", geometry_report)
            emit_progress(12, "Analyze 완료")

            # ------ 2. Preprocess ------
            stage = "preprocess"
            emit_progress(15, "Preprocess 시작")
            log.info("Pipeline stage: Preprocess")
            work_dir = output_dir / "_work"
            work_dir.mkdir(parents=True, exist_ok=True)

            preprocessed_path, preprocessed_report = self._preprocessor.run(
                input_path=input_path,
                geometry_report=geometry_report,
                output_dir=work_dir,
                tier_hint=tier_hint if tier_hint != "auto" else None,
                no_repair=no_repair,
                surface_remesh=surface_remesh,
                remesh_engine=remesh_engine,
                allow_ai_fallback=allow_ai_fallback,
                prefer_native=prefer_native,
            )
            result.preprocessed_report = preprocessed_report
            self._save_json(output_dir / "preprocessed_report.json", preprocessed_report)
            emit_progress(32, "Preprocess 완료")

            # ------ 3. Strategize ------
            stage = "strategize"
            emit_progress(35, "Strategize 시작")
            log.info(
                "Pipeline stage: Strategize",
                quality_level=quality_level,
                mesh_type=mesh_type,
            )
            strategy = self._planner.plan(
                geometry_report=geometry_report,
                preprocessed_report=preprocessed_report,
                tier_hint=tier_hint,
                quality_level=quality_level,
                mesh_type=mesh_type,
                prefer_native_tier=prefer_native_tier,
            )

            self._apply_strategy_overrides(
                strategy,
                element_size=element_size,
                max_cells=max_cells,
                tier_specific_params=tier_specific_params,
            )
            # strict_tier 정보를 strategy 에 기록 (Generator 가 fallback 회피용으로 참조)
            try:
                strategy.strict_tier = bool(
                    strict_tier and str(tier_hint).lower() != "auto"
                )
            except Exception:
                pass
            if strict_tier and str(tier_hint).lower() != "auto":
                if strategy.fallback_tiers:
                    log.info(
                        "strict_tier_applied",
                        selected_tier=strategy.selected_tier,
                        removed_fallbacks=strategy.fallback_tiers,
                    )
                strategy.fallback_tiers = []
            result.strategy = strategy
            self._save_json(output_dir / "mesh_strategy.json", strategy)
            emit_progress(42, "Strategize 완료")

            if dry_run:
                log.info("Dry-run mode: stopping after strategy")
                result.success = True
                result.total_time_seconds = time.perf_counter() - start
                emit_progress(100, "Dry-run 완료")
                return result

            # ------ 4 & 5. Generate ↔ Evaluate loop ------
            # auto_retry 가 자동 재시도 모드를 결정 (v0.4 이후 기본 off):
            #   off      → 1 회 시도 후 FAIL 이어도 종료 (사용자가 결정)
            #   once     → 최대 2 회
            #   continue → 기존 max_iterations (하위호환)
            _auto_retry_mode = str(auto_retry or "off").lower()
            if _auto_retry_mode == "off":
                effective_iters = 1
            elif _auto_retry_mode == "once":
                effective_iters = 2
            elif _auto_retry_mode == "continue":
                effective_iters = max_iterations
            else:
                # 알 수 없는 값 → off 취급 (가장 안전)
                log.warning(
                    "auto_retry_unknown_value_fallback_off", value=auto_retry,
                )
                effective_iters = 1
            log.info(
                "auto_retry_mode",
                mode=_auto_retry_mode,
                effective_iterations=effective_iters,
                max_iterations=max_iterations,
            )

            quality_report: QualityReport | None = None
            _last_iter_cells: int | None = None  # strict_tier early-stop 용

            for iteration in range(1, effective_iters + 1):
                loop_start = 45 + int((iteration - 1) * (45 / effective_iters))
                loop_generate_done = 45 + int(((iteration - 1) + 0.55) * (45 / effective_iters))
                loop_eval_done = 45 + int(((iteration - 1) + 0.90) * (45 / effective_iters))
                emit_progress(loop_start, f"Generate {iteration}/{effective_iters}")
                stage = f"generate(iter={iteration})"
                log.info(
                    "Pipeline stage: Generate",
                    iteration=iteration,
                    tier=strategy.selected_tier,
                )
                result.iterations = iteration

                # 재시도 시 전략 재수립
                if iteration > 1 and quality_report is not None:
                    log.info("Re-strategizing based on evaluator feedback")
                    prev_summary = quality_report.evaluation_summary
                    strategy = self._planner.plan(
                        geometry_report=geometry_report,
                        preprocessed_report=preprocessed_report,
                        quality_report=quality_report,
                        tier_hint=tier_hint,
                        iteration=iteration,
                        quality_level=quality_level,
                        mesh_type=mesh_type,
                        prefer_native_tier=prefer_native_tier,
                    )
                    self._apply_strategy_overrides(
                        strategy,
                        element_size=element_size,
                        max_cells=max_cells,
                        tier_specific_params=tier_specific_params,
                    )
                    # strict_tier: 사용자가 명시적으로 엔진을 선택했을 때 Strategist 가
                    # 다른 tier 로 switch 해버리면 안 된다. tier_hint canonical 이름으로
                    # 강제 복원 (planner 가 switch_tier 를 적용해 selected_tier 가
                    # 바뀐 경우 되돌림).
                    if strict_tier and str(tier_hint).lower() != "auto":
                        from core.strategist.tier_selector import canonical_tier
                        try:
                            forced = canonical_tier(str(tier_hint))
                        except Exception:
                            forced = None
                        if forced and forced != "auto" and strategy.selected_tier != forced:
                            log.warning(
                                "strict_tier_override_switch",
                                from_tier=strategy.selected_tier,
                                forced_to=forced,
                                reason="user 명시 엔진 유지",
                            )
                            strategy.selected_tier = forced
                        strategy.fallback_tiers = []
                    result.strategy = strategy
                    self._save_json(output_dir / "mesh_strategy.json", strategy)
                    log.info(
                        "retry_decision",
                        iteration=iteration,
                        previous_tier=prev_summary.tier_evaluated,
                        previous_verdict=prev_summary.verdict.value,
                        previous_failed_checks=prev_summary.checkmesh.failed_checks,
                        previous_cells=prev_summary.checkmesh.cells,
                        next_tier=strategy.selected_tier,
                        fallback_tiers=strategy.fallback_tiers,
                        quality_level=strategy.quality_level.value,
                        base_cell_size=strategy.domain.base_cell_size,
                        target_cell_size=strategy.surface_mesh.target_cell_size,
                    )

                # case 디렉터리 초기화 (재시도 시)
                case_dir = output_dir
                if iteration > 1:
                    polymesh = case_dir / "constant" / "polyMesh"
                    if polymesh.exists():
                        shutil.rmtree(polymesh)

                # Generate
                generator_log = self._generator.run(
                    strategy=strategy,
                    preprocessed_path=preprocessed_path,
                    case_dir=case_dir,
                )
                result.generator_log = generator_log
                self._save_json(output_dir / "generator_log.json", generator_log)
                emit_progress(loop_generate_done, f"Generate 완료 {iteration}/{max_iterations}")

                # 모든 Tier 실패 시 루프 종료
                successful_tier = self._find_successful_tier(generator_log)
                if successful_tier is None:
                    log.warning("All tiers failed", iteration=iteration)
                    result.error = "All mesh generation tiers failed"
                    break

                # ── Tier 4 (BL post-processing) 선택적 실행 ──
                # 주 엔진이 snappy/cfmesh 가 아니어도 tier_specific_params 로
                # post_layers_engine 이 지정되면 layer 엔진 독립 실행.
                # v0.4.0-beta24+: strategy.boundary_layers.enabled=True 이고
                # post_layers_engine 이 명시되지 않으면 "auto" 로 기본 주입.
                # mesh_type 별 BL 엔진 (tet_bl_subdivide / native_bl /
                # poly_bl_transition) 이 LayersPostGenerator 내부에서 자동 선택.
                _tsp = (strategy.tier_specific_params or {}) if strategy else {}
                _post_engine = _tsp.get("post_layers_engine", None)
                if _post_engine is None:
                    if (
                        strategy is not None
                        and strategy.boundary_layers is not None
                        and bool(strategy.boundary_layers.enabled)
                        and int(strategy.boundary_layers.num_layers) > 0
                    ):
                        _post_engine = "auto"
                        # strategy 에도 기록 (downstream gen 이 읽을 수 있도록)
                        if strategy.tier_specific_params is None:
                            strategy.tier_specific_params = {}
                        strategy.tier_specific_params["post_layers_engine"] = "auto"
                        log.info(
                            "post_layers_engine_auto_populated",
                            reason="boundary_layers_enabled",
                            num_layers=strategy.boundary_layers.num_layers,
                        )
                    else:
                        _post_engine = "disabled"
                _post_result_for_bl: Any = None
                if str(_post_engine).lower() not in ("disabled", "none", "off", ""):
                    try:
                        from core.generator.tier_layers_post import LayersPostGenerator
                        post_gen = LayersPostGenerator()
                        _post_result_for_bl = post_gen.run(
                            strategy=strategy,
                            preprocessed_path=preprocessed_path,
                            case_dir=case_dir,
                        )
                        log.info(
                            "post_layers_stage_done",
                            engine=_post_engine,
                            status=_post_result_for_bl.status,
                            elapsed=_post_result_for_bl.time_seconds,
                            msg=_post_result_for_bl.error_message,
                        )
                    except Exception as exc:
                        log.warning(
                            "post_layers_stage_exception",
                            engine=_post_engine, error=str(exc),
                        )

                # OpenFOAM 케이스 파일 생성 (write_of_case=True 일 때)
                if write_of_case:
                    try:
                        flow_type = strategy.flow_type if strategy else "external"
                        solver = (
                            "pimpleFoam"
                            if strategy and strategy.quality_level.value == "fine"
                            else "simpleFoam"
                        )
                        polymesh_dir = case_dir / "constant" / "polyMesh"
                        patches = classify_boundaries(case_dir, flow_type=flow_type)
                        result.boundary_patches = patches
                        # beta83: GUI 는 flow_velocity / turbulence_model 을
                        # tier_specific_params 로 전달 (TIER_PARAM_SPECS 경유).
                        # CLI 직접 kwarg 가 우선, tier_specific_params 는 fallback.
                        tsp = tier_specific_params or {}
                        _fv = float(tsp.get("flow_velocity", flow_velocity))
                        _tm = str(tsp.get("turbulence_model", turbulence_model))
                        case_writer = FoamCaseWriter(
                            flow_velocity=_fv,
                            turbulence_model=_tm,
                        )
                        of_files = case_writer.write_case(
                            mesh_dir=polymesh_dir,
                            case_dir=case_dir,
                            flow_type=flow_type,
                            solver=solver,
                            patches=patches or None,
                        )
                        log.info(
                            "openfoam_case_files_generated",
                            count=len(of_files),
                            solver=solver,
                        )
                    except Exception as exc:
                        log.warning(
                            "openfoam_case_generation_skipped",
                            error=str(exc),
                        )

                # Evaluate
                stage = f"evaluate(iter={iteration})"
                emit_progress(loop_generate_done + 2, f"Evaluate {iteration}/{max_iterations}")
                log.info("Pipeline stage: Evaluate", tier=successful_tier)
                try:
                    _bl_p2_for_eval = getattr(
                        _post_result_for_bl, "native_bl_phase2", None,
                    )
                    quality_report = self._evaluate(
                        case_dir=case_dir,
                        strategy=strategy,
                        iteration=iteration,
                        tier=successful_tier,
                        quality_level=quality_level,
                        preprocessed_path=preprocessed_path,
                        geometry_report=geometry_report,
                        bl_phase2_stats=_bl_p2_for_eval,
                    )
                except Exception as exc:
                    log.warning("Evaluation failed", error=str(exc))
                    quality_report = None
                    result.error = f"Evaluation error: {exc}"
                    break

                result.quality_report = quality_report
                self._save_json(output_dir / "quality_report.json", quality_report)
                emit_progress(loop_eval_done, f"Evaluate 완료 {iteration}/{effective_iters}")

                verdict = quality_report.evaluation_summary.verdict
                if verdict in ("PASS", "PASS_WITH_WARNINGS"):
                    log.info("Pipeline PASS", verdict=verdict, iteration=iteration)
                    result.success = True
                    # Refresh boundary typing from the final mesh, then rewrite BCs.
                    try:
                        stage = f"postprocess_boundary(iter={iteration})"
                        flow_type = strategy.flow_type if strategy else "external"
                        patches = classify_boundaries(case_dir, flow_type=flow_type)
                        result.boundary_patches = patches
                        log.info(
                            "boundary_patches_classified",
                            count=len(patches),
                            patches=[(p["name"], p["type"]) for p in patches],
                        )
                        # 경계 조건 자동 생성
                        if patches:
                            bc_files = write_boundary_conditions(case_dir, patches)
                            log.info("boundary_conditions_generated", files=bc_files)
                    except Exception as exc:
                        log.warning("boundary_classification_skipped", error=str(exc))
                    emit_progress(100, f"PASS ({iteration}회)")
                    break
                else:
                    will_retry = iteration < effective_iters
                    log.warning(
                        "Evaluation FAIL",
                        verdict=verdict,
                        iteration=iteration,
                        max_iterations=max_iterations,
                        effective_iterations=effective_iters,
                        auto_retry=_auto_retry_mode,
                        will_retry=will_retry,
                    )
                    if not will_retry:
                        # auto_retry=off / once-끝난 경우 → 루프 탈출,
                        # recommendation 은 quality_report 에 이미 기록됨.
                        # 사용자 확인은 cli/main.py 또는 GUI 가 처리.
                        break
                    # strict_tier 모드에서 Strategist 가 파라미터 조정 없이 동일한
                    # tier/cell 수 를 반복하면 재시도가 의미 없다 → 조기 종료.
                    if strict_tier and str(tier_hint).lower() != "auto":
                        prev_cells = getattr(
                            getattr(quality_report, "checkmesh", None),
                            "cells", None,
                        )
                        if prev_cells is not None and prev_cells == _last_iter_cells:
                            log.warning(
                                "strict_tier_early_stop",
                                reason=(
                                    "동일 tier/cells 반복 — Strategist 에 "
                                    "유효한 파라미터 조정 없음. 재시도 중단."
                                ),
                                iteration=iteration,
                                cells=prev_cells,
                            )
                            result.error = (
                                "strict_tier 모드 재시도 조기 종료: "
                                f"tier={strategy.selected_tier} 가 동일 cells={prev_cells} "
                                "을 반복 생성. 파라미터 수동 튜닝 필요."
                            )
                            break
                        _last_iter_cells = prev_cells

            if not result.success and result.error is None:
                result.error = f"Failed after {result.iterations} iterations"
            if not result.success:
                emit_progress(100, "FAIL")

        except Exception as exc:
            log.exception(
                "pipeline_exception",
                stage=stage,
                error=str(exc),
                error_type=exc.__class__.__name__,
                input_path=str(input_path),
                output_dir=str(output_dir),
            )
            result.error = f"[{stage}] {exc.__class__.__name__}: {exc}"
            emit_progress(100, "오류로 중단")

        result.total_time_seconds = time.perf_counter() - start

        # beta68: cross-engine fallback — poly 실패 시 hex_dominant 로 1 회 재시도.
        # _cross_engine_retried 는 recursive flag (무한 루프 방지).
        if (
            not result.success
            and cross_engine_fallback
            and not _cross_engine_retried
            and str(mesh_type or "").lower() == "poly"
        ):
            log.warning(
                "cross_engine_fallback_triggered",
                from_mesh_type="poly", to_mesh_type="hex_dominant",
                original_error=result.error,
            )
            retried = self.run(
                input_path=input_path,
                output_dir=output_dir,
                quality_level=quality_level,
                mesh_type="hex_dominant",
                tier_hint=tier_hint,
                max_iterations=max_iterations,
                auto_retry=auto_retry,
                dry_run=dry_run,
                element_size=element_size,
                max_cells=max_cells,
                tier_specific_params=tier_specific_params,
                no_repair=no_repair,
                surface_remesh=surface_remesh,
                remesh_engine=remesh_engine,
                allow_ai_fallback=allow_ai_fallback,
                write_of_case=write_of_case,
                strict_tier=strict_tier,
                validator_engine=validator_engine,
                prefer_native=prefer_native,
                prefer_native_tier=prefer_native_tier,
                cross_engine_fallback=False,
                _cross_engine_retried=True,
                progress_callback=progress_callback,
            )
            # annotate: 재시도 성공이라도 originally poly 였음을 표시.
            if retried.error:
                retried.error = (
                    f"[cross_engine_fallback poly→hex_dominant] {retried.error}"
                )
            else:
                retried.error = None
            return retried

        return result

    def _evaluate(
        self,
        case_dir: Path,
        strategy: MeshStrategy,
        iteration: int,
        tier: str,
        quality_level: str,
        preprocessed_path: Path | None = None,
        geometry_report: GeometryReport | None = None,
        bl_phase2_stats=None,  # NativeBLPhase2Stats | None — beta76
    ) -> QualityReport:
        """Evaluator 단계 실행."""
        eval_start = time.perf_counter()
        checkmesh = self._checker.run(case_dir)
        metrics = self._metrics.compute(case_dir)
        # beta76: inject BL Phase 2 stats passed from tier_layers_post.
        if bl_phase2_stats is not None:
            metrics.native_bl_phase2 = bl_phase2_stats

        # 지오메트리 충실도 계산 (원본 STL과 대각선 길이가 있을 때만)
        geometry_fidelity = None
        if preprocessed_path is not None and geometry_report is not None:
            try:
                diagonal = geometry_report.geometry.bounding_box.diagonal
                geometry_fidelity = self._fidelity.compute(
                    original_stl=preprocessed_path,
                    case_dir=case_dir,
                    diagonal=diagonal,
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("Geometry fidelity 계산 실패 (무시)", error=str(exc))

        elapsed = time.perf_counter() - eval_start

        report = self._reporter.evaluate(
            checkmesh=checkmesh,
            strategy=strategy,
            metrics=metrics,
            geometry_fidelity=geometry_fidelity,
            iteration=iteration,
            tier=tier,
            elapsed=elapsed,
            quality_level=quality_level,
        )
        # v0.4: 어느 checker 엔진이 실제 사용됐는지 + mesh_type 을 report 에 주입.
        try:
            engine_used = getattr(self._checker, "last_engine_used", None)
            # MagicMock 등 str 이 아닌 값은 None 처리 (pydantic 직렬화 경고 회피)
            if engine_used is not None and not isinstance(engine_used, str):
                engine_used = None
            report.evaluation_summary.checker_engine_used = engine_used
            mt_val = getattr(strategy, "mesh_type", None)
            if hasattr(mt_val, "value"):
                mt_val = mt_val.value
            if mt_val is not None and not isinstance(mt_val, str):
                mt_val = str(mt_val)
            report.evaluation_summary.mesh_type = mt_val
        except Exception:
            pass
        return report

    @staticmethod
    def _find_successful_tier(generator_log: GeneratorLog) -> str | None:
        """GeneratorLog에서 성공한 Tier를 찾는다."""
        for attempt in generator_log.execution_summary.tiers_attempted:
            if attempt.status == "success":
                return attempt.tier
        return None

    @staticmethod
    def _save_json(path: Path, model: object) -> None:
        """Pydantic 모델을 JSON 파일로 저장한다."""
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            if hasattr(model, "model_dump_json"):
                path.write_text(model.model_dump_json(indent=2))
            elif hasattr(model, "json"):
                path.write_text(model.json(indent=2))
            else:
                path.write_text(json.dumps(model, indent=2, default=str))
        except Exception as exc:
            log.warning("Failed to save JSON", path=str(path), error=str(exc))

    @staticmethod
    def _apply_max_cells_limit(strategy: MeshStrategy, max_cells: int | None) -> None:
        """max_cells 제한을 만족하도록 base_cell_size를 보정한다."""
        if max_cells is None:
            return

        base_cell = strategy.domain.base_cell_size
        if base_cell <= 0:
            return

        domain_vol = 1.0
        for i in range(3):
            domain_vol *= strategy.domain.max[i] - strategy.domain.min[i]

        est_cells = domain_vol / (base_cell ** 3)
        if est_cells > max_cells:
            strategy.domain.base_cell_size = (domain_vol / max_cells) ** (1.0 / 3.0)
            log.info(
                "base_cell_enlarged_for_max_cells",
                est_cells=int(est_cells),
                max_cells=max_cells,
                new_base_cell=strategy.domain.base_cell_size,
            )

    @staticmethod
    def _apply_tier_specific_params(
        strategy: MeshStrategy,
        tier_specific_params: dict[str, Any] | None,
    ) -> None:
        if not tier_specific_params:
            return
        strategy.tier_specific_params.update(tier_specific_params)
        log.info(
            "tier_specific_params_override",
            keys=sorted(tier_specific_params.keys()),
            tier=strategy.selected_tier,
        )

    @staticmethod
    def _apply_strategy_overrides(
        strategy: MeshStrategy,
        *,
        element_size: float | None,
        max_cells: int | None,
        tier_specific_params: dict[str, Any] | None,
    ) -> None:
        if element_size is not None:
            strategy.surface_mesh.target_cell_size = element_size
            strategy.surface_mesh.min_cell_size = element_size / 4
            strategy.domain.base_cell_size = element_size * 4
            log.info("element_size_override", element_size=element_size)
        PipelineOrchestrator._apply_max_cells_limit(strategy, max_cells)

        # BL, 표면 메쉬 파라미터 처리 (tier_specific_params에서 추출)
        if tier_specific_params:
            # GUI Tier 4 콤보 → BL on/off 강제 override
            # (quality_level 기반 자동 결정보다 우선)
            if "boundary_layers_enabled" in tier_specific_params:
                bl_enabled = bool(tier_specific_params["boundary_layers_enabled"])
                strategy.boundary_layers.enabled = bl_enabled
                if not bl_enabled:
                    strategy.boundary_layers.num_layers = 0
                log.info("boundary_layers_enabled_override", enabled=bl_enabled)
            if "bl_layers" in tier_specific_params:
                bl_layers = tier_specific_params["bl_layers"]
                strategy.boundary_layers.enabled = bl_layers > 0
                strategy.boundary_layers.num_layers = bl_layers
                log.info("bl_layers_override", bl_layers=bl_layers)
            if "bl_first_height" in tier_specific_params:
                bl_first_height = tier_specific_params["bl_first_height"]
                strategy.boundary_layers.first_layer_thickness = bl_first_height
                log.info("bl_first_height_override", bl_first_height=bl_first_height)
            if "bl_growth_ratio" in tier_specific_params:
                bl_growth_ratio = tier_specific_params["bl_growth_ratio"]
                strategy.boundary_layers.growth_ratio = bl_growth_ratio
                log.info("bl_growth_ratio_override", bl_growth_ratio=bl_growth_ratio)
            if "min_cell_size" in tier_specific_params:
                min_cell_size = tier_specific_params["min_cell_size"]
                strategy.surface_mesh.min_cell_size = min_cell_size
                log.info("min_cell_size_override", min_cell_size=min_cell_size)

        PipelineOrchestrator._apply_tier_specific_params(strategy, tier_specific_params)
