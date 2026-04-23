"""beta44 — ComplexityAnalyzer dedicated 회귀.

core/strategist/complexity_analyzer.py 의 analyze / classify / 파라미터 빌더
단위 회귀. GeometryReport duck-type stub 으로 독립 테스트.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from core.strategist.complexity_analyzer import (
    ComplexityAnalyzer,
    ComplexityScore,
)


def _make_report(
    *,
    edge_ratio: float = 1.0,
    genus: int = 0,
    bbox_min: tuple = (0, 0, 0),
    bbox_max: tuple = (1, 1, 1),
    char_length: float = 1.0,
    n_critical: int = 0,
    n_major: int = 0,
    n_sharp: int = 0,
):
    """GeometryReport duck-type stub."""
    issues = []
    for _ in range(n_critical):
        issues.append(SimpleNamespace(severity="critical"))
    for _ in range(n_major):
        issues.append(SimpleNamespace(severity="major"))
    return SimpleNamespace(
        geometry=SimpleNamespace(
            bounding_box=SimpleNamespace(
                min=list(bbox_min),
                max=list(bbox_max),
                characteristic_length=char_length,
            ),
            surface=SimpleNamespace(
                edge_length_ratio=edge_ratio,
                genus=genus,
            ),
            features=SimpleNamespace(
                num_sharp_edges=n_sharp,
            ),
        ),
        issues=issues,
    )


# ---------------------------------------------------------------------------
# ComplexityScore dataclass
# ---------------------------------------------------------------------------


def test_complexity_score_repr_contains_all_fields() -> None:
    """__str__ 이 overall/features/topology/aspect/surface/variation 모두 포함."""
    s = ComplexityScore(
        overall=45.2, feature_density=50.1, topology=10.3,
        aspect_ratio=20.5, surface_quality=80.0, size_variation=30.7,
    )
    out = str(s)
    assert "overall=" in out
    assert "features=" in out
    assert "topology=" in out
    assert "aspect=" in out
    assert "surface=" in out
    assert "variation=" in out


# ---------------------------------------------------------------------------
# analyze - feature_density
# ---------------------------------------------------------------------------


def test_analyze_simple_shape_low_complexity() -> None:
    """edge_ratio=1, genus=0, cube bbox → overall 낮음 (simple)."""
    report = _make_report(edge_ratio=1.0, genus=0)
    score = ComplexityAnalyzer.analyze(report)
    assert 0.0 <= score.overall <= 100.0
    assert score.feature_density < 10
    assert score.topology == 0.0
    assert ComplexityAnalyzer.classify(score) == "simple"


def test_analyze_high_edge_ratio_raises_feature_density() -> None:
    """edge_ratio=500 → feature_density >= 80."""
    report = _make_report(edge_ratio=500.0)
    score = ComplexityAnalyzer.analyze(report)
    assert score.feature_density >= 80.0


def test_analyze_extreme_edge_ratio_saturates() -> None:
    """edge_ratio > 1000 → feature_density == 100."""
    report = _make_report(edge_ratio=5000.0)
    score = ComplexityAnalyzer.analyze(report)
    assert score.feature_density == 100.0


# ---------------------------------------------------------------------------
# analyze - topology (genus)
# ---------------------------------------------------------------------------


def test_analyze_topology_scales_with_genus() -> None:
    s0 = ComplexityAnalyzer.analyze(_make_report(genus=0))
    s2 = ComplexityAnalyzer.analyze(_make_report(genus=2))
    s10 = ComplexityAnalyzer.analyze(_make_report(genus=10))
    assert s0.topology < s2.topology < s10.topology


def test_analyze_topology_saturates_at_high_genus() -> None:
    """genus >= 7 → topology == 100 (15 * 7 = 105 > 100, cap)."""
    report = _make_report(genus=10)
    score = ComplexityAnalyzer.analyze(report)
    assert score.topology == 100.0


# ---------------------------------------------------------------------------
# analyze - aspect ratio
# ---------------------------------------------------------------------------


def test_analyze_cube_aspect_ratio_low() -> None:
    """동일 bbox dims → aspect_ratio 0."""
    report = _make_report(bbox_min=(0, 0, 0), bbox_max=(1, 1, 1))
    score = ComplexityAnalyzer.analyze(report)
    assert score.aspect_ratio < 1.0


def test_analyze_elongated_shape_high_aspect() -> None:
    """bbox 극단 aspect (1:1:100) → aspect_ratio >= 50."""
    report = _make_report(bbox_min=(0, 0, 0), bbox_max=(1, 1, 100))
    score = ComplexityAnalyzer.analyze(report)
    assert score.aspect_ratio >= 50.0


def test_analyze_extreme_aspect_saturates() -> None:
    """aspect 1000 → saturate to 100."""
    report = _make_report(bbox_min=(0, 0, 0), bbox_max=(1, 1, 1000))
    score = ComplexityAnalyzer.analyze(report)
    assert score.aspect_ratio == 100.0


# ---------------------------------------------------------------------------
# analyze - surface quality
# ---------------------------------------------------------------------------


def test_analyze_no_issues_good_quality() -> None:
    """issues=0 → surface_quality >= 90."""
    report = _make_report(n_critical=0, n_major=0)
    score = ComplexityAnalyzer.analyze(report)
    assert score.surface_quality == 90.0


def test_analyze_many_critical_issues_low_quality() -> None:
    """critical >= 5 → surface_quality = 10."""
    report = _make_report(n_critical=5)
    score = ComplexityAnalyzer.analyze(report)
    assert score.surface_quality == 10.0


def test_analyze_some_major_issues_mid_quality() -> None:
    """major 3 → surface_quality 70 (some 존재)."""
    report = _make_report(n_major=3)
    score = ComplexityAnalyzer.analyze(report)
    assert score.surface_quality == 70.0


# ---------------------------------------------------------------------------
# classify
# ---------------------------------------------------------------------------


def test_classify_simple() -> None:
    s = ComplexityScore(overall=10, feature_density=0, topology=0,
                        aspect_ratio=0, surface_quality=90, size_variation=0)
    assert ComplexityAnalyzer.classify(s) == "simple"


def test_classify_moderate() -> None:
    s = ComplexityScore(overall=45, feature_density=0, topology=0,
                        aspect_ratio=0, surface_quality=90, size_variation=0)
    assert ComplexityAnalyzer.classify(s) == "moderate"


def test_classify_complex() -> None:
    s = ComplexityScore(overall=70, feature_density=0, topology=0,
                        aspect_ratio=0, surface_quality=90, size_variation=0)
    assert ComplexityAnalyzer.classify(s) == "complex"


def test_classify_extreme() -> None:
    s = ComplexityScore(overall=90, feature_density=0, topology=0,
                        aspect_ratio=0, surface_quality=90, size_variation=0)
    assert ComplexityAnalyzer.classify(s) == "extreme"


# ---------------------------------------------------------------------------
# overall bounded [0, 100]
# ---------------------------------------------------------------------------


def test_analyze_overall_always_bounded() -> None:
    """극단적 입력에도 overall ∈ [0, 100]."""
    extreme = _make_report(
        edge_ratio=10000, genus=100, bbox_max=(1, 1, 10000),
        n_critical=100, n_major=100,
    )
    score = ComplexityAnalyzer.analyze(extreme)
    assert 0.0 <= score.overall <= 100.0


def test_analyze_very_simple_shape_low_overall() -> None:
    """완전 simple → overall < 30."""
    report = _make_report(
        edge_ratio=1.5, genus=0, bbox_min=(0, 0, 0), bbox_max=(1, 1, 1),
    )
    score = ComplexityAnalyzer.analyze(report)
    assert score.overall < 30
