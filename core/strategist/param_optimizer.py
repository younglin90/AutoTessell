"""셀 크기, 도메인, Boundary Layer 파라미터 자동 결정."""

from __future__ import annotations


from core.schemas import (
    BoundaryLayerConfig,
    DomainConfig,
    GeometryReport,
    QualityLevel,
    QualityTargets,
)
from core.utils.logging import get_logger

log = get_logger(__name__)

# 도메인 배율 기본값 (외부 유동) — quality_level별
_DOMAIN_FACTORS: dict[str, tuple[float, float, float]] = {
    # (upstream, downstream, lateral)
    "draft": (3.0, 5.0, 2.0),       # 빠른 검증용, 작은 도메인
    "standard": (5.0, 10.0, 3.0),   # 엔지니어링, 중간 도메인
    "fine": (10.0, 20.0, 5.0),      # 최종 CFD, 표준 도메인
}

# 최대 배경 셀 수 제한 (메모리 보호)
_MAX_BG_CELLS: dict[str, int] = {
    "draft": 500_000,
    "standard": 5_000_000,
    "fine": 50_000_000,
}

# Legacy defaults (backward compatibility)
_UPSTREAM_FACTOR = 5.0
_DOWNSTREAM_FACTOR = 10.0
_LATERAL_FACTOR = 3.0

# BL 기본값
_BL_LAYERS = 5
_BL_GROWTH_RATIO = 1.2
_TARGET_Y_PLUS = 1.0
_FLOW_VELOCITY_ESTIMATE = 1.0  # 무차원 속도

# QualityLevel별 셀 크기 배율
_CELL_SIZE_FACTOR: dict[str, float] = {
    "draft": 4.0,
    "standard": 2.0,
    "fine": 1.0,
}

# QualityLevel별 품질 목표값
_QUALITY_TARGETS: dict[str, dict[str, float]] = {
    "draft": {
        "max_non_orthogonality": 85.0,
        "max_skewness": 8.0,
        "max_aspect_ratio": 500.0,
        "min_determinant": 0.0001,
    },
    "standard": {
        "max_non_orthogonality": 70.0,
        "max_skewness": 6.0,
        "max_aspect_ratio": 200.0,
        "min_determinant": 0.001,
    },
    "fine": {
        "max_non_orthogonality": 65.0,
        "max_skewness": 4.0,
        "max_aspect_ratio": 100.0,
        "min_determinant": 0.001,
    },
}


