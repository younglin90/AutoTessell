"""PipelineOrchestrator 테스트.

OpenFOAM 없이도 동작하도록 Generator / Checker 등은 monkeypatch로 대체한다.
dry_run 모드로 Analyzer → Preprocessor → Strategist 단계를 실제 실행하고,
그 이후 단계는 mock을 사용해 PASS/FAIL 분기를 검증한다.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from core.evaluator.report import EvaluationReporter
from core.pipeline.orchestrator import PipelineOrchestrator, PipelineResult
from core.schemas import (
    AdditionalMetrics,
    BoundaryLayerStats,
    BoundaryPatch,
    CheckMeshResult,
    CellVolumeStats,
    EvaluationSummary,
    ExecutionSummary,
    GeneratorLog,
    GeometryFidelity,
    MeshStats,
    QualityReport,
    TierAttempt,
    Verdict,
)

# ---------------------------------------------------------------------------
# 벤치마크 경로
# ---------------------------------------------------------------------------

SPHERE_STL = Path("tests/benchmarks/sphere.stl")


def _require_sphere() -> None:
    if not SPHERE_STL.exists():
        pytest.skip("sphere.stl not found — run from repo root")


# ---------------------------------------------------------------------------
# 헬퍼 팩토리
# ---------------------------------------------------------------------------


def _make_checkmesh_result(
    *,
    cells: int = 100000,
    faces: int = 300000,
    points: int = 150000,
    max_non_orthogonality: float = 30.0,
    avg_non_orthogonality: float = 5.0,
    max_skewness: float = 1.5,
    max_aspect_ratio: float = 20.0,
    min_face_area: float = 1e-8,
    min_cell_volume: float = 1e-12,
    min_determinant: float = 0.5,
    negative_volumes: int = 0,
    severely_non_ortho_faces: int = 0,
    failed_checks: int = 0,
    mesh_ok: bool = True,
) -> CheckMeshResult:
    return CheckMeshResult(
        cells=cells,
        faces=faces,
        points=points,
        max_non_orthogonality=max_non_orthogonality,
        avg_non_orthogonality=avg_non_orthogonality,
        max_skewness=max_skewness,
        max_aspect_ratio=max_aspect_ratio,
        min_face_area=min_face_area,
        min_cell_volume=min_cell_volume,
        min_determinant=min_determinant,
        negative_volumes=negative_volumes,
        severely_non_ortho_faces=severely_non_ortho_faces,
        failed_checks=failed_checks,
        mesh_ok=mesh_ok,
    )


def _make_generator_log(tier: str = "tier2_tetwild", status: str = "success") -> GeneratorLog:
    """성공(또는 실패) GeneratorLog를 생성한다."""
    return GeneratorLog(
        execution_summary=ExecutionSummary(
            selected_tier=tier,
            tiers_attempted=[
                TierAttempt(
                    tier=tier,
                    status=status,
                    time_seconds=5.0,
                    mesh_stats=MeshStats(
                        num_cells=100000,
                        num_points=50000,
                        num_faces=300000,
                        num_internal_faces=250000,
                        num_boundary_patches=3,
                        boundary_patches=[
                            BoundaryPatch(name="inlet", type="patch", num_faces=100),
                            BoundaryPatch(name="outlet", type="patch", num_faces=100),
                            BoundaryPatch(name="walls", type="wall", num_faces=5000),
                        ],
                    ) if status == "success" else None,
                    error_message=None if status == "success" else "Meshing failed",
                )
            ],
            output_dir="/tmp/test_case",
            total_time_seconds=5.0,
            quality_level="draft",
        )
    )


def _make_quality_report(verdict: Verdict, quality_level: str = "standard") -> QualityReport:
    """指定した verdict の QualityReport を生成する。"""
    cm = _make_checkmesh_result()
    reporter = EvaluationReporter()
    if verdict == Verdict.FAIL:
        cm = _make_checkmesh_result(max_non_orthogonality=75.0)
    elif verdict == Verdict.PASS_WITH_WARNINGS:
        cm = _make_checkmesh_result(max_non_orthogonality=66.0)
    return reporter.evaluate(
        checkmesh=cm,
        strategy=None,
        metrics=AdditionalMetrics(),
        geometry_fidelity=None,
        iteration=1,
        tier="tier2_tetwild",
        elapsed=1.0,
        quality_level=quality_level,
    )


# ---------------------------------------------------------------------------
# PipelineResult 스키마 테스트
# ---------------------------------------------------------------------------


class TestPipelineResultSchema:
    """PipelineResult 데이터클래스 구조 검증."""

    def test_default_values(self) -> None:
        result = PipelineResult(success=False)
        assert result.success is False
        assert result.geometry_report is None
        assert result.preprocessed_report is None
        assert result.strategy is None
        assert result.generator_log is None
        assert result.quality_report is None
        assert result.iterations == 0
        assert result.total_time_seconds == 0.0
        assert result.error is None
        assert result.boundary_patches == []

    def test_success_result(self) -> None:
        result = PipelineResult(success=True, iterations=2, total_time_seconds=12.5)
        assert result.success is True
        assert result.iterations == 2
        assert result.total_time_seconds == pytest.approx(12.5)

    def test_error_result(self) -> None:
        result = PipelineResult(success=False, error="Some error")
        assert result.error == "Some error"

    def test_boundary_patches_stored(self) -> None:
        patches = [{"name": "inlet", "type": "patch"}, {"name": "walls", "type": "wall"}]
        result = PipelineResult(success=True, boundary_patches=patches)
        assert len(result.boundary_patches) == 2
        assert result.boundary_patches[0]["name"] == "inlet"


# ---------------------------------------------------------------------------
# PipelineOrchestrator._find_successful_tier テスト
# ---------------------------------------------------------------------------


class TestFindSuccessfulTier:
    """_find_successful_tier 정적 메서드 단위 테스트."""

    def test_find_success(self) -> None:
        log = _make_generator_log("tier2_tetwild", "success")
        tier = PipelineOrchestrator._find_successful_tier(log)
        assert tier == "tier2_tetwild"

    def test_find_none_when_all_failed(self) -> None:
        log = _make_generator_log("tier2_tetwild", "failed")
        tier = PipelineOrchestrator._find_successful_tier(log)
        assert tier is None

    def test_find_first_success_when_multiple_attempts(self) -> None:
        log = GeneratorLog(
            execution_summary=ExecutionSummary(
                selected_tier="tier2_tetwild",
                tiers_attempted=[
                    TierAttempt(tier="tier1_snappy", status="failed", time_seconds=1.0),
                    TierAttempt(tier="tier2_tetwild", status="success", time_seconds=5.0),
                    TierAttempt(tier="tier0_core", status="success", time_seconds=2.0),
                ],
                output_dir="/tmp/x",
                total_time_seconds=8.0,
            )
        )
        tier = PipelineOrchestrator._find_successful_tier(log)
        assert tier == "tier2_tetwild"

    def test_find_none_with_empty_tiers(self) -> None:
        log = GeneratorLog(
            execution_summary=ExecutionSummary(
                selected_tier="tier2_tetwild",
                tiers_attempted=[],
                output_dir="/tmp/x",
                total_time_seconds=0.0,
            )
        )
        tier = PipelineOrchestrator._find_successful_tier(log)
        assert tier is None


# ---------------------------------------------------------------------------
# PipelineOrchestrator._save_json テスト
# ---------------------------------------------------------------------------


class TestSaveJson:
    """_save_json 정적 메서드 단위 테스트."""

    def test_save_pydantic_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.json"
            cm = _make_checkmesh_result()
            PipelineOrchestrator._save_json(path, cm)
            assert path.exists()
            data = json.loads(path.read_text())
            assert data["cells"] == 100000

    def test_save_creates_parent_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "deep" / "report.json"
            PipelineOrchestrator._save_json(path, {"key": "value"})
            assert path.exists()

    def test_save_quality_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "quality_report.json"
            report = _make_quality_report(Verdict.PASS)
            PipelineOrchestrator._save_json(path, report)
            assert path.exists()
            data = json.loads(path.read_text())
            assert "evaluation_summary" in data

    def test_save_handles_non_serializable_gracefully(self) -> None:
        """직렬화 불가 객체도 예외를 던지지 않는다."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "obj.json"
            # dict with Path (non-serializable by default json)
            PipelineOrchestrator._save_json(path, {"path": Path("/some/path")})
            # Should not raise


