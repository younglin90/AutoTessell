"""QualityReport 생성 및 Rich 터미널 출력."""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from core.schemas import (
    AdditionalMetrics,
    CheckMeshResult,
    EvaluationSummary,
    FailCriterion,
    GeometryFidelity,
    MeshStrategy,
    QualityReport,
    Recommendation,
    Verdict,
)
from core.utils.logging import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# QualityLevel별 Hard / Soft FAIL 임계값
# ---------------------------------------------------------------------------

_QUALITY_THRESHOLDS: dict[str, dict[str, Any]] = {
    "draft": {
        "hard_non_ortho": 85.0,
        "hard_skewness": 8.0,
        "hard_hausdorff": 0.10,  # Draft: 표면 충실도 검증 스킵 (_check_hard_fails에서 조건 확인)
        "soft_non_ortho": 80.0,
        "soft_skewness": 6.0,
        "soft_aspect_ratio": 1000.0,
        "soft_volume_ratio": 100000.0,
        "soft_area_deviation": 20.0,
        "soft_bl_missing": None,  # N/A for draft
    },
    "standard": {
        "hard_non_ortho": 70.0,
        "hard_skewness": 6.0,
        "hard_hausdorff": 0.05,
        "soft_non_ortho": 65.0,
        "soft_skewness": 4.0,
        "soft_aspect_ratio": 200.0,
        "soft_volume_ratio": 10000.0,
        "soft_area_deviation": 10.0,
        "soft_bl_missing": 30.0,
    },
    "fine": {
        "hard_non_ortho": 65.0,
        "hard_skewness": 4.0,
        "hard_hausdorff": 0.02,
        "soft_non_ortho": 60.0,
        "soft_skewness": 3.0,
        "soft_aspect_ratio": 100.0,
        "soft_volume_ratio": 1000.0,
        "soft_area_deviation": 5.0,
        "soft_bl_missing": 20.0,
    },
}


def get_thresholds(quality_level: str) -> dict[str, Any]:
    """quality_level에 맞는 임계값 딕셔너리를 반환한다.

    알 수 없는 quality_level이면 "standard"로 폴백한다.
    """
    return _QUALITY_THRESHOLDS.get(quality_level, _QUALITY_THRESHOLDS["standard"])


# Quality-level-independent hard fail checks (non-orthogonality / skewness
# thresholds are handled separately via get_thresholds).
_HARD_FAIL_FIXED: dict[str, dict[str, Any]] = {
    "negative_volumes": {
        "threshold": 0,
        "op": "gt",
        "label": "Negative Volumes",
        "location_hint": "negative volume 셀 발생 (checkMesh 로그 참조)",
    },
    # Note: failed_checks는 개별 지표(negative_volumes, min_determinant 등)로
    # 이미 커버되므로 hard fail에서 제거. OpenFOAM checkMesh의 "Failed N mesh checks"는
    # small determinant 등 draft에서 허용 가능한 항목도 포함하기 때문.
    "min_cell_volume": {
        "threshold": 0.0,
        "op": "le",
        "label": "Min Cell Volume",
        "location_hint": "축퇴 셀 발생",
    },
    "min_determinant": {
        "threshold": 0.0,
        "op": "le",
        "label": "Min Determinant",
        "location_hint": "비정상 셀 형상",
    },
}

# ---------------------------------------------------------------------------
# 권고사항 생성 규칙
# ---------------------------------------------------------------------------

