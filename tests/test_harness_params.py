"""native tier per-quality harness params 회귀 테스트 (v0.4.0-beta17)."""
from __future__ import annotations

from pathlib import Path

import pytest

from core.generator._tier_native_common import (
    HARNESS_PARAMS,
    get_harness_params,
    run_native_tier,
)
from core.schemas import (
    BoundaryLayerConfig,
    DomainConfig,
    MeshStrategy,
    QualityLevel,
    SurfaceMeshConfig,
    SurfaceQualityLevel,
)


def _mk_strategy(quality: QualityLevel, target_edge: float = 0.1) -> MeshStrategy:
    """테스트용 최소 MeshStrategy."""
    return MeshStrategy(
        quality_level=quality,
        surface_quality_level=SurfaceQualityLevel.L1_REPAIR,
        selected_tier="tier_native_tet",
        flow_type="internal",
        domain=DomainConfig(
            type="box",
            min=[-1.0, -1.0, -1.0],
            max=[1.0, 1.0, 1.0],
            base_cell_size=0.1,
            location_in_mesh=[0.0, 0.0, 0.0],
        ),
        surface_mesh=SurfaceMeshConfig(
            input_file="dummy.stl",
            target_cell_size=target_edge,
            min_cell_size=target_edge * 0.1,
        ),
        boundary_layers=BoundaryLayerConfig(
            enabled=False,
            num_layers=0,
            first_layer_thickness=0.0,
            growth_ratio=1.0,
            max_total_thickness=0.0,
            min_thickness_ratio=0.0,
        ),
    )


def test_harness_params_covers_three_native_tiers() -> None:
    """HARNESS_PARAMS 가 tier_native_{tet,hex,poly} 를 모두 정의."""
    assert "tier_native_tet" in HARNESS_PARAMS
    assert "tier_native_hex" in HARNESS_PARAMS
    assert "tier_native_poly" in HARNESS_PARAMS
    for tier in ("tier_native_tet", "tier_native_hex", "tier_native_poly"):
        table = HARNESS_PARAMS[tier]
        assert "draft" in table
        assert "standard" in table
        assert "fine" in table


@pytest.mark.parametrize(
    "tier",
    ["tier_native_tet", "tier_native_hex", "tier_native_poly"],
)
def test_seed_density_monotone_with_quality(tier: str) -> None:
    """draft ≤ standard ≤ fine 순으로 seed_density 가 단조 증가."""
    draft = get_harness_params(tier, "draft")
    standard = get_harness_params(tier, "standard")
    fine = get_harness_params(tier, "fine")
    assert draft["seed_density"] <= standard["seed_density"] <= fine["seed_density"]


def test_get_harness_params_accepts_enum() -> None:
    """QualityLevel enum 을 직접 전달해도 value 로 매핑."""
    by_str = get_harness_params("tier_native_tet", "fine")
    by_enum = get_harness_params("tier_native_tet", QualityLevel.FINE)
    assert by_str == by_enum


def test_get_harness_params_unknown_quality_falls_back_to_standard() -> None:
    """존재하지 않는 quality 는 standard 로 fallback."""
    unknown = get_harness_params("tier_native_tet", "xxx")
    standard = get_harness_params("tier_native_tet", "standard")
    assert unknown == standard


def test_get_harness_params_unknown_tier_returns_empty() -> None:
    """존재하지 않는 tier 는 빈 dict."""
    assert get_harness_params("tier_does_not_exist", "draft") == {}


def test_run_native_tier_injects_quality_params(tmp_path: Path) -> None:
    """run_native_tier 가 strategy.quality_level 의 HARNESS_PARAMS 를 runner_fn 에
    주입한다."""
    # 최소 STL 생성 (단일 삼각형) — file_reader 가 읽을 수 있을 정도면 됨
    stl_path = tmp_path / "tri.stl"
    stl_path.write_text(
        "solid tri\n"
        "  facet normal 0 0 1\n"
        "    outer loop\n"
        "      vertex 0 0 0\n"
        "      vertex 1 0 0\n"
        "      vertex 0 1 0\n"
        "    endloop\n"
        "  endfacet\n"
        "endsolid\n"
    )

    captured: dict = {}

    def _capture_runner(vertices, faces, case_dir, **kwargs):  # noqa: ANN001
        captured.update(kwargs)

        class _R:
            success = True
            n_cells = 1
            n_points = int(len(vertices))
            n_faces = int(len(faces))
            message = "captured"
        return _R()

    # draft quality 로 호출
    run_native_tier(
        _capture_runner, "tier_native_tet",
        _mk_strategy(QualityLevel.DRAFT), stl_path, tmp_path / "case_d",
    )
    assert captured.get("seed_density") == HARNESS_PARAMS["tier_native_tet"]["draft"]["seed_density"]
    assert captured.get("max_iter") == HARNESS_PARAMS["tier_native_tet"]["draft"]["max_iter"]

    # fine quality 로 호출 → 다른 값이 들어가야 함
    captured.clear()
    run_native_tier(
        _capture_runner, "tier_native_tet",
        _mk_strategy(QualityLevel.FINE), stl_path, tmp_path / "case_f",
    )
    assert captured.get("seed_density") == HARNESS_PARAMS["tier_native_tet"]["fine"]["seed_density"]
    assert captured.get("max_iter") == HARNESS_PARAMS["tier_native_tet"]["fine"]["max_iter"]


def test_run_native_tier_extra_kwargs_overrides_table(tmp_path: Path) -> None:
    """caller 가 extra_kwargs 로 명시한 값은 HARNESS_PARAMS 를 override."""
    stl_path = tmp_path / "tri.stl"
    stl_path.write_text(
        "solid tri\nfacet normal 0 0 1\nouter loop\n"
        "vertex 0 0 0\nvertex 1 0 0\nvertex 0 1 0\n"
        "endloop\nendfacet\nendsolid\n"
    )

    captured: dict = {}

    def _capture(vertices, faces, case_dir, **kwargs):  # noqa: ANN001
        captured.update(kwargs)

        class _R:
            success = True
            n_cells = 1
            n_points = int(len(vertices))
            n_faces = int(len(faces))
            message = "x"
        return _R()

    run_native_tier(
        _capture, "tier_native_hex",
        _mk_strategy(QualityLevel.DRAFT), stl_path, tmp_path / "case",
        extra_kwargs={"seed_density": 99},
    )
    assert captured["seed_density"] == 99  # override 성공