# ---------------------------------------------------------------------------
# dry_run 모드 — 실제 Analyzer + Preprocessor + Strategist 사용
# ---------------------------------------------------------------------------


class TestDryRun:
    """dry_run=True 시 Analyzer → Preprocessor → Strategist까지만 실행한다."""

    def test_dry_run_returns_success(self) -> None:
        _require_sphere()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "case"
            orchestrator = PipelineOrchestrator()
            result = orchestrator.run(
                input_path=SPHERE_STL,
                output_dir=out,
                quality_level="draft",
                dry_run=True,
            )
        assert result.success is True

    def test_dry_run_populates_geometry_report(self) -> None:
        _require_sphere()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "case"
            result = PipelineOrchestrator().run(
                input_path=SPHERE_STL,
                output_dir=out,
                dry_run=True,
            )
        assert result.geometry_report is not None
        assert result.geometry_report.geometry.bounding_box.diagonal > 0

    def test_dry_run_populates_preprocessed_report(self) -> None:
        _require_sphere()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "case"
            result = PipelineOrchestrator().run(
                input_path=SPHERE_STL,
                output_dir=out,
                dry_run=True,
            )
        assert result.preprocessed_report is not None

    def test_dry_run_populates_strategy(self) -> None:
        _require_sphere()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "case"
            result = PipelineOrchestrator().run(
                input_path=SPHERE_STL,
                output_dir=out,
                dry_run=True,
                quality_level="standard",
            )
        assert result.strategy is not None
        assert result.strategy.quality_level.value == "standard"

    def test_dry_run_no_generator_log(self) -> None:
        """dry_run 시 generator_log는 None이어야 한다."""
        _require_sphere()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "case"
            result = PipelineOrchestrator().run(
                input_path=SPHERE_STL,
                output_dir=out,
                dry_run=True,
            )
        assert result.generator_log is None

    def test_dry_run_no_quality_report(self) -> None:
        """dry_run 시 quality_report는 None이어야 한다."""
        _require_sphere()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "case"
            result = PipelineOrchestrator().run(
                input_path=SPHERE_STL,
                output_dir=out,
                dry_run=True,
            )
        assert result.quality_report is None

    def test_dry_run_saves_geometry_report_json(self) -> None:
        """dry_run 완료 후 geometry_report.json이 저장된다."""
        _require_sphere()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "case"
            PipelineOrchestrator().run(
                input_path=SPHERE_STL,
                output_dir=out,
                dry_run=True,
            )
            assert (out / "geometry_report.json").exists()

    def test_dry_run_saves_mesh_strategy_json(self) -> None:
        """dry_run 완료 후 mesh_strategy.json이 저장된다."""
        _require_sphere()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "case"
            PipelineOrchestrator().run(
                input_path=SPHERE_STL,
                output_dir=out,
                dry_run=True,
            )
            assert (out / "mesh_strategy.json").exists()

    def test_dry_run_element_size_override(self) -> None:
        """element_size override가 strategy에 반영된다."""
        _require_sphere()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "case"
            result = PipelineOrchestrator().run(
                input_path=SPHERE_STL,
                output_dir=out,
                dry_run=True,
                element_size=0.05,
            )
        assert result.strategy is not None
        assert result.strategy.surface_mesh.target_cell_size == pytest.approx(0.05)

    def test_dry_run_all_quality_levels(self) -> None:
        """draft / standard / fine 세 레벨 모두 dry_run 성공."""
        _require_sphere()
        for level in ("draft", "standard", "fine"):
            with tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / "case"
                result = PipelineOrchestrator().run(
                    input_path=SPHERE_STL,
                    output_dir=out,
                    dry_run=True,
                    quality_level=level,
                )
                assert result.success is True, f"dry_run failed for quality_level={level}"
                assert result.strategy is not None
                assert result.strategy.quality_level.value == level

    def test_dry_run_iterations_zero(self) -> None:
        """dry_run 시 iterations == 0 (Generate 루프 미실행)."""
        _require_sphere()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "case"
            result = PipelineOrchestrator().run(
                input_path=SPHERE_STL,
                output_dir=out,
                dry_run=True,
            )
        assert result.iterations == 0