RECOMMENDATION_RULES: dict[str, dict[str, Any]] = {
    "high_non_orthogonality": {
        "diagnosis": "Non-orthogonality가 {value}°로 기준({threshold}°) 초과",
        "recommendations": [
            ("snap_tolerance 증가", "snappyHexMesh snap tolerance 상향으로 표면 적합도 향상"),
            ("snap_iterations 증가", "추가 snap 반복으로 비직교 셀 감소"),
            ("feature_extract_level 상향", "날카로운 엣지 특징선을 더 정밀하게 포착"),
            ("local refinement 추가", "해당 영역의 셀 크기 축소"),
        ],
    },
    "negative_volumes": {
        "diagnosis": "{count}개의 negative volume 셀 발생",
        "recommendations": [
            ("bl_num_layers 축소", "BL 층 수 축소로 negative volume 방지"),
            ("bl_growth_ratio 축소", "BL 성장비 축소로 셀 품질 향상"),
            ("bl_feature_angle 축소", "곡면/날카로운 엣지 근처 BL 생략"),
            ("bl_enabled → false", "심각한 경우 BL 비활성화 후 재시도"),
        ],
    },
    "high_skewness": {
        "diagnosis": "Skewness가 {value}로 기준({threshold}) 초과",
        "recommendations": [
            ("cell_size 축소", "셀 크기 축소로 스큐니스 감소"),
            ("snap_nSolveIter 증가", "snap 반복 횟수 증가"),
            ("remesh_target_faces 증가", "지오메트리 리메쉬로 표면 품질 향상"),
        ],
    },
    "geometry_deviation": {
        "diagnosis": "표면 Hausdorff 편차 {percent:.2f}%",
        "recommendations": [
            ("snap_tolerance 축소", "더 정밀한 snapping으로 표면 충실도 향상"),
            ("refinement_level 상향", "castellated level 상향으로 표면 해상도 증가"),
            ("remesh_target_faces 증가", "원본 STL 삼각형 수 증가로 표면 정밀도 향상"),
        ],
    },
    "high_aspect_ratio": {
        "diagnosis": "Aspect ratio가 {value}로 기준({threshold}) 초과",
        "recommendations": [
            ("cell_size 축소", "셀 크기 균일화로 aspect ratio 개선"),
            ("refinement_regions 추가", "고 aspect ratio 영역에 local refinement 추가"),
        ],
    },
    "high_cell_volume_ratio": {
        "diagnosis": "셀 크기 비율이 {value:.0f}로 기준({threshold:.0f}) 초과",
        "recommendations": [
            ("refinement_level 상향", "전환 영역에 점진적 refinement 추가"),
            ("cell_size 균일화", "최소/최대 셀 크기 비율 축소"),
        ],
    },
}


def _check_condition(value: float, threshold: float, op: str) -> bool:
    """op에 따라 value와 threshold를 비교한다."""
    if op == "gt":
        return value > threshold
    if op == "ge":
        return value >= threshold
    if op == "lt":
        return value < threshold
    if op == "le":
        return value <= threshold
    return False


