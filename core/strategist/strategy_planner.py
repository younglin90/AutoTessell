"""메쉬 전략 수립 메인 로직."""

from __future__ import annotations

from core.schemas import (
    GeometryReport,
    MeshStrategy,
    PreviousAttempt,
    PreprocessedReport,
    QualityLevel,
    QualityReport,
    RefinementRegion,
    SurfaceMeshConfig,
    SurfaceQualityLevel,
    Verdict,
)
from core.strategist.param_optimizer import ParamOptimizer
from core.strategist.tier_selector import TierSelector
from core.utils.logging import get_logger

log = get_logger(__name__)

# Tier-specific 파라미터 기본값
_TIER_PARAMS: dict[str, dict] = {
    "tier1_snappy": {
        "snappy_castellated_level": [2, 3],
        "snappy_snap_tolerance": 2.0,
        "snappy_snap_iterations": 5,
        "snappy_merge_tolerance": 1e-6,
    },
    "tier15_cfmesh": {
        "cf_max_cell_size": None,  # 런타임에 채워짐
        "cf_surface_feature_angle": 30.0,
        "cf_keep_cells_intersecting_boundary": False,
    },
    "tier05_netgen": {
        "ng_max_h": None,
        "ng_min_h": None,
        "ng_second_order": False,
        "ng_fineness": 0.5,
    },
    "tier0_core": {
        "core_output_format": "vtk",
        "core_lloyd_iterations": 10,
    },
    "tier2_tetwild": {
        "tw_edge_length": None,
        "tw_epsilon": 1e-3,
        "tw_stop_energy": 10.0,
        "tw_max_iterations": 80,
    },
}

# Draft 전용 TetWild epsilon (coarse)
_DRAFT_EPSILON = 1e-2

# Quality level downgrade path for retry
_QUALITY_DOWNGRADE: dict[str, str | None] = {
    "fine": "standard",
    "standard": "draft",
    "draft": None,
}