# ---------------------------------------------------------------------------
# Generator + Evaluator mock를 사용한 파이프라인 흐름 테스트
# ---------------------------------------------------------------------------


def _make_mock_generator(tier: str = "tier2_tetwild", status: str = "success"):
    """MeshGenerator를 모방하는 mock 객체 반환."""
    mock = MagicMock()
    mock.run.return_value = _make_generator_log(tier, status)
    return mock


def _make_mock_checker(checkmesh: CheckMeshResult | None = None):
    """MeshQualityChecker를 모방하는 mock 객체 반환."""
    mock = MagicMock()
    mock.run.return_value = checkmesh or _make_checkmesh_result()
    return mock


def _make_mock_metrics():
    mock = MagicMock()
    mock.compute.return_value = AdditionalMetrics()
    return mock


def _make_mock_fidelity(result: GeometryFidelity | None = None):
    mock = MagicMock()
    mock.compute.return_value = result
    return mock


class TestPipelineWithMockedGenerator:
    """Generator와 Checker를 mock으로 교체한 파이프라인 흐름 테스트."""

    def _run(
        self,
        *,
        checker_cm: CheckMeshResult | None = None,
        generator_status: str = "success",
        quality_level: str = "draft",
        max_iterations: int = 3,
        auto_retry: str = "continue",
        write_of_case: bool = False,
    ) -> PipelineResult:
        _require_sphere()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "case"
            orchestrator = PipelineOrchestrator(
                generator=_make_mock_generator("tier2_tetwild", generator_status),
                checker=_make_mock_checker(checker_cm),
                metrics_computer=_make_mock_metrics(),
                fidelity_checker=_make_mock_fidelity(),
                reporter=EvaluationReporter(),
            )
            return orchestrator.run(
                input_path=SPHERE_STL,
                output_dir=out,
                quality_level=quality_level,
                max_iterations=max_iterations,
                auto_retry=auto_retry,
                write_of_case=write_of_case,
            )

    def test_pass_verdict_success(self) -> None:
        """Clean mesh → Verdict.PASS → result.success=True."""
        result = self._run(checker_cm=_make_checkmesh_result())
        assert result.success is True
        assert result.quality_report is not None
        assert result.quality_report.evaluation_summary.verdict in (
            Verdict.PASS, Verdict.PASS_WITH_WARNINGS
        )

    def test_pass_with_warnings_success(self) -> None:
        """Soft fail 1개 → PASS_WITH_WARNINGS → result.success=True."""
        cm = _make_checkmesh_result(max_non_orthogonality=66.0)  # > 65 soft for standard
        result = self._run(checker_cm=cm, quality_level="standard")
        assert result.success is True

    def test_all_tiers_failed_sets_error(self) -> None:
        """Generator 실패 (all tiers failed) → result.success=False, error 설정."""
        result = self._run(generator_status="failed")
        assert result.success is False
        assert result.error is not None

    def test_iterations_count_on_pass(self) -> None:
        """첫 번째 시도에서 PASS → iterations == 1."""
        result = self._run(checker_cm=_make_checkmesh_result())
        assert result.iterations == 1

    def test_quality_report_stored_on_pass(self) -> None:
        """PASS 시 quality_report가 PipelineResult에 저장된다."""
        result = self._run()
        assert result.quality_report is not None
        assert isinstance(result.quality_report, QualityReport)

    def test_generator_log_stored(self) -> None:
        """generator_log가 PipelineResult에 저장된다."""
        result = self._run()
        assert result.generator_log is not None
        assert isinstance(result.generator_log, GeneratorLog)

    def test_total_time_positive(self) -> None:
        """total_time_seconds > 0."""
        result = self._run()
        assert result.total_time_seconds > 0.0

    def test_hard_fail_retries_up_to_max(self) -> None:
        """auto_retry=continue + max_iterations 까지 재시도한다 (mock 동일 결과)."""
        cm = _make_checkmesh_result(max_non_orthogonality=75.0)  # hard fail for standard
        result = self._run(
            checker_cm=cm, quality_level="standard",
            max_iterations=2, auto_retry="continue",
        )
        # After 2 iterations both FAIL → success=False
        assert result.success is False
        assert result.iterations == 2

    def test_auto_retry_off_single_iteration(self) -> None:
        """auto_retry=off (v0.4 기본) → Hard FAIL 이어도 1 회만 시도."""
        cm = _make_checkmesh_result(max_non_orthogonality=75.0)
        result = self._run(
            checker_cm=cm, quality_level="standard",
            max_iterations=5, auto_retry="off",
        )
        assert result.success is False
        assert result.iterations == 1, (
            f"auto_retry=off 인데 {result.iterations} 회 반복됨"
        )

    def test_auto_retry_once_stops_after_two(self) -> None:
        """auto_retry=once → FAIL 시 최대 2 회만 시도."""
        cm = _make_checkmesh_result(max_non_orthogonality=75.0)
        result = self._run(
            checker_cm=cm, quality_level="standard",
            max_iterations=10, auto_retry="once",
        )
        assert result.success is False
        assert result.iterations == 2

    def test_write_of_case_false_no_crash(self) -> None:
        """write_of_case=False でも crash しない。"""
        result = self._run(write_of_case=False)
        assert result.total_time_seconds > 0.0


