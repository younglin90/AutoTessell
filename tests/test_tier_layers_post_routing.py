"""beta34 — LayersPostGenerator auto-engine 라우팅 회귀 테스트.

engine="auto" + mesh_type 조합에 따라 올바른 BL 엔진이 선택되는지 (tet →
tet_bl_subdivide, hex_dominant → native_bl, poly → poly_bl_transition) 검증.

실제 엔진 실행은 비용이 커서 logic 만 검증 — monkeypatch 로 각 runner 를
capture.
"""
from __future__ import annotations

from pathlib import Path

import pytest


def _make_strategy(mesh_type: str, engine: str = "auto"):
    """테스트용 최소 MeshStrategy."""
    from core.schemas import (
        BoundaryLayerConfig, DomainConfig, MeshStrategy, MeshType,
        QualityLevel, SurfaceMeshConfig, SurfaceQualityLevel,
    )

    return MeshStrategy(
        quality_level=QualityLevel.FINE,
        mesh_type=MeshType(mesh_type) if mesh_type != "auto" else MeshType.AUTO,
        surface_quality_level=SurfaceQualityLevel.L1_REPAIR,
        selected_tier=f"tier_native_{mesh_type}" if mesh_type in ("tet", "hex", "poly")
                      else "tier_native_tet",
        flow_type="internal",
        domain=DomainConfig(
            type="box", min=[-1.0] * 3, max=[1.0] * 3,
            base_cell_size=0.1, location_in_mesh=[0.0] * 3,
        ),
        surface_mesh=SurfaceMeshConfig(
            input_file="dummy.stl", target_cell_size=0.1, min_cell_size=0.01,
        ),
        boundary_layers=BoundaryLayerConfig(
            enabled=True, num_layers=3, first_layer_thickness=0.001,
            growth_ratio=1.2, max_total_thickness=0.01, min_thickness_ratio=0.1,
        ),
        tier_specific_params={"post_layers_engine": engine},
    )


def _make_case_with_polymesh(tmp_path: Path) -> Path:
    """최소 polyMesh (faces 파일만) — run() 이 존재 검사만 하므로 충분."""
    poly_dir = tmp_path / "constant" / "polyMesh"
    poly_dir.mkdir(parents=True)
    (poly_dir / "faces").write_text("0\n(\n)\n")
    return tmp_path


def test_disabled_engine_skips_gracefully(tmp_path: Path) -> None:
    """post_layers_engine='disabled' → TierAttempt(success) + 'layers_post_disabled'."""
    from core.generator.tier_layers_post import LayersPostGenerator

    gen = LayersPostGenerator()
    strategy = _make_strategy("tet", engine="disabled")
    case = _make_case_with_polymesh(tmp_path)
    attempt = gen.run(strategy, preprocessed_path=tmp_path / "in.stl", case_dir=case)
    assert attempt.status == "success"
    assert "disabled" in (attempt.error_message or "").lower()


@pytest.mark.parametrize("mt,expected_engine_contains", [
    ("tet", "tet_bl_subdivide"),
    ("hex_dominant", "native_bl"),
    ("poly", "poly_bl_transition"),
])
def test_auto_engine_routes_by_mesh_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    mt: str, expected_engine_contains: str,
) -> None:
    """engine='auto' + mesh_type → 해당 엔진 이름이 로그 또는 라우팅 분기에 나타남.

    실제 엔진 runner 를 stub 으로 교체해 호출되는 engine 문자열 capture.
    """
    from core.generator import tier_layers_post as tlp

    captured: dict[str, str] = {}

    # generate_native_bl 을 stub 으로 교체 (hex_dominant 경로)
    def _stub_generate_native_bl(case_dir, cfg):
        captured["engine_used"] = "native_bl"
        class _R:
            success = True
            message = "stub"
        return _R()

    # tet_bl_subdivide 경로
    def _stub_subdivide(case_dir, **kw):
        captured["engine_used"] = "tet_bl_subdivide"
        class _R:
            success = True
            message = "stub"
        return _R()

    # poly_bl_transition 경로
    def _stub_poly_bl(case_dir, **kw):
        captured["engine_used"] = "poly_bl_transition"
        class _R:
            success = True
            message = "stub"
        return _R()

    # 각 import 지점을 패치 — tlp 모듈 안에서 쓰는 이름을 직접 대체
    import core.layers.native_bl as nb
    import core.layers.tet_bl_subdivide as tb
    import core.layers.poly_bl_transition as pb

    monkeypatch.setattr(nb, "generate_native_bl", _stub_generate_native_bl)
    monkeypatch.setattr(tb, "subdivide_prism_layers_to_tet", _stub_subdivide)
    monkeypatch.setattr(pb, "run_poly_bl_transition", _stub_poly_bl)

    gen = tlp.LayersPostGenerator()
    strategy = _make_strategy(mt, engine="auto")
    case = _make_case_with_polymesh(tmp_path)

    attempt = gen.run(strategy, preprocessed_path=tmp_path / "in.stl", case_dir=case)
    # 라우팅 자체가 stub 을 호출했는지
    assert captured.get("engine_used") == expected_engine_contains, (
        f"mt={mt}: expected engine '{expected_engine_contains}', got "
        f"{captured.get('engine_used')!r} (attempt={attempt.status})"
    )


def test_auto_engine_unknown_mesh_type_falls_back_to_native_bl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """mesh_type='auto' 또는 알 수 없는 값 → native_bl 로 fallback."""
    from core.generator import tier_layers_post as tlp
    import core.layers.native_bl as nb

    captured = {}

    def _stub(case_dir, cfg):
        captured["called"] = True
        class _R:
            success = True
            message = "stub"
        return _R()

    monkeypatch.setattr(nb, "generate_native_bl", _stub)

    gen = tlp.LayersPostGenerator()
    strategy = _make_strategy("auto", engine="auto")
    case = _make_case_with_polymesh(tmp_path)
    gen.run(strategy, preprocessed_path=tmp_path / "in.stl", case_dir=case)
    assert captured.get("called") is True
