"""메쉬 전략 수립 메인 로직."""

from __future__ import annotations

from dataclasses import dataclass, field

from core.schemas import (
    BoundaryLayerConfig,
    GeometryReport,
    MeshStrategy,
    MeshType,
    PreprocessedReport,
    PreviousAttempt,
    QualityLevel,
    QualityReport,
    RefinementRegion,
    SurfaceMeshConfig,
    SurfaceQualityLevel,
    Verdict,
)
from core.strategist.complexity_analyzer import ComplexityAnalyzer
from core.strategist.param_optimizer import ParamOptimizer
from core.strategist.tier_selector import TierSelector
from core.utils.logging import get_logger
from core.utils.openfoam_utils import get_openfoam_label_size

log = get_logger(__name__)

# Tier-specific 파라미터 기본값
_TIER_PARAMS: dict[str, dict[str, object]] = {
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
        "tetwild_edge_length": None,
        "tetwild_epsilon": 1e-3,
        "tetwild_stop_energy": 10.0,
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

# Bounds for parameter adjustments to avoid nonsensical values
_MIN_CELL_SIZE_ABS = 0.001  # absolute minimum cell size [m]
_MIN_CELL_SIZE_FACTOR = 0.001  # cell size won't go below 0.1% of characteristic_length
_MIN_BL_LAYERS = 0
_MIN_BL_GROWTH_RATIO = 1.0
_MAX_SNAP_TOLERANCE = 10.0
_MAX_SNAP_ITERATIONS = 30
_MAX_CASTELLATED_LEVEL_BUMP = 5

# snappy 대형 셀 전략: label 크기별 기본/상한 프로파일
_SNAPPY_CELL_LIMITS_INT32: dict[str, tuple[int, int]] = {
    # (max_local_cells, max_global_cells)
    "draft": (2_000_000, 20_000_000),
    "standard": (5_000_000, 50_000_000),
    "fine": (20_000_000, 200_000_000),
}
_SNAPPY_CELL_LIMITS_INT64: dict[str, tuple[int, int]] = {
    "draft": (20_000_000, 200_000_000),
    "standard": (100_000_000, 1_000_000_000),
    "fine": (500_000_000, 4_000_000_000),
}


@dataclass
class _StrategyAdjustments:
    """Accumulated parameter adjustments from evaluator feedback."""

    # Cell size multipliers (applied multiplicatively)
    surface_cell_size_factor: float = 1.0
    base_cell_size_factor: float = 1.0

    # Snap parameters (additive)
    snap_tolerance_factor: float = 1.0
    snap_iterations_add: int = 0
    castellated_level_add: int = 0

    # Surface mesh adjustments
    feature_extract_level_add: int = 0

    # BL adjustments
    bl_layers_add: int = 0
    bl_growth_ratio_factor: float = 1.0
    bl_disable: bool = False

    # Tier change
    switch_tier: str | None = None
    switch_fallbacks: list[str] = field(default_factory=list)

    # Quality level downgrade
    downgrade_quality: QualityLevel | None = None

    # Tracking
    modifications: list[str] = field(default_factory=list)
    failure_reasons: list[str] = field(default_factory=list)
    evaluator_recs: list[str] = field(default_factory=list)


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
        mesh_type: "MeshType | str" = "auto",
        prefer_native_tier: bool = False,
    ) -> MeshStrategy:
        """MeshStrategy를 수립한다.

        Args:
            geometry_report: Analyzer 출력.
            preprocessed_report: Preprocessor 출력 (없으면 원본 파일 사용).
            quality_report: Evaluator 피드백 (재시도 시에만).
            tier_hint: CLI --tier 값.
            iteration: 현재 시도 횟수 (1-indexed).
            quality_level: 품질 레벨 (draft / standard / fine).
            mesh_type: 사용자가 1차로 선택한 메쉬 대분류
                ("auto" / "tet" / "hex_dominant" / "poly"). v0.4 이후 도입.

        Returns:
            MeshStrategy Pydantic 모델.
        """
        # Normalise quality_level
        if isinstance(quality_level, QualityLevel):
            ql = quality_level
        else:
            ql = QualityLevel(quality_level)

        # Normalise mesh_type
        if isinstance(mesh_type, MeshType):
            mt = mesh_type
        else:
            try:
                mt = MeshType(str(mesh_type).lower())
            except ValueError:
                log.warning("mesh_type_unknown_fallback_auto", value=mesh_type)
                mt = MeshType.AUTO

        # v0.4: mesh_type=AUTO 이면 strategy.mesh_type 에는 그대로 AUTO 를 기록.
        # (tier_selector 가 AUTO 면 매핑 단계를 skip 하고 기존 geometry 기반
        # _auto_select 로 fallback 하므로 legacy 동작 그대로 보존된다.) 대신 사용자가
        # 참고할 "추천 mesh_type" 을 tier_specific_params 에 힌트로 기록.
        recommended_mt_hint: str | None = None
        if mt == MeshType.AUTO:
            auto_mt = MeshType.HEX_DOMINANT
            if ql == QualityLevel.DRAFT:
                auto_mt = MeshType.TET
            try:
                is_wt = geometry_report.geometry.surface.is_watertight
                n_comp = geometry_report.geometry.surface.num_connected_components
                if not is_wt or n_comp > 1:
                    auto_mt = MeshType.TET
            except Exception:
                pass
            recommended_mt_hint = auto_mt.value
            log.info(
                "mesh_type_auto_recommendation",
                recommended=auto_mt.value,
                quality_level=ql.value,
            )

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
            geometry_report, tier_hint,
            quality_level=ql, surface_quality_level=sql,
            mesh_type=mt,
            prefer_native_tier=prefer_native_tier,
        )
        selection_context = dict(self._selector.last_selection_context)

        # 2. quality_report FAIL 피드백 반영
        previous_attempt: PreviousAttempt | None = None
        adjustments: _StrategyAdjustments | None = None

        if quality_report is not None:
            summary = quality_report.evaluation_summary
            if summary.verdict == Verdict.FAIL:
                adjustments = self._compute_adjustments(
                    quality_report, selected_tier, fallback_tiers, ql
                )
                # Apply tier/quality changes from adjustments
                if adjustments.switch_tier is not None:
                    selected_tier = adjustments.switch_tier
                    fallback_tiers = adjustments.switch_fallbacks
                if adjustments.downgrade_quality is not None:
                    ql = adjustments.downgrade_quality

                previous_attempt = PreviousAttempt(
                    tier=quality_report.evaluation_summary.tier_evaluated,
                    quality_level=ql.value,
                    failure_reason="; ".join(adjustments.failure_reasons) if adjustments.failure_reasons else "quality_fail",
                    evaluator_recommendation="; ".join(adjustments.evaluator_recs) if adjustments.evaluator_recs else "adjust parameters",
                    modifications=list(adjustments.modifications),
                )

        # 3. 유동 타입 결정
        flow_type = geometry_report.flow_estimation.type
        if flow_type not in ("external", "internal"):
            flow_type = "external"  # 알 수 없으면 외부 유동으로 보수적 처리

        # 3.5. 형상 복잡도 분석
        complexity_score = ComplexityAnalyzer.analyze(geometry_report)
        complexity_class = ComplexityAnalyzer.classify(complexity_score)
        log.info(
            "geometry_complexity_classified",
            classification=complexity_class,
            overall_score=f"{complexity_score.overall:.1f}",
        )

        # 4. 파라미터 계산
        domain = self._optimizer.compute_domain(geometry_report, flow_type, quality_level=ql)
        cell_sizes = self._optimizer.compute_cell_sizes(geometry_report, quality_level=ql)
        bl_config = self._optimizer.compute_boundary_layers(geometry_report, quality_level=ql)
        quality_targets = self._optimizer.compute_quality_targets(quality_level=ql)

        # 5. Apply adjustments to computed parameters
        if adjustments is not None:
            cell_sizes, bl_config = self._apply_adjustments(
                adjustments, cell_sizes, bl_config, geometry_report
            )

        # 6. 입력 파일 결정
        if preprocessed_report is not None:
            input_file = preprocessed_report.preprocessing_summary.output_file
        else:
            input_file = geometry_report.file_info.path

        # 7. SurfaceMeshConfig
        feature_extract_level = 1
        if adjustments is not None:
            feature_extract_level = max(1, feature_extract_level + adjustments.feature_extract_level_add)

        surface_mesh = SurfaceMeshConfig(
            input_file=input_file,
            target_cell_size=cell_sizes["surface_cell_size"],
            min_cell_size=cell_sizes["min_cell_size"],
            feature_angle=150.0,
            feature_extract_level=feature_extract_level,
        )

        # 8. Tier-specific params (deep copy + 런타임 값 채우기)
        tier_params = dict(_TIER_PARAMS.get(selected_tier, {}))
        self._fill_runtime_params(tier_params, selected_tier, cell_sizes, ql)
        if selection_context:
            tier_params["engine_selection"] = selection_context

        # 8.5. Apply complexity-based tuning for snappyHexMesh
        self._apply_complexity_tuning(tier_params, selected_tier, complexity_score)

        # 9. Apply tier-specific adjustments (snap tolerance, castellated level, etc.)
        if adjustments is not None:
            self._apply_tier_param_adjustments(tier_params, selected_tier, adjustments)

        # 9.5 label-size 기반 guard/apply (snappy 고셀 전략)
        self._apply_label_size_guards(tier_params, selected_tier, ql)

        # 10. 외부 유동이면 wake 리파인먼트 영역 추가
        refinement_regions = self._build_refinement_regions(
            geometry_report, flow_type, cell_sizes
        )

        strategy = MeshStrategy(
            strategy_version=3,
            iteration=iteration,
            quality_level=ql,
            mesh_type=mt,
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
        # mesh_type=AUTO 추천 힌트를 tier_specific_params 에 추가 (사용자 참고용).
        if recommended_mt_hint is not None:
            strategy.tier_specific_params.setdefault(
                "recommended_mesh_type", recommended_mt_hint,
            )

        if adjustments and adjustments.modifications:
            log.info(
                "strategy_modifications_applied",
                iteration=iteration,
                modifications=adjustments.modifications,
            )

        log.info(
            "strategy_planned",
            tier=selected_tier,
            flow_type=flow_type,
            quality_level=ql.value,
            iteration=iteration,
            selection_source=selection_context.get("source"),
            selection_reason=selection_context.get("reason"),
        )
        return strategy

    # ------------------------------------------------------------------
    # Evaluator FAIL feedback -> structured adjustments
    # ------------------------------------------------------------------

    def _compute_adjustments(
        self,
        quality_report: QualityReport,
        selected_tier: str,
        fallback_tiers: list[str],
        quality_level: QualityLevel,
    ) -> _StrategyAdjustments:
        """Analyze evaluator FAIL feedback and compute structured adjustments."""
        adj = _StrategyAdjustments()
        summary = quality_report.evaluation_summary
        cm = summary.checkmesh

        # ----------------------------------------------------------
        # checkMesh complete failure (cells=0) -> fallback tier
        # ----------------------------------------------------------
        if not cm.mesh_ok and cm.cells == 0:
            adj.failure_reasons.append("checkMesh complete failure")
            adj.evaluator_recs.append("fallback to next tier")
            if fallback_tiers:
                new_tier = fallback_tiers[0]
                new_fallbacks = fallback_tiers[1:]
                adj.switch_tier = new_tier
                adj.switch_fallbacks = new_fallbacks
                adj.modifications.append(
                    f"tier: {selected_tier} -> {new_tier} (checkMesh complete failure)"
                )
                log.warning(
                    "tier_fallback_on_checkmesh_failure",
                    from_tier=selected_tier,
                    to_tier=new_tier,
                )
            else:
                # All tiers failed -> downgrade quality level
                new_ql = self._downgrade_quality(
                    quality_level, adj.failure_reasons, adj.evaluator_recs, adj.modifications
                )
                adj.downgrade_quality = new_ql
            return adj

        # ----------------------------------------------------------
        # failed_checks > 0 but cells > 0 -> try different tier
        # ----------------------------------------------------------
        if cm.failed_checks > 0 and not cm.mesh_ok and cm.cells > 0:
            adj.failure_reasons.append(f"checkMesh hard fail (failed_checks={cm.failed_checks})")
            adj.evaluator_recs.append("switch to different tier")
            if fallback_tiers:
                new_tier = fallback_tiers[0]
                new_fallbacks = fallback_tiers[1:]
                adj.switch_tier = new_tier
                adj.switch_fallbacks = new_fallbacks
                adj.modifications.append(
                    f"tier: {selected_tier} -> {new_tier} (checkMesh hard fail)"
                )
                log.warning(
                    "tier_switch_on_checkmesh_hard_fail",
                    from_tier=selected_tier,
                    to_tier=new_tier,
                    failed_checks=cm.failed_checks,
                )
            # Continue to also apply parameter adjustments below

        # ----------------------------------------------------------
        # high_non_orthogonality
        # ----------------------------------------------------------
        if cm.max_non_orthogonality > 70.0:
            adj.failure_reasons.append(
                f"max_non_orthogonality={cm.max_non_orthogonality:.1f}"
            )
            adj.evaluator_recs.append("snap tolerance increase, castellated level up")
            adj.snap_tolerance_factor = 1.5
            adj.snap_iterations_add = 3
            adj.castellated_level_add = 1
            adj.modifications.append(
                f"snappy_snap_tolerance: x1.5 (non_ortho={cm.max_non_orthogonality:.1f})"
            )
            adj.modifications.append("snappy_snap_iterations: +3")
            adj.modifications.append("snappy_castellated_level: +1")
            log.info(
                "retry_adjust_non_orthogonality",
                max_non_ortho=cm.max_non_orthogonality,
                snap_tolerance_factor=1.5,
                snap_iterations_add=3,
            )

        # ----------------------------------------------------------
        # high_skewness
        # ----------------------------------------------------------
        if cm.max_skewness > 6.0:
            adj.failure_reasons.append(f"max_skewness={cm.max_skewness:.1f}")
            adj.evaluator_recs.append("decrease cell size, add refinement")
            adj.surface_cell_size_factor = 0.7
            adj.modifications.append(
                f"surface_cell_size: x0.7 (skewness={cm.max_skewness:.1f})"
            )
            log.info(
                "retry_adjust_skewness",
                max_skewness=cm.max_skewness,
                cell_size_factor=0.7,
            )

        # ----------------------------------------------------------
        # negative_volumes
        # ----------------------------------------------------------
        if cm.negative_volumes > 0:
            adj.failure_reasons.append(f"negative_volumes={cm.negative_volumes}")
            adj.evaluator_recs.append("disable BL or reduce layers, reduce growth ratio")
            adj.bl_layers_add = -2
            adj.bl_growth_ratio_factor = 0.8
            adj.modifications.append(
                f"boundary_layers.num_layers: -2 (neg_vols={cm.negative_volumes})"
            )
            adj.modifications.append("boundary_layers.growth_ratio: x0.8")
            log.info(
                "retry_adjust_negative_volumes",
                negative_volumes=cm.negative_volumes,
                bl_layers_add=-2,
                bl_growth_ratio_factor=0.8,
            )

        # ----------------------------------------------------------
        # high_aspect_ratio
        # ----------------------------------------------------------
        if cm.max_aspect_ratio > 200.0:
            adj.failure_reasons.append(f"max_aspect_ratio={cm.max_aspect_ratio:.1f}")
            adj.evaluator_recs.append("decrease cell size for better aspect ratio")
            # Compound with skewness adjustment if both triggered
            adj.surface_cell_size_factor *= 0.8
            adj.modifications.append(
                f"surface_cell_size: x0.8 (aspect_ratio={cm.max_aspect_ratio:.1f})"
            )
            log.info(
                "retry_adjust_aspect_ratio",
                max_aspect_ratio=cm.max_aspect_ratio,
                cell_size_factor=0.8,
            )

        # ----------------------------------------------------------
        # hausdorff_high (geometry fidelity)
        # ----------------------------------------------------------
        if summary.geometry_fidelity is not None:
            if summary.geometry_fidelity.hausdorff_relative > 0.05:
                adj.failure_reasons.append(
                    f"hausdorff_relative={summary.geometry_fidelity.hausdorff_relative:.4f}"
                )
                adj.evaluator_recs.append(
                    "increase castellated level, decrease cell size for surface resolution"
                )
                adj.castellated_level_add += 1
                adj.feature_extract_level_add += 1
                adj.surface_cell_size_factor *= 0.8
                adj.modifications.append(
                    f"castellated_level: +1 (hausdorff={summary.geometry_fidelity.hausdorff_relative:.4f})"
                )
                adj.modifications.append("feature_extract_level: +1 (hausdorff)")
                adj.modifications.append("surface_cell_size: x0.8 (hausdorff)")
                log.info(
                    "retry_adjust_hausdorff",
                    hausdorff_relative=summary.geometry_fidelity.hausdorff_relative,
                    feature_extract_level_add=1,
                )

        # ----------------------------------------------------------
        # Excessive cell count
        # ----------------------------------------------------------
        if cm.cells > 10_000_000:
            adj.failure_reasons.append(f"cell_count={cm.cells}")
            adj.evaluator_recs.append("increase cell size, reduce refinement")
            adj.base_cell_size_factor = 1.3
            adj.modifications.append("base_cell_size: x1.3")

        # ----------------------------------------------------------
        # BL-related hard fails
        # ----------------------------------------------------------
        for fail in summary.hard_fails:
            if "bl" in fail.criterion.lower() or "layer" in fail.criterion.lower():
                adj.failure_reasons.append(f"{fail.criterion}={fail.value:.3f}")
                adj.evaluator_recs.append("BL feature angle relax, min thickness decrease")
                adj.modifications.append("boundary_layers.feature_angle: -30")
                adj.modifications.append("boundary_layers.min_thickness_ratio: +0.2")
                break

        # If no specific failure was identified, record generic quality fail
        if not adj.failure_reasons:
            adj.failure_reasons.append("quality_fail")
            adj.evaluator_recs.append("adjust parameters")

        return adj

    def _apply_adjustments(
        self,
        adj: _StrategyAdjustments,
        cell_sizes: dict[str, float],
        bl_config: BoundaryLayerConfig,
        geometry_report: GeometryReport,
    ) -> tuple[dict[str, float], BoundaryLayerConfig]:
        """Apply computed adjustments to cell sizes and BL config.

        Returns modified copies. Values are bounded to sensible ranges.
        """
        L = geometry_report.geometry.bounding_box.characteristic_length
        min_allowed_cell = max(L * _MIN_CELL_SIZE_FACTOR, _MIN_CELL_SIZE_ABS)

        # -- Cell size adjustments --
        new_sizes = dict(cell_sizes)
        new_sizes["surface_cell_size"] = max(
            new_sizes["surface_cell_size"] * adj.surface_cell_size_factor,
            min_allowed_cell,
        )
        new_sizes["min_cell_size"] = max(
            new_sizes["surface_cell_size"] / 4.0,
            min_allowed_cell / 4.0,
        )
        new_sizes["base_cell_size"] = max(
            new_sizes["base_cell_size"] * adj.base_cell_size_factor,
            min_allowed_cell,
        )

        # -- BL adjustments --
        new_bl = bl_config.model_copy()

        if adj.bl_disable or (new_bl.num_layers + adj.bl_layers_add <= _MIN_BL_LAYERS):
            # Disable BL entirely
            new_bl = BoundaryLayerConfig(
                enabled=False,
                num_layers=0,
                first_layer_thickness=0.0,
                growth_ratio=bl_config.growth_ratio,
                max_total_thickness=0.0,
                min_thickness_ratio=bl_config.min_thickness_ratio,
                feature_angle=bl_config.feature_angle,
            )
            if adj.bl_layers_add < 0:
                log.info("retry_bl_disabled", reason="layers reduced to zero or below")
        else:
            new_layers = max(new_bl.num_layers + adj.bl_layers_add, _MIN_BL_LAYERS)
            new_growth = max(
                new_bl.growth_ratio * adj.bl_growth_ratio_factor,
                _MIN_BL_GROWTH_RATIO,
            )
            new_bl = BoundaryLayerConfig(
                enabled=new_bl.enabled and new_layers > 0,
                num_layers=new_layers,
                first_layer_thickness=new_bl.first_layer_thickness,
                growth_ratio=new_growth,
                max_total_thickness=new_bl.max_total_thickness,
                min_thickness_ratio=new_bl.min_thickness_ratio,
                feature_angle=new_bl.feature_angle,
            )

        return new_sizes, new_bl

    def _apply_tier_param_adjustments(
        self,
        tier_params: dict[str, object],
        tier: str,
        adj: _StrategyAdjustments,
    ) -> None:
        """Apply snap/castellated adjustments to tier-specific params in-place."""
        if tier == "tier1_snappy":
            # Snap tolerance: multiply, bounded
            old_tol = float(tier_params.get("snappy_snap_tolerance", 2.0))  # type: ignore[arg-type]
            new_tol = min(old_tol * adj.snap_tolerance_factor, _MAX_SNAP_TOLERANCE)
            tier_params["snappy_snap_tolerance"] = new_tol

            # Snap iterations: add, bounded
            old_iters = int(tier_params.get("snappy_snap_iterations", 5))  # type: ignore[call-overload]
            new_iters = min(old_iters + adj.snap_iterations_add, _MAX_SNAP_ITERATIONS)
            tier_params["snappy_snap_iterations"] = new_iters

            # Castellated level: bump both min and max
            old_level = tier_params.get("snappy_castellated_level", [2, 3])
            if isinstance(old_level, list) and len(old_level) == 2:
                bump = min(adj.castellated_level_add, _MAX_CASTELLATED_LEVEL_BUMP)
                tier_params["snappy_castellated_level"] = [
                    old_level[0] + bump,
                    old_level[1] + bump,
                ]

    @staticmethod
    def _downgrade_quality(
        quality_level: QualityLevel,
        failure_reasons: list[str],
        evaluator_recs: list[str],
        modifications: list[str],
    ) -> QualityLevel:
        """Quality level을 한 단계 낮춘다 (fine->standard->draft)."""
        downgrade_map = {
            QualityLevel.FINE: QualityLevel.STANDARD,
            QualityLevel.STANDARD: QualityLevel.DRAFT,
            QualityLevel.DRAFT: QualityLevel.DRAFT,  # 최저 -> 유지
        }
        new_ql = downgrade_map.get(quality_level, QualityLevel.DRAFT)
        if new_ql != quality_level:
            failure_reasons.append(f"all_tiers_failed_at_{quality_level.value}")
            evaluator_recs.append(f"downgrade quality: {quality_level.value} -> {new_ql.value}")
            modifications.append(f"quality_level: {quality_level.value} -> {new_ql.value}")
            log.warning("quality_level_downgraded", from_ql=quality_level.value, to_ql=new_ql.value)
        return new_ql

    # ------------------------------------------------------------------
    # 헬퍼
    # ------------------------------------------------------------------

    @staticmethod
    def _fill_runtime_params(
        params: dict[str, object],
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
            if params.get("tetwild_edge_length") is None:
                params["tetwild_edge_length"] = cell_sizes["base_cell_size"]
            # draft: coarse epsilon
            ql = quality_level.value if isinstance(quality_level, QualityLevel) else str(quality_level)
            if ql == QualityLevel.DRAFT.value:
                params["tetwild_epsilon"] = _DRAFT_EPSILON
                params["tetwild_stop_energy"] = 20.0

    @staticmethod
    def _apply_label_size_guards(
        params: dict[str, object],
        tier: str,
        quality_level: QualityLevel,
    ) -> None:
        """OpenFOAM label 크기에 따라 tier 파라미터를 보정한다."""
        if tier != "tier1_snappy":
            return

        ql = quality_level.value if isinstance(quality_level, QualityLevel) else str(quality_level)
        label_bits = get_openfoam_label_size()

        if label_bits >= 64:
            local_default, global_default = _SNAPPY_CELL_LIMITS_INT64.get(
                ql, _SNAPPY_CELL_LIMITS_INT64["standard"]
            )
            params.setdefault("snappy_max_local_cells", local_default)
            params.setdefault("snappy_max_global_cells", global_default)
            params["snappy_int64_mode"] = True
            return

        # Int32: 안전 상한 강제 (초대형 설정 차단)
        local_cap, global_cap = _SNAPPY_CELL_LIMITS_INT32.get(
            ql, _SNAPPY_CELL_LIMITS_INT32["standard"]
        )
        current_local = int(params.get("snappy_max_local_cells", local_cap))
        current_global = int(params.get("snappy_max_global_cells", global_cap))
        params["snappy_max_local_cells"] = min(current_local, local_cap)
        params["snappy_max_global_cells"] = min(current_global, global_cap)
        params["snappy_int64_mode"] = False

        if current_local > local_cap or current_global > global_cap:
            log.warning(
                "snappy_cells_clamped_for_int32",
                label_bits=label_bits,
                local_before=current_local,
                global_before=current_global,
                local_after=params["snappy_max_local_cells"],
                global_after=params["snappy_max_global_cells"],
            )

    @staticmethod
    def _apply_complexity_tuning(
        params: dict[str, object],
        tier: str,
        complexity_score: Any,
    ) -> None:
        """형상 복잡도에 따라 snappyHexMesh/Netgen 파라미터를 동적으로 조정한다."""
        # snappyHexMesh 튜닝
        if tier == "tier1_snappy":
            snappy_params = ComplexityAnalyzer.get_snappy_tuning_params(complexity_score)
            params.update(snappy_params)

            # skip layers if geometry is extremely complex
            if ComplexityAnalyzer.should_skip_layers(complexity_score):
                params["skip_addLayers"] = True
                log.info("complexity_tuning_skip_layers", classification=ComplexityAnalyzer.classify(complexity_score))

            log.info(
                "complexity_tuning_applied_snappy",
                classification=ComplexityAnalyzer.classify(complexity_score),
                maxLocalCells=snappy_params.get("maxLocalCells"),
                castellatedLevel=snappy_params.get("castellatedLevel"),
            )

        # Netgen 튜닝
        elif tier == "tier05_netgen":
            netgen_params = ComplexityAnalyzer.get_netgen_tuning_params(complexity_score)
            # ng_max_h, ng_min_h, ng_grading이 이미 설정되었을 수 있으므로, 기본값만 설정
            params.setdefault("ng_grading", netgen_params["grading"])
            params.setdefault("ng_quality", netgen_params["quality"])

            log.info(
                "complexity_tuning_applied_netgen",
                classification=ComplexityAnalyzer.classify(complexity_score),
                grading=netgen_params["grading"],
                quality=netgen_params["quality"],
            )

        # TetWild 튜닝
        elif tier == "tier2_tetwild":
            tw_params = ComplexityAnalyzer.get_tetwild_tuning_params(complexity_score)
            params.update(tw_params)
            log.info(
                "complexity_tuning_applied_tetwild",
                classification=ComplexityAnalyzer.classify(complexity_score),
                epsilon=tw_params["tetwild_epsilon"],
                stop_energy=tw_params["tetwild_stop_energy"],
            )

        # WildMesh 튜닝 — overall_score 기반으로 TetWild-매칭 파라미터 주입.
        # ComplexityAnalyzer.classify() 는 threshold 가 50+ 라 knot류(score~7)가
        # "simple"로 분류돼 기본값이 못 바뀌는 문제가 있음. 따라서 classification
        # 대신 overall_score 를 직접 본다.
        elif tier == "tier_wildmesh":
            if complexity_score.overall >= 5.0:
                # borderline~complex: TetWild 매칭 값 주입.
                # 사용자/CLI 명시값은 보존 (setdefault).
                wm_params = ComplexityAnalyzer.get_wildmesh_tuning_params(
                    complexity_score
                )
                # classification "simple" 분기는 draft 와 동일 → 상향 효과 없음.
                # overall_score >= 5.0 케이스는 최소 moderate 값 강제 적용.
                if complexity_score.overall < ComplexityAnalyzer.THRESHOLD_SIMPLE:
                    wm_params = {
                        "wildmesh_epsilon": 1e-3,
                        "wildmesh_edge_length_r": 0.05,
                        "wildmesh_stop_quality": 10.0,
                        "wildmesh_max_its": 80,
                    }
                for key, value in wm_params.items():
                    params.setdefault(key, value)
                log.info(
                    "complexity_tuning_applied_wildmesh",
                    classification=ComplexityAnalyzer.classify(complexity_score),
                    overall=complexity_score.overall,
                    epsilon=params.get("wildmesh_epsilon"),
                    edge_length_r=params.get("wildmesh_edge_length_r"),
                    stop_quality=params.get("wildmesh_stop_quality"),
                    max_its=params.get("wildmesh_max_its"),
                )
            else:
                # 단순 형상 (cube 등): tuning 안 해야 draft 값 유지돼 빠르게 통과.
                log.debug(
                    "wildmesh_tuning_skipped",
                    overall=complexity_score.overall,
                    reason="simple_geometry_uses_quality_level_defaults",
                )

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