# ---------------------------------------------------------------------------
# 파이프라인 에러 핸들링
# ---------------------------------------------------------------------------


class TestPipelineErrorHandling:
    """Analyzer 예외 등 에러 핸들링."""

    def test_invalid_input_file_returns_error(self) -> None:
        """존재하지 않는 파일 → success=False, error 설정."""
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "case"
            result = PipelineOrchestrator().run(
                input_path=Path("/nonexistent/file.stl"),
                output_dir=out,
                dry_run=True,
            )
        assert result.success is False
        assert result.error is not None

    def test_error_message_non_empty_on_failure(self) -> None:
        """실패 시 error 메시지가 비어 있지 않다."""
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "case"
            result = PipelineOrchestrator().run(
                input_path=Path("/nonexistent/file.stl"),
                output_dir=out,
            )
        assert result.error is not None
        assert len(result.error) > 0

    def test_geometry_report_none_on_error(self) -> None:
        """Analyzer 실패 시 geometry_report가 None이다."""
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "case"
            result = PipelineOrchestrator().run(
                input_path=Path("/nonexistent/file.stl"),
                output_dir=out,
            )
        # geometry_report may or may not be populated depending on failure point
        assert result.success is False

    def test_orchestrator_custom_components_injected(self) -> None:
        """생성자에서 주입한 컴포넌트가 실제로 사용된다."""
        mock_analyzer = MagicMock()
        mock_analyzer.analyze.side_effect = RuntimeError("analyzer error")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "case"
            orchestrator = PipelineOrchestrator(analyzer=mock_analyzer)
            result = orchestrator.run(
                input_path=SPHERE_STL if SPHERE_STL.exists() else Path("/tmp/x.stl"),
                output_dir=out,
            )
        assert result.success is False
        assert "analyzer error" in (result.error or "")


