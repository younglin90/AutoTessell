"""PipelineOrchestrator 테스트 — mock 기반 통합 테스트."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.pipeline.orchestrator import PipelineOrchestrator, PipelineResult
from core.schemas import (
    AdditionalMetrics,
    BoundingBox,
    CheckMeshResult,
    CellVolumeStats,
    DomainConfig,
    EvaluationSummary,
    ExecutionSummary,
    FeatureStats,
    FileInfo,
    FlowEstimation,
    GeneratorLog,
    Geometry,
    GeometryReport,
    MeshStrategy,
    PreprocessedReport,
    PreprocessingSummary,
    QualityLevel,
    QualityReport,
    QualityTargets,
    SurfaceMeshConfig,
    SurfaceQualityLevel,
    SurfaceStats,
    TierAttempt,
    TierCompatibility,
    TierCompatibilityMap,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_output(tmp_path):
    return tmp_path / "case"


@pytest.fixture
def sphere_stl():
    p = Path("tests/benchmarks/sphere.stl")
    if not p.exists():
        pytest.skip("sphere.stl not found")
    return p


def _make_geometry_report() -> GeometryReport:
    return GeometryReport(
        file_info=FileInfo(
            path="/test/sphere.stl",
            format="STL",
            file_size_bytes=1000,
            detected_encoding="binary",
            is_cad_brep=False,
            is_surface_mesh=True,
            is_volume_mesh=False,
        ),
        geometry=Geometry(
            bounding_box=BoundingBox(
                min=[-1, -1, -1], max=[1, 1, 1],
                center=[0, 0, 0], diagonal=3.46, characteristic_length=2.0,
            ),
            surface=SurfaceStats(
                num_vertices=642, num_faces=1280,
                surface_area=12.56, is_watertight=True,
                is_manifold=True, num_connected_components=1,
                euler_number=2, genus=0,
                has_degenerate_faces=False, num_degenerate_faces=0,
                min_face_area=1e-4, max_face_area=1e-2,
                face_area_std=1e-3,
                min_edge_length=0.01, max_edge_length=0.1,
                edge_length_ratio=10.0,
            ),
            features=FeatureStats(
                has_sharp_edges=False, num_sharp_edges=0,
                has_thin_walls=False, min_wall_thickness_estimate=0.1,
                has_small_features=False, smallest_feature_size=0.1,
                feature_to_bbox_ratio=0.05, curvature_max=2.0, curvature_mean=1.0,
            ),
        ),
        flow_estimation=FlowEstimation(
            type="external", confidence=0.9,
            reasoning="test", alternatives=[],
        ),
        issues=[],
        tier_compatibility=TierCompatibilityMap(
            tier0_core=TierCompatibility(compatible=True, notes="ok"),
            tier05_netgen=TierCompatibility(compatible=True, notes="ok"),
            tier1_snappy=TierCompatibility(compatible=True, notes="ok"),
            tier15_cfmesh=TierCompatibility(compatible=True, notes="ok"),
            tier2_tetwild=TierCompatibility(compatible=True, notes="ok"),
        ),
    )


def _make_preprocessed_report() -> PreprocessedReport:
    from core.schemas import FinalValidation
    return PreprocessedReport(
        preprocessing_summary=PreprocessingSummary(
            input_file="sphere.stl",
            input_format="STL",
            output_file="preprocessed.stl",
            passthrough_cad=False,
            total_time_seconds=0.1,
            steps_performed=[],
            final_validation=FinalValidation(
                is_watertight=True,
                is_manifold=True,
                num_faces=1280,
                min_face_area=1e-4,
                max_edge_length_ratio=10.0,
            ),
        )
    )


def _make_strategy() -> MeshStrategy:
    from core.schemas import BoundaryLayerConfig
    return MeshStrategy(
        strategy_version=2,
        iteration=1,
        selected_tier="tier2_tetwild",
        fallback_tiers=["tier05_netgen"],
        quality_level=QualityLevel.STANDARD,
        flow_type="external",
        domain=DomainConfig(
            type="box",
            min=[-10, -5, -5], max=[20, 5, 5],
            base_cell_size=0.1,
            location_in_mesh=[-9, 0, 0],
        ),
        surface_mesh=SurfaceMeshConfig(
            input_file="preprocessed.stl",
            target_cell_size=0.05,
            min_cell_size=0.01,
        ),
        boundary_layers=BoundaryLayerConfig(
            enabled=False, num_layers=0,
            first_layer_thickness=0.0, growth_ratio=1.2,
            max_total_thickness=0.0, min_thickness_ratio=0.1,
        ),
    )


def _make_checkmesh_result(**kwargs) -> CheckMeshResult:
    defaults = dict(
        cells=10000,
        faces=60000,
        points=12000,
        max_non_orthogonality=45.0,
        avg_non_orthogonality=10.0,
        max_skewness=1.5,
        max_aspect_ratio=5.0,
        min_face_area=1e-6,
        min_cell_volume=1e-9,
        min_determinant=0.8,
        negative_volumes=0,
        severely_non_ortho_faces=0,
        failed_checks=0,
        mesh_ok=True,
    )
    defaults.update(kwargs)
    return CheckMeshResult(**defaults)


def _make_cell_volume_stats(**kwargs) -> CellVolumeStats:
    defaults = dict(min=1e-9, max=1e-6, mean=5e-8, std=1e-8, ratio_max_min=1000.0)
    defaults.update(kwargs)
    return CellVolumeStats(**defaults)


def _make_generator_log(status: str = "success") -> GeneratorLog:
    return GeneratorLog(
        execution_summary=ExecutionSummary(
            selected_tier="tier2_tetwild",
            tiers_attempted=[
                TierAttempt(
                    tier="tier2_tetwild",
                    status=status,
                    time_seconds=1.0,
                )
            ],
            output_dir="/tmp/case",
            total_time_seconds=1.0,
        )
    )


def _make_quality_report(verdict: str = "PASS") -> QualityReport:
    return QualityReport(
        evaluation_summary=EvaluationSummary(
            verdict=verdict,
            iteration=1,
            tier_evaluated="tier2_tetwild",
            evaluation_time_seconds=0.5,
            checkmesh=_make_checkmesh_result(),
            additional_metrics=AdditionalMetrics(
                cell_volume_stats=_make_cell_volume_stats(),
            ),
        )
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPipelineOrchestrator:
    """오케스트레이터 기본 동작."""

    def test_init_default(self):
        orch = PipelineOrchestrator()
        assert orch._analyzer is not None
        assert orch._preprocessor is not None
        assert orch._planner is not None
        assert orch._generator is not None

    def test_init_custom_components(self):
        mock_analyzer = MagicMock()
        orch = PipelineOrchestrator(analyzer=mock_analyzer)
        assert orch._analyzer is mock_analyzer


class TestPipelineFlow:
    """파이프라인 실행 흐름 테스트."""

    def _make_orchestrator(
        self,
        generator_status="success",
        verdict="PASS",
    ) -> PipelineOrchestrator:
        analyzer = MagicMock()
        analyzer.analyze.return_value = _make_geometry_report()

        preprocessor = MagicMock()
        preprocessor.run.return_value = (Path("/tmp/preprocessed.stl"), _make_preprocessed_report())

        planner = MagicMock()
        planner.plan.return_value = _make_strategy()

        generator = MagicMock()
        generator.run.return_value = _make_generator_log(generator_status)

        checker = MagicMock()
        checker.run.return_value = _make_checkmesh_result()

        metrics = MagicMock()
        metrics.compute.return_value = AdditionalMetrics(
            cell_volume_stats=_make_cell_volume_stats(),
        )

        reporter = MagicMock()
        reporter.evaluate.return_value = _make_quality_report(verdict)

        return PipelineOrchestrator(
            analyzer=analyzer,
            preprocessor=preprocessor,
            planner=planner,
            generator=generator,
            checker=checker,
            metrics_computer=metrics,
            reporter=reporter,
        )

    def test_full_pipeline_pass(self, tmp_output):
        orch = self._make_orchestrator(verdict="PASS")
        result = orch.run(Path("sphere.stl"), tmp_output)

        assert result.success is True
        assert result.iterations == 1
        assert result.geometry_report is not None
        assert result.preprocessed_report is not None
        assert result.strategy is not None
        assert result.generator_log is not None
        assert result.quality_report is not None
        assert result.error is None

    def test_full_pipeline_pass_with_warnings(self, tmp_output):
        orch = self._make_orchestrator(verdict="PASS_WITH_WARNINGS")
        result = orch.run(Path("sphere.stl"), tmp_output)
        assert result.success is True

    def test_pipeline_calls_all_stages(self, tmp_output):
        orch = self._make_orchestrator()
        orch.run(Path("sphere.stl"), tmp_output)

        orch._analyzer.analyze.assert_called_once()
        orch._preprocessor.run.assert_called_once()
        orch._planner.plan.assert_called_once()
        orch._generator.run.assert_called_once()
        orch._checker.run.assert_called_once()
        orch._reporter.evaluate.assert_called_once()

    def test_dry_run_stops_after_strategy(self, tmp_output):
        orch = self._make_orchestrator()
        result = orch.run(Path("sphere.stl"), tmp_output, dry_run=True)

        assert result.success is True
        assert result.strategy is not None
        assert result.generator_log is None
        orch._generator.run.assert_not_called()

    def test_quality_level_passed_through(self, tmp_output):
        orch = self._make_orchestrator()
        orch.run(Path("sphere.stl"), tmp_output, quality_level="draft")

        call_kwargs = orch._planner.plan.call_args
        assert call_kwargs.kwargs.get("quality_level") == "draft" or \
               (len(call_kwargs.args) > 0 and "draft" in str(call_kwargs))

    def test_tier_hint_passed_through(self, tmp_output):
        orch = self._make_orchestrator()
        orch.run(Path("sphere.stl"), tmp_output, tier_hint="netgen")

        call_kwargs = orch._planner.plan.call_args
        assert call_kwargs.kwargs.get("tier_hint") == "netgen"


class TestRetryLoop:
    """Generator ↔ Evaluator 재시도 루프."""

    def _make_retry_orchestrator(self, verdicts: list[str]) -> PipelineOrchestrator:
        """여러 iteration에 걸쳐 다른 verdict를 반환하는 오케스트레이터."""
        analyzer = MagicMock()
        analyzer.analyze.return_value = _make_geometry_report()

        preprocessor = MagicMock()
        preprocessor.run.return_value = (Path("/tmp/preprocessed.stl"), _make_preprocessed_report())

        planner = MagicMock()
        planner.plan.return_value = _make_strategy()

        generator = MagicMock()
        generator.run.return_value = _make_generator_log("success")

        checker = MagicMock()
        checker.run.return_value = _make_checkmesh_result()

        metrics = MagicMock()
        metrics.compute.return_value = AdditionalMetrics(
            cell_volume_stats=_make_cell_volume_stats(),
        )

        reporter = MagicMock()
        reports = [_make_quality_report(v) for v in verdicts]
        reporter.evaluate.side_effect = reports

        return PipelineOrchestrator(
            analyzer=analyzer,
            preprocessor=preprocessor,
            planner=planner,
            generator=generator,
            checker=checker,
            metrics_computer=metrics,
            reporter=reporter,
        )

    def test_retry_on_fail_then_pass(self, tmp_output):
        orch = self._make_retry_orchestrator(["FAIL", "PASS"])
        result = orch.run(Path("sphere.stl"), tmp_output, max_iterations=3)

        assert result.success is True
        assert result.iterations == 2
        assert orch._generator.run.call_count == 2
        # planner called twice: initial + retry
        assert orch._planner.plan.call_count == 2

    def test_retry_exhausted(self, tmp_output):
        orch = self._make_retry_orchestrator(["FAIL", "FAIL", "FAIL"])
        result = orch.run(Path("sphere.stl"), tmp_output, max_iterations=3)

        assert result.success is False
        assert result.iterations == 3
        assert orch._generator.run.call_count == 3

    def test_retry_single_iteration(self, tmp_output):
        orch = self._make_retry_orchestrator(["FAIL"])
        result = orch.run(Path("sphere.stl"), tmp_output, max_iterations=1)

        assert result.success is False
        assert result.iterations == 1

    def test_no_retry_on_pass(self, tmp_output):
        orch = self._make_retry_orchestrator(["PASS"])
        result = orch.run(Path("sphere.stl"), tmp_output, max_iterations=3)

        assert result.success is True
        assert result.iterations == 1
        assert orch._generator.run.call_count == 1


class TestAllTiersFailed:
    """모든 Tier 실패 시 동작."""

    def test_all_tiers_failed_stops_loop(self, tmp_output):
        analyzer = MagicMock()
        analyzer.analyze.return_value = _make_geometry_report()

        preprocessor = MagicMock()
        preprocessor.run.return_value = (Path("/tmp/p.stl"), _make_preprocessed_report())

        planner = MagicMock()
        planner.plan.return_value = _make_strategy()

        generator = MagicMock()
        generator.run.return_value = _make_generator_log("failed")

        orch = PipelineOrchestrator(
            analyzer=analyzer, preprocessor=preprocessor,
            planner=planner, generator=generator,
        )
        result = orch.run(Path("sphere.stl"), tmp_output)

        assert result.success is False
        assert "All mesh generation tiers failed" in result.error
        assert result.iterations == 1


class TestJsonSave:
    """중간 결과 JSON 저장."""

    def test_saves_geometry_report(self, tmp_output):
        orch = TestPipelineFlow()._make_orchestrator()
        orch.run(Path("sphere.stl"), tmp_output, dry_run=True)

        assert (tmp_output / "geometry_report.json").exists()

    def test_saves_preprocessed_report(self, tmp_output):
        orch = TestPipelineFlow()._make_orchestrator()
        orch.run(Path("sphere.stl"), tmp_output, dry_run=True)

        assert (tmp_output / "preprocessed_report.json").exists()

    def test_saves_mesh_strategy(self, tmp_output):
        orch = TestPipelineFlow()._make_orchestrator()
        orch.run(Path("sphere.stl"), tmp_output, dry_run=True)

        assert (tmp_output / "mesh_strategy.json").exists()

    def test_saves_generator_log(self, tmp_output):
        orch = TestPipelineFlow()._make_orchestrator()
        orch.run(Path("sphere.stl"), tmp_output)

        assert (tmp_output / "generator_log.json").exists()

    def test_saves_quality_report(self, tmp_output):
        orch = TestPipelineFlow()._make_orchestrator()
        orch.run(Path("sphere.stl"), tmp_output)

        assert (tmp_output / "quality_report.json").exists()


class TestErrorHandling:
    """에러 핸들링."""

    def test_analyzer_error_caught(self, tmp_output):
        analyzer = MagicMock()
        analyzer.analyze.side_effect = RuntimeError("file not found")

        orch = PipelineOrchestrator(analyzer=analyzer)
        result = orch.run(Path("nonexistent.stl"), tmp_output)

        assert result.success is False
        assert "file not found" in result.error

    def test_evaluation_error_caught(self, tmp_output):
        orch = TestPipelineFlow()._make_orchestrator()
        orch._checker.run.side_effect = FileNotFoundError("checkMesh not found")

        result = orch.run(Path("sphere.stl"), tmp_output)

        assert result.success is False
        assert "checkMesh" in result.error


class TestPipelineResult:
    """PipelineResult 데이터클래스."""

    def test_default_values(self):
        r = PipelineResult(success=False)
        assert r.success is False
        assert r.iterations == 0
        assert r.error is None
        assert r.geometry_report is None

    def test_total_time_positive(self, tmp_output):
        orch = TestPipelineFlow()._make_orchestrator()
        result = orch.run(Path("sphere.stl"), tmp_output, dry_run=True)
        assert result.total_time_seconds > 0
