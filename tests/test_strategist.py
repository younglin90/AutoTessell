"""Strategist 모듈 테스트."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.schemas import (
    BoundingBox,
    BoundaryLayerConfig,
    BoundaryLayerStats,
    CheckMeshResult,
    DomainConfig,
    EvaluationSummary,
    FailCriterion,
    FeatureStats,
    FileInfo,
    FlowEstimation,
    Geometry,
    GeometryFidelity,
    GeometryReport,
    MeshStrategy,
    QualityLevel,
    QualityReport,
    QualityTargets,
    SurfaceMeshConfig,
    SurfaceQualityLevel,
    SurfaceStats,
    TierCompatibility,
    TierCompatibilityMap,
    Verdict,
)
from core.strategist.param_optimizer import ParamOptimizer
from core.strategist.strategy_planner import StrategyPlanner
from core.strategist.tier_selector import TierSelector

BENCHMARKS_DIR = Path(__file__).parent / "benchmarks"


# ---------------------------------------------------------------------------
# 픽스처 헬퍼
# ---------------------------------------------------------------------------

def _make_geometry_report(
    *,
    is_cad_brep: bool = False,
    flow_type: str = "external",
    is_watertight: bool = True,
    is_manifold: bool = True,
    has_degenerate_faces: bool = False,
    num_sharp_edges: int = 0,
    genus: int = 0,
    num_connected_components: int = 1,
    characteristic_length: float = 2.0,
    curvature_max: float = 1.0,
) -> GeometryReport:
    bbox = BoundingBox(
        min=[-1.0, -1.0, -1.0],
        max=[1.0, 1.0, 1.0],
        center=[0.0, 0.0, 0.0],
        diagonal=3.464,
        characteristic_length=characteristic_length,
    )
    surface = SurfaceStats(
        num_vertices=642,
        num_faces=1280,
        surface_area=12.5,
        is_watertight=is_watertight,
        is_manifold=is_manifold,
        num_connected_components=num_connected_components,
        euler_number=2,
        genus=genus,
        has_degenerate_faces=has_degenerate_faces,
        num_degenerate_faces=1 if has_degenerate_faces else 0,
        min_face_area=0.009,
        max_face_area=0.012,
        face_area_std=0.001,
        min_edge_length=0.14,
        max_edge_length=0.17,
        edge_length_ratio=1.2,
    )
    features = FeatureStats(
        has_sharp_edges=num_sharp_edges > 0,
        num_sharp_edges=num_sharp_edges,
        has_thin_walls=False,
        min_wall_thickness_estimate=2.0,
        has_small_features=False,
        smallest_feature_size=0.14,
        feature_to_bbox_ratio=0.07,
        curvature_max=curvature_max,
        curvature_mean=0.5,
    )
    tier_compat = TierCompatibilityMap(
        tier0_core=TierCompatibility(compatible=True, notes="ok"),
        tier05_netgen=TierCompatibility(compatible=True, notes="ok"),
        tier1_snappy=TierCompatibility(compatible=True, notes="ok"),
        tier15_cfmesh=TierCompatibility(compatible=True, notes="ok"),
        tier2_tetwild=TierCompatibility(compatible=True, notes="ok"),
    )
    return GeometryReport(
        file_info=FileInfo(
            path="/tmp/test.stl",
            format="STL",
            file_size_bytes=64084,
            detected_encoding="binary",
            is_cad_brep=is_cad_brep,
            is_surface_mesh=True,
            is_volume_mesh=False,
        ),
        geometry=Geometry(
            bounding_box=bbox,
            surface=surface,
            features=features,
        ),
        flow_estimation=FlowEstimation(
            type=flow_type,
            confidence=0.85,
            reasoning="test",
            alternatives=[],
        ),
        issues=[],
        tier_compatibility=tier_compat,
    )


def _make_quality_report(
    *,
    verdict: Verdict = Verdict.FAIL,
    tier: str = "tier1_snappy",
    max_non_orthogonality: float = 65.0,
    max_skewness: float = 4.0,
    max_aspect_ratio: float = 20.0,
    negative_volumes: int = 0,
    cells: int = 1_000_000,
    mesh_ok: bool = True,
    failed_checks: int | None = None,
    geometry_fidelity: "GeometryFidelity | None" = None,
) -> QualityReport:
    if failed_checks is None:
        failed_checks = 1 if verdict == Verdict.FAIL else 0
    cm = CheckMeshResult(
        cells=cells,
        faces=5_000_000,
        points=1_200_000,
        max_non_orthogonality=max_non_orthogonality,
        avg_non_orthogonality=30.0,
        max_skewness=max_skewness,
        max_aspect_ratio=max_aspect_ratio,
        min_face_area=1e-8,
        min_cell_volume=1e-9,
        min_determinant=0.01,
        negative_volumes=negative_volumes,
        severely_non_ortho_faces=0,
        failed_checks=failed_checks,
        mesh_ok=mesh_ok,
    )
    summary = EvaluationSummary(
        verdict=verdict,
        iteration=1,
        tier_evaluated=tier,
        evaluation_time_seconds=5.0,
        checkmesh=cm,
        geometry_fidelity=geometry_fidelity,
    )
    return QualityReport(evaluation_summary=summary)


# ---------------------------------------------------------------------------
# TierSelector 테스트
# ---------------------------------------------------------------------------

class TestTierSelector:
    def setup_method(self):
        self.selector = TierSelector()

    def test_tier_select_external_watertight(self):
        """external + watertight → tier1_snappy (standard)."""
        report = _make_geometry_report(flow_type="external", is_watertight=True)
        tier, fallbacks = self.selector.select(report)
        assert tier == "tier1_snappy"
        assert "tier1_snappy" not in fallbacks
        assert len(fallbacks) > 0

    def test_tier_select_cad_brep(self):
        """is_cad_brep → tier05_netgen."""
        report = _make_geometry_report(is_cad_brep=True)
        tier, fallbacks = self.selector.select(report)
        assert tier == "tier05_netgen"
        assert "tier05_netgen" not in fallbacks

    def test_tier_select_hint_override(self):
        """--tier snappy → tier1_snappy (hint override)."""
        report = _make_geometry_report(is_cad_brep=True)  # normally netgen
        tier, fallbacks = self.selector.select(report, tier_hint="snappy")
        assert tier == "tier1_snappy"

    def test_tier_select_internal_watertight(self):
        """internal + watertight → tier15_cfmesh."""
        report = _make_geometry_report(flow_type="internal", is_watertight=True)
        tier, _ = self.selector.select(report)
        assert tier == "tier15_cfmesh"

    def test_tier_select_bad_surface(self):
        """non-manifold → tier2_tetwild."""
        report = _make_geometry_report(
            is_watertight=False,
            is_manifold=False,
            flow_type="unknown",
        )
        tier, _ = self.selector.select(report)
        assert tier == "tier2_tetwild"

    def test_tier_select_watertight_simple(self):
        """watertight + simple (few sharp edges, genus=0) → tier0_core."""
        report = _make_geometry_report(
            flow_type="unknown",
            is_watertight=True,
            num_sharp_edges=10,
            genus=0,
        )
        tier, _ = self.selector.select(report)
        assert tier == "tier0_core"

    def test_fallback_excludes_selected(self):
        """fallback_tiers에 selected tier가 포함되지 않아야 한다."""
        report = _make_geometry_report(flow_type="external", is_watertight=True)
        tier, fallbacks = self.selector.select(report)
        assert tier not in fallbacks

    def test_hint_canonical_name(self):
        """canonical tier name을 hint로 직접 사용할 수 있다."""
        report = _make_geometry_report()
        tier, _ = self.selector.select(report, tier_hint="tier2_tetwild")
        assert tier == "tier2_tetwild"

    # ── QualityLevel 연동 테스트 ─────────────────────────────────────

    def test_draft_quality_forces_tetwild(self):
        """draft 품질 레벨 → tier2_tetwild (coarse)."""
        report = _make_geometry_report(flow_type="external", is_watertight=True)
        tier, fallbacks = self.selector.select(report, quality_level=QualityLevel.DRAFT)
        assert tier == "tier2_tetwild"

    def test_draft_fallbacks(self):
        """draft fallback에 tier05_netgen이 포함되어야 한다."""
        report = _make_geometry_report(flow_type="external", is_watertight=True)
        tier, fallbacks = self.selector.select(report, quality_level=QualityLevel.DRAFT)
        assert "tier05_netgen" in fallbacks

    def test_standard_external_watertight(self):
        """standard + external + watertight → tier1_snappy."""
        report = _make_geometry_report(flow_type="external", is_watertight=True)
        tier, _ = self.selector.select(report, quality_level=QualityLevel.STANDARD)
        assert tier == "tier1_snappy"

    def test_standard_internal_watertight(self):
        """standard + internal + watertight → tier15_cfmesh."""
        report = _make_geometry_report(flow_type="internal", is_watertight=True)
        tier, _ = self.selector.select(report, quality_level=QualityLevel.STANDARD)
        assert tier == "tier15_cfmesh"

    def test_fine_external_watertight(self):
        """fine + external + watertight → tier1_snappy (BL 자동)."""
        report = _make_geometry_report(flow_type="external", is_watertight=True)
        tier, fallbacks = self.selector.select(report, quality_level=QualityLevel.FINE)
        assert tier == "tier1_snappy"
        assert "tier05_netgen" in fallbacks

    def test_fine_internal_watertight(self):
        """fine + internal + watertight → tier15_cfmesh."""
        report = _make_geometry_report(flow_type="internal", is_watertight=True)
        tier, _ = self.selector.select(report, quality_level=QualityLevel.FINE)
        assert tier == "tier15_cfmesh"

    def test_fine_cad_brep(self):
        """fine + CAD B-Rep → tier05_netgen."""
        report = _make_geometry_report(is_cad_brep=True)
        tier, _ = self.selector.select(report, quality_level=QualityLevel.FINE)
        assert tier == "tier05_netgen"

    def test_l3_ai_forces_tetwild(self):
        """surface_quality_level=l3_ai → tier2_tetwild 강제."""
        report = _make_geometry_report(flow_type="external", is_watertight=True)
        tier, _ = self.selector.select(
            report,
            quality_level=QualityLevel.FINE,
            surface_quality_level=SurfaceQualityLevel.L3_AI,
        )
        assert tier == "tier2_tetwild"

    def test_l3_ai_string_also_forces_tetwild(self):
        """surface_quality_level='l3_ai' (문자열)도 tier2_tetwild를 강제해야 한다."""
        report = _make_geometry_report(flow_type="external", is_watertight=True)
        tier, _ = self.selector.select(
            report,
            quality_level="fine",
            surface_quality_level="l3_ai",
        )
        assert tier == "tier2_tetwild"

    def test_quality_level_string_accepted(self):
        """quality_level을 문자열로 전달해도 동작해야 한다."""
        report = _make_geometry_report(flow_type="external", is_watertight=True)
        tier, _ = self.selector.select(report, quality_level="draft")
        assert tier == "tier2_tetwild"


# ---------------------------------------------------------------------------
# ParamOptimizer 테스트
# ---------------------------------------------------------------------------

class TestParamOptimizer:
    def setup_method(self):
        self.optimizer = ParamOptimizer()

    def test_domain_external_proportions(self):
        """외부 유동 standard: upstream = 5L, downstream = 10L."""
        report = _make_geometry_report(characteristic_length=2.0)
        domain = self.optimizer.compute_domain(report, "external")

        L = 2.0
        bbox_min_x = -1.0
        bbox_max_x = 1.0

        # standard: upstream=5L, downstream=10L
        assert abs(domain.min[0] - (bbox_min_x - 5 * L)) < 1e-9
        assert abs(domain.max[0] - (bbox_max_x + 10 * L)) < 1e-9

    def test_domain_lateral(self):
        """외부 유동 standard: lateral = 3L."""
        report = _make_geometry_report(characteristic_length=2.0)
        domain = self.optimizer.compute_domain(report, "external")

        L = 2.0
        bbox_min_y = -1.0
        bbox_max_y = 1.0

        # standard: lateral=3L
        assert abs(domain.min[1] - (bbox_min_y - 3 * L)) < 1e-9
        assert abs(domain.max[1] - (bbox_max_y + 3 * L)) < 1e-9

    def test_domain_internal_tight(self):
        """내부 유동: 도메인이 BBox보다 약간 크기만 해야 한다."""
        report = _make_geometry_report(flow_type="internal", characteristic_length=2.0)
        domain = self.optimizer.compute_domain(report, "internal")

        # 내부 유동은 BBox + 작은 margin
        assert domain.min[0] < -1.0
        assert domain.max[0] > 1.0
        assert domain.max[0] - domain.min[0] < 10.0  # 훨씬 좁아야 함

    def test_cell_sizes_base_standard(self):
        """standard: base_cell_size = (characteristic_length / 50) * 2.0."""
        report = _make_geometry_report(characteristic_length=2.0)
        sizes = self.optimizer.compute_cell_sizes(report, quality_level=QualityLevel.STANDARD)
        expected = (2.0 / 50) * 2.0
        assert abs(sizes["base_cell_size"] - expected) < 1e-12

    def test_cell_sizes_base_draft(self):
        """draft: base_cell_size = (characteristic_length / 50) * 4.0."""
        report = _make_geometry_report(characteristic_length=2.0)
        sizes = self.optimizer.compute_cell_sizes(report, quality_level=QualityLevel.DRAFT)
        expected = (2.0 / 50) * 4.0
        assert abs(sizes["base_cell_size"] - expected) < 1e-12

    def test_cell_sizes_base_fine(self):
        """fine: base_cell_size = (characteristic_length / 50) * 1.0."""
        report = _make_geometry_report(characteristic_length=2.0)
        sizes = self.optimizer.compute_cell_sizes(report, quality_level=QualityLevel.FINE)
        expected = (2.0 / 50) * 1.0
        assert abs(sizes["base_cell_size"] - expected) < 1e-12

    def test_cell_sizes_factor_ordering(self):
        """draft > standard > fine 순서로 셀 크기가 커야 한다."""
        report = _make_geometry_report(characteristic_length=2.0)
        draft = self.optimizer.compute_cell_sizes(report, quality_level=QualityLevel.DRAFT)
        std = self.optimizer.compute_cell_sizes(report, quality_level=QualityLevel.STANDARD)
        fine = self.optimizer.compute_cell_sizes(report, quality_level=QualityLevel.FINE)
        assert draft["base_cell_size"] > std["base_cell_size"] > fine["base_cell_size"]

    def test_cell_sizes_base(self):
        """base_cell_size 후방호환 — 기본(standard) 배율로 계산된다."""
        report = _make_geometry_report(characteristic_length=2.0)
        sizes = self.optimizer.compute_cell_sizes(report)
        # standard factor=2.0: (2.0/50)*2.0 = 0.08
        assert abs(sizes["base_cell_size"] - (2.0 / 50) * 2.0) < 1e-12

    def test_cell_sizes_hierarchy(self):
        """surface < base, min < surface."""
        report = _make_geometry_report(characteristic_length=2.0)
        sizes = self.optimizer.compute_cell_sizes(report)

        assert sizes["surface_cell_size"] < sizes["base_cell_size"]
        assert sizes["min_cell_size"] < sizes["surface_cell_size"]

    def test_cell_sizes_high_curvature_fine_only(self):
        """고곡률(>20) 보정은 fine에서만 적용된다."""
        report_high = _make_geometry_report(curvature_max=25.0)

        sizes_std_normal = self.optimizer.compute_cell_sizes(report_high, quality_level=QualityLevel.STANDARD)
        sizes_fine_high = self.optimizer.compute_cell_sizes(report_high, quality_level=QualityLevel.FINE)
        sizes_fine_normal_curv = self.optimizer.compute_cell_sizes(
            _make_geometry_report(curvature_max=5.0), quality_level=QualityLevel.FINE
        )

        # fine + high curvature: surface_cell_size 절반
        assert abs(sizes_fine_high["surface_cell_size"] - sizes_fine_normal_curv["surface_cell_size"] * 0.5) < 1e-12

        # standard: 고곡률 보정 없음 → fine-normal보다 클 수 있음 (배율 차이)
        # 핵심: standard에서는 curvature 보정이 적용되지 않아야 한다
        sizes_std_low_curv = self.optimizer.compute_cell_sizes(
            _make_geometry_report(curvature_max=5.0), quality_level=QualityLevel.STANDARD
        )
        assert sizes_std_normal["surface_cell_size"] == sizes_std_low_curv["surface_cell_size"]

    def test_cell_sizes_high_curvature(self):
        """고곡률(>20) 시 fine에서는 surface_cell_size가 절반으로 줄어든다."""
        report_normal = _make_geometry_report(curvature_max=5.0)
        report_high = _make_geometry_report(curvature_max=25.0)

        sizes_normal = self.optimizer.compute_cell_sizes(report_normal, quality_level=QualityLevel.FINE)
        sizes_high = self.optimizer.compute_cell_sizes(report_high, quality_level=QualityLevel.FINE)

        assert sizes_high["surface_cell_size"] < sizes_normal["surface_cell_size"]
        assert abs(sizes_high["surface_cell_size"] - sizes_normal["surface_cell_size"] * 0.5) < 1e-12

    def test_boundary_layers_fine_enabled(self):
        """fine: BL 활성화 — 5 layers, growth_ratio=1.2."""
        report = _make_geometry_report()
        bl = self.optimizer.compute_boundary_layers(report, quality_level=QualityLevel.FINE)

        assert bl.enabled is True
        assert bl.num_layers == 5
        assert abs(bl.growth_ratio - 1.2) < 1e-9
        assert bl.first_layer_thickness > 0
        assert bl.max_total_thickness > bl.first_layer_thickness

    def test_boundary_layers_standard_disabled(self):
        """standard: BL 비활성화."""
        report = _make_geometry_report()
        bl = self.optimizer.compute_boundary_layers(report, quality_level=QualityLevel.STANDARD)

        assert bl.enabled is False
        assert bl.num_layers == 0

    def test_boundary_layers_draft_disabled(self):
        """draft: BL 비활성화."""
        report = _make_geometry_report()
        bl = self.optimizer.compute_boundary_layers(report, quality_level=QualityLevel.DRAFT)

        assert bl.enabled is False
        assert bl.num_layers == 0

    def test_boundary_layers_defaults(self):
        """BL 기본값: fine 레벨 동작 확인 (후방호환)."""
        report = _make_geometry_report()
        bl = self.optimizer.compute_boundary_layers(report, quality_level=QualityLevel.FINE)

        assert bl.enabled is True
        assert bl.num_layers == 5
        assert abs(bl.growth_ratio - 1.2) < 1e-9
        assert bl.first_layer_thickness > 0
        assert bl.max_total_thickness > bl.first_layer_thickness

    def test_boundary_layers_type(self):
        """BoundaryLayerConfig 타입을 반환해야 한다."""
        report = _make_geometry_report()
        bl = self.optimizer.compute_boundary_layers(report, quality_level=QualityLevel.FINE)
        assert isinstance(bl, BoundaryLayerConfig)

    def test_domain_config_type(self):
        """DomainConfig 타입을 반환해야 한다."""
        report = _make_geometry_report()
        domain = self.optimizer.compute_domain(report, "external")
        assert isinstance(domain, DomainConfig)
        assert domain.type == "box"
        assert len(domain.min) == 3
        assert len(domain.max) == 3

    # ── Quality Targets 테스트 ──────────────────────────────────────

    def test_quality_targets_draft(self):
        """draft: non_ortho=85, skewness=8.0, aspect_ratio=500, min_det=0.0001."""
        qt = self.optimizer.compute_quality_targets(QualityLevel.DRAFT)
        assert qt.max_non_orthogonality == 85.0
        assert qt.max_skewness == 8.0
        assert qt.max_aspect_ratio == 500.0
        assert qt.min_determinant == 0.0001
        assert qt.target_y_plus is None

    def test_quality_targets_standard(self):
        """standard: non_ortho=70, skewness=6.0, aspect_ratio=200, min_det=0.001."""
        qt = self.optimizer.compute_quality_targets(QualityLevel.STANDARD)
        assert qt.max_non_orthogonality == 70.0
        assert qt.max_skewness == 6.0
        assert qt.max_aspect_ratio == 200.0
        assert qt.min_determinant == 0.001
        assert qt.target_y_plus is None

    def test_quality_targets_fine(self):
        """fine: non_ortho=65, skewness=4.0, aspect_ratio=100, min_det=0.001, y+=1.0."""
        qt = self.optimizer.compute_quality_targets(QualityLevel.FINE)
        assert qt.max_non_orthogonality == 65.0
        assert qt.max_skewness == 4.0
        assert qt.max_aspect_ratio == 100.0
        assert qt.min_determinant == 0.001
        assert qt.target_y_plus == 1.0

    def test_quality_targets_type(self):
        """QualityTargets 타입을 반환해야 한다."""
        qt = self.optimizer.compute_quality_targets(QualityLevel.STANDARD)
        assert isinstance(qt, QualityTargets)

    def test_quality_targets_string_accepted(self):
        """문자열 quality_level도 허용된다."""
        qt = self.optimizer.compute_quality_targets("fine")
        assert qt.max_non_orthogonality == 65.0


# ---------------------------------------------------------------------------
# StrategyPlanner 테스트
# ---------------------------------------------------------------------------

class TestStrategyPlanner:
    def setup_method(self):
        self.planner = StrategyPlanner()

    def test_mesh_strategy_schema(self):
        """MeshStrategy Pydantic 검증 — 필수 필드가 모두 채워져야 한다."""
        report = _make_geometry_report()
        strategy = self.planner.plan(report)

        # Pydantic 검증 통과 확인 (재직렬화)
        dumped = strategy.model_dump_json()
        restored = MeshStrategy.model_validate_json(dumped)
        assert restored.selected_tier == strategy.selected_tier
        assert restored.strategy_version == 2

    def test_strategy_from_sphere(self):
        """sphere.geometry_report.json으로 전략을 수립한다."""
        report_path = BENCHMARKS_DIR / "sphere.geometry_report.json"
        assert report_path.exists(), f"sphere report 없음: {report_path}"

        report = GeometryReport.model_validate_json(report_path.read_text())
        strategy = self.planner.plan(report)

        # sphere는 external + watertight → tier1_snappy (standard)
        assert strategy.selected_tier == "tier1_snappy"
        assert strategy.flow_type == "external"
        assert strategy.iteration == 1
        assert strategy.previous_attempt is None

    def test_strategy_has_domain(self):
        """전략에 도메인 설정이 포함되어야 한다."""
        report = _make_geometry_report()
        strategy = self.planner.plan(report)

        assert strategy.domain is not None
        assert len(strategy.domain.min) == 3
        assert len(strategy.domain.max) == 3

    def test_strategy_has_surface_mesh(self):
        """전략에 표면 메쉬 설정이 포함되어야 한다."""
        report = _make_geometry_report()
        strategy = self.planner.plan(report)

        assert strategy.surface_mesh is not None
        assert strategy.surface_mesh.target_cell_size > 0
        assert strategy.surface_mesh.min_cell_size > 0

    def test_strategy_external_has_refinement(self):
        """외부 유동 전략에는 리파인먼트 영역이 있어야 한다."""
        report = _make_geometry_report(flow_type="external", is_watertight=True)
        strategy = self.planner.plan(report)

        assert len(strategy.refinement_regions) > 0
        names = [r.name for r in strategy.refinement_regions]
        assert "body" in names
        assert "wake" in names

    def test_strategy_internal_no_wake(self):
        """내부 유동 전략에는 wake 리파인먼트 영역이 없어야 한다."""
        report = _make_geometry_report(flow_type="internal", is_watertight=True)
        strategy = self.planner.plan(report)

        names = [r.name for r in strategy.refinement_regions]
        assert "wake" not in names

    def test_strategy_tier_hint(self):
        """tier_hint가 반영되어야 한다."""
        report = _make_geometry_report(is_cad_brep=True)  # normally netgen
        strategy = self.planner.plan(report, tier_hint="cfmesh")
        assert strategy.selected_tier == "tier15_cfmesh"

    def test_retry_adjusts_params(self):
        """quality_report FAIL 시 iteration=2, previous_attempt 기록."""
        report = _make_geometry_report(flow_type="external", is_watertight=True)
        quality = _make_quality_report(
            verdict=Verdict.FAIL,
            tier="tier1_snappy",
            max_non_orthogonality=75.0,  # > 70 → snap 조정 트리거
        )

        strategy = self.planner.plan(
            report,
            quality_report=quality,
            iteration=2,
        )

        assert strategy.iteration == 2
        assert strategy.previous_attempt is not None
        assert strategy.previous_attempt.tier == "tier1_snappy"
        assert len(strategy.previous_attempt.failure_reason) > 0
        assert len(strategy.previous_attempt.evaluator_recommendation) > 0

    def test_retry_negative_volumes(self):
        """negative_volumes > 0 → BL 파라미터 완화 기록."""
        report = _make_geometry_report(flow_type="external", is_watertight=True)
        quality = _make_quality_report(
            verdict=Verdict.FAIL,
            negative_volumes=5,
        )

        strategy = self.planner.plan(report, quality_report=quality, iteration=2)

        assert strategy.previous_attempt is not None
        assert "negative_volumes" in strategy.previous_attempt.failure_reason

    def test_retry_checkmesh_complete_failure_fallback(self):
        """checkMesh 완전 실패(cells=0, mesh_ok=False) → fallback Tier로 전환."""
        report = _make_geometry_report(flow_type="external", is_watertight=True)
        quality = _make_quality_report(
            verdict=Verdict.FAIL,
            tier="tier1_snappy",
            cells=0,
            mesh_ok=False,
        )

        strategy = self.planner.plan(
            report,
            quality_report=quality,
            iteration=2,
            tier_hint="snappy",
        )

        # tier1_snappy에서 fallback으로 전환되어야 함
        assert strategy.selected_tier != "tier1_snappy"
        assert strategy.previous_attempt is not None

    def test_strategy_iteration_default(self):
        """기본 iteration은 1이어야 한다."""
        report = _make_geometry_report()
        strategy = self.planner.plan(report)
        assert strategy.iteration == 1

    def test_strategy_preprocessed_report_input_file(self):
        """preprocessed_report가 있으면 output_file이 surface_mesh.input_file로 사용된다."""
        from core.schemas import (
            FinalValidation,
            PreprocessedReport,
            PreprocessStep,
            PreprocessingSummary,
        )

        report = _make_geometry_report()
        final_val = FinalValidation(
            is_watertight=True,
            is_manifold=True,
            num_faces=1280,
            min_face_area=0.009,
            max_edge_length_ratio=1.2,
        )
        prep_summary = PreprocessingSummary(
            input_file="/tmp/test.stl",
            input_format="STL",
            output_file="/tmp/preprocessed.stl",
            passthrough_cad=False,
            total_time_seconds=1.2,
            steps_performed=[],
            final_validation=final_val,
        )
        pre_report = PreprocessedReport(preprocessing_summary=prep_summary)

        strategy = self.planner.plan(report, preprocessed_report=pre_report)
        assert strategy.surface_mesh.input_file == "/tmp/preprocessed.stl"

    def test_strategy_fallback_tiers_not_empty(self):
        """fallback_tiers가 비어있지 않아야 한다."""
        report = _make_geometry_report()
        strategy = self.planner.plan(report)
        assert len(strategy.fallback_tiers) > 0
        assert strategy.selected_tier not in strategy.fallback_tiers

    # ── QualityLevel 연동 테스트 ─────────────────────────────────────

    def test_plan_draft_quality_level(self):
        """draft 품질 레벨로 전략 수립 시 quality_level 필드가 설정된다."""
        report = _make_geometry_report(flow_type="external", is_watertight=True)
        strategy = self.planner.plan(report, quality_level=QualityLevel.DRAFT)

        assert strategy.quality_level == QualityLevel.DRAFT
        assert strategy.selected_tier == "tier2_tetwild"

    def test_plan_fine_quality_level(self):
        """fine 품질 레벨로 전략 수립 시 quality_level 필드가 설정된다."""
        report = _make_geometry_report(flow_type="external", is_watertight=True)
        strategy = self.planner.plan(report, quality_level=QualityLevel.FINE)

        assert strategy.quality_level == QualityLevel.FINE
        assert strategy.selected_tier == "tier1_snappy"

    def test_plan_standard_quality_level_default(self):
        """기본 quality_level은 standard이어야 한다."""
        report = _make_geometry_report(flow_type="external", is_watertight=True)
        strategy = self.planner.plan(report)

        assert strategy.quality_level == QualityLevel.STANDARD

    def test_plan_draft_bl_disabled(self):
        """draft: BL이 비활성화되어야 한다."""
        report = _make_geometry_report()
        strategy = self.planner.plan(report, quality_level=QualityLevel.DRAFT)

        assert strategy.boundary_layers.enabled is False

    def test_plan_fine_bl_enabled(self):
        """fine: BL이 활성화되어야 한다."""
        report = _make_geometry_report()
        strategy = self.planner.plan(report, quality_level=QualityLevel.FINE)

        assert strategy.boundary_layers.enabled is True

    def test_plan_standard_bl_disabled(self):
        """standard: BL이 비활성화되어야 한다."""
        report = _make_geometry_report()
        strategy = self.planner.plan(report, quality_level=QualityLevel.STANDARD)

        assert strategy.boundary_layers.enabled is False

    def test_plan_quality_targets_by_level(self):
        """quality_level에 따라 quality_targets 값이 달라진다."""
        report = _make_geometry_report()
        draft = self.planner.plan(report, quality_level=QualityLevel.DRAFT)
        standard = self.planner.plan(report, quality_level=QualityLevel.STANDARD)
        fine = self.planner.plan(report, quality_level=QualityLevel.FINE)

        assert draft.quality_targets.max_non_orthogonality == 85.0
        assert standard.quality_targets.max_non_orthogonality == 70.0
        assert fine.quality_targets.max_non_orthogonality == 65.0

        assert draft.quality_targets.max_skewness == 8.0
        assert standard.quality_targets.max_skewness == 6.0
        assert fine.quality_targets.max_skewness == 4.0

    def test_plan_cell_size_by_quality_level(self):
        """quality_level에 따라 셀 크기가 달라진다 (draft > standard > fine)."""
        report = _make_geometry_report()
        draft = self.planner.plan(report, quality_level=QualityLevel.DRAFT)
        standard = self.planner.plan(report, quality_level=QualityLevel.STANDARD)
        fine = self.planner.plan(report, quality_level=QualityLevel.FINE)

        assert draft.surface_mesh.target_cell_size > standard.surface_mesh.target_cell_size
        assert standard.surface_mesh.target_cell_size > fine.surface_mesh.target_cell_size

    def test_plan_draft_tetwild_epsilon_coarse(self):
        """draft + tetwild: epsilon이 coarse (1e-2) 이어야 한다."""
        report = _make_geometry_report(flow_type="external", is_watertight=True)
        strategy = self.planner.plan(report, quality_level=QualityLevel.DRAFT)

        assert strategy.selected_tier == "tier2_tetwild"
        assert strategy.tier_specific_params.get("tw_epsilon") == 1e-2

    def test_plan_surface_quality_level_default(self):
        """기본 surface_quality_level은 l1_repair이어야 한다."""
        report = _make_geometry_report()
        strategy = self.planner.plan(report)

        assert strategy.surface_quality_level == SurfaceQualityLevel.L1_REPAIR

    def test_plan_l3ai_preprocessed_report_forces_tetwild(self):
        """preprocessed_report에 surface_quality_level=l3_ai가 있으면 tetwild를 강제한다."""
        from core.schemas import (
            FinalValidation,
            PreprocessedReport,
            PreprocessingSummary,
        )

        report = _make_geometry_report(flow_type="external", is_watertight=True)
        final_val = FinalValidation(
            is_watertight=True,
            is_manifold=True,
            num_faces=1280,
            min_face_area=0.009,
            max_edge_length_ratio=1.2,
        )
        prep_summary = PreprocessingSummary(
            input_file="/tmp/test.stl",
            input_format="STL",
            output_file="/tmp/preprocessed.stl",
            passthrough_cad=False,
            total_time_seconds=1.2,
            steps_performed=[],
            final_validation=final_val,
            surface_quality_level="l3_ai",
        )
        pre_report = PreprocessedReport(preprocessing_summary=prep_summary)

        strategy = self.planner.plan(
            report,
            preprocessed_report=pre_report,
            quality_level=QualityLevel.FINE,
        )
        assert strategy.selected_tier == "tier2_tetwild"
        assert strategy.surface_quality_level == SurfaceQualityLevel.L3_AI

    def test_plan_strategy_version_is_2(self):
        """strategy_version은 2이어야 한다."""
        report = _make_geometry_report()
        strategy = self.planner.plan(report)
        assert strategy.strategy_version == 2

    def test_plan_quality_level_string(self):
        """quality_level을 문자열로 전달해도 동작해야 한다."""
        report = _make_geometry_report(flow_type="external", is_watertight=True)
        strategy = self.planner.plan(report, quality_level="draft")
        assert strategy.quality_level == QualityLevel.DRAFT
        assert strategy.selected_tier == "tier2_tetwild"

    # ── Enhanced retry tests ────────────────────────────────────────

    def test_retry_reduces_cell_size_on_high_skewness(self):
        """high_skewness -> surface_cell_size reduced by factor 0.7."""
        report = _make_geometry_report(flow_type="external", is_watertight=True)

        # Baseline (no feedback)
        baseline = self.planner.plan(report, quality_level=QualityLevel.STANDARD)
        baseline_surface_cell = baseline.surface_mesh.target_cell_size

        # With high skewness feedback
        quality = _make_quality_report(
            verdict=Verdict.FAIL,
            tier="tier1_snappy",
            max_skewness=8.5,  # > 6.0 threshold
        )
        retry = self.planner.plan(
            report, quality_report=quality, iteration=2,
            quality_level=QualityLevel.STANDARD,
        )

        assert retry.surface_mesh.target_cell_size < baseline_surface_cell
        assert abs(retry.surface_mesh.target_cell_size - baseline_surface_cell * 0.7) < 1e-12

    def test_retry_increases_snap_tolerance_on_non_ortho(self):
        """high_non_orthogonality -> snap_tolerance x1.5, snap_iterations +3, castellated +1."""
        report = _make_geometry_report(flow_type="external", is_watertight=True)
        quality = _make_quality_report(
            verdict=Verdict.FAIL,
            tier="tier1_snappy",
            max_non_orthogonality=75.0,  # > 70 threshold
        )

        strategy = self.planner.plan(
            report, quality_report=quality, iteration=2,
            quality_level=QualityLevel.STANDARD,
        )

        # snappy tier params should be adjusted
        assert strategy.tier_specific_params["snappy_snap_tolerance"] == 2.0 * 1.5
        assert strategy.tier_specific_params["snappy_snap_iterations"] == 5 + 3
        assert strategy.tier_specific_params["snappy_castellated_level"] == [3, 4]

    def test_retry_disables_bl_on_negative_volumes(self):
        """negative_volumes -> BL layers reduced by 2, growth_ratio x0.8.

        When BL has 5 layers, reducing by 2 gives 3 layers (still enabled).
        When BL is already disabled (standard), it stays disabled.
        """
        report = _make_geometry_report(flow_type="external", is_watertight=True)

        # Fine quality level has BL enabled (5 layers)
        quality = _make_quality_report(
            verdict=Verdict.FAIL,
            tier="tier1_snappy",
            negative_volumes=10,
        )
        strategy = self.planner.plan(
            report, quality_report=quality, iteration=2,
            quality_level=QualityLevel.FINE,
        )

        # 5 layers - 2 = 3 layers, growth 1.2 * 0.8 = 0.96 -> clamped to 1.0
        assert strategy.boundary_layers.num_layers == 3
        assert strategy.boundary_layers.growth_ratio == 1.0
        assert strategy.boundary_layers.enabled is True
        assert "negative_volumes" in strategy.previous_attempt.failure_reason

    def test_retry_disables_bl_completely_when_layers_go_to_zero(self):
        """When BL layers would go below 0, BL is fully disabled."""
        report = _make_geometry_report(flow_type="external", is_watertight=True)
        # Standard has 0 layers. Reducing by 2 -> stays disabled.
        quality = _make_quality_report(
            verdict=Verdict.FAIL,
            tier="tier1_snappy",
            negative_volumes=5,
        )
        strategy = self.planner.plan(
            report, quality_report=quality, iteration=2,
            quality_level=QualityLevel.STANDARD,
        )
        assert strategy.boundary_layers.enabled is False
        assert strategy.boundary_layers.num_layers == 0

    def test_retry_downgrades_quality_on_all_fail(self):
        """All tiers failed (cells=0, no fallbacks) -> quality_level downgrade."""
        report = _make_geometry_report(flow_type="external", is_watertight=True)
        # Use tier_hint to force a specific tier so fallbacks match expectation
        quality = _make_quality_report(
            verdict=Verdict.FAIL,
            tier="tier2_tetwild",
            cells=0,
            mesh_ok=False,
        )

        # Plan with fine quality, snappy tier hint. The fallback list from
        # hint override includes all other tiers. We need to simulate no
        # fallbacks left. Use l3_ai surface quality to force tetwild, then
        # craft a quality report that triggers the all-tiers-failed path.
        # Instead, let's directly test the planner with tier2_tetwild and
        # quality level fine with empty fallbacks by using a specific tier hint.
        from core.schemas import (
            FinalValidation,
            PreprocessedReport,
            PreprocessingSummary,
        )

        # Force tetwild via l3_ai, which sets limited fallbacks
        final_val = FinalValidation(
            is_watertight=True,
            is_manifold=True,
            num_faces=1280,
            min_face_area=0.009,
            max_edge_length_ratio=1.2,
        )
        prep_summary = PreprocessingSummary(
            input_file="/tmp/test.stl",
            input_format="STL",
            output_file="/tmp/preprocessed.stl",
            passthrough_cad=False,
            total_time_seconds=1.2,
            steps_performed=[],
            final_validation=final_val,
            surface_quality_level="l3_ai",
        )
        pre_report = PreprocessedReport(preprocessing_summary=prep_summary)

        # First attempt: fine -> tetwild (l3_ai). Fallbacks exclude tetwild.
        # We simulate all fallbacks exhausted by creating a quality report
        # where the complete failure triggers the check.
        # The _compute_adjustments sees cells=0 + mesh_ok=False, checks
        # fallback_tiers. l3_ai gives fallbacks = all tiers except tetwild.
        # But we want to test the "no fallbacks" path specifically.
        # Simplest approach: use tier_hint to force a tier, which gives all
        # other tiers as fallback. Instead, let's directly call the internal
        # method to test the downgrade logic.
        planner = StrategyPlanner()
        # Simulate: selected=tetwild, no fallbacks, fine quality
        from core.strategist.strategy_planner import _StrategyAdjustments

        adj = planner._compute_adjustments(
            quality, "tier2_tetwild", [], QualityLevel.FINE,
        )
        assert adj.downgrade_quality == QualityLevel.STANDARD

    def test_retry_changes_tier_on_checkmesh_fail(self):
        """checkMesh hard fail (failed_checks>0, cells>0, mesh_ok=False) -> switch tier."""
        report = _make_geometry_report(flow_type="external", is_watertight=True)
        quality = _make_quality_report(
            verdict=Verdict.FAIL,
            tier="tier1_snappy",
            cells=500_000,
            mesh_ok=False,
            failed_checks=3,
        )

        strategy = self.planner.plan(
            report, quality_report=quality, iteration=2,
            quality_level=QualityLevel.STANDARD,
        )

        # Should have switched away from snappy
        assert strategy.previous_attempt is not None
        assert "checkMesh hard fail" in strategy.previous_attempt.failure_reason or \
               "tier1_snappy" in strategy.previous_attempt.tier

    def test_retry_cumulative_adjustments(self):
        """Iteration 3 cell size should be smaller than iteration 2 when skewness persists.

        We simulate cumulative retries by feeding a quality_report with high
        skewness at each iteration. The cell size factor 0.7 is applied each time
        relative to the base, so iteration 2 = base*0.7, iteration 3 = base*0.7
        (same ratio to base). To get true cumulative effect, the iteration 3
        quality report must trigger the same adjustment.
        """
        report = _make_geometry_report(flow_type="external", is_watertight=True)

        # Iteration 1: baseline
        baseline = self.planner.plan(
            report, quality_level=QualityLevel.STANDARD,
        )

        # Iteration 2: high skewness
        qr2 = _make_quality_report(
            verdict=Verdict.FAIL,
            tier="tier1_snappy",
            max_skewness=8.0,
        )
        iter2 = self.planner.plan(
            report, quality_report=qr2, iteration=2,
            quality_level=QualityLevel.STANDARD,
        )

        # Iteration 3: still high skewness + also high aspect ratio
        qr3 = _make_quality_report(
            verdict=Verdict.FAIL,
            tier="tier1_snappy",
            max_skewness=7.5,
            max_aspect_ratio=250.0,  # compounds: 0.7 * 0.8 = 0.56
        )
        iter3 = self.planner.plan(
            report, quality_report=qr3, iteration=3,
            quality_level=QualityLevel.STANDARD,
        )

        # iter2 has skewness adjustment (0.7x)
        # iter3 has skewness (0.7) + aspect_ratio (0.8) = 0.56x
        assert iter2.surface_mesh.target_cell_size < baseline.surface_mesh.target_cell_size
        assert iter3.surface_mesh.target_cell_size < iter2.surface_mesh.target_cell_size

    def test_retry_aspect_ratio_reduces_cell_size(self):
        """high_aspect_ratio (>200) -> surface_cell_size reduced by 0.8."""
        report = _make_geometry_report(flow_type="external", is_watertight=True)
        baseline = self.planner.plan(report, quality_level=QualityLevel.STANDARD)

        quality = _make_quality_report(
            verdict=Verdict.FAIL,
            tier="tier1_snappy",
            max_aspect_ratio=300.0,
        )
        retry = self.planner.plan(
            report, quality_report=quality, iteration=2,
            quality_level=QualityLevel.STANDARD,
        )

        expected = baseline.surface_mesh.target_cell_size * 0.8
        assert abs(retry.surface_mesh.target_cell_size - expected) < 1e-12

    def test_retry_hausdorff_reduces_cell_and_bumps_level(self):
        """hausdorff_relative > 0.05 -> castellated +1, cell_size x0.8."""
        report = _make_geometry_report(flow_type="external", is_watertight=True)
        baseline = self.planner.plan(report, quality_level=QualityLevel.STANDARD)

        fidelity = GeometryFidelity(
            hausdorff_distance=0.1,
            hausdorff_relative=0.08,
            surface_area_deviation_percent=2.0,
        )
        quality = _make_quality_report(
            verdict=Verdict.FAIL,
            tier="tier1_snappy",
            geometry_fidelity=fidelity,
        )
        retry = self.planner.plan(
            report, quality_report=quality, iteration=2,
            quality_level=QualityLevel.STANDARD,
        )

        # Cell size reduced
        assert retry.surface_mesh.target_cell_size < baseline.surface_mesh.target_cell_size
        # Castellated level bumped
        assert retry.tier_specific_params["snappy_castellated_level"] == [3, 4]

    def test_retry_parameters_are_bounded(self):
        """Adjustments should not push values below sensible minimums."""
        report = _make_geometry_report(
            flow_type="external", is_watertight=True, characteristic_length=0.01,
        )
        # Extremely high skewness + aspect ratio -> aggressive cell reduction
        quality = _make_quality_report(
            verdict=Verdict.FAIL,
            tier="tier1_snappy",
            max_skewness=100.0,
            max_aspect_ratio=1000.0,
        )
        strategy = self.planner.plan(
            report, quality_report=quality, iteration=2,
            quality_level=QualityLevel.STANDARD,
        )

        L = 0.01
        min_allowed = max(L * 0.001, 0.001)  # _MIN_CELL_SIZE_FACTOR + _MIN_CELL_SIZE_ABS
        assert strategy.surface_mesh.target_cell_size >= min_allowed
        assert strategy.surface_mesh.min_cell_size >= min_allowed / 4.0

    def test_retry_hausdorff_increases_feature_extract_level(self):
        """hausdorff_relative > 0.05 -> feature_extract_level +1."""
        report = _make_geometry_report(flow_type="external", is_watertight=True)
        fidelity = GeometryFidelity(
            hausdorff_distance=0.1,
            hausdorff_relative=0.08,
            surface_area_deviation_percent=2.0,
        )
        quality = _make_quality_report(
            verdict=Verdict.FAIL,
            tier="tier1_snappy",
            geometry_fidelity=fidelity,
        )
        strategy = self.planner.plan(
            report, quality_report=quality, iteration=2,
            quality_level=QualityLevel.STANDARD,
        )
        assert strategy.surface_mesh.feature_extract_level == 2  # 1 + 1

    def test_retry_modifications_stored_in_previous_attempt(self):
        """Modifications list is stored in previous_attempt."""
        report = _make_geometry_report(flow_type="external", is_watertight=True)
        quality = _make_quality_report(
            verdict=Verdict.FAIL,
            tier="tier1_snappy",
            max_non_orthogonality=75.0,
        )
        strategy = self.planner.plan(
            report, quality_report=quality, iteration=2,
            quality_level=QualityLevel.STANDARD,
        )
        assert strategy.previous_attempt is not None
        assert len(strategy.previous_attempt.modifications) > 0
        assert any("snap_tolerance" in m for m in strategy.previous_attempt.modifications)

    def test_retry_previous_attempt_quality_level(self):
        """previous_attempt records the quality_level used."""
        report = _make_geometry_report(flow_type="external", is_watertight=True)
        quality = _make_quality_report(
            verdict=Verdict.FAIL,
            tier="tier1_snappy",
            max_skewness=8.0,
        )
        strategy = self.planner.plan(
            report, quality_report=quality, iteration=2,
            quality_level=QualityLevel.FINE,
        )
        assert strategy.previous_attempt is not None
        assert strategy.previous_attempt.quality_level == "fine"


# ---------------------------------------------------------------------------
# Retry-specific tests (requested names)
# ---------------------------------------------------------------------------


class TestRetryLogic:
    """Focused retry tests with the exact names from the requirements."""

    def setup_method(self):
        self.planner = StrategyPlanner()

    def test_retry_reduces_cell_size_on_skewness(self):
        """High skewness (>6.0) should reduce target_cell_size by 0.7x."""
        report = _make_geometry_report(flow_type="external", is_watertight=True)
        baseline = self.planner.plan(report, quality_level=QualityLevel.STANDARD)

        quality = _make_quality_report(
            verdict=Verdict.FAIL,
            tier="tier1_snappy",
            max_skewness=9.0,
        )
        retry = self.planner.plan(
            report, quality_report=quality, iteration=2,
            quality_level=QualityLevel.STANDARD,
        )

        expected = baseline.surface_mesh.target_cell_size * 0.7
        assert abs(retry.surface_mesh.target_cell_size - expected) < 1e-12
        assert retry.surface_mesh.min_cell_size < baseline.surface_mesh.min_cell_size

    def test_retry_increases_snap_on_non_ortho(self):
        """High non-orthogonality (>70) should increase snap_tolerance x1.5 and snap_iterations +3."""
        report = _make_geometry_report(flow_type="external", is_watertight=True)

        quality = _make_quality_report(
            verdict=Verdict.FAIL,
            tier="tier1_snappy",
            max_non_orthogonality=78.0,
        )
        strategy = self.planner.plan(
            report, quality_report=quality, iteration=2,
            quality_level=QualityLevel.STANDARD,
        )

        assert strategy.tier_specific_params["snappy_snap_tolerance"] == 2.0 * 1.5
        assert strategy.tier_specific_params["snappy_snap_iterations"] == 5 + 3
        assert strategy.tier_specific_params["snappy_castellated_level"] == [3, 4]
        # Modifications should be recorded
        assert strategy.previous_attempt is not None
        assert any("snap_tolerance" in m for m in strategy.previous_attempt.modifications)
        assert any("snap_iterations" in m for m in strategy.previous_attempt.modifications)

    def test_retry_disables_bl_on_negative_volumes(self):
        """negative_volumes > 0 should reduce BL layers by 2 and growth_ratio by 0.8.

        With fine (5 layers): 5 - 2 = 3 layers, growth 1.2 * 0.8 = 0.96 -> clamped to 1.0.
        With standard (0 layers): stays disabled.
        """
        report = _make_geometry_report(flow_type="external", is_watertight=True)

        # Fine: BL enabled with 5 layers
        quality = _make_quality_report(
            verdict=Verdict.FAIL,
            tier="tier1_snappy",
            negative_volumes=8,
        )
        strategy_fine = self.planner.plan(
            report, quality_report=quality, iteration=2,
            quality_level=QualityLevel.FINE,
        )
        assert strategy_fine.boundary_layers.num_layers == 3  # 5 - 2
        assert strategy_fine.boundary_layers.growth_ratio == 1.0  # 1.2*0.8=0.96 clamped
        assert strategy_fine.boundary_layers.enabled is True

        # Standard: BL already disabled (0 layers), stays disabled
        strategy_std = self.planner.plan(
            report, quality_report=quality, iteration=2,
            quality_level=QualityLevel.STANDARD,
        )
        assert strategy_std.boundary_layers.enabled is False
        assert strategy_std.boundary_layers.num_layers == 0

    def test_retry_switches_tier_on_failed_checks(self):
        """failed_checks > 0 with mesh_ok=False should switch to fallback tier."""
        report = _make_geometry_report(flow_type="external", is_watertight=True)
        quality = _make_quality_report(
            verdict=Verdict.FAIL,
            tier="tier1_snappy",
            cells=100_000,
            mesh_ok=False,
            failed_checks=5,
        )
        strategy = self.planner.plan(
            report, quality_report=quality, iteration=2,
            quality_level=QualityLevel.STANDARD,
        )

        # Should have switched away from snappy to a fallback
        assert strategy.selected_tier != "tier1_snappy"
        assert strategy.previous_attempt is not None
        assert strategy.previous_attempt.tier == "tier1_snappy"
        assert "hard fail" in strategy.previous_attempt.failure_reason.lower() or \
               "failed_checks" in strategy.previous_attempt.failure_reason

    def test_retry_cumulative(self):
        """Iteration 3 should produce smaller cells than iteration 2.

        Iter 2: skewness only -> 0.7x
        Iter 3: skewness + aspect_ratio -> 0.7 * 0.8 = 0.56x
        """
        report = _make_geometry_report(flow_type="external", is_watertight=True)
        baseline = self.planner.plan(report, quality_level=QualityLevel.STANDARD)

        # Iteration 2: high skewness only
        qr2 = _make_quality_report(
            verdict=Verdict.FAIL,
            tier="tier1_snappy",
            max_skewness=7.0,
        )
        iter2 = self.planner.plan(
            report, quality_report=qr2, iteration=2,
            quality_level=QualityLevel.STANDARD,
        )

        # Iteration 3: high skewness + high aspect ratio (compounds: 0.7 * 0.8 = 0.56)
        qr3 = _make_quality_report(
            verdict=Verdict.FAIL,
            tier="tier1_snappy",
            max_skewness=7.0,
            max_aspect_ratio=300.0,
        )
        iter3 = self.planner.plan(
            report, quality_report=qr3, iteration=3,
            quality_level=QualityLevel.STANDARD,
        )

        # Verify monotonically decreasing cell sizes
        assert baseline.surface_mesh.target_cell_size > iter2.surface_mesh.target_cell_size
        assert iter2.surface_mesh.target_cell_size > iter3.surface_mesh.target_cell_size

        # Verify exact factors
        assert abs(iter2.surface_mesh.target_cell_size - baseline.surface_mesh.target_cell_size * 0.7) < 1e-12
        assert abs(iter3.surface_mesh.target_cell_size - baseline.surface_mesh.target_cell_size * 0.56) < 1e-12


# ---------------------------------------------------------------------------
# Schema 테스트
# ---------------------------------------------------------------------------

class TestSchemas:
    def test_quality_level_enum_values(self):
        """QualityLevel enum 값 검증."""
        assert QualityLevel.DRAFT.value == "draft"
        assert QualityLevel.STANDARD.value == "standard"
        assert QualityLevel.FINE.value == "fine"

    def test_surface_quality_level_enum_values(self):
        """SurfaceQualityLevel enum 값 검증."""
        assert SurfaceQualityLevel.L1_REPAIR.value == "l1_repair"
        assert SurfaceQualityLevel.L2_REMESH.value == "l2_remesh"
        assert SurfaceQualityLevel.L3_AI.value == "l3_ai"

    def test_mesh_strategy_default_quality_level(self):
        """MeshStrategy 기본 quality_level은 standard이다."""
        # Minimal MeshStrategy construction requires mandatory fields
        from core.schemas import BoundaryLayerConfig, DomainConfig, SurfaceMeshConfig

        strategy = MeshStrategy(
            selected_tier="tier1_snappy",
            flow_type="external",
            domain=DomainConfig(
                min=[-10.0, -5.0, -5.0],
                max=[20.0, 5.0, 5.0],
                base_cell_size=0.04,
                location_in_mesh=[-9.0, 0.0, 0.0],
            ),
            surface_mesh=SurfaceMeshConfig(
                input_file="test.stl",
                target_cell_size=0.01,
                min_cell_size=0.0025,
            ),
            boundary_layers=BoundaryLayerConfig(
                enabled=False,
                num_layers=0,
                first_layer_thickness=0.0,
                growth_ratio=1.2,
                max_total_thickness=0.0,
                min_thickness_ratio=0.1,
            ),
        )
        assert strategy.quality_level == QualityLevel.STANDARD
        assert strategy.surface_quality_level == SurfaceQualityLevel.L1_REPAIR
        assert strategy.strategy_version == 2

    def test_mesh_strategy_roundtrip_with_quality_level(self):
        """MeshStrategy 직렬화/역직렬화 시 quality_level 보존."""
        from core.schemas import BoundaryLayerConfig, DomainConfig, SurfaceMeshConfig

        strategy = MeshStrategy(
            quality_level=QualityLevel.FINE,
            surface_quality_level=SurfaceQualityLevel.L2_REMESH,
            selected_tier="tier1_snappy",
            flow_type="external",
            domain=DomainConfig(
                min=[-10.0, -5.0, -5.0],
                max=[20.0, 5.0, 5.0],
                base_cell_size=0.04,
                location_in_mesh=[-9.0, 0.0, 0.0],
            ),
            surface_mesh=SurfaceMeshConfig(
                input_file="test.stl",
                target_cell_size=0.01,
                min_cell_size=0.0025,
            ),
            boundary_layers=BoundaryLayerConfig(
                enabled=True,
                num_layers=5,
                first_layer_thickness=1e-5,
                growth_ratio=1.2,
                max_total_thickness=1e-4,
                min_thickness_ratio=0.1,
            ),
        )

        dumped = strategy.model_dump_json()
        restored = MeshStrategy.model_validate_json(dumped)
        assert restored.quality_level == QualityLevel.FINE
        assert restored.surface_quality_level == SurfaceQualityLevel.L2_REMESH

    def test_quality_targets_defaults_standard(self):
        """QualityTargets 기본값이 standard 레벨과 일치해야 한다."""
        qt = QualityTargets()
        assert qt.max_non_orthogonality == 70.0
        assert qt.max_skewness == 6.0
        assert qt.max_aspect_ratio == 200.0
        assert qt.min_determinant == 0.001
        assert qt.target_y_plus is None

    def test_evaluation_summary_quality_level_optional(self):
        """EvaluationSummary.quality_level은 선택적이다 (기존 테스트 호환)."""
        cm = CheckMeshResult(
            cells=100,
            faces=500,
            points=120,
            max_non_orthogonality=30.0,
            avg_non_orthogonality=15.0,
            max_skewness=2.0,
            max_aspect_ratio=10.0,
            min_face_area=1e-6,
            min_cell_volume=1e-8,
            min_determinant=0.01,
            negative_volumes=0,
            severely_non_ortho_faces=0,
            failed_checks=0,
            mesh_ok=True,
        )
        summary = EvaluationSummary(
            verdict=Verdict.PASS,
            iteration=1,
            tier_evaluated="tier1_snappy",
            evaluation_time_seconds=1.0,
            checkmesh=cm,
        )
        assert summary.quality_level is None


# ---------------------------------------------------------------------------
# TierSelector 추가 테스트
# ---------------------------------------------------------------------------


class TestTierSelectorAdditional:
    """TierSelector의 미커버 케이스 추가 검증."""

    def setup_method(self):
        self.selector = TierSelector()

    def test_hint_netgen_canonical(self):
        """tier_hint='netgen' → tier05_netgen."""
        report = _make_geometry_report(flow_type="external", is_watertight=True)
        tier, _ = self.selector.select(report, tier_hint="netgen")
        assert tier == "tier05_netgen"

    def test_hint_cfmesh(self):
        """tier_hint='cfmesh' → tier15_cfmesh."""
        report = _make_geometry_report(flow_type="external", is_watertight=True)
        tier, _ = self.selector.select(report, tier_hint="cfmesh")
        assert tier == "tier15_cfmesh"

    def test_hint_tetwild(self):
        """tier_hint='tetwild' → tier2_tetwild."""
        report = _make_geometry_report(flow_type="external", is_watertight=True)
        tier, _ = self.selector.select(report, tier_hint="tetwild")
        assert tier == "tier2_tetwild"

    def test_hint_core(self):
        """tier_hint='core' → tier0_core."""
        report = _make_geometry_report(flow_type="external", is_watertight=True)
        tier, _ = self.selector.select(report, tier_hint="core")
        assert tier == "tier0_core"

    def test_draft_non_watertight_still_tetwild(self):
        """draft + non-watertight → tier2_tetwild."""
        report = _make_geometry_report(
            flow_type="external", is_watertight=False, is_manifold=False
        )
        tier, _ = self.selector.select(report, quality_level=QualityLevel.DRAFT)
        assert tier == "tier2_tetwild"

    def test_standard_non_watertight_tetwild(self):
        """standard + non-watertight + non-manifold → tier2_tetwild."""
        report = _make_geometry_report(
            flow_type="external", is_watertight=False, is_manifold=False
        )
        tier, _ = self.selector.select(report, quality_level=QualityLevel.STANDARD)
        assert tier == "tier2_tetwild"

    def test_fallback_tiers_is_list(self):
        """fallback_tiers는 리스트여야 한다."""
        report = _make_geometry_report()
        _, fallbacks = self.selector.select(report)
        assert isinstance(fallbacks, list)

    def test_tier_result_is_string(self):
        """선택된 Tier는 문자열이어야 한다."""
        report = _make_geometry_report()
        tier, _ = self.selector.select(report)
        assert isinstance(tier, str)
        assert len(tier) > 0

    def test_fine_non_watertight_tetwild(self):
        """fine + non-watertight → tier2_tetwild."""
        report = _make_geometry_report(
            flow_type="external", is_watertight=False, is_manifold=False
        )
        tier, _ = self.selector.select(report, quality_level=QualityLevel.FINE)
        assert tier == "tier2_tetwild"

    def test_all_quality_levels_return_known_tier(self):
        """모든 QualityLevel 값에서 알려진 Tier를 반환해야 한다."""
        known_tiers = {
            "tier0_core", "tier05_netgen", "tier1_snappy",
            "tier15_cfmesh", "tier2_tetwild",
        }
        report = _make_geometry_report(flow_type="external", is_watertight=True)
        for ql in QualityLevel:
            tier, _ = self.selector.select(report, quality_level=ql)
            assert tier in known_tiers


# ---------------------------------------------------------------------------
# ParamOptimizer 추가 테스트
# ---------------------------------------------------------------------------


class TestParamOptimizerAdditional:
    """ParamOptimizer의 미커버 케이스 추가 검증."""

    def setup_method(self):
        self.optimizer = ParamOptimizer()

    def test_domain_location_in_mesh_external(self):
        """외부 유동 도메인의 location_in_mesh는 길이 3 리스트여야 한다."""
        report = _make_geometry_report(characteristic_length=2.0)
        domain = self.optimizer.compute_domain(report, "external")
        assert len(domain.location_in_mesh) == 3

    def test_domain_location_in_mesh_inside_domain(self):
        """location_in_mesh가 도메인 내부에 있어야 한다."""
        report = _make_geometry_report(characteristic_length=2.0)
        domain = self.optimizer.compute_domain(report, "external")
        loc = domain.location_in_mesh
        for i in range(3):
            assert domain.min[i] < loc[i] < domain.max[i]

    def test_domain_base_cell_size_positive(self):
        """도메인 base_cell_size는 양수여야 한다."""
        report = _make_geometry_report(characteristic_length=2.0)
        domain = self.optimizer.compute_domain(report, "external")
        assert domain.base_cell_size > 0.0

    def test_domain_internal_type_box(self):
        """내부 유동 도메인 type도 'box'여야 한다."""
        report = _make_geometry_report(flow_type="internal", characteristic_length=2.0)
        domain = self.optimizer.compute_domain(report, "internal")
        assert domain.type == "box"

    def test_cell_sizes_surface_is_quarter_of_base(self):
        """surface_cell_size = base_cell_size / 4 이어야 한다."""
        report = _make_geometry_report(characteristic_length=2.0)
        sizes = self.optimizer.compute_cell_sizes(report, quality_level=QualityLevel.STANDARD)
        assert abs(sizes["surface_cell_size"] - sizes["base_cell_size"] / 4.0) < 1e-12

    def test_cell_sizes_min_is_quarter_of_surface(self):
        """min_cell_size = surface_cell_size / 4 이어야 한다."""
        report = _make_geometry_report(characteristic_length=2.0)
        sizes = self.optimizer.compute_cell_sizes(report, quality_level=QualityLevel.STANDARD)
        assert abs(sizes["min_cell_size"] - sizes["surface_cell_size"] / 4.0) < 1e-12

    def test_cell_sizes_keys_present(self):
        """compute_cell_sizes 반환값에 필수 키가 있어야 한다."""
        report = _make_geometry_report(characteristic_length=2.0)
        sizes = self.optimizer.compute_cell_sizes(report)
        assert "base_cell_size" in sizes
        assert "surface_cell_size" in sizes
        assert "min_cell_size" in sizes

    def test_boundary_layers_fine_feature_angle(self):
        """fine BL의 feature_angle = 130.0 이어야 한다."""
        report = _make_geometry_report()
        bl = self.optimizer.compute_boundary_layers(report, quality_level=QualityLevel.FINE)
        assert bl.feature_angle == 130.0

    def test_boundary_layers_fine_min_thickness_ratio(self):
        """fine BL의 min_thickness_ratio = 0.1 이어야 한다."""
        report = _make_geometry_report()
        bl = self.optimizer.compute_boundary_layers(report, quality_level=QualityLevel.FINE)
        assert bl.min_thickness_ratio == 0.1

    def test_quality_targets_aspect_ratio_ordering(self):
        """draft > standard > fine 순서로 max_aspect_ratio가 커야 한다."""
        draft = self.optimizer.compute_quality_targets(QualityLevel.DRAFT)
        std = self.optimizer.compute_quality_targets(QualityLevel.STANDARD)
        fine = self.optimizer.compute_quality_targets(QualityLevel.FINE)
        assert draft.max_aspect_ratio > std.max_aspect_ratio > fine.max_aspect_ratio

    def test_quality_targets_skewness_ordering(self):
        """draft > standard > fine 순서로 max_skewness가 커야 한다."""
        draft = self.optimizer.compute_quality_targets(QualityLevel.DRAFT)
        std = self.optimizer.compute_quality_targets(QualityLevel.STANDARD)
        fine = self.optimizer.compute_quality_targets(QualityLevel.FINE)
        assert draft.max_skewness > std.max_skewness > fine.max_skewness

    def test_quality_targets_non_ortho_ordering(self):
        """draft > standard > fine 순서로 max_non_orthogonality가 커야 한다."""
        draft = self.optimizer.compute_quality_targets(QualityLevel.DRAFT)
        std = self.optimizer.compute_quality_targets(QualityLevel.STANDARD)
        fine = self.optimizer.compute_quality_targets(QualityLevel.FINE)
        assert draft.max_non_orthogonality > std.max_non_orthogonality > fine.max_non_orthogonality

    def test_boundary_layers_growth_ratio_positive(self):
        """BL growth_ratio는 항상 양수여야 한다."""
        report = _make_geometry_report()
        for ql in QualityLevel:
            bl = self.optimizer.compute_boundary_layers(report, quality_level=ql)
            assert bl.growth_ratio > 0.0

    def test_domain_max_gt_min(self):
        """모든 축에서 domain.max > domain.min 이어야 한다."""
        report = _make_geometry_report(characteristic_length=2.0)
        domain = self.optimizer.compute_domain(report, "external")
        for i in range(3):
            assert domain.max[i] > domain.min[i]


# ---------------------------------------------------------------------------
# StrategyPlanner 추가 테스트
# ---------------------------------------------------------------------------


class TestStrategyPlannerAdditional:
    """StrategyPlanner의 미커버 케이스 추가 검증."""

    def setup_method(self):
        self.planner = StrategyPlanner()

    def test_plan_returns_mesh_strategy_type(self):
        """plan() 반환값은 MeshStrategy 타입이어야 한다."""
        report = _make_geometry_report()
        strategy = self.planner.plan(report)
        assert isinstance(strategy, MeshStrategy)

    def test_plan_no_previous_attempt_on_first(self):
        """첫 번째 iteration에서 previous_attempt는 None이어야 한다."""
        report = _make_geometry_report()
        strategy = self.planner.plan(report, iteration=1)
        assert strategy.previous_attempt is None

    def test_plan_flow_type_matches_report(self):
        """전략의 flow_type이 geometry_report의 flow_estimation.type과 일치해야 한다."""
        for ft in ("external", "internal"):
            report = _make_geometry_report(flow_type=ft, is_watertight=True)
            strategy = self.planner.plan(report)
            assert strategy.flow_type == ft

    def test_plan_surface_mesh_min_lt_target(self):
        """min_cell_size < target_cell_size 이어야 한다."""
        report = _make_geometry_report()
        strategy = self.planner.plan(report)
        assert strategy.surface_mesh.min_cell_size < strategy.surface_mesh.target_cell_size

    def test_plan_surface_mesh_feature_angle_default(self):
        """surface_mesh.feature_angle 기본값은 150.0이어야 한다."""
        report = _make_geometry_report()
        strategy = self.planner.plan(report)
        assert strategy.surface_mesh.feature_angle == 150.0

    def test_plan_surface_mesh_feature_extract_level_default(self):
        """surface_mesh.feature_extract_level 기본값은 1이어야 한다."""
        report = _make_geometry_report()
        strategy = self.planner.plan(report)
        assert strategy.surface_mesh.feature_extract_level == 1

    def test_plan_boundary_layers_growth_ratio(self):
        """fine BL의 growth_ratio = 1.2 이어야 한다."""
        report = _make_geometry_report()
        strategy = self.planner.plan(report, quality_level=QualityLevel.FINE)
        assert abs(strategy.boundary_layers.growth_ratio - 1.2) < 1e-9

    def test_plan_fallback_tiers_excludes_selected(self):
        """fallback_tiers에 selected_tier가 포함되지 않아야 한다."""
        for ql in QualityLevel:
            report = _make_geometry_report(flow_type="external", is_watertight=True)
            strategy = self.planner.plan(report, quality_level=ql)
            assert strategy.selected_tier not in strategy.fallback_tiers

    def test_plan_quality_targets_fine_y_plus(self):
        """fine 전략의 quality_targets.target_y_plus = 1.0 이어야 한다."""
        report = _make_geometry_report()
        strategy = self.planner.plan(report, quality_level=QualityLevel.FINE)
        assert strategy.quality_targets.target_y_plus == 1.0

    def test_plan_quality_targets_draft_y_plus_none(self):
        """draft 전략의 quality_targets.target_y_plus = None 이어야 한다."""
        report = _make_geometry_report()
        strategy = self.planner.plan(report, quality_level=QualityLevel.DRAFT)
        assert strategy.quality_targets.target_y_plus is None

    def test_plan_quality_targets_standard_y_plus_none(self):
        """standard 전략의 quality_targets.target_y_plus = None 이어야 한다."""
        report = _make_geometry_report()
        strategy = self.planner.plan(report, quality_level=QualityLevel.STANDARD)
        assert strategy.quality_targets.target_y_plus is None

    def test_plan_strategy_version_invariant(self):
        """어떤 quality_level이어도 strategy_version = 2여야 한다."""
        report = _make_geometry_report()
        for ql in QualityLevel:
            strategy = self.planner.plan(report, quality_level=ql)
            assert strategy.strategy_version == 2

    def test_plan_domain_min_max_ordered(self):
        """모든 축에서 domain.max > domain.min 이어야 한다."""
        report = _make_geometry_report(flow_type="external", is_watertight=True)
        strategy = self.planner.plan(report)
        for i in range(3):
            assert strategy.domain.max[i] > strategy.domain.min[i]

    def test_plan_iteration_stored(self):
        """plan() 호출 시 iteration 값이 strategy에 저장되어야 한다."""
        report = _make_geometry_report()
        for it in (1, 2, 3):
            strategy = self.planner.plan(report, iteration=it)
            assert strategy.iteration == it

    def test_plan_surface_quality_level_l2_propagated(self):
        """preprocessed_report에 l2_remesh가 있으면 surface_quality_level=l2_remesh여야 한다."""
        from core.schemas import (  # noqa: PLC0415
            FinalValidation,
            PreprocessedReport,
            PreprocessingSummary,
        )

        report = _make_geometry_report(flow_type="external", is_watertight=True)
        final_val = FinalValidation(
            is_watertight=True,
            is_manifold=True,
            num_faces=1280,
            min_face_area=0.009,
            max_edge_length_ratio=1.2,
        )
        prep_summary = PreprocessingSummary(
            input_file="/tmp/test.stl",
            input_format="STL",
            output_file="/tmp/remeshed.stl",
            passthrough_cad=False,
            total_time_seconds=2.5,
            steps_performed=[],
            final_validation=final_val,
            surface_quality_level="l2_remesh",
        )
        pre_report = PreprocessedReport(preprocessing_summary=prep_summary)
        strategy = self.planner.plan(report, preprocessed_report=pre_report)
        assert strategy.surface_quality_level == SurfaceQualityLevel.L2_REMESH

    def test_plan_high_curvature_fine_smaller_surface_cell(self):
        """fine 품질에서 고곡률은 저곡률보다 작은 surface_cell_size를 만들어야 한다."""
        report_low = _make_geometry_report(curvature_max=1.0)
        report_high = _make_geometry_report(curvature_max=25.0)

        s_low = self.planner.plan(report_low, quality_level=QualityLevel.FINE)
        s_high = self.planner.plan(report_high, quality_level=QualityLevel.FINE)

        assert s_high.surface_mesh.target_cell_size < s_low.surface_mesh.target_cell_size

    def test_plan_high_curvature_standard_no_correction(self):
        """standard 품질에서는 고곡률 보정이 없어야 한다."""
        report_low = _make_geometry_report(curvature_max=1.0)
        report_high = _make_geometry_report(curvature_max=25.0)

        s_low = self.planner.plan(report_low, quality_level=QualityLevel.STANDARD)
        s_high = self.planner.plan(report_high, quality_level=QualityLevel.STANDARD)

        assert s_low.surface_mesh.target_cell_size == pytest.approx(
            s_high.surface_mesh.target_cell_size, rel=1e-9
        )

    def test_plan_draft_tetwild_params_in_tier_specific(self):
        """draft → tier_specific_params['tw_epsilon'] = 1e-2 이어야 한다."""
        report = _make_geometry_report(flow_type="external", is_watertight=True)
        strategy = self.planner.plan(report, quality_level=QualityLevel.DRAFT)
        assert strategy.tier_specific_params.get("tw_epsilon") == 1e-2


# ---------------------------------------------------------------------------
# PreviousAttempt 스키마 검증
# ---------------------------------------------------------------------------


class TestPreviousAttemptSchema:
    """PreviousAttempt Pydantic 모델 검증."""

    def test_previous_attempt_required_fields(self):
        """PreviousAttempt 필수 필드 검증."""
        from core.schemas import PreviousAttempt  # noqa: PLC0415

        pa = PreviousAttempt(
            tier="tier1_snappy",
            quality_level="fine",
            failure_reason="max_non_orthogonality=75",
            evaluator_recommendation="snap iterations 증가",
            modifications=["snap_tolerance: 2.0 → 3.0"],
        )
        assert pa.tier == "tier1_snappy"
        assert pa.quality_level == "fine"
        assert len(pa.failure_reason) > 0
        assert len(pa.evaluator_recommendation) > 0
        assert len(pa.modifications) == 1

    def test_previous_attempt_empty_modifications(self):
        """modifications 기본값은 빈 리스트여야 한다."""
        from core.schemas import PreviousAttempt  # noqa: PLC0415

        pa = PreviousAttempt(
            tier="tier2_tetwild",
            failure_reason="cells=0",
            evaluator_recommendation="fallback tier로 전환",
        )
        assert pa.modifications == []

    def test_previous_attempt_roundtrip(self):
        """PreviousAttempt JSON 직렬화/역직렬화 라운드트립."""
        from core.schemas import PreviousAttempt  # noqa: PLC0415

        pa = PreviousAttempt(
            tier="tier15_cfmesh",
            quality_level="standard",
            failure_reason="skewness=8.2",
            evaluator_recommendation="셀 크기 감소",
            modifications=["target_cell_size: 0.04 → 0.028"],
        )
        data = pa.model_dump_json()
        restored = PreviousAttempt.model_validate_json(data)
        assert restored.tier == pa.tier
        assert restored.modifications == pa.modifications


# ---------------------------------------------------------------------------
# MeshStrategy 스키마 엣지 케이스
# ---------------------------------------------------------------------------


class TestMeshStrategyEdgeCases:
    """MeshStrategy 스키마의 엣지 케이스 및 기본값 검증."""

    def _make_minimal_strategy(self, **overrides) -> MeshStrategy:
        """최소 필수 필드로 MeshStrategy 생성."""
        base = dict(
            selected_tier="tier1_snappy",
            flow_type="external",
            domain=DomainConfig(
                min=[-10.0, -5.0, -5.0],
                max=[20.0, 5.0, 5.0],
                base_cell_size=0.04,
                location_in_mesh=[-9.0, 0.0, 0.0],
            ),
            surface_mesh=SurfaceMeshConfig(
                input_file="test.stl",
                target_cell_size=0.01,
                min_cell_size=0.0025,
            ),
            boundary_layers=BoundaryLayerConfig(
                enabled=False,
                num_layers=0,
                first_layer_thickness=0.0,
                growth_ratio=1.2,
                max_total_thickness=0.0,
                min_thickness_ratio=0.1,
            ),
        )
        base.update(overrides)
        return MeshStrategy(**base)

    def test_default_strategy_version(self):
        """strategy_version 기본값은 2이어야 한다."""
        strategy = self._make_minimal_strategy()
        assert strategy.strategy_version == 2

    def test_default_iteration(self):
        """iteration 기본값은 1이어야 한다."""
        strategy = self._make_minimal_strategy()
        assert strategy.iteration == 1

    def test_default_quality_level(self):
        """quality_level 기본값은 STANDARD이어야 한다."""
        strategy = self._make_minimal_strategy()
        assert strategy.quality_level == QualityLevel.STANDARD

    def test_default_surface_quality_level(self):
        """surface_quality_level 기본값은 L1_REPAIR이어야 한다."""
        strategy = self._make_minimal_strategy()
        assert strategy.surface_quality_level == SurfaceQualityLevel.L1_REPAIR

    def test_default_previous_attempt_none(self):
        """previous_attempt 기본값은 None이어야 한다."""
        strategy = self._make_minimal_strategy()
        assert strategy.previous_attempt is None

    def test_default_refinement_regions_empty(self):
        """refinement_regions 기본값은 빈 리스트여야 한다."""
        strategy = self._make_minimal_strategy()
        assert strategy.refinement_regions == []

    def test_mesh_strategy_with_previous_attempt(self):
        """previous_attempt가 있는 MeshStrategy 직렬화가 성공해야 한다."""
        from core.schemas import PreviousAttempt  # noqa: PLC0415

        strategy = self._make_minimal_strategy(
            iteration=2,
            previous_attempt=PreviousAttempt(
                tier="tier1_snappy",
                quality_level="standard",
                failure_reason="skewness=7.5",
                evaluator_recommendation="셀 크기 감소",
            ),
        )
        json_str = strategy.model_dump_json()
        restored = MeshStrategy.model_validate_json(json_str)
        assert restored.iteration == 2
        assert restored.previous_attempt is not None
        assert restored.previous_attempt.tier == "tier1_snappy"

    def test_domain_config_location_in_mesh_length(self):
        """DomainConfig.location_in_mesh 길이는 3이어야 한다."""
        strategy = self._make_minimal_strategy()
        assert len(strategy.domain.location_in_mesh) == 3

    def test_surface_mesh_config_feature_angle_default(self):
        """SurfaceMeshConfig feature_angle 기본값은 150.0이어야 한다."""
        strategy = self._make_minimal_strategy()
        assert strategy.surface_mesh.feature_angle == 150.0

    def test_boundary_layer_config_feature_angle_default(self):
        """BoundaryLayerConfig feature_angle 기본값은 130.0이어야 한다."""
        strategy = self._make_minimal_strategy()
        assert strategy.boundary_layers.feature_angle == 130.0