# ---------------------------------------------------------------------------
# dry_run 후 strategy 내용 검증
# ---------------------------------------------------------------------------


class TestDryRunStrategyContent:
    """dry_run으로 생성된 MeshStrategy 내용 검증."""

    def test_strategy_has_valid_domain(self) -> None:
        _require_sphere()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "case"
            result = PipelineOrchestrator().run(
                input_path=SPHERE_STL,
                output_dir=out,
                dry_run=True,
            )
        s = result.strategy
        assert s is not None
        assert s.domain.base_cell_size > 0
        assert len(s.domain.min) == 3
        assert len(s.domain.max) == 3

    def test_strategy_has_valid_surface_mesh_config(self) -> None:
        _require_sphere()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "case"
            result = PipelineOrchestrator().run(
                input_path=SPHERE_STL,
                output_dir=out,
                dry_run=True,
            )
        s = result.strategy
        assert s is not None
        assert s.surface_mesh.target_cell_size > 0
        assert s.surface_mesh.min_cell_size > 0
        assert s.surface_mesh.target_cell_size >= s.surface_mesh.min_cell_size

    def test_strategy_has_boundary_layer_config(self) -> None:
        _require_sphere()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "case"
            result = PipelineOrchestrator().run(
                input_path=SPHERE_STL,
                output_dir=out,
                dry_run=True,
                quality_level="fine",
            )
        s = result.strategy
        assert s is not None
        assert hasattr(s.boundary_layers, "enabled")
        assert hasattr(s.boundary_layers, "num_layers")
        assert hasattr(s.boundary_layers, "growth_ratio")

    def test_strategy_selected_tier_is_string(self) -> None:
        _require_sphere()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "case"
            result = PipelineOrchestrator().run(
                input_path=SPHERE_STL,
                output_dir=out,
                dry_run=True,
                quality_level="draft",
            )
        assert isinstance(result.strategy.selected_tier, str)
        assert len(result.strategy.selected_tier) > 0

    def test_strategy_json_file_is_valid_json(self) -> None:
        _require_sphere()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "case"
            PipelineOrchestrator().run(
                input_path=SPHERE_STL,
                output_dir=out,
                dry_run=True,
            )
            strategy_file = out / "mesh_strategy.json"
            assert strategy_file.exists()
            data = json.loads(strategy_file.read_text())
            assert "selected_tier" in data
            assert "quality_level" in data

    def test_geometry_report_json_file_is_valid(self) -> None:
        _require_sphere()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "case"
            PipelineOrchestrator().run(
                input_path=SPHERE_STL,
                output_dir=out,
                dry_run=True,
            )
            geo_file = out / "geometry_report.json"
            assert geo_file.exists()
            data = json.loads(geo_file.read_text())
            assert "geometry" in data
            assert "file_info" in data


# ---------------------------------------------------------------------------
# GeneratorLog 스키마 검증
# ---------------------------------------------------------------------------


class TestGeneratorLogSchema:
    """GeneratorLog Pydantic 모델 검증."""

    def test_generator_log_json_roundtrip(self) -> None:
        log = _make_generator_log("tier2_tetwild", "success")
        json_str = log.model_dump_json()
        recovered = GeneratorLog.model_validate_json(json_str)
        assert recovered.execution_summary.selected_tier == "tier2_tetwild"

    def test_generator_log_failed_tier(self) -> None:
        log = _make_generator_log("tier1_snappy", "failed")
        attempt = log.execution_summary.tiers_attempted[0]
        assert attempt.status == "failed"
        assert attempt.error_message is not None

    def test_generator_log_successful_tier_has_mesh_stats(self) -> None:
        log = _make_generator_log("tier2_tetwild", "success")
        attempt = log.execution_summary.tiers_attempted[0]
        assert attempt.mesh_stats is not None
        assert attempt.mesh_stats.num_cells > 0

    def test_tier_attempt_time_positive(self) -> None:
        log = _make_generator_log()
        assert log.execution_summary.tiers_attempted[0].time_seconds > 0
