"""Tier 자동 선택 로직."""

from __future__ import annotations

from core.schemas import GeometryReport, QualityLevel, SurfaceQualityLevel
from core.utils.logging import get_logger

log = get_logger(__name__)

# Tier 우선순위 (품질/안정성 순)
_TIER_ORDER = [
    "tier1_snappy",
    "tier15_cfmesh",
    "tier05_netgen",
    "tier0_core",
    "tier2_tetwild",
]

# CLI hint → canonical tier name
_HINT_MAP: dict[str, str] = {
    "auto": "auto",
    "core": "tier0_core",
    "netgen": "tier05_netgen",
    "snappy": "tier1_snappy",
    "cfmesh": "tier15_cfmesh",
    "tetwild": "tier2_tetwild",
    # canonical names are also accepted directly
    "tier0_core": "tier0_core",
    "tier05_netgen": "tier05_netgen",
    "tier1_snappy": "tier1_snappy",
    "tier15_cfmesh": "tier15_cfmesh",
    "tier2_tetwild": "tier2_tetwild",
}

# QualityLevel → (primary_tiers_candidates, fallback_tiers)
# primary_tiers_candidates: ordered list — first matching compatible tier wins
_QUALITY_FALLBACKS: dict[str, list[str]] = {
    "draft":    ["tier05_netgen"],
    "standard": ["tier2_tetwild", "tier0_core"],
    "fine":     ["tier05_netgen", "tier2_tetwild"],
}


class TierSelector:
    """입력 특성 기반으로 최적 Tier를 자동 선택한다."""

    def select(
        self,
        report: GeometryReport,
        tier_hint: str = "auto",
        quality_level: QualityLevel | str = QualityLevel.STANDARD,
        surface_quality_level: SurfaceQualityLevel | str = SurfaceQualityLevel.L1_REPAIR,
    ) -> tuple[str, list[str]]:
        """Tier를 선택하고 fallback 순서를 반환한다.

        Args:
            report: GeometryReport (Analyzer 출력)
            tier_hint: CLI --tier 값. 'auto'가 아니면 그 값을 사용한다.
            quality_level: 품질 레벨 (draft / standard / fine).
            surface_quality_level: 표면 품질 레벨 (l1_repair / l2_remesh / l3_ai).

        Returns:
            (selected_tier, fallback_tiers) 튜플.
        """
        # Normalise to string value for comparisons
        if isinstance(quality_level, QualityLevel):
            ql = quality_level.value
        else:
            ql = str(quality_level)

        if isinstance(surface_quality_level, SurfaceQualityLevel):
            sql = surface_quality_level.value
        else:
            sql = str(surface_quality_level)

        # tier_hint override
        canonical = _HINT_MAP.get(tier_hint, tier_hint)
        if canonical != "auto":
            log.info("tier_hint_override", hint=tier_hint, canonical=canonical)
            fallbacks = [t for t in _TIER_ORDER if t != canonical]
            return canonical, fallbacks

        # l3_ai 표면 → tetwild 강제
        if sql == SurfaceQualityLevel.L3_AI.value:
            log.info("tier_forced_l3ai", tier="tier2_tetwild")
            fallbacks = [t for t in _TIER_ORDER if t != "tier2_tetwild"]
            return "tier2_tetwild", fallbacks

        selected = self._auto_select(report, ql)
        fallbacks = _QUALITY_FALLBACKS.get(ql, [t for t in _TIER_ORDER if t != selected])
        # Remove selected from fallbacks to avoid duplicates
        fallbacks = [t for t in fallbacks if t != selected]
        log.info("tier_auto_selected", tier=selected, quality_level=ql, fallbacks=fallbacks)
        return selected, fallbacks

    # ------------------------------------------------------------------
    # 내부 결정 트리
    # ------------------------------------------------------------------

    def _auto_select(self, report: GeometryReport, quality_level: str) -> str:
        is_cad = report.file_info.is_cad_brep
        flow_type = report.flow_estimation.type
        is_watertight = report.geometry.surface.is_watertight
        is_manifold = report.geometry.surface.is_manifold
        has_degenerate = report.geometry.surface.has_degenerate_faces

        # ── draft ─────────────────────────────────────────────────────
        if quality_level == QualityLevel.DRAFT.value:
            log.debug("tier_decision", reason="draft_quality", tier="tier2_tetwild")
            return "tier2_tetwild"

        # ── fine ──────────────────────────────────────────────────────
        if quality_level == QualityLevel.FINE.value:
            # B-Rep → Netgen (can process B-Rep directly)
            if is_cad:
                log.debug("tier_decision", reason="fine_cad_brep", tier="tier05_netgen")
                return "tier05_netgen"
            # 외부 유동 + watertight → snappyHexMesh (BL 자동)
            if flow_type == "external" and is_watertight:
                log.debug("tier_decision", reason="fine_external_watertight", tier="tier1_snappy")
                return "tier1_snappy"
            # 내부 유동 → cfMesh
            if is_watertight:
                log.debug("tier_decision", reason="fine_internal_watertight", tier="tier15_cfmesh")
                return "tier15_cfmesh"
            # 불량 표면 → tetwild
            log.debug("tier_decision", reason="fine_bad_surface", tier="tier2_tetwild")
            return "tier2_tetwild"

        # ── standard (default) ────────────────────────────────────────
        # 1. CAD B-Rep (STEP/IGES/BREP) → Netgen
        if is_cad:
            log.debug("tier_decision", reason="cad_brep", tier="tier05_netgen")
            return "tier05_netgen"

        # 2. 외부 유동 + watertight → snappyHexMesh
        if flow_type == "external" and is_watertight:
            log.debug("tier_decision", reason="external_watertight", tier="tier1_snappy")
            return "tier1_snappy"

        # 3. 내부 유동 + watertight → cfMesh
        if flow_type == "internal" and is_watertight:
            log.debug("tier_decision", reason="internal_watertight", tier="tier15_cfmesh")
            return "tier15_cfmesh"

        # 4. watertight + 단순 형상 → Tier 0 core
        if is_watertight and self._is_simple(report):
            log.debug("tier_decision", reason="watertight_simple", tier="tier0_core")
            return "tier0_core"

        # 5. 불량 표면 / non-manifold → TetWild
        if not is_manifold or has_degenerate:
            log.debug("tier_decision", reason="bad_surface", tier="tier2_tetwild")
            return "tier2_tetwild"

        # default fallback
        log.debug("tier_decision", reason="default", tier="tier2_tetwild")
        return "tier2_tetwild"

    @staticmethod
    def _is_simple(report: GeometryReport) -> bool:
        """단순 형상 판별: 날카로운 엣지 수가 적고, genus=0 이면 단순."""
        surface = report.geometry.surface
        features = report.geometry.features
        return (
            surface.genus == 0
            and surface.num_connected_components == 1
            and features.num_sharp_edges < 100
        )
