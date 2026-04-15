"""Tier 자동 선택 로직."""

from __future__ import annotations

from core.schemas import GeometryReport, QualityLevel, SurfaceQualityLevel
from core.utils.logging import get_logger

log = get_logger(__name__)

# Tier 우선순위 (품질/안정성 순)
_TIER_ORDER = [
    "tier0_2d_meshpy",          # 2D 감지 시 먼저 시도
    "tier1_snappy",             # 외부유동 + 경계층
    "tier_hex_classy_blocks",   # 구조화 Hex (단순 형상)
    "tier_polyhedral",          # 다면체 메시 (셀 수 최소화)
    "tier15_cfmesh",            # 내부유동
    "tier05_netgen",            # CAD/일반
    "tier0_core",               # 단순 형상
    "tier_meshpy",              # Tet fallback
    "tier2_tetwild",            # 불량 표면
    "tier_jigsaw",              # JIGSAW Tet
    "tier_jigsaw_fallback",     # 최후 fallback (매우 안정적)
    "tier_wildmesh",            # WildMesh
    "tier_gmsh_hex",            # GMSH Hex
    "tier_cinolib_hex",         # Cinolib Hex
    "tier_voro_poly",           # Voronoi Polyhedral
    "tier_hohqmesh",            # HOHQMesh structured
    "tier_classy_blocks",       # Classy Blocks
]

# CLI hint → canonical tier name
_HINT_MAP: dict[str, str] = {
    "auto": "auto",
    "2d": "tier0_2d_meshpy",
    "hex": "tier_hex_classy_blocks",
    "polyhedral": "tier_polyhedral",
    "core": "tier0_core",
    "netgen": "tier05_netgen",
    "snappy": "tier1_snappy",
    "cfmesh": "tier15_cfmesh",
    "tetwild": "tier2_tetwild",
    "jigsaw": "tier_jigsaw",
    "jigsaw_fallback": "tier_jigsaw_fallback",
    "mmg": "tier_mmg3d",
    "mmg3d": "tier_mmg3d",
    "tier_mmg3d": "tier_mmg3d",
    "robust_hex": "tier_robust_hex",
    "tier_robust_hex": "tier_robust_hex",
    "algohex": "tier_algohex",
    "algo_hex": "tier_algohex",
    "tier_algohex": "tier_algohex",
    "meshpy": "tier_meshpy",
    "classy_blocks": "tier_classy_blocks",
    "wildmesh": "tier_wildmesh",
    "gmsh_hex": "tier_gmsh_hex",
    "cinolib_hex": "tier_cinolib_hex",
    "voro_poly": "tier_voro_poly",
    "voro": "tier_voro_poly",
    "hohqmesh": "tier_hohqmesh",
    "hohq": "tier_hohqmesh",
    # canonical names are also accepted directly
    "tier0_2d_meshpy": "tier0_2d_meshpy",
    "tier0_core": "tier0_core",
    "tier05_netgen": "tier05_netgen",
    "tier1_snappy": "tier1_snappy",
    "tier15_cfmesh": "tier15_cfmesh",
    "tier2_tetwild": "tier2_tetwild",
    "tier_hex_classy_blocks": "tier_hex_classy_blocks",
    "tier_polyhedral": "tier_polyhedral",
    "tier_jigsaw": "tier_jigsaw",
    "tier_jigsaw_fallback": "tier_jigsaw_fallback",
    "tier_meshpy": "tier_meshpy",
    "tier_classy_blocks": "tier_classy_blocks",
    "tier_wildmesh": "tier_wildmesh",
    "tier_gmsh_hex": "tier_gmsh_hex",
    "tier_cinolib_hex": "tier_cinolib_hex",
    "tier_voro_poly": "tier_voro_poly",
    "tier_hohqmesh": "tier_hohqmesh",
}