class ParamOptimizer:
    """지오메트리 보고서 기반 메쉬 파라미터 자동 최적화."""

    # ------------------------------------------------------------------
    # 도메인 설정
    # ------------------------------------------------------------------

    def compute_domain(
        self,
        report: GeometryReport,
        flow_type: str,
        *,
        upstream: float | None = None,
        downstream: float | None = None,
        lateral: float | None = None,
        domain_scale: float = 1.0,
        quality_level: QualityLevel | str = QualityLevel.STANDARD,
    ) -> DomainConfig:
        """외부/내부 유동 도메인 박스를 계산한다.

        quality_level에 따라 도메인 크기가 달라진다:
          draft:    upstream=3L, downstream=5L, lateral=2L
          standard: upstream=5L, downstream=10L, lateral=3L
          fine:     upstream=10L, downstream=20L, lateral=5L

        내부 유동은 지오메트리 BBox 그대로 사용.
        """
        bbox = report.geometry.bounding_box
        L = bbox.characteristic_length

        # Quality level에 따른 도메인 배율
        ql_str = quality_level.value if hasattr(quality_level, "value") else str(quality_level)
        factors = _DOMAIN_FACTORS.get(ql_str, _DOMAIN_FACTORS["standard"])

        if flow_type == "external":
            us = (upstream if upstream is not None else factors[0]) * L * domain_scale
            ds = (downstream if downstream is not None else factors[1]) * L * domain_scale
            lat = (lateral if lateral is not None else factors[2]) * L * domain_scale

            domain_min = [
                bbox.min[0] - us,
                bbox.min[1] - lat,
                bbox.min[2] - lat,
            ]
            domain_max = [
                bbox.max[0] + ds,
                bbox.max[1] + lat,
                bbox.max[2] + lat,
            ]
        else:
            # 내부 유동: BBox에 약간의 여유만 추가
            margin = L * 0.1
            domain_min = [v - margin for v in bbox.min]
            domain_max = [v + margin for v in bbox.max]

        base_cell_size = self._base_cell_size(L, quality_level)

        # location_in_mesh: 업스트림 입구 근처 (외부), 도메인 중심 (내부)
        if flow_type == "external":
            loc = [domain_min[0] + L * 0.5, bbox.center[1], bbox.center[2]]
        else:
            loc = list(bbox.center)

        cfg = DomainConfig(
            type="box",
            min=domain_min,
            max=domain_max,
            base_cell_size=base_cell_size,
            location_in_mesh=loc,
        )
        log.debug("domain_computed", flow_type=flow_type, L=L, domain_min=domain_min, domain_max=domain_max)
        return cfg

    # ------------------------------------------------------------------
    # 셀 크기
    # ------------------------------------------------------------------

    def compute_cell_sizes(
        self,
        report: GeometryReport,
        quality_level: QualityLevel | str = QualityLevel.STANDARD,
    ) -> dict[str, float]:
        """특성 길이 기반 셀 크기를 계산한다.

        QualityLevel에 따라 셀 크기 배율이 달라진다:
          draft=4.0, standard=2.0, fine=1.0

        Returns:
            {
                "base_cell_size": ...,
                "surface_cell_size": ...,
                "min_cell_size": ...,
            }
        """
        L = report.geometry.bounding_box.characteristic_length
        curvature_max = report.geometry.features.curvature_max

        # Normalise quality_level
        ql = quality_level.value if isinstance(quality_level, QualityLevel) else str(quality_level)

        base = self._base_cell_size(L, ql)
        surface = base / 4.0
        min_size = surface / 4.0

        # 고곡률 보정 (fine에만 적용)
        if ql == QualityLevel.FINE.value and curvature_max > 20.0:
            surface *= 0.5
            min_size = surface / 4.0
            log.debug("high_curvature_correction", curvature_max=curvature_max)

        sizes = {
            "base_cell_size": base,
            "surface_cell_size": surface,
            "min_cell_size": min_size,
        }
        log.debug("cell_sizes_computed", quality_level=ql, **sizes)
        return sizes

    # ------------------------------------------------------------------
    # Boundary Layer
    # ------------------------------------------------------------------

    def compute_boundary_layers(
        self,
        report: GeometryReport,
        *,
        quality_level: QualityLevel | str = QualityLevel.STANDARD,
        target_y_plus: float = _TARGET_Y_PLUS,
        num_layers: int = _BL_LAYERS,
        growth_ratio: float = _BL_GROWTH_RATIO,
    ) -> BoundaryLayerConfig:
        """목표 y+ 기반 Boundary Layer 파라미터를 계산한다.

        BL은 fine에서만 자동 활성화된다.
        draft / standard: 비활성화 (enabled=False, layers=0).
        """
        ql = quality_level.value if isinstance(quality_level, QualityLevel) else str(quality_level)

        # draft / standard: BL 비활성화
        if ql != QualityLevel.FINE.value:
            cfg = BoundaryLayerConfig(
                enabled=False,
                num_layers=0,
                first_layer_thickness=0.0,
                growth_ratio=growth_ratio,
                max_total_thickness=0.0,
                min_thickness_ratio=0.1,
                feature_angle=130.0,
            )
            log.debug("bl_disabled", quality_level=ql)
            return cfg

        L = report.geometry.bounding_box.characteristic_length

        # Reynolds 수 추정 (무차원 속도 기준)
        Re = self._estimate_reynolds(L, _FLOW_VELOCITY_ESTIMATE)

        # 첫 번째 레이어 두께
        y_first = L * target_y_plus * (Re ** -0.9) * 6.0

        # 전체 두께
        total = y_first * sum(growth_ratio ** i for i in range(num_layers))

        cfg = BoundaryLayerConfig(
            enabled=True,
            num_layers=num_layers,
            first_layer_thickness=y_first,
            growth_ratio=growth_ratio,
            max_total_thickness=total,
            min_thickness_ratio=0.1,
            feature_angle=130.0,
        )
        log.debug("bl_computed", Re=Re, y_first=y_first, total_thickness=total)
        return cfg

    # ------------------------------------------------------------------
    # 품질 목표값
    # ------------------------------------------------------------------

    def compute_quality_targets(
        self,
        quality_level: QualityLevel | str = QualityLevel.STANDARD,
    ) -> QualityTargets:
        """QualityLevel별 품질 목표값을 반환한다."""
        ql = quality_level.value if isinstance(quality_level, QualityLevel) else str(quality_level)
        targets = _QUALITY_TARGETS.get(ql, _QUALITY_TARGETS["standard"])

        target_y_plus = 1.0 if ql == QualityLevel.FINE.value else None

        qt = QualityTargets(
            max_non_orthogonality=targets["max_non_orthogonality"],
            max_skewness=targets["max_skewness"],
            max_aspect_ratio=targets["max_aspect_ratio"],
            min_determinant=targets["min_determinant"],
            target_y_plus=target_y_plus,
        )
        log.debug("quality_targets_computed", quality_level=ql, **targets)
        return qt

    # ------------------------------------------------------------------
    # 헬퍼
    # ------------------------------------------------------------------

    @staticmethod
    def _base_cell_size(L: float, quality_level: QualityLevel | str = QualityLevel.STANDARD) -> float:
        ql = quality_level.value if isinstance(quality_level, QualityLevel) else str(quality_level)
        factor = _CELL_SIZE_FACTOR.get(ql, 2.0)
        return (L / 50.0) * factor

    @staticmethod
    def _estimate_reynolds(L: float, velocity: float, nu: float = 1.5e-5) -> float:
        """동점성 계수 nu [m²/s] 기준 Reynolds 수 추정 (기본: 공기 15°C)."""
        return max(velocity * L / nu, 1.0)
