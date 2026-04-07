"""전체 파이프라인 오케스트레이터.

Analyzer → Preprocessor → Strategist → Generator ↔ Evaluator (최대 N회 반복)
"""

from __future__ import annotations

import json
import shutil
import time
from typing import Any
from dataclasses import dataclass, field
from pathlib import Path

from core.analyzer.geometry_analyzer import GeometryAnalyzer
from core.evaluator.fidelity import GeometryFidelityChecker
from core.evaluator.metrics import AdditionalMetricsComputer
from core.evaluator.quality_checker import MeshQualityChecker
from core.evaluator.report import EvaluationReporter
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
from core.generator.case_writer import FoamCaseWriter
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
        tier_hint: str = "auto",
        max_iterations: int = 3,
        dry_run: bool = False,
        element_size: float | None = None,
        no_repair: bool = False,
        surface_remesh: bool = False,
        allow_ai_fallback: bool = False,
        write_of_case: bool = True,
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
            no_repair: 표면 수리 건너뛰기.
            surface_remesh: 강제 리메쉬.
            allow_ai_fallback: L3 AI 수리 허용.
            write_of_case: True이면 Generator 완료 후 OpenFOAM 케이스 파일 자동 생성.

        Returns:
            PipelineResult with all intermediate artifacts.
        """
        start = time.perf_counter()
        result = PipelineResult(success=False)

        try:
            # ------ 1. Analyze ------
            log.info("Pipeline stage: Analyze", input=str(input_path))
            geometry_report = self._analyzer.analyze(input_path)
            result.geometry_report = geometry_report
            self._save_json(output_dir / "geometry_report.json", geometry_report)

            # ------ 2. Preprocess ------
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
                allow_ai_fallback=allow_ai_fallback,
            )
            result.preprocessed_report = preprocessed_report
            self._save_json(output_dir / "preprocessed_report.json", preprocessed_report)

            # ------ 3. Strategize ------
            log.info("Pipeline stage: Strategize", quality_level=quality_level)
            strategy = self._planner.plan(
                geometry_report=geometry_report,
                preprocessed_report=preprocessed_report,
                tier_hint=tier_hint,
                quality_level=quality_level,
            )

            # element_size override
            if element_size is not None:
                strategy.surface_mesh.target_cell_size = element_size
                strategy.surface_mesh.min_cell_size = element_size / 4
                strategy.domain.base_cell_size = element_size * 4
                log.info("element_size_override", element_size=element_size)

            result.strategy = strategy
            self._save_json(output_dir / "mesh_strategy.json", strategy)

            if dry_run:
                log.info("Dry-run mode: stopping after strategy")
                result.success = True
                result.total_time_seconds = time.perf_counter() - start
                return result

            # ------ 4 & 5. Generate ↔ Evaluate loop ------
            quality_report: QualityReport | None = None

            for iteration in range(1, max_iterations + 1):
                log.info(
                    "Pipeline stage: Generate",
                    iteration=iteration,
                    tier=strategy.selected_tier,
                )
                result.iterations = iteration

                # 재시도 시 전략 재수립
                if iteration > 1 and quality_report is not None:
                    log.info("Re-strategizing based on evaluator feedback")
                    strategy = self._planner.plan(
                        geometry_report=geometry_report,
                        preprocessed_report=preprocessed_report,
                        quality_report=quality_report,
                        tier_hint=tier_hint,
                        iteration=iteration,
                        quality_level=quality_level,
                    )
                    result.strategy = strategy
                    self._save_json(output_dir / "mesh_strategy.json", strategy)

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

                # 모든 Tier 실패 시 루프 종료
                successful_tier = self._find_successful_tier(generator_log)
                if successful_tier is None:
                    log.warning("All tiers failed", iteration=iteration)
                    result.error = "All mesh generation tiers failed"
                    break

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
                        case_writer = FoamCaseWriter()
                        of_files = case_writer.write_case(
                            mesh_dir=polymesh_dir,
                            case_dir=case_dir,
                            flow_type=flow_type,
                            solver=solver,
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
                log.info("Pipeline stage: Evaluate", tier=successful_tier)
                try:
                    quality_report = self._evaluate(
                        case_dir=case_dir,
                        strategy=strategy,
                        iteration=iteration,
                        tier=successful_tier,
                        quality_level=quality_level,
                        preprocessed_path=preprocessed_path,
                        geometry_report=geometry_report,
                    )
                except Exception as exc:
                    log.warning("Evaluation failed", error=str(exc))
                    quality_report = None
                    result.error = f"Evaluation error: {exc}"
                    break

                result.quality_report = quality_report
                self._save_json(output_dir / "quality_report.json", quality_report)

                verdict = quality_report.evaluation_summary.verdict
                if verdict in ("PASS", "PASS_WITH_WARNINGS"):
                    log.info("Pipeline PASS", verdict=verdict, iteration=iteration)
                    result.success = True
                    # Classify boundary patches on success
                    try:
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
                    break
                else:
                    log.warning(
                        "Evaluation FAIL, will retry",
                        verdict=verdict,
                        iteration=iteration,
                        max_iterations=max_iterations,
                    )

            if not result.success and result.error is None:
                result.error = f"Failed after {result.iterations} iterations"

        except Exception as exc:
            log.error("Pipeline error", error=str(exc), exc_info=True)
            result.error = str(exc)

        result.total_time_seconds = time.perf_counter() - start
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
    ) -> QualityReport:
        """Evaluator 단계 실행."""
        eval_start = time.perf_counter()
        checkmesh = self._checker.run(case_dir)
        metrics = self._metrics.compute(case_dir)

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

        return self._reporter.evaluate(
            checkmesh=checkmesh,
            strategy=strategy,
            metrics=metrics,
            geometry_fidelity=geometry_fidelity,
            iteration=iteration,
            tier=tier,
            elapsed=elapsed,
            quality_level=quality_level,
        )

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
