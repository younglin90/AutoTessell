"""beta45 — ParamOptimizer dedicated 회귀.

core/strategist/param_optimizer.ParamOptimizer 의 compute_domain /
compute_cell_sizes / compute_quality_targets / _base_cell_size / _estimate_reynolds
단위 격리. GeometryReport duck-type stub.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.schemas import QualityLevel, QualityTargets
from core.strategist.param_optimizer import ParamOptimizer


def _make_report(
    *,
    char_length: float = 1.0,
    bbox_min: tuple = (0, 0, 0),
    bbox_max: tuple = (1, 1, 1),
    edge_ratio: float = 1.0,
    genus: int = 0,
    is_watertight: bool = True,
    num_faces: int = 100,
    num_components: int = 1,
):
    """GeometryReport duck-type stub for ParamOptimizer."""
    return SimpleNamespace(
        geometry=SimpleNamespace(
            bounding_box=SimpleNamespace(
                min=list(bbox_min),
                max=list(bbox_max),
                center=[(a + b) / 2 for a, b in zip(bbox_min, bbox_max)],
                characteristic_length=char_length,
            ),
            surface=SimpleNamespace(
                edge_length_ratio=edge_ratio,
                genus=genus,
                is_watertight=is_watertight,
                is_manifold=True,
                num_faces=num_faces,
                num_connected_components=num_components,
                has_degenerate_faces=False,
                num_degenerate_faces=0,
                min_face_area=0.01,
                max_face_area=1.0,
                surface_area=6.0,
                num_vertices=num_faces // 2,
                min_edge_length=0.1,
                max_edge_length=1.0,
                face_area_std=0.01,
                euler_number=2,
            ),
            features=SimpleNamespace(
                num_sharp_edges=0,
                has_thin_walls=False,
                has_sharp_edges=False,
                has_small_features=False,
                min_wall_thickness_estimate=1.0,
                smallest_feature_size=0.1,
                feature_to_bbox_ratio=0.1,
                curvature_max=0.0,
                curvature_mean=0.0,
            ),
        ),
        issues=[],
    )


# ---------------------------------------------------------------------------
# _base_cell_size + _estimate_reynolds (static methods)
# ---------------------------------------------------------------------------


def test_base_cell_size_scales_with_L() -> None:
    """_base_cell_size 는 L 에 비례."""
    cs1 = ParamOptimizer._base_cell_size(1.0, "standard")
    cs10 = ParamOptimizer._base_cell_size(10.0, "standard")
    assert cs10 == pytest.approx(cs1 * 10.0)


def test_base_cell_size_draft_larger_than_fine() -> None:
    """draft (coarse) > standard > fine (fine-grained) → cell size 단조 감소."""
    cs_draft = ParamOptimizer._base_cell_size(1.0, "draft")
    cs_std = ParamOptimizer._base_cell_size(1.0, "standard")
    cs_fine = ParamOptimizer._base_cell_size(1.0, "fine")
    assert cs_draft > cs_std > cs_fine


def test_estimate_reynolds_basic() -> None:
    """Re = v*L/nu 공식."""
    Re = ParamOptimizer._estimate_reynolds(L=1.0, velocity=1.0, nu=1.5e-5)
    assert Re == pytest.approx(1.0 / 1.5e-5)


def test_estimate_reynolds_clamped_to_one() -> None:
    """Re 하한 1.0."""
    Re = ParamOptimizer._estimate_reynolds(L=1e-20, velocity=1e-20, nu=1.0)
    assert Re == 1.0


def test_estimate_reynolds_scales_with_velocity() -> None:
    Re1 = ParamOptimizer._estimate_reynolds(L=1.0, velocity=1.0)
    Re10 = ParamOptimizer._estimate_reynolds(L=1.0, velocity=10.0)
    assert Re10 == pytest.approx(Re1 * 10.0)


# ---------------------------------------------------------------------------
# compute_domain
# ---------------------------------------------------------------------------


def test_compute_domain_external_fine_larger_than_draft() -> None:
    """fine quality 는 draft 대비 도메인 훨씬 큼."""
    opt = ParamOptimizer()
    r = _make_report(char_length=1.0, bbox_min=(0, 0, 0), bbox_max=(1, 1, 1))
    d_draft = opt.compute_domain(r, flow_type="external", quality_level="draft")
    d_fine = opt.compute_domain(r, flow_type="external", quality_level="fine")
    # fine domain x-extent > draft
    fine_x = d_fine.max[0] - d_fine.min[0]
    draft_x = d_draft.max[0] - d_draft.min[0]
    assert fine_x > draft_x


def test_compute_domain_internal_uses_bbox_with_margin() -> None:
    """internal flow → bbox 근접."""
    opt = ParamOptimizer()
    r = _make_report(char_length=1.0, bbox_min=(0, 0, 0), bbox_max=(2, 2, 2))
    d = opt.compute_domain(r, flow_type="internal", quality_level="standard")
    # internal 은 margin L*0.1 만 추가
    assert d.max[0] - d.min[0] < 3.0  # bbox 2 + margins 0.4


def test_compute_domain_upstream_override() -> None:
    """upstream 인자 override 반영."""
    opt = ParamOptimizer()
    r = _make_report(char_length=1.0)
    d = opt.compute_domain(
        r, flow_type="external", upstream=20.0, quality_level="standard",
    )
    # upstream=20L → domain_min[0] = bbox.min[0] - 20
    assert d.min[0] == -20.0


def test_compute_domain_location_in_mesh_placement() -> None:
    """external: location 이 upstream 입구 근처."""
    opt = ParamOptimizer()
    r = _make_report(char_length=1.0, bbox_min=(0, 0, 0), bbox_max=(1, 1, 1))
    d = opt.compute_domain(r, flow_type="external", quality_level="draft")
    # location[0] 이 domain_min[0] + L/2 (upstream 근처)
    assert d.location_in_mesh[0] == d.min[0] + 0.5


def test_compute_domain_internal_location_at_bbox_center() -> None:
    """internal: location 이 bbox 중심."""
    opt = ParamOptimizer()
    r = _make_report(char_length=1.0, bbox_min=(0, 0, 0), bbox_max=(2, 2, 2))
    d = opt.compute_domain(r, flow_type="internal", quality_level="standard")
    assert d.location_in_mesh == [1.0, 1.0, 1.0]


def test_compute_domain_scale_applied() -> None:
    """domain_scale > 1 → 도메인 확대."""
    opt = ParamOptimizer()
    r = _make_report(char_length=1.0)
    d1 = opt.compute_domain(r, flow_type="external", quality_level="draft", domain_scale=1.0)
    d2 = opt.compute_domain(r, flow_type="external", quality_level="draft", domain_scale=2.0)
    assert (d2.max[0] - d2.min[0]) > (d1.max[0] - d1.min[0])


# ---------------------------------------------------------------------------
# compute_cell_sizes
# ---------------------------------------------------------------------------


def test_compute_cell_sizes_returns_base_surface_min() -> None:
    """compute_cell_sizes 가 base/surface/min 세 크기 반환."""
    opt = ParamOptimizer()
    r = _make_report(char_length=1.0)
    cs = opt.compute_cell_sizes(r, quality_level="standard")
    assert "base_cell_size" in cs
    assert "surface_cell_size" in cs
    assert "min_cell_size" in cs
    # 관계: base >= surface >= min
    assert cs["base_cell_size"] >= cs["surface_cell_size"]
    assert cs["surface_cell_size"] >= cs["min_cell_size"]


def test_compute_cell_sizes_fine_smaller_than_draft() -> None:
    """fine quality → cell 크기 감소."""
    opt = ParamOptimizer()
    r = _make_report(char_length=1.0)
    cs_draft = opt.compute_cell_sizes(r, quality_level="draft")
    cs_fine = opt.compute_cell_sizes(r, quality_level="fine")
    assert cs_fine["base_cell_size"] < cs_draft["base_cell_size"]
    assert cs_fine["surface_cell_size"] < cs_draft["surface_cell_size"]


# ---------------------------------------------------------------------------
# compute_quality_targets
# ---------------------------------------------------------------------------


def test_compute_quality_targets_returns_pydantic_model() -> None:
    opt = ParamOptimizer()
    qt = opt.compute_quality_targets(quality_level="standard")
    assert isinstance(qt, QualityTargets)
    assert qt.max_non_orthogonality > 0
    assert qt.max_skewness > 0


def test_compute_quality_targets_fine_has_y_plus() -> None:
    """fine quality → target_y_plus=1.0 설정."""
    opt = ParamOptimizer()
    qt_fine = opt.compute_quality_targets(quality_level="fine")
    qt_draft = opt.compute_quality_targets(quality_level="draft")
    assert qt_fine.target_y_plus == 1.0
    assert qt_draft.target_y_plus is None


def test_compute_quality_targets_enum_accepted() -> None:
    """QualityLevel enum 직접 수용."""
    opt = ParamOptimizer()
    qt = opt.compute_quality_targets(quality_level=QualityLevel.FINE)
    assert qt.target_y_plus == 1.0