class EvaluationReporter:
    """checkMesh 결과와 추가 지표를 종합해 QualityReport를 생성한다."""

    def evaluate(
        self,
        checkmesh: CheckMeshResult,
        strategy: MeshStrategy | None,
        metrics: AdditionalMetrics,
        geometry_fidelity: GeometryFidelity | None,
        iteration: int,
        tier: str,
        elapsed: float,
        quality_level: str = "standard",
    ) -> QualityReport:
        """PASS/FAIL 판정 후 QualityReport를 반환한다.

        Args:
            checkmesh: checkMesh 파싱 결과.
            strategy: Strategist의 MeshStrategy (없으면 None).
            metrics: pyvista 추가 지표.
            geometry_fidelity: Hausdorff 지오메트리 충실도 (없으면 None).
            iteration: 현재 반복 횟수.
            tier: 평가 대상 Tier 이름.
            elapsed: 평가 소요 시간(초).
            quality_level: 평가 품질 레벨 ("draft" / "standard" / "fine").
                strategy에 quality_level이 있으면 그것을 우선 사용한다.

        Returns:
            QualityReport 객체.
        """
        # strategy의 quality_level을 우선 사용
        effective_quality_level = quality_level
        if strategy is not None and hasattr(strategy, "quality_level"):
            effective_quality_level = strategy.quality_level.value

        thresholds = get_thresholds(effective_quality_level)

        hard_fails = self._check_hard_fails(
            checkmesh, metrics, geometry_fidelity, thresholds, effective_quality_level
        )
        soft_fails = self._check_soft_fails(
            checkmesh, metrics, geometry_fidelity, thresholds, effective_quality_level
        )

        if hard_fails:
            verdict = Verdict.FAIL
        elif len(soft_fails) >= 2:
            verdict = Verdict.FAIL
        elif soft_fails:
            verdict = Verdict.PASS_WITH_WARNINGS
        else:
            verdict = Verdict.PASS

        # Generate verdict_reasoning for transparency
        reasoning_parts = []
        if hard_fails:
            criteria = ", ".join(f.criterion for f in hard_fails)
            reasoning_parts.append(f"Hard FAIL: {criteria}")
        if len(soft_fails) >= 2:
            criteria = ", ".join(f.criterion for f in soft_fails)
            reasoning_parts.append(f"Soft FAIL (2+): {criteria}")
        elif soft_fails:
            criteria = ", ".join(f.criterion for f in soft_fails)
            reasoning_parts.append(f"경고 (soft fail 1): {criteria}")
        if checkmesh.mesh_ok is False and verdict != Verdict.FAIL:
            reasoning_parts.append(
                f"OpenFOAM checkMesh FAIL(failed_checks={checkmesh.failed_checks})이나 "
                f"{effective_quality_level} 기준 내 허용 범위 → AutoTessell {verdict.value}"
            )
        verdict_reasoning = "; ".join(reasoning_parts) if reasoning_parts else "모든 기준 통과"

        recommendations = self._generate_recommendations(
            checkmesh=checkmesh,
            metrics=metrics,
            geometry_fidelity=geometry_fidelity,
            hard_fails=hard_fails,
            soft_fails=soft_fails,
            strategy=strategy,
        )

        log.info(
            "Evaluation complete",
            verdict=verdict,
            quality_level=effective_quality_level,
            hard_fails=len(hard_fails),
            soft_fails=len(soft_fails),
        )

        summary = EvaluationSummary(
            verdict=verdict,
            iteration=iteration,
            tier_evaluated=tier,
            evaluation_time_seconds=elapsed,
            checkmesh=checkmesh,
            additional_metrics=metrics,
            geometry_fidelity=geometry_fidelity,
            hard_fails=hard_fails,
            soft_fails=soft_fails,
            recommendations=recommendations,
            quality_level=effective_quality_level,
            verdict_reasoning=verdict_reasoning,
        )
        return QualityReport(evaluation_summary=summary)

    # ------------------------------------------------------------------
    # Hard / Soft FAIL 판정
    # ------------------------------------------------------------------

    def _check_hard_fails(
        self,
        checkmesh: CheckMeshResult,
        metrics: AdditionalMetrics,
        fidelity: GeometryFidelity | None,
        thresholds: dict[str, Any],
        quality_level: str,
    ) -> list[FailCriterion]:
        fails: list[FailCriterion] = []

        # Quality-level-independent fixed checks
        for field, cfg in _HARD_FAIL_FIXED.items():
            value = float(getattr(checkmesh, field, 0))
            if _check_condition(value, cfg["threshold"], cfg["op"]):
                fails.append(
                    FailCriterion(
                        criterion=field,
                        value=value,
                        threshold=float(cfg["threshold"]),
                        location_hint=cfg.get("location_hint", ""),
                    )
                )

        # QualityLevel-aware: Max non-orthogonality
        non_ortho_threshold = thresholds["hard_non_ortho"]
        if checkmesh.max_non_orthogonality > non_ortho_threshold:
            fails.append(
                FailCriterion(
                    criterion="max_non_orthogonality",
                    value=checkmesh.max_non_orthogonality,
                    threshold=non_ortho_threshold,
                    location_hint="날카로운 엣지/곡면 근처 (checkMesh 로그 참조)",
                )
            )

        # QualityLevel-aware: Max skewness
        skewness_threshold = thresholds["hard_skewness"]
        if checkmesh.max_skewness > skewness_threshold:
            fails.append(
                FailCriterion(
                    criterion="max_skewness",
                    value=checkmesh.max_skewness,
                    threshold=skewness_threshold,
                    location_hint="복잡한 지오메트리 근처 (checkMesh 로그 참조)",
                )
            )

        # QualityLevel-aware: Hausdorff relative
        # Draft는 속도 우선이므로 표면 충실도 검증 스킵
        if quality_level != "draft":
            hausdorff_threshold = thresholds["hard_hausdorff"]
            if fidelity is not None and fidelity.hausdorff_relative > hausdorff_threshold:
                fails.append(
                    FailCriterion(
                        criterion="hausdorff_relative",
                        value=fidelity.hausdorff_relative,
                        threshold=hausdorff_threshold,
                        location_hint="표면 지오메트리 충실도 불량",
                    )
                )

        return fails

    def _check_soft_fails(
        self,
        checkmesh: CheckMeshResult,
        metrics: AdditionalMetrics,
        fidelity: GeometryFidelity | None,
        thresholds: dict[str, Any],
        quality_level: str,
    ) -> list[FailCriterion]:
        fails: list[FailCriterion] = []

        # QualityLevel-aware: Max non-orthogonality (soft)
        soft_non_ortho = thresholds["soft_non_ortho"]
        if checkmesh.max_non_orthogonality > soft_non_ortho:
            fails.append(
                FailCriterion(
                    criterion="max_non_orthogonality",
                    value=checkmesh.max_non_orthogonality,
                    threshold=soft_non_ortho,
                    location_hint="",
                )
            )

        # QualityLevel-aware: Max skewness (soft)
        soft_skewness = thresholds["soft_skewness"]
        if checkmesh.max_skewness > soft_skewness:
            fails.append(
                FailCriterion(
                    criterion="max_skewness",
                    value=checkmesh.max_skewness,
                    threshold=soft_skewness,
                    location_hint="",
                )
            )

        # QualityLevel-aware: Max aspect ratio
        soft_aspect = thresholds["soft_aspect_ratio"]
        if checkmesh.max_aspect_ratio > soft_aspect:
            fails.append(
                FailCriterion(
                    criterion="max_aspect_ratio",
                    value=checkmesh.max_aspect_ratio,
                    threshold=soft_aspect,
                    location_hint="",
                )
            )

        # QualityLevel-aware: Cell volume ratio
        soft_vol_ratio = thresholds["soft_volume_ratio"]
        if (
            metrics.cell_volume_stats is not None
            and metrics.cell_volume_stats.ratio_max_min > soft_vol_ratio
        ):
            fails.append(
                FailCriterion(
                    criterion="cell_volume_ratio",
                    value=metrics.cell_volume_stats.ratio_max_min,
                    threshold=soft_vol_ratio,
                    location_hint="셀 크기 불균일",
                )
            )

        # QualityLevel-aware: Surface area deviation
        soft_area_dev = thresholds["soft_area_deviation"]
        if fidelity is not None and fidelity.surface_area_deviation_percent > soft_area_dev:
            fails.append(
                FailCriterion(
                    criterion="surface_area_deviation_percent",
                    value=fidelity.surface_area_deviation_percent,
                    threshold=soft_area_dev,
                    location_hint="표면적 편차 과다",
                )
            )

        # QualityLevel-aware: BL missing ratio (N/A for draft)
        soft_bl_missing = thresholds.get("soft_bl_missing")
        if (
            soft_bl_missing is not None
            and metrics.boundary_layer is not None
        ):
            bl_missing_ratio = 100.0 - metrics.boundary_layer.bl_coverage_percent
            if bl_missing_ratio > soft_bl_missing:
                fails.append(
                    FailCriterion(
                        criterion="bl_missing_ratio",
                        value=bl_missing_ratio,
                        threshold=soft_bl_missing,
                        location_hint="경계층 미생성 비율 과다",
                    )
                )

        return fails

    # ------------------------------------------------------------------
    # 권고사항 생성
    # ------------------------------------------------------------------

    def _generate_recommendations(
        self,
        checkmesh: CheckMeshResult,
        metrics: AdditionalMetrics,
        geometry_fidelity: GeometryFidelity | None,
        hard_fails: list[FailCriterion],
        soft_fails: list[FailCriterion],
        strategy: MeshStrategy | None,
    ) -> list[Recommendation]:
        recs: list[Recommendation] = []
        priority = 1

        all_fails = hard_fails + soft_fails
        criteria_names = {f.criterion for f in all_fails}

        # negative volumes
        if checkmesh.negative_volumes > 0:
            rule = RECOMMENDATION_RULES["negative_volumes"]
            current_layers = strategy.boundary_layers.num_layers if strategy else "N/A"
            current_ratio = strategy.boundary_layers.growth_ratio if strategy else "N/A"
            suggested_layers = (current_layers - 1) if isinstance(current_layers, int) else "N/A"
            suggested_ratio = round(current_ratio * 0.9, 2) if isinstance(current_ratio, float) else "N/A"

            for action, rationale in rule["recommendations"]:
                recs.append(
                    Recommendation(
                        priority=priority,
                        action=action,
                        current_value=current_layers if "layers" in action else current_ratio,
                        suggested_value=suggested_layers if "layers" in action else suggested_ratio,
                        rationale=rationale,
                    )
                )
                priority += 1

        # high non-orthogonality
        if "max_non_orthogonality" in criteria_names:
            # derive threshold from the first matching fail entry
            matching = [f for f in all_fails if f.criterion == "max_non_orthogonality"]
            matching[0].threshold if matching else 70.0
            rule = RECOMMENDATION_RULES["high_non_orthogonality"]
            snap_tol = strategy.tier_specific_params.get("snap_tolerance", 2.0) if strategy else 2.0
            snap_iter = strategy.tier_specific_params.get("snap_iterations", 5) if strategy else 5
            feat_level = strategy.surface_mesh.feature_extract_level if strategy else 1

            suggestions = [
                (snap_tol, round(snap_tol * 2, 1)),
                (snap_iter, snap_iter * 2),
                (feat_level, feat_level + 1),
                (None, None),
            ]
            for (action, rationale), (cur, sug) in zip(rule["recommendations"], suggestions):
                recs.append(
                    Recommendation(
                        priority=priority,
                        action=action,
                        current_value=cur,
                        suggested_value=sug,
                        rationale=rationale,
                    )
                )
                priority += 1

        # high skewness
        if "max_skewness" in criteria_names:
            rule = RECOMMENDATION_RULES["high_skewness"]
            cell_size = strategy.surface_mesh.target_cell_size if strategy else None
            for action, rationale in rule["recommendations"]:
                cur = cell_size
                sug = round(cell_size * 0.7, 5) if cell_size else None
                recs.append(
                    Recommendation(
                        priority=priority,
                        action=action,
                        current_value=cur,
                        suggested_value=sug,
                        rationale=rationale,
                    )
                )
                priority += 1

        # geometry deviation
        if (
            geometry_fidelity is not None
            and (
                "hausdorff_relative" in criteria_names
                or "surface_area_deviation_percent" in criteria_names
            )
        ):
            rule = RECOMMENDATION_RULES["geometry_deviation"]
            snap_tol = strategy.tier_specific_params.get("snap_tolerance", 2.0) if strategy else 2.0
            for action, rationale in rule["recommendations"]:
                recs.append(
                    Recommendation(
                        priority=priority,
                        action=action,
                        current_value=snap_tol,
                        suggested_value=round(snap_tol * 0.5, 2),
                        rationale=rationale,
                    )
                )
                priority += 1

        # high aspect ratio
        if "max_aspect_ratio" in criteria_names:
            rule = RECOMMENDATION_RULES["high_aspect_ratio"]
            cell_size = strategy.surface_mesh.target_cell_size if strategy else None
            for action, rationale in rule["recommendations"]:
                recs.append(
                    Recommendation(
                        priority=priority,
                        action=action,
                        current_value=cell_size,
                        suggested_value=round(cell_size * 0.7, 5) if cell_size else None,
                        rationale=rationale,
                    )
                )
                priority += 1

        # high cell volume ratio
        if "cell_volume_ratio" in criteria_names and metrics.cell_volume_stats is not None:
            rule = RECOMMENDATION_RULES["high_cell_volume_ratio"]
            ratio = metrics.cell_volume_stats.ratio_max_min
            for action, rationale in rule["recommendations"]:
                recs.append(
                    Recommendation(
                        priority=priority,
                        action=action,
                        current_value=round(ratio, 0),
                        suggested_value=round(ratio * 0.1, 0),
                        rationale=rationale,
                    )
                )
                priority += 1

        return recs


