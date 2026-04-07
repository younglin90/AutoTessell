"""core/schemas.py 및 core/utils/errors.py 포괄적 테스트.

Pydantic 모델 기본값·필수 필드 누락·JSON 라운드트립·Enum 값·
필드 타입·제약 조건·에러 클래스 계층 구조를 검증한다.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from core.schemas import (
    AdditionalMetrics,
    BoundaryLayerConfig,
    BoundaryLayerStats,
    BoundaryPatch,
    BoundingBox,
    CellVolumeStats,
    CheckMeshResult,
    DomainConfig,
    EvaluationSummary,
    ExecutionSummary,
    FailCriterion,
    FeatureStats,
    FileInfo,
    FinalValidation,
    FlowEstimation,
    Geometry,
    GeometryFidelity,
    GeometryReport,
    GeneratorLog,
    GeneratorStep,
    Issue,
    MeshStats,
    MeshStrategy,
    PreprocessedReport,
    PreprocessingSummary,
    PreprocessStep,
    PreviousAttempt,
    QualityLevel,
    QualityReport,
    QualityTargets,
    Recommendation,
    RefinementRegion,
    Severity,
    SurfaceMeshConfig,
    SurfaceQualityLevel,
    SurfaceStats,
    TierAttempt,
    TierCompatibility,
    TierCompatibilityMap,
    Verdict,
)
from core.utils.errors import AutoTessellError, diagnose_error


# ---------------------------------------------------------------------------
# Enum 검증
# ---------------------------------------------------------------------------


class TestSeverityEnum:
    def test_values(self):
        assert Severity.CRITICAL == "critical"
        assert Severity.WARNING == "warning"
        assert Severity.INFO == "info"

    def test_from_string(self):
        assert Severity("critical") is Severity.CRITICAL
        assert Severity("warning") is Severity.WARNING
        assert Severity("info") is Severity.INFO

    def test_invalid_value(self):
        with pytest.raises(ValueError):
            Severity("unknown")

    def test_is_str_subclass(self):
        assert isinstance(Severity.CRITICAL, str)


class TestVerdictEnum:
    def test_values(self):
        assert Verdict.PASS == "PASS"
        assert Verdict.PASS_WITH_WARNINGS == "PASS_WITH_WARNINGS"
        assert Verdict.FAIL == "FAIL"

    def test_from_string(self):
        assert Verdict("PASS") is Verdict.PASS
        assert Verdict("FAIL") is Verdict.FAIL

    def test_invalid_value(self):
        with pytest.raises(ValueError):
            Verdict("pass")  # 소문자는 유효하지 않음

    def test_is_str_subclass(self):
        assert isinstance(Verdict.PASS, str)


class TestQualityLevelEnum:
    def test_values(self):
        assert QualityLevel.DRAFT == "draft"
        assert QualityLevel.STANDARD == "standard"
        assert QualityLevel.FINE == "fine"

    def test_from_string(self):
        assert QualityLevel("draft") is QualityLevel.DRAFT
        assert QualityLevel("fine") is QualityLevel.FINE

    def test_invalid_value(self):
        with pytest.raises(ValueError):
            QualityLevel("ultra")


class TestSurfaceQualityLevelEnum:
    def test_values(self):
        assert SurfaceQualityLevel.L1_REPAIR == "l1_repair"
        assert SurfaceQualityLevel.L2_REMESH == "l2_remesh"
        assert SurfaceQualityLevel.L3_AI == "l3_ai"

    def test_from_string(self):
        assert SurfaceQualityLevel("l1_repair") is SurfaceQualityLevel.L1_REPAIR

    def test_invalid_value(self):
        with pytest.raises(ValueError):
            SurfaceQualityLevel("l4_magic")


# ---------------------------------------------------------------------------
# BoundingBox
# ---------------------------------------------------------------------------


class TestBoundingBox:
    def _make(self, **kwargs):
        defaults = dict(
            min=[-1.0, -1.0, -1.0],
            max=[1.0, 1.0, 1.0],
            center=[0.0, 0.0, 0.0],
            diagonal=3.464,
            characteristic_length=1.732,
        )
        defaults.update(kwargs)
        return BoundingBox(**defaults)

    def test_valid(self):
        bb = self._make()
        assert bb.diagonal == pytest.approx(3.464)
        assert bb.characteristic_length == pytest.approx(1.732)

    def test_min_length_3_required(self):
        with pytest.raises(ValidationError):
            self._make(min=[0.0, 0.0])  # length 2

    def test_max_length_3_required(self):
        with pytest.raises(ValidationError):
            self._make(max=[1.0, 1.0, 1.0, 1.0])  # length 4

    def test_center_length_3_required(self):
        with pytest.raises(ValidationError):
            self._make(center=[0.0])

    def test_missing_diagonal_raises(self):
        with pytest.raises(ValidationError):
            BoundingBox(
                min=[0.0, 0.0, 0.0],
                max=[1.0, 1.0, 1.0],
                center=[0.5, 0.5, 0.5],
                characteristic_length=1.0,
            )

    def test_json_roundtrip(self):
        bb = self._make()
        data = bb.model_dump_json()
        bb2 = BoundingBox.model_validate_json(data)
        assert bb2.diagonal == bb.diagonal
        assert bb2.min == bb.min


# ---------------------------------------------------------------------------
# SurfaceStats
# ---------------------------------------------------------------------------


class TestSurfaceStats:
    def _make(self, **kwargs):
        defaults = dict(
            num_vertices=1000,
            num_faces=2000,
            surface_area=12.5,
            is_watertight=True,
            is_manifold=True,
            num_connected_components=1,
            euler_number=2,
            genus=0,
            has_degenerate_faces=False,
            num_degenerate_faces=0,
            min_face_area=0.001,
            max_face_area=0.5,
            face_area_std=0.05,
            min_edge_length=0.01,
            max_edge_length=0.8,
            edge_length_ratio=80.0,
        )
        defaults.update(kwargs)
        return SurfaceStats(**defaults)

    def test_valid(self):
        s = self._make()
        assert s.num_vertices == 1000
        assert s.is_watertight is True
        assert s.edge_length_ratio == pytest.approx(80.0)

    def test_missing_required_field_raises(self):
        with pytest.raises(ValidationError):
            SurfaceStats(
                num_vertices=100,
                # num_faces missing
                surface_area=1.0,
                is_watertight=True,
                is_manifold=True,
                num_connected_components=1,
                euler_number=2,
                genus=0,
                has_degenerate_faces=False,
                num_degenerate_faces=0,
                min_face_area=0.001,
                max_face_area=0.5,
                face_area_std=0.05,
                min_edge_length=0.01,
                max_edge_length=0.8,
                edge_length_ratio=80.0,
            )

    def test_bool_fields(self):
        s = self._make(is_watertight=False, is_manifold=False, has_degenerate_faces=True)
        assert s.is_watertight is False
        assert s.has_degenerate_faces is True

    def test_json_roundtrip(self):
        s = self._make()
        s2 = SurfaceStats.model_validate_json(s.model_dump_json())
        assert s2.num_faces == s.num_faces
        assert s2.edge_length_ratio == s.edge_length_ratio


# ---------------------------------------------------------------------------
# FeatureStats
# ---------------------------------------------------------------------------


class TestFeatureStats:
    def _make(self, **kwargs):
        defaults = dict(
            has_sharp_edges=True,
            num_sharp_edges=50,
            has_thin_walls=False,
            min_wall_thickness_estimate=0.5,
            has_small_features=False,
            smallest_feature_size=0.1,
            feature_to_bbox_ratio=0.05,
            curvature_max=10.0,
            curvature_mean=2.0,
        )
        defaults.update(kwargs)
        return FeatureStats(**defaults)

    def test_default_sharp_edge_angle(self):
        f = self._make()
        assert f.sharp_edge_angle_threshold == pytest.approx(30.0)

    def test_custom_sharp_edge_angle(self):
        f = self._make(sharp_edge_angle_threshold=45.0)
        assert f.sharp_edge_angle_threshold == pytest.approx(45.0)

    def test_required_fields_present(self):
        f = self._make()
        assert f.curvature_max == pytest.approx(10.0)
        assert f.curvature_mean == pytest.approx(2.0)

    def test_missing_required_raises(self):
        with pytest.raises(ValidationError):
            FeatureStats(
                has_sharp_edges=True,
                num_sharp_edges=10,
                # has_thin_walls missing
                min_wall_thickness_estimate=0.5,
                has_small_features=False,
                smallest_feature_size=0.1,
                feature_to_bbox_ratio=0.05,
                curvature_max=5.0,
                curvature_mean=1.0,
            )


# ---------------------------------------------------------------------------
# FlowEstimation
# ---------------------------------------------------------------------------


class TestFlowEstimation:
    def test_valid(self):
        fe = FlowEstimation(type="external", confidence=0.9, reasoning="open domain")
        assert fe.confidence == pytest.approx(0.9)
        assert fe.alternatives == []

    def test_confidence_ge_0(self):
        with pytest.raises(ValidationError):
            FlowEstimation(type="external", confidence=-0.1, reasoning="bad")

    def test_confidence_le_1(self):
        with pytest.raises(ValidationError):
            FlowEstimation(type="internal", confidence=1.1, reasoning="bad")

    def test_confidence_boundary_0(self):
        fe = FlowEstimation(type="unknown", confidence=0.0, reasoning="no idea")
        assert fe.confidence == pytest.approx(0.0)

    def test_confidence_boundary_1(self):
        fe = FlowEstimation(type="external", confidence=1.0, reasoning="certain")
        assert fe.confidence == pytest.approx(1.0)

    def test_alternatives_default_empty(self):
        fe = FlowEstimation(type="external", confidence=0.5, reasoning="guess")
        assert fe.alternatives == []

    def test_alternatives_provided(self):
        fe = FlowEstimation(
            type="external", confidence=0.7, reasoning="likely", alternatives=["internal"]
        )
        assert "internal" in fe.alternatives


# ---------------------------------------------------------------------------
# TierCompatibilityMap
# ---------------------------------------------------------------------------


class TestTierCompatibilityMap:
    def _make_tier(self, compatible=True):
        return TierCompatibility(compatible=compatible, notes="ok")

    def test_all_5_tiers_present(self):
        tcm = TierCompatibilityMap(
            tier0_core=self._make_tier(True),
            tier05_netgen=self._make_tier(True),
            tier1_snappy=self._make_tier(False),
            tier15_cfmesh=self._make_tier(True),
            tier2_tetwild=self._make_tier(True),
        )
        assert tcm.tier0_core.compatible is True
        assert tcm.tier1_snappy.compatible is False
        assert tcm.tier2_tetwild.compatible is True

    def test_missing_tier_raises(self):
        with pytest.raises(ValidationError):
            TierCompatibilityMap(
                tier0_core=self._make_tier(),
                tier05_netgen=self._make_tier(),
                # tier1_snappy missing
                tier15_cfmesh=self._make_tier(),
                tier2_tetwild=self._make_tier(),
            )

    def test_json_roundtrip(self):
        tcm = TierCompatibilityMap(
            tier0_core=self._make_tier(),
            tier05_netgen=self._make_tier(),
            tier1_snappy=self._make_tier(False),
            tier15_cfmesh=self._make_tier(),
            tier2_tetwild=self._make_tier(),
        )
        tcm2 = TierCompatibilityMap.model_validate_json(tcm.model_dump_json())
        assert tcm2.tier1_snappy.compatible is False


# ---------------------------------------------------------------------------
# MeshStrategy
# ---------------------------------------------------------------------------


def _make_domain():
    return DomainConfig(
        min=[-5.0, -5.0, -5.0],
        max=[5.0, 5.0, 5.0],
        base_cell_size=0.5,
        location_in_mesh=[0.0, 0.0, 0.0],
    )


def _make_surface_mesh():
    return SurfaceMeshConfig(
        input_file="/tmp/surface.stl",
        target_cell_size=0.1,
        min_cell_size=0.05,
    )


def _make_bl():
    return BoundaryLayerConfig(
        enabled=True,
        num_layers=3,
        first_layer_thickness=0.001,
        growth_ratio=1.2,
        max_total_thickness=0.05,
        min_thickness_ratio=0.1,
    )


class TestMeshStrategy:
    def _make(self, **kwargs):
        defaults = dict(
            selected_tier="tier2_tetwild",
            flow_type="external",
            domain=_make_domain(),
            surface_mesh=_make_surface_mesh(),
            boundary_layers=_make_bl(),
        )
        defaults.update(kwargs)
        return MeshStrategy(**defaults)

    def test_strategy_version_default(self):
        ms = self._make()
        assert ms.strategy_version == 2

    def test_iteration_default(self):
        ms = self._make()
        assert ms.iteration == 1

    def test_quality_level_default(self):
        ms = self._make()
        assert ms.quality_level == QualityLevel.STANDARD

    def test_surface_quality_level_default(self):
        ms = self._make()
        assert ms.surface_quality_level == SurfaceQualityLevel.L1_REPAIR

    def test_fallback_tiers_default_empty(self):
        ms = self._make()
        assert ms.fallback_tiers == []

    def test_refinement_regions_default_empty(self):
        ms = self._make()
        assert ms.refinement_regions == []

    def test_quality_targets_defaults(self):
        ms = self._make()
        assert ms.quality_targets.max_non_orthogonality == pytest.approx(70.0)
        assert ms.quality_targets.max_skewness == pytest.approx(6.0)
        assert ms.quality_targets.max_aspect_ratio == pytest.approx(200.0)
        assert ms.quality_targets.min_determinant == pytest.approx(0.001)
        assert ms.quality_targets.target_y_plus is None

    def test_previous_attempt_default_none(self):
        ms = self._make()
        assert ms.previous_attempt is None

    def test_missing_selected_tier_raises(self):
        with pytest.raises(ValidationError):
            MeshStrategy(
                flow_type="external",
                domain=_make_domain(),
                surface_mesh=_make_surface_mesh(),
                boundary_layers=_make_bl(),
            )

    def test_json_roundtrip(self):
        ms = self._make()
        ms2 = MeshStrategy.model_validate_json(ms.model_dump_json())
        assert ms2.selected_tier == "tier2_tetwild"
        assert ms2.strategy_version == 2


# ---------------------------------------------------------------------------
# CheckMeshResult
# ---------------------------------------------------------------------------


def _make_checkmesh(**kwargs):
    defaults = dict(
        cells=100000,
        faces=300000,
        points=150000,
        max_non_orthogonality=30.0,
        avg_non_orthogonality=5.0,
        max_skewness=1.5,
        max_aspect_ratio=20.0,
        min_face_area=1e-6,
        min_cell_volume=1e-9,
        min_determinant=0.8,
        negative_volumes=0,
        severely_non_ortho_faces=10,
        failed_checks=0,
        mesh_ok=True,
    )
    defaults.update(kwargs)
    return CheckMeshResult(**defaults)


class TestCheckMeshResult:
    def test_valid(self):
        cm = _make_checkmesh()
        assert cm.cells == 100000
        assert cm.mesh_ok is True

    def test_negative_volumes_int(self):
        cm = _make_checkmesh(negative_volumes=5)
        assert isinstance(cm.negative_volumes, int)

    def test_mesh_ok_false(self):
        cm = _make_checkmesh(mesh_ok=False, failed_checks=3)
        assert cm.mesh_ok is False
        assert cm.failed_checks == 3

    def test_missing_cells_raises(self):
        with pytest.raises(ValidationError):
            CheckMeshResult(
                faces=300000,
                points=150000,
                max_non_orthogonality=30.0,
                avg_non_orthogonality=5.0,
                max_skewness=1.5,
                max_aspect_ratio=20.0,
                min_face_area=1e-6,
                min_cell_volume=1e-9,
                min_determinant=0.8,
                negative_volumes=0,
                severely_non_ortho_faces=0,
                failed_checks=0,
                mesh_ok=True,
            )

    def test_json_roundtrip(self):
        cm = _make_checkmesh()
        cm2 = CheckMeshResult.model_validate_json(cm.model_dump_json())
        assert cm2.cells == cm.cells
        assert cm2.max_non_orthogonality == cm.max_non_orthogonality


# ---------------------------------------------------------------------------
# QualityReport
# ---------------------------------------------------------------------------


def _make_evaluation_summary(**kwargs):
    defaults = dict(
        verdict=Verdict.PASS,
        iteration=1,
        tier_evaluated="tier2_tetwild",
        evaluation_time_seconds=2.5,
        checkmesh=_make_checkmesh(),
    )
    defaults.update(kwargs)
    return EvaluationSummary(**defaults)


class TestQualityReport:
    def test_valid(self):
        qr = QualityReport(evaluation_summary=_make_evaluation_summary())
        assert qr.evaluation_summary.verdict == Verdict.PASS

    def test_verdict_enum_in_report(self):
        qr = QualityReport(evaluation_summary=_make_evaluation_summary(verdict=Verdict.FAIL))
        assert qr.evaluation_summary.verdict == Verdict.FAIL

    def test_verdict_pass_with_warnings(self):
        qr = QualityReport(
            evaluation_summary=_make_evaluation_summary(verdict=Verdict.PASS_WITH_WARNINGS)
        )
        assert qr.evaluation_summary.verdict == Verdict.PASS_WITH_WARNINGS

    def test_missing_evaluation_summary_raises(self):
        with pytest.raises(ValidationError):
            QualityReport()

    def test_hard_fails_default_empty(self):
        qr = QualityReport(evaluation_summary=_make_evaluation_summary())
        assert qr.evaluation_summary.hard_fails == []

    def test_soft_fails_default_empty(self):
        qr = QualityReport(evaluation_summary=_make_evaluation_summary())
        assert qr.evaluation_summary.soft_fails == []

    def test_recommendations_default_empty(self):
        qr = QualityReport(evaluation_summary=_make_evaluation_summary())
        assert qr.evaluation_summary.recommendations == []

    def test_geometry_fidelity_optional_none(self):
        qr = QualityReport(evaluation_summary=_make_evaluation_summary())
        assert qr.evaluation_summary.geometry_fidelity is None

    def test_geometry_fidelity_provided(self):
        gf = GeometryFidelity(
            hausdorff_distance=0.001,
            hausdorff_relative=0.0001,
            surface_area_deviation_percent=0.5,
        )
        es = _make_evaluation_summary(geometry_fidelity=gf)
        qr = QualityReport(evaluation_summary=es)
        assert qr.evaluation_summary.geometry_fidelity.hausdorff_distance == pytest.approx(0.001)

    def test_with_fail_criteria(self):
        fc = FailCriterion(
            criterion="max_non_orthogonality", value=85.0, threshold=70.0, location_hint="cell 42"
        )
        es = _make_evaluation_summary(hard_fails=[fc])
        qr = QualityReport(evaluation_summary=es)
        assert len(qr.evaluation_summary.hard_fails) == 1
        assert qr.evaluation_summary.hard_fails[0].value == pytest.approx(85.0)

    def test_with_recommendations(self):
        rec = Recommendation(
            priority=1,
            action="reduce cell size",
            current_value=0.5,
            suggested_value=0.3,
            rationale="too coarse near walls",
        )
        es = _make_evaluation_summary(recommendations=[rec])
        qr = QualityReport(evaluation_summary=es)
        assert len(qr.evaluation_summary.recommendations) == 1
        assert qr.evaluation_summary.recommendations[0].priority == 1

    def test_additional_metrics_default(self):
        qr = QualityReport(evaluation_summary=_make_evaluation_summary())
        assert qr.evaluation_summary.additional_metrics.cell_volume_stats is None
        assert qr.evaluation_summary.additional_metrics.boundary_layer is None

    def test_quality_level_optional(self):
        es = _make_evaluation_summary(quality_level="draft")
        qr = QualityReport(evaluation_summary=es)
        assert qr.evaluation_summary.quality_level == "draft"

    def test_json_roundtrip(self):
        qr = QualityReport(evaluation_summary=_make_evaluation_summary())
        qr2 = QualityReport.model_validate_json(qr.model_dump_json())
        assert qr2.evaluation_summary.verdict == Verdict.PASS
        assert qr2.evaluation_summary.checkmesh.cells == 100000

    def test_dict_roundtrip(self):
        qr = QualityReport(evaluation_summary=_make_evaluation_summary())
        d = qr.model_dump()
        qr2 = QualityReport.model_validate(d)
        assert qr2.evaluation_summary.tier_evaluated == "tier2_tetwild"


# ---------------------------------------------------------------------------
# PreprocessedReport
# ---------------------------------------------------------------------------


def _make_final_validation():
    return FinalValidation(
        is_watertight=True,
        is_manifold=True,
        num_faces=2000,
        min_face_area=0.001,
        max_edge_length_ratio=10.0,
    )


def _make_preprocessing_summary(**kwargs):
    defaults = dict(
        input_file="/tmp/input.stl",
        input_format="stl",
        output_file="/tmp/output.stl",
        passthrough_cad=False,
        total_time_seconds=1.5,
        final_validation=_make_final_validation(),
    )
    defaults.update(kwargs)
    return PreprocessingSummary(**defaults)


class TestPreprocessedReport:
    def test_valid(self):
        pr = PreprocessedReport(preprocessing_summary=_make_preprocessing_summary())
        assert pr.preprocessing_summary.passthrough_cad is False

    def test_surface_quality_level_optional_none(self):
        pr = PreprocessedReport(preprocessing_summary=_make_preprocessing_summary())
        assert pr.surface_quality_level is None

    def test_surface_quality_level_provided(self):
        pr = PreprocessedReport(
            preprocessing_summary=_make_preprocessing_summary(),
            surface_quality_level="l1_repair",
        )
        assert pr.surface_quality_level == "l1_repair"

    def test_steps_default_empty(self):
        pr = PreprocessedReport(preprocessing_summary=_make_preprocessing_summary())
        assert pr.preprocessing_summary.steps_performed == []

    def test_json_roundtrip(self):
        pr = PreprocessedReport(preprocessing_summary=_make_preprocessing_summary())
        pr2 = PreprocessedReport.model_validate_json(pr.model_dump_json())
        assert pr2.preprocessing_summary.input_file == "/tmp/input.stl"


# ---------------------------------------------------------------------------
# GeneratorLog
# ---------------------------------------------------------------------------


def _make_execution_summary(**kwargs):
    defaults = dict(
        selected_tier="tier2_tetwild",
        output_dir="/tmp/case",
        total_time_seconds=10.0,
    )
    defaults.update(kwargs)
    return ExecutionSummary(**defaults)


class TestGeneratorLog:
    def test_execution_summary_required(self):
        with pytest.raises(ValidationError):
            GeneratorLog()

    def test_valid(self):
        gl = GeneratorLog(execution_summary=_make_execution_summary())
        assert gl.execution_summary.selected_tier == "tier2_tetwild"

    def test_tiers_attempted_default_empty(self):
        gl = GeneratorLog(execution_summary=_make_execution_summary())
        assert gl.execution_summary.tiers_attempted == []

    def test_quality_level_optional(self):
        gl = GeneratorLog(execution_summary=_make_execution_summary(quality_level="standard"))
        assert gl.execution_summary.quality_level == "standard"

    def test_with_tier_attempt(self):
        ta = TierAttempt(tier="tier2_tetwild", status="success", time_seconds=9.0)
        es = _make_execution_summary(tiers_attempted=[ta])
        gl = GeneratorLog(execution_summary=es)
        assert len(gl.execution_summary.tiers_attempted) == 1
        assert gl.execution_summary.tiers_attempted[0].status == "success"

    def test_json_roundtrip(self):
        gl = GeneratorLog(execution_summary=_make_execution_summary())
        gl2 = GeneratorLog.model_validate_json(gl.model_dump_json())
        assert gl2.execution_summary.output_dir == "/tmp/case"


# ---------------------------------------------------------------------------
# AdditionalMetrics / CellVolumeStats / BoundaryLayerStats
# ---------------------------------------------------------------------------


class TestAdditionalMetrics:
    def test_defaults_none(self):
        am = AdditionalMetrics()
        assert am.cell_volume_stats is None
        assert am.boundary_layer is None

    def test_with_cell_volume_stats(self):
        cvs = CellVolumeStats(min=1e-9, max=1e-3, mean=5e-6, std=1e-6, ratio_max_min=1000.0)
        am = AdditionalMetrics(cell_volume_stats=cvs)
        assert am.cell_volume_stats.ratio_max_min == pytest.approx(1000.0)

    def test_with_boundary_layer(self):
        bl = BoundaryLayerStats(
            bl_coverage_percent=95.0,
            avg_first_layer_height=0.001,
            min_first_layer_height=0.0005,
            max_first_layer_height=0.002,
        )
        am = AdditionalMetrics(boundary_layer=bl)
        assert am.boundary_layer.bl_coverage_percent == pytest.approx(95.0)


# ---------------------------------------------------------------------------
# AutoTessellError (core/utils/errors.py)
# ---------------------------------------------------------------------------


class TestAutoTessellError:
    def test_is_exception(self):
        err = AutoTessellError("something went wrong")
        assert isinstance(err, Exception)

    def test_message_stored(self):
        err = AutoTessellError("test message")
        assert str(err) == "test message"

    def test_hint_default_empty(self):
        err = AutoTessellError("msg")
        assert err.hint == ""

    def test_details_default_empty(self):
        err = AutoTessellError("msg")
        assert err.details == ""

    def test_hint_stored(self):
        err = AutoTessellError("msg", hint="try this")
        assert err.hint == "try this"

    def test_details_stored(self):
        err = AutoTessellError("msg", details="stack trace here")
        assert err.details == "stack trace here"

    def test_rich_message_contains_error(self):
        err = AutoTessellError("bad thing happened")
        rm = err.rich_message()
        assert "bad thing happened" in rm

    def test_rich_message_contains_hint(self):
        err = AutoTessellError("error", hint="use --verbose")
        rm = err.rich_message()
        assert "use --verbose" in rm

    def test_rich_message_contains_details(self):
        err = AutoTessellError("error", details="line 42 in foo.py")
        rm = err.rich_message()
        assert "line 42 in foo.py" in rm

    def test_rich_message_no_hint_when_empty(self):
        err = AutoTessellError("error")
        rm = err.rich_message()
        assert "Hint" not in rm

    def test_rich_message_no_details_when_empty(self):
        err = AutoTessellError("error")
        rm = err.rich_message()
        # details 섹션 없을 때 dim 태그 없음
        assert "[dim]" not in rm

    def test_raise_and_catch(self):
        with pytest.raises(AutoTessellError) as exc_info:
            raise AutoTessellError("pipeline failed", hint="check input")
        assert "pipeline failed" in str(exc_info.value)
        assert exc_info.value.hint == "check input"

    def test_subclass_of_exception(self):
        err = AutoTessellError("x")
        assert isinstance(err, Exception)
        assert isinstance(err, AutoTessellError)


# ---------------------------------------------------------------------------
# diagnose_error
# ---------------------------------------------------------------------------


class TestDiagnoseError:
    def test_returns_string(self):
        result = diagnose_error(ValueError("something broke"))
        assert isinstance(result, str)

    def test_memory_error_pattern(self):
        err = MemoryError("out of memory")
        result = diagnose_error(err)
        assert "메모리" in result

    def test_watertight_pattern(self):
        err = RuntimeError("mesh is not watertight")
        result = diagnose_error(err)
        assert "watertight" in result.lower() or "watertight" in str(err).lower()

    def test_unknown_error_fallback(self):
        err = ValueError("completely unrelated error xyz123")
        result = diagnose_error(err)
        assert "ValueError" in result or "unrelated" in result

    def test_cadquery_pattern(self):
        err = ImportError("No module named 'cadquery'")
        result = diagnose_error(err)
        assert "cadquery" in result.lower()

    def test_netgen_pattern(self):
        err = ImportError("No module named 'netgen'")
        result = diagnose_error(err)
        assert "netgen" in result.lower() or "Netgen" in result

    def test_pytetwild_pattern(self):
        err = ImportError("No module named 'pytetwild'")
        result = diagnose_error(err)
        assert "pytetwild" in result.lower() or "TetWild" in result

    def test_autotessell_error_diagnosable(self):
        err = AutoTessellError("mesh not watertight")
        result = diagnose_error(err)
        assert isinstance(result, str)
        assert len(result) > 0