class TierSelector:
    """입력 특성 기반으로 최적 Tier를 자동 선택한다."""

    def __init__(self) -> None:
        self.last_selection_context: dict[str, object] = {}

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
            self.last_selection_context = {
                "source": "hint_override",
                "hint": tier_hint,
                "canonical_hint": canonical,
                "reason": "cli_tier_override",
                "quality_level": ql,
                "surface_quality_level": sql,
                "selected_tier": canonical,
                "fallback_tiers": list(fallbacks),
            }
            return canonical, fallbacks

        # Check for critical issues that prevent meshing
        from core.schemas import Severity
        critical_issues = [issue for issue in report.issues if issue.severity == Severity.CRITICAL]
        if critical_issues:
            log.warning(
                "critical_issues_detected",
                count=len(critical_issues),
                issues=[f"{i.type}:{i.description}" for i in critical_issues[:2]]
            )
            # Use most robust fallback for critical issues
            fallbacks = [t for t in _TIER_ORDER if t != "tier_jigsaw_fallback"]
            self.last_selection_context = {
                "source": "auto",
                "hint": tier_hint,
                "reason": "critical_input_issues",
                "quality_level": ql,
                "surface_quality_level": sql,
                "selected_tier": "tier_jigsaw_fallback",
                "fallback_tiers": list(fallbacks),
            }
            log.info("tier_auto_selected", tier="tier_jigsaw_fallback", quality_level=ql, fallbacks=fallbacks)
            return "tier_jigsaw_fallback", fallbacks

        # l3_ai 표면 → tetwild 강제
        if sql == SurfaceQualityLevel.L3_AI.value:
            log.info("tier_forced_l3ai", tier="tier2_tetwild")
            fallbacks = [t for t in _TIER_ORDER if t != "tier2_tetwild"]
            self.last_selection_context = {
                "source": "surface_quality_forced",
                "hint": tier_hint,
                "reason": "l3_ai_forces_tetwild",
                "quality_level": ql,
                "surface_quality_level": sql,
                "selected_tier": "tier2_tetwild",
                "fallback_tiers": list(fallbacks),
            }
            return "tier2_tetwild", fallbacks

        selected, reason = self._auto_select(report, ql)
        # fallback: 선택된 tier를 제외한 모든 tier를 우선순위대로 정렬
        # (이렇게 하면 _QUALITY_FALLBACKS의 불일치 문제 해결)
        fallbacks = [t for t in _TIER_ORDER if t != selected]
        self.last_selection_context = {
            "source": "auto",
            "hint": tier_hint,
            "reason": reason,
            "quality_level": ql,
            "surface_quality_level": sql,
            "selected_tier": selected,
            "fallback_tiers": list(fallbacks),
        }
        log.info("tier_auto_selected", tier=selected, quality_level=ql, fallbacks=fallbacks)
        return selected, fallbacks

    # ------------------------------------------------------------------
    # 내부 결정 트리
    # ------------------------------------------------------------------

    def _auto_select(self, report: GeometryReport, quality_level: str) -> tuple[str, str]:
        is_cad = report.file_info.is_cad_brep
        flow_type = report.flow_estimation.type
        is_watertight = report.geometry.surface.is_watertight
        is_manifold = report.geometry.surface.is_manifold
        has_degenerate = report.geometry.surface.has_degenerate_faces

        # ── 2D 감지 (모든 quality level)
        # ComplexityAnalyzer의 추가 2D 감지 로직과 OR-결합하여 감지 범위 확장
        from core.strategist.complexity_analyzer import ComplexityAnalyzer
        is_2d_classic = self._is_2d(report)
        is_2d_complexity = ComplexityAnalyzer.is_likely_2d_shape(report)
        if is_2d_classic or is_2d_complexity:
            log.debug("tier_decision", reason="2d_geometry_detected", tier="tier0_2d_meshpy",
                      classic_check=is_2d_classic, complexity_check=is_2d_complexity)
            return "tier0_2d_meshpy", "2d_geometry_detected"

        # ── Thin-wall 조기 감지 (극도 얇은 형상)
        # aspect ratio > 100 또는 극도로 작은 차원 → 2D 메쉬 기술 사용
        is_thin_wall = self._is_thin_wall(report)
        if is_thin_wall:
            log.debug("tier_decision", reason="thin_wall_detected", tier="tier0_2d_meshpy",
                      note="extreme aspect ratio — 2D 메쉬 기술 권장")
            return "tier0_2d_meshpy", "thin_wall_detected"

        # ── Open boundary 감지 (모든 quality level)
        # Open boundary는 전처리 강화 필요 → TetWild 우선 (L2/L3 후처리 안정성)
        if not is_watertight and not is_cad:
            log.debug(
                "tier_decision",
                reason="open_boundary_detected",
                tier="tier2_tetwild",
                note="L2/L3 전처리 권장",
            )
            return "tier2_tetwild", "open_boundary_detected"

        # ── draft ─────────────────────────────────────────────────────
        if quality_level == QualityLevel.DRAFT.value:
            log.debug("tier_decision", reason="draft_quality", tier="tier2_tetwild")
            return "tier2_tetwild", "draft_quality"

        # ── fine ──────────────────────────────────────────────────────
        if quality_level == QualityLevel.FINE.value:
            # B-Rep → Netgen (can process B-Rep directly)
            if is_cad:
                log.debug("tier_decision", reason="fine_cad_brep", tier="tier05_netgen")
                return "tier05_netgen", "fine_cad_brep"
            # 외부 유동 + watertight → snappyHexMesh (BL 자동)
            if flow_type == "external" and is_watertight:
                log.debug("tier_decision", reason="fine_external_watertight", tier="tier1_snappy")
                return "tier1_snappy", "fine_external_watertight"
            # 내부 유동 → cfMesh
            if is_watertight:
                log.debug("tier_decision", reason="fine_internal_watertight", tier="tier15_cfmesh")
                return "tier15_cfmesh", "fine_internal_watertight"
            # 불량 표면 → tetwild
            log.debug("tier_decision", reason="fine_bad_surface", tier="tier2_tetwild")
            return "tier2_tetwild", "fine_bad_surface"

        # ── standard (default) ────────────────────────────────────────
        # 1. CAD B-Rep (STEP/IGES/BREP) → Netgen
        if is_cad:
            log.debug("tier_decision", reason="cad_brep", tier="tier05_netgen")
            return "tier05_netgen", "cad_brep"

        # 2. 외부 유동 + watertight → snappyHexMesh
        if flow_type == "external" and is_watertight:
            log.debug("tier_decision", reason="external_watertight", tier="tier1_snappy")
            return "tier1_snappy", "external_watertight"

        # 3. 내부 유동 + watertight → cfMesh
        if flow_type == "internal" and is_watertight:
            log.debug("tier_decision", reason="internal_watertight", tier="tier15_cfmesh")
            return "tier15_cfmesh", "internal_watertight"

        # 4. watertight + 단순 형상 → Tier 0 core
        if is_watertight and self._is_simple(report):
            log.debug("tier_decision", reason="watertight_simple", tier="tier0_core")
            return "tier0_core", "watertight_simple"

        # 5. 불량 표면 / non-manifold → TetWild
        if not is_manifold or has_degenerate:
            log.debug("tier_decision", reason="bad_surface", tier="tier2_tetwild")
            return "tier2_tetwild", "bad_surface"

        # default fallback
        log.debug("tier_decision", reason="default", tier="tier2_tetwild")
        return "tier2_tetwild", "default"

    @staticmethod
    def _is_2d(report: GeometryReport) -> bool:
        """2D 기하학 판별: 한 축의 좌표 분산이 대각선의 2% 이하, 또는 높은 aspect ratio."""
        bounds = report.geometry.bounding_box
        if bounds is None:
            return False

        x_min, y_min, z_min = bounds.min
        x_max, y_max, z_max = bounds.max

        dx = x_max - x_min
        dy = y_max - y_min
        dz = z_max - z_min

        # 대각선 길이
        diagonal = bounds.diagonal

        # 방법 1: 한 축의 범위가 대각선의 2% 미만 → 2D (완화된 임계값)
        threshold_strict = 0.01 * diagonal
        threshold_loose = 0.02 * diagonal
        is_2d_strict = min(dx, dy, dz) < threshold_strict
        is_2d_loose = min(dx, dy, dz) < threshold_loose

        # 방법 2: 항공형/칼날 같은 높은 aspect ratio 형상 감지
        # (예: naca0012, blade) — 두 축은 크고 한 축은 매우 작음
        sorted_dims = sorted([dx, dy, dz])
        min_dim = sorted_dims[0]
        max_dim = sorted_dims[2]
        aspect_ratio = max_dim / max(min_dim, 1e-10)

        # aspect ratio > 100이고 min_dim이 대각선의 2% 미만이면 2D
        is_2d_aspect = (aspect_ratio > 100) and (min_dim < threshold_loose)

        is_2d = is_2d_strict or is_2d_aspect

        if is_2d:
            log.debug(
                "is_2d_detected",
                method="strict" if is_2d_strict else "aspect_ratio",
                threshold=threshold_strict,
                dx=dx,
                dy=dy,
                dz=dz,
                aspect_ratio=aspect_ratio if is_2d_aspect else None,
            )

        return is_2d

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

    @staticmethod
    def _is_thin_wall(report: GeometryReport) -> bool:
        """극도 얇은 형상 판별: aspect ratio > 100 또는 한 차원이 매우 작음."""
        bounds = report.geometry.bounding_box
        if bounds is None:
            return False

        dx = bounds.max[0] - bounds.min[0]
        dy = bounds.max[1] - bounds.min[1]
        dz = bounds.max[2] - bounds.min[2]

        # aspect ratio 계산
        dims = sorted([dx, dy, dz])
        min_dim = dims[0]
        max_dim = dims[2]
        aspect_ratio = max_dim / max(min_dim, 1e-10)

        # 극도 얇은 형상 판정: aspect_ratio > 100
        is_thin_wall = aspect_ratio > 100

        if is_thin_wall:
            log.debug(
                "thin_wall_detected",
                aspect_ratio=aspect_ratio,
                min_dim=min_dim,
                max_dim=max_dim,
                dims=(dx, dy, dz),
            )

        return is_thin_wall