# ---------------------------------------------------------------------------
# Rich 터미널 출력
# ---------------------------------------------------------------------------

_CONSOLE = Console()


def _ok_mark(ok: bool) -> str:
    return "[green]OK[/green]" if ok else "[red]FAIL[/red]"


class _MetricRow:
    def __init__(
        self,
        name: str,
        value: str,
        target: str,
        ok: bool,
    ) -> None:
        self.name = name
        self.value = value
        self.target = target
        self.ok = ok


def render_terminal(report: QualityReport) -> None:
    """QualityReport를 Rich 패널 + 테이블 형식으로 터미널에 출력한다."""
    summary = report.evaluation_summary
    cm = summary.checkmesh

    verdict = summary.verdict
    verdict_color = {
        Verdict.PASS: "green",
        Verdict.PASS_WITH_WARNINGS: "yellow",
        Verdict.FAIL: "red",
    }[verdict]
    verdict_text = f"[bold {verdict_color}]{verdict.value}[/bold {verdict_color}]"

    quality_level = summary.quality_level or "standard"
    thresholds = get_thresholds(quality_level)

    # 메트릭 테이블
    table = Table(show_header=True, header_style="bold blue", box=None, padding=(0, 1))
    table.add_column("Metric", style="white", min_width=24)
    table.add_column("Value", justify="right", min_width=12)
    table.add_column("Target", justify="right", min_width=12)
    table.add_column("", justify="center", min_width=4)

    soft_non_ortho = thresholds["soft_non_ortho"]
    soft_skewness = thresholds["soft_skewness"]
    soft_aspect = thresholds["soft_aspect_ratio"]

    rows: list[_MetricRow] = [
        _MetricRow(
            "Max Non-Ortho",
            f"{cm.max_non_orthogonality:.1f}°",
            f"< {soft_non_ortho:.0f}°",
            cm.max_non_orthogonality <= soft_non_ortho,
        ),
        _MetricRow(
            "Avg Non-Ortho",
            f"{cm.avg_non_orthogonality:.1f}°",
            "-",
            True,
        ),
        _MetricRow(
            "Max Skewness",
            f"{cm.max_skewness:.2f}",
            f"< {soft_skewness:.1f}",
            cm.max_skewness <= soft_skewness,
        ),
        _MetricRow(
            "Max Aspect Ratio",
            f"{cm.max_aspect_ratio:.1f}",
            f"< {soft_aspect:.0f}",
            cm.max_aspect_ratio <= soft_aspect,
        ),
        _MetricRow(
            "Min Determinant",
            f"{cm.min_determinant:.4f}",
            "> 0.001",
            cm.min_determinant > 0.001,
        ),
        _MetricRow(
            "Negative Volumes",
            str(cm.negative_volumes),
            "0",
            cm.negative_volumes == 0,
        ),
    ]

    # BL coverage (quality_level에 따라 검증 여부 결정)
    if summary.additional_metrics.boundary_layer is not None:
        bl = summary.additional_metrics.boundary_layer
        # draft: BL 검증 스킵 (속도 우선)
        # standard: > 50% (느슨한 검증)
        # fine: > 80% (엄격한 검증)
        if quality_level == "draft":
            bl_required = False  # draft는 BL 검증 비활성화
            bl_threshold = 0.0
        elif quality_level == "fine":
            bl_required = True
            bl_threshold = 80.0
        else:  # standard
            bl_required = True
            bl_threshold = 50.0

        if bl_required:
            rows.append(
                _MetricRow(
                    "BL Coverage",
                    f"{bl.bl_coverage_percent:.1f}%",
                    f"> {bl_threshold:.0f}%",
                    bl.bl_coverage_percent >= bl_threshold,
                )
            )

    # Hausdorff
    if summary.geometry_fidelity is not None:
        gf = summary.geometry_fidelity
        hard_hausdorff = thresholds["hard_hausdorff"]
        rows.append(
            _MetricRow(
                "Hausdorff Rel.",
                f"{gf.hausdorff_relative * 100:.2f}%",
                f"< {hard_hausdorff * 100:.0f}%",
                gf.hausdorff_relative <= hard_hausdorff,
            )
        )

    for row in rows:
        table.add_row(row.name, row.value, row.target, _ok_mark(row.ok))

    # 권고사항 텍스트
    rec_lines: list[str] = []
    for rec in summary.recommendations[:5]:
        rec_lines.append(
            f"  {rec.priority}. {rec.action}: "
            f"{rec.current_value} → {rec.suggested_value}"
        )

    # 패널 내용 조합
    header = (
        f"Verdict: {verdict_text} (iteration {summary.iteration})\n"
        f"Quality: {quality_level}  "
        f"Tier: {summary.tier_evaluated}  "
        f"Cells: {cm.cells:,}  Points: {cm.points:,}\n"
    )

    content = Text.from_markup(header)
    _CONSOLE.print(
        Panel(
            content,
            title="[bold]Mesh Quality Report[/bold]",
            border_style="cyan",
            expand=False,
        )
    )
    _CONSOLE.print(table)

    if rec_lines:
        _CONSOLE.print("\n[bold]Recommendations:[/bold]")
        for line in rec_lines:
            _CONSOLE.print(line)

    if summary.verdict != Verdict.PASS and summary.iteration > 0:
        _CONSOLE.print(
            "\n[dim]→ Strategist에 피드백 전달, 재시도 예정...[/dim]"
        )