class StrategyPlanner:
    """Analyzer/Preprocessor 출력과 Evaluator 피드백을 종합해 MeshStrategy를 수립한다."""

    def __init__(self) -> None:
        self._selector = TierSelector()
        self._optimizer = ParamOptimizer()

    def plan(
        self,
        geometry_report: GeometryReport,
        preprocessed_report: PreprocessedReport | None = None,
        quality_report: QualityReport | None = None,
        tier_hint: str = "auto",
        iteration: int = 1,
        quality_level: QualityLevel | str = QualityLevel.STANDARD,
    ) -> MeshStrategy:
        """MeshStrategy를 수립한다.

        Args:
            geometry_report: Analyzer 출력.
            preprocessed_report: Preprocessor 출력 (없으면 원본 파일 사용).
            quality_report: Evaluator 피드백 (재시도 시에만).
            tier_hint: CLI --tier 값.
            iteration: 현재 시도 횟수 (1-indexed).
            quality_level: 품질 레벨 (draft / standard / fine).

        Returns:
            MeshStrategy Pydantic 모델.
        """
        # Normalise quality_level
        if isinstance(quality_level, QualityLevel):
            ql = quality_level
        else:
            ql = QualityLevel(quality_level)

        # Determine surface_quality_level from preprocessed_report (if available)
        sql_str = SurfaceQualityLevel.L1_REPAIR.value
        if preprocessed_report is not None:
            # Check both top-level and summary-level fields
            sql_candidate = (
                preprocessed_report.surface_quality_level
                or preprocessed_report.preprocessing_summary.surface_quality_level
            )
            if sql_candidate:
                sql_str = sql_candidate
        try:
            sql = SurfaceQualityLevel(sql_str)
        except ValueError:
            sql = SurfaceQualityLevel.L1_REPAIR

        # 1. Tier 선택
        selected_tier, fallback_tiers = self._selector.select(
            geometry_report, tier_hint, quality_level=ql, surface_quality_level=sql
        )

        # 2. quality_report FAIL 피드백 반영
        previous_attempt: PreviousAttempt | None = None
        modifications: list[str] = []

        if quality_report is not None:
            summary = quality_report.evaluation_summary
            if summary.verdict == Verdict.FAIL:
                selected_tier, fallback_tiers, previous_attempt, modifications, ql = (
                    self._apply_fail_feedback(
                        quality_report,
                        selected_tier,
                        fallback_tiers,
                        ql,
                    )
                )

        # 3. 유동 타입 결정
        flow_type = geometry_report.flow_estimation.type
        if flow_type not in ("external", "internal"):
            flow_type = "external"  # 알 수 없으면 외부 유동으로 보수적 처리

        # 4. 파라미터 계산
        domain = self._optimizer.compute_domain(geometry_report, flow_type, quality_level=ql)
        cell_sizes = self._optimizer.compute_cell_sizes(geometry_report, quality_level=ql)
        bl_config = self._optimizer.compute_boundary_layers(geometry_report, quality_level=ql)
        quality_targets = self._optimizer.compute_quality_targets(quality_level=ql)

        # 5. 입력 파일 결정
        if preprocessed_report is not None:
            input_file = preprocessed_report.preprocessing_summary.output_file
        else:
            input_file = geometry_report.file_info.path

        # 6. SurfaceMeshConfig
        surface_mesh = SurfaceMeshConfig(
            input_file=input_file,
            target_cell_size=cell_sizes["surface_cell_size"],
            min_cell_size=cell_sizes["min_cell_size"],
            feature_angle=150.0,
            feature_extract_level=1,
        )

        # 7. Tier-specific params (deep copy + 런타임 값 채우기)
        tier_params = dict(_TIER_PARAMS.get(selected_tier, {}))
        self._fill_runtime_params(tier_params, selected_tier, cell_sizes, ql)

        # 8. 외부 유동이면 wake 리파인먼트 영역 추가
        refinement_regions = self._build_refinement_regions(
            geometry_report, flow_type, cell_sizes
        )

        strategy = MeshStrategy(
            strategy_version=2,
            iteration=iteration,
            quality_level=ql,
            surface_quality_level=sql,
            selected_tier=selected_tier,
            fallback_tiers=fallback_tiers,
            flow_type=flow_type,
            domain=domain,
            surface_mesh=surface_mesh,
            boundary_layers=bl_config,
            refinement_regions=refinement_regions,
            quality_targets=quality_targets,
            tier_specific_params=tier_params,
            previous_attempt=previous_attempt,
        )

        if modifications:
            log.info(
                "strategy_modifications_applied",
                iteration=iteration,
                modifications=modifications,
            )

        log.info(
            "strategy_planned",
            tier=selected_tier,
            flow_type=flow_type,
            quality_level=ql.value,
            iteration=iteration,
        )
        return strategy

    # ------------------------------------------------------------------
    # Evaluator FAIL 피드백 반영
    # ------------------------------------------------------------------

    def _apply_fail_feedback(
        self,
        quality_report: QualityReport,
        selected_tier: str,
        fallback_tiers: list[str],
        quality_level: QualityLevel,
    ) -> tuple[str, list[str], PreviousAttempt, list[str], QualityLevel]:
        """Evaluator FAIL 피드백을 바탕으로 전략을 수정한다."""
        summary = quality_report.evaluation_summary
        cm = summary.checkmesh
        modifications: list[str] = []

        failure_reasons: list[str] = []
        evaluator_recs: list[str] = []

        # checkMesh 완전 실패 → 다음 fallback Tier로 전환
        if not cm.mesh_ok and cm.cells == 0:
            failure_reasons.append("checkMesh complete failure")
            evaluator_recs.append("fallback to next tier")
            if fallback_tiers:
                new_tier = fallback_tiers[0]
                new_fallbacks = fallback_tiers[1:]
                modifications.append(f"tier: {selected_tier} → {new_tier} (checkMesh complete failure)")
                log.warning("tier_fallback_on_checkmesh_failure", from_tier=selected_tier, to_tier=new_tier)
                previous = PreviousAttempt(
                    tier=selected_tier,
                    failure_reason="; ".join(failure_reasons),
                    evaluator_recommendation="; ".join(evaluator_recs),
                )
                return new_tier, new_fallbacks, previous, modifications, quality_level
            else:
                # 모든 Tier 실패 → quality level 다운그레이드
                downgraded_ql = self._downgrade_quality(quality_level, failure_reasons, evaluator_recs, modifications)
                previous = PreviousAttempt(
                    tier=selected_tier,
                    failure_reason="; ".join(failure_reasons),
                    evaluator_recommendation="; ".join(evaluator_recs),
                )
                return selected_tier, [], previous, modifications, downgraded_ql

        # 개별 품질 지표 기반 수정 (Tier 유지, 파라미터 조정 — 상위 strategy_planner에서 tier_specific_params에 반영)
        # 이 함수는 tier 유지 경우에도 previous_attempt를 기록한다.
        if cm.max_non_orthogonality > 70.0:
            failure_reasons.append(f"max_non_orthogonality={cm.max_non_orthogonality:.1f}")
            evaluator_recs.append("snap tolerance 증가, castellated level 상향")
            modifications.append("snappy_snap_tolerance: +1.0")
            modifications.append("snappy_snap_iterations: +3")

        if cm.max_skewness > 6.0:
            failure_reasons.append(f"max_skewness={cm.max_skewness:.1f}")
            evaluator_recs.append("셀 크기 축소, 리파인먼트 추가")
            modifications.append("surface_cell_size: *0.8")

        if cm.negative_volumes > 0:
            failure_reasons.append(f"negative_volumes={cm.negative_volumes}")
            evaluator_recs.append("BL 파라미터 완화 (층수 감소, 성장비 축소)")
            modifications.append("boundary_layers.num_layers: -1")
            modifications.append("boundary_layers.growth_ratio: -0.05")

        if cm.cells > 10_000_000:
            failure_reasons.append(f"cell_count={cm.cells}")
            evaluator_recs.append("셀 크기 확대, 리파인먼트 영역 축소")
            modifications.append("base_cell_size: *1.3")

        # hard fails의 BL 관련 항목
        for fail in summary.hard_fails:
            if "bl" in fail.criterion.lower() or "layer" in fail.criterion.lower():
                failure_reasons.append(f"{fail.criterion}={fail.value:.3f}")
                evaluator_recs.append("BL feature angle 완화, min thickness 축소")
                modifications.append("boundary_layers.feature_angle: -30")
                modifications.append("boundary_layers.min_thickness_ratio: +0.2")
                break

        previous = PreviousAttempt(
            tier=selected_tier,
            failure_reason="; ".join(failure_reasons) if failure_reasons else "quality_fail",
            evaluator_recommendation="; ".join(evaluator_recs) if evaluator_recs else "adjust parameters",
        )
        return selected_tier, fallback_tiers, previous, modifications, quality_level

    @staticmethod
    def _downgrade_quality(
        quality_level: QualityLevel,
        failure_reasons: list[str],
        evaluator_recs: list[str],
        modifications: list[str],
    ) -> QualityLevel:
        """Quality level을 한 단계 낮춘다 (fine→standard→draft)."""
        downgrade_map = {
            QualityLevel.FINE: QualityLevel.STANDARD,
            QualityLevel.STANDARD: QualityLevel.DRAFT,
            QualityLevel.DRAFT: QualityLevel.DRAFT,  # 최저 → 유지
        }
        new_ql = downgrade_map.get(quality_level, QualityLevel.DRAFT)
        if new_ql != quality_level:
            failure_reasons.append(f"all_tiers_failed_at_{quality_level.value}")
            evaluator_recs.append(f"downgrade quality: {quality_level.value} → {new_ql.value}")
            modifications.append(f"quality_level: {quality_level.value} → {new_ql.value}")
            log.warning("quality_level_downgraded", from_ql=quality_level.value, to_ql=new_ql.value)
        return new_ql

    # ------------------------------------------------------------------
    # 헬퍼
    # ------------------------------------------------------------------

    @staticmethod
    def _fill_runtime_params(
        params: dict,
        tier: str,
        cell_sizes: dict[str, float],
        quality_level: QualityLevel = QualityLevel.STANDARD,
    ) -> None:
        """None placeholder를 실제 값으로 채운다."""
        if tier == "tier15_cfmesh":
            if params.get("cf_max_cell_size") is None:
                params["cf_max_cell_size"] = cell_sizes["base_cell_size"]
        elif tier == "tier05_netgen":
            if params.get("ng_max_h") is None:
                params["ng_max_h"] = cell_sizes["base_cell_size"]
            if params.get("ng_min_h") is None:
                params["ng_min_h"] = cell_sizes["min_cell_size"]
        elif tier == "tier2_tetwild":
            if params.get("tw_edge_length") is None:
                params["tw_edge_length"] = cell_sizes["base_cell_size"]
            # draft: coarse epsilon
            ql = quality_level.value if isinstance(quality_level, QualityLevel) else str(quality_level)
            if ql == QualityLevel.DRAFT.value:
                params["tw_epsilon"] = _DRAFT_EPSILON

    @staticmethod
    def _build_refinement_regions(
        report: GeometryReport,
        flow_type: str,
        cell_sizes: dict[str, float],
    ) -> list[RefinementRegion]:
        """외부 유동이면 표면 + wake 리파인먼트 영역을 생성한다."""
        if flow_type != "external":
            return []

        bbox = report.geometry.bounding_box
        L = bbox.characteristic_length

        surface_region = RefinementRegion(
            type="surface",
            name="body",
            level=[2, 3],
            cell_size=cell_sizes["surface_cell_size"],
        )

        wake_region = RefinementRegion(
            type="box",
            name="wake",
            level=1,
            cell_size=cell_sizes["base_cell_size"],
            bounds={
                "min": [bbox.max[0], bbox.center[1] - L * 0.2, bbox.center[2] - L * 0.2],
                "max": [bbox.max[0] + L * 2.0, bbox.center[1] + L * 0.2, bbox.center[2] + L * 0.2],
            },
        )

        return [surface_region, wake_region]
