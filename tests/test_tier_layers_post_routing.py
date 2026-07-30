"""beta34 — LayersPostGenerator auto-engine 라우팅 회귀 테스트.

engine="auto" + mesh_type 조합에 따라 올바른 BL 엔진이 선택되는지 (tet →
native_bl, hex_dominant → native_bl, poly → poly_bl_transition) 검증.

실제 엔진 실행은 비용이 커서 logic 만 검증 — monkeypatch 로 각 runner 를
capture.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
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
    ("tet", "native_bl"),
    ("hex_dominant", "native_hex_bl"),
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

    def _stub_native_hex_bl(case_dir, **kw):
        captured["engine_used"] = "native_hex_bl"
        return True, "stub", 1

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
    monkeypatch.setattr(tlp, "_run_native_hex_bl", _stub_native_hex_bl)

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


@pytest.mark.parametrize("explicit_override", [False, True])
def test_native_hex_bl_zero_is_successful_noop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, explicit_override: bool,
) -> None:
    """BL=0 never reaches the native hex layer writer."""
    from core.generator import tier_layers_post as tlp

    calls: list[dict[str, object]] = []

    def _stub_native_hex_bl(_case_dir, **kwargs):
        calls.append(kwargs)
        return True, "unexpected", 1

    monkeypatch.setattr(tlp, "_run_native_hex_bl", _stub_native_hex_bl)
    strategy = _make_strategy("hex_dominant", engine="native_hex_bl")
    strategy.boundary_layers.enabled = False
    strategy.boundary_layers.num_layers = 0
    if explicit_override:
        strategy.tier_specific_params["post_layers_num_layers"] = 0
    attempt = tlp.LayersPostGenerator().run(
        strategy, tmp_path / "in.stl", _make_case_with_polymesh(tmp_path),
    )
    assert attempt.status == "success"
    assert attempt.error_message == "layers_post_disabled_zero"
    assert calls == []


def test_native_hex_bl_negative_layers_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Negative BL count is invalid, not an implicit no-op."""
    from core.generator import tier_layers_post as tlp

    monkeypatch.setattr(
        tlp,
        "_run_native_hex_bl",
        lambda *_args, **_kwargs: pytest.fail("negative layers reached native hex BL"),
    )
    strategy = _make_strategy("hex_dominant", engine="native_hex_bl")
    strategy.tier_specific_params["post_layers_num_layers"] = -1
    attempt = tlp.LayersPostGenerator().run(
        strategy, tmp_path / "in.stl", _make_case_with_polymesh(tmp_path),
    )
    assert attempt.status == "failed"
    assert attempt.error_message == "invalid_num_layers:-1"


@pytest.mark.parametrize("num_layers", [1, 3])
def test_native_hex_bl_positive_layers_still_route(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, num_layers: int,
) -> None:
    """Zero guard must not alter positive native hex BL requests."""
    from core.generator import tier_layers_post as tlp

    seen: list[int] = []

    def _stub_native_hex_bl(_case_dir, **kwargs):
        seen.append(int(kwargs["num_layers"]))
        return True, "stub", 1

    monkeypatch.setattr(tlp, "_run_native_hex_bl", _stub_native_hex_bl)
    strategy = _make_strategy("hex_dominant", engine="native_hex_bl")
    strategy.tier_specific_params["post_layers_num_layers"] = num_layers
    attempt = tlp.LayersPostGenerator().run(
        strategy, tmp_path / "in.stl", _make_case_with_polymesh(tmp_path),
    )
    assert attempt.status == "success"
    assert seen == [num_layers]


def test_native_hex_bl_rewrites_quad_caps_and_preserves_patch_types(
    tmp_path: Path,
) -> None:
    """Quad caps become bulk/BL internal faces; top walls retain patch types."""
    from core.generator.polymesh_writer import write_generic_polymesh
    from core.generator.tier_layers_post import _run_native_hex_bl
    from core.utils.polymesh_reader import (
        parse_foam_boundary,
        parse_foam_faces,
        parse_foam_labels,
    )

    points = np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
    ], dtype=np.float64)
    cell_faces = [[
        [0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4],
        [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7],
    ]]
    inlet_key = tuple(sorted(cell_faces[0][0]))

    def _classify(face, _points):
        if tuple(sorted(face)) == inlet_key:
            return "inlet", "patch"
        return "wall", "wall"

    write_generic_polymesh(
        points, cell_faces, tmp_path, boundary_patch_classifier=_classify,
    )
    ok, msg, n_quad = _run_native_hex_bl(
        tmp_path,
        num_layers=2,
        growth_ratio=1.2,
        first_thickness=0.05,
        params={},
    )
    assert ok, msg
    assert n_quad == 5

    poly_dir = tmp_path / "constant" / "polyMesh"
    faces = parse_foam_faces(poly_dir / "faces")
    owner = parse_foam_labels(poly_dir / "owner")
    neighbour = parse_foam_labels(poly_dir / "neighbour")
    assert max(owner) + 1 == 11  # 1 bulk + 5 quads * 2 layers
    assert len(owner) == len(faces)
    assert len(neighbour) < len(faces)

    # Each original wall quad is now an internal bulk/BL cap.  The inlet
    # remains boundary because patch type is not wall.
    for face in cell_faces[0][1:]:
        cap_key = tuple(sorted(face))
        fi = next(i for i, out_face in enumerate(faces) if tuple(sorted(out_face)) == cap_key)
        assert fi < len(neighbour)
        assert owner[fi] == 0
        assert neighbour[fi] > 0

    boundary = parse_foam_boundary(poly_dir / "boundary")
    assert {entry["name"] for entry in boundary} == {"inlet", "wall"}
    raw_boundary = (poly_dir / "boundary").read_text(encoding="utf-8")
    assert "inlet\n    {\n        type            patch;" in raw_boundary
    assert "wall\n    {\n        type            wall;" in raw_boundary


def test_native_hex_bl_zero_leaves_polymesh_bytes_unchanged(tmp_path: Path) -> None:
    """BL=0 preserves cells, points, patch names/types, and topology bytes."""
    from core.generator.polymesh_writer import write_generic_polymesh
    from core.generator.tier_layers_post import LayersPostGenerator

    points = np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
    ], dtype=np.float64)
    cell_faces = [[
        [0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4],
        [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7],
    ]]
    write_generic_polymesh(points, cell_faces, tmp_path)
    poly_dir = tmp_path / "constant" / "polyMesh"
    tracked = ("points", "faces", "owner", "neighbour", "boundary")
    before = {name: (poly_dir / name).read_bytes() for name in tracked}

    strategy = _make_strategy("hex_dominant", engine="native_hex_bl")
    strategy.boundary_layers.enabled = False
    strategy.boundary_layers.num_layers = 0
    attempt = LayersPostGenerator().run(strategy, tmp_path / "in.stl", tmp_path)

    after = {name: (poly_dir / name).read_bytes() for name in tracked}
    assert attempt.status == "success"
    assert attempt.error_message == "layers_post_disabled_zero"
    assert after == before
