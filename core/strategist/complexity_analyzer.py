"""형상 복잡도 분석기 — 기하학적 특성을 점수화하여 메싱 파라미터 최적화."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from core.utils.logging import get_logger

if TYPE_CHECKING:
    from core.schemas import GeometryReport

log = get_logger(__name__)


@dataclass
class ComplexityScore:
    """형상 복잡도 점수."""

    overall: float  # 0-100, 높을수록 복잡함
    feature_density: float  # 특징선 밀집도 (0-100)
    topology: float  # 위상 복잡도 (0-100, genus 기반)
    aspect_ratio: float  # 종횡비 극단성 (0-100)
    surface_quality: float  # 표면 품질 (0-100, 낮을수록 나쁨)
    size_variation: float  # 셀 크기 변화 (0-100)

    def __str__(self) -> str:
        return (
            f"Complexity(overall={self.overall:.1f}, "
            f"features={self.feature_density:.1f}, "
            f"topology={self.topology:.1f}, "
            f"aspect={self.aspect_ratio:.1f}, "
            f"surface={self.surface_quality:.1f}, "
            f"variation={self.size_variation:.1f})"
        )


class ComplexityAnalyzer:
    """GeometryReport를 기반으로 형상 복잡도를 분석한다.

    복잡도 점수를 바탕으로 snappyHexMesh, Netgen 등의 파라미터를 동적으로 조정한다.
    """

    # 복잡도 경계값
    THRESHOLD_SIMPLE = 30  # 0-30: 단순
    THRESHOLD_MODERATE = 60  # 30-60: 중간
    THRESHOLD_COMPLEX = 80  # 60-80: 복잡
    # 80+: 극도로 복잡

    @staticmethod
    def analyze(report: GeometryReport) -> ComplexityScore:
        """기하학 보고서를 기반으로 복잡도를 분석한다.

        Args:
            report: GeometryReport 객체.

        Returns:
            ComplexityScore 객체.
        """
        bbox = report.geometry.bounding_box
        surface = report.geometry.surface
        features = report.geometry.features
        issues = report.issues

        L = bbox.characteristic_length

        # 1. 특징선 밀집도 (edge_length_ratio 기반)
        #    비율이 높을수록 특징선이 많음
        edge_ratio = surface.edge_length_ratio or 1.0
        if edge_ratio > 1000:
            feature_density = 100.0
        elif edge_ratio > 100:
            feature_density = 80.0 + (min(edge_ratio, 1000) - 100) / 900 * 20
        else:
            feature_density = max(0.0, (edge_ratio - 1) / 99 * 80)

        # 2. 위상 복잡도 (genus 기반)
        #    genus가 높을수록 고리가 많음
        genus = surface.genus or 0
        topology = min(100.0, genus * 15)  # 각 genus마다 15점 추가

        # 3. 종횡비 극단성
        #    bbox의 종횡비가 높을수록 극단적
        bbox_size = bbox.max[:]  # Copy list
        bbox_size_sorted = sorted(bbox_size)
        aspect_min_max = bbox_size_sorted[2] / max(bbox_size_sorted[0], 1e-10)
        if aspect_min_max > 100:
            aspect_ratio = 100.0
        elif aspect_min_max > 10:
            aspect_ratio = 50.0 + (min(aspect_min_max, 100) - 10) / 90 * 50
        else:
            aspect_ratio = max(0.0, (aspect_min_max - 1) / 9 * 50)

        # 4. 표면 품질 점수 (낮을수록 나쁨, 결함이 많음)
        #    critical issues의 개수로 판단
        critical_issues = sum(1 for issue in issues if issue.severity == "critical")
        major_issues = sum(1 for issue in issues if issue.severity == "major")

        # 문제가 많을수록 품질이 낮음
        if critical_issues >= 5:
            surface_quality = 10.0
        elif critical_issues >= 2 or major_issues >= 10:
            surface_quality = 30.0
        elif major_issues >= 5:
            surface_quality = 50.0
        elif major_issues > 0:
            surface_quality = 70.0
        else:
            surface_quality = 90.0

        # 5. 셀 크기 변화 (edge_length_ratio)
        #    비율이 높을수록 셀 크기 변화가 큼
        if edge_ratio > 200:
            size_variation = 90.0
        elif edge_ratio > 50:
            size_variation = 60.0 + (min(edge_ratio, 200) - 50) / 150 * 30
        else:
            size_variation = max(0.0, (edge_ratio - 1) / 49 * 60)

        # 6. 전체 복잡도 점수 (가중 평균)
        # surface_quality를 역으로 변환: 품질이 나쁠수록 복잡도가 높음
        surface_quality_complexity = 100.0 - surface_quality
        overall = (
            feature_density * 0.25 +  # 특징선이 가장 중요
            topology * 0.20 +          # 위상도 중요
            aspect_ratio * 0.20 +      # 종횡비도 중요
            surface_quality_complexity * 0.20 +  # 품질이 나쁠수록 복잡함
            size_variation * 0.15      # 셀 크기 변화
        )
        overall = max(0.0, min(100.0, overall))

        log.info(
            "geometry_complexity_analyzed",
            overall=f"{overall:.1f}",
            features=f"{feature_density:.1f}",
            topology=f"{topology:.1f}",
            aspect=f"{aspect_ratio:.1f}",
            surface=f"{surface_quality:.1f}",
            variation=f"{size_variation:.1f}",
        )

        return ComplexityScore(
            overall=overall,
            feature_density=feature_density,
            topology=topology,
            aspect_ratio=aspect_ratio,
            surface_quality=surface_quality,
            size_variation=size_variation,
        )

    @staticmethod
    def classify(score: ComplexityScore) -> str:
        """복잡도 점수를 분류한다.

        Args:
            score: ComplexityScore 객체.

        Returns:
            분류 ('simple', 'moderate', 'complex', 'extreme').
        """
        if score.overall < ComplexityAnalyzer.THRESHOLD_SIMPLE:
            return "simple"
        elif score.overall < ComplexityAnalyzer.THRESHOLD_MODERATE:
            return "moderate"
        elif score.overall < ComplexityAnalyzer.THRESHOLD_COMPLEX:
            return "complex"
        else:
            return "extreme"

    @staticmethod
    def get_snappy_tuning_params(score: ComplexityScore) -> dict[str, int | float | bool]:
        """복잡도 점수에 따라 snappyHexMesh 파라미터를 반환한다.

        Args:
            score: ComplexityScore 객체.

        Returns:
            snappyHexMeshDict 파라미터 사전.
        """
        classification = ComplexityAnalyzer.classify(score)

        if classification == "simple":
            # 단순 형상: 세밀한 refinement, 깨끗한 메싱
            return {
                "maxLocalCells": 2_000_000,
                "maxGlobalCells": 10_000_000,
                "nCellsBetweenLevels": 3,
                "maxRefinementCells": 1_000_000,
                "snapSmoothPatch": 3,
                "nSolveIter": 30,
                "nRelaxIter": 5,
                "featureSnapIter": 10,
                "castellatedLevel": [2, 3],
            }
        elif classification == "moderate":
            # 중간 복잡도: 균형잡힌 파라미터
            return {
                "maxLocalCells": 1_000_000,
                "maxGlobalCells": 5_000_000,
                "nCellsBetweenLevels": 3,
                "maxRefinementCells": 500_000,
                "snapSmoothPatch": 3,
                "nSolveIter": 20,
                "nRelaxIter": 3,
                "featureSnapIter": 5,
                "castellatedLevel": [1, 2],
            }
        elif classification == "complex":
            # 복잡 형상: 빠른 메싱, 제한된 refinement
            return {
                "maxLocalCells": 500_000,
                "maxGlobalCells": 2_000_000,
                "nCellsBetweenLevels": 4,
                "maxRefinementCells": 200_000,
                "snapSmoothPatch": 1,
                "nSolveIter": 10,
                "nRelaxIter": 1,
                "featureSnapIter": 3,
                "castellatedLevel": [1, 1],
            }
        else:  # extreme
            # 극도로 복잡: 빠른 완성, 최소 refinement
            return {
                "maxLocalCells": 100_000,
                "maxGlobalCells": 1_000_000,
                "nCellsBetweenLevels": 5,
                "maxRefinementCells": 100_000,
                "snapSmoothPatch": 0,
                "nSolveIter": 5,
                "nRelaxIter": 0,
                "featureSnapIter": 1,
                "castellatedLevel": [0, 1],
            }

    @staticmethod
    def get_netgen_tuning_params(score: ComplexityScore) -> dict[str, float | int]:
        """복잡도 점수에 따라 Netgen 파라미터를 반환한다.

        Args:
            score: ComplexityScore 객체.

        Returns:
            Netgen 메싱 파라미터 사전.
        """
        classification = ComplexityAnalyzer.classify(score)

        if classification == "simple":
            # 단순 형상: 세밀함
            return {
                "maxh": 1.0,  # 기준
                "minh": 0.05,
                "grading": 0.2,  # 공격적
                "quality": 2.0,  # 최고 품질
            }
        elif classification == "moderate":
            # 중간: 균형
            return {
                "maxh": 1.2,
                "minh": 0.1,
                "grading": 0.3,
                "quality": 1.5,
            }
        elif classification == "complex":
            # 복잡: 빠른 메싱
            return {
                "maxh": 1.5,
                "minh": 0.15,
                "grading": 0.5,
                "quality": 1.0,
            }
        else:  # extreme
            # 극도로 복잡: 매우 빠름
            return {
                "maxh": 2.0,
                "minh": 0.2,
                "grading": 0.8,
                "quality": 0.5,
            }

    @staticmethod
    def should_skip_layers(score: ComplexityScore) -> bool:
        """경계층을 스킵해야 하는지 판단한다.

        Args:
            score: ComplexityScore 객체.

        Returns:
            True면 경계층 스킵 권장.
        """
        # 복잡도가 높으면 경계층 처리를 스킵하여 속도 향상
        classification = ComplexityAnalyzer.classify(score)
        return classification in ("complex", "extreme")

    @staticmethod
    def should_use_fallback(score: ComplexityScore) -> bool:
        """snappyHexMesh 대신 다른 Tier로 fallback할지 판단한다.

        Args:
            score: ComplexityScore 객체.

        Returns:
            True면 fallback 권장 (TetWild, Netgen 등으로).
        """
        # 극도로 복잡하면 snappyHexMesh 스킵
        return score.overall > 85 or score.topology > 80

    @staticmethod
    def get_estimated_time(score: ComplexityScore, quality_level: str) -> float:
        """예상 메싱 시간을 추정한다.

        Args:
            score: ComplexityScore 객체.
            quality_level: 품질 레벨 ('draft', 'standard', 'fine').

        Returns:
            예상 시간 (초).
        """
        classification = ComplexityAnalyzer.classify(score)

        base_times = {
            "draft": {"simple": 5, "moderate": 10, "complex": 20, "extreme": 60},
            "standard": {"simple": 15, "moderate": 30, "complex": 60, "extreme": 180},
            "fine": {"simple": 60, "moderate": 180, "complex": 300, "extreme": 600},
        }

        return float(base_times.get(quality_level, {}).get(classification, 30))
