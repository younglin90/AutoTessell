"""beta26 — Preprocessor L1 native 기본화 (prefer_native CLI default=True)."""
from __future__ import annotations

from click.testing import CliRunner


def test_cli_default_prefer_native_is_true() -> None:
    """CLI 기본: --prefer-native 미지정 시 prefer_native=True."""
    from cli.main import run

    r = CliRunner().invoke(
        run, ["tests/stl/01_easy_cube.stl", "--dry-run",
              "--mesh-type", "tet", "--quality", "draft"],
    )
    assert r.exit_code == 0
    # CLI 출력 또는 로그에서 prefer_native=True 확인
    assert "prefer_native=True" in r.output


def test_cli_legacy_repair_sets_prefer_native_false() -> None:
    """--legacy-repair 플래그 시 prefer_native=False 로 전환 (opt-out)."""
    from cli.main import run

    r = CliRunner().invoke(
        run, ["tests/stl/01_easy_cube.stl", "--dry-run",
              "--mesh-type", "tet", "--quality", "draft", "--legacy-repair"],
    )
    assert r.exit_code == 0
    assert "prefer_native=False" in r.output


def test_cli_explicit_prefer_native_stays_true() -> None:
    """--prefer-native 명시해도 동일 (True 유지)."""
    from cli.main import run

    r = CliRunner().invoke(
        run, ["tests/stl/01_easy_cube.stl", "--dry-run",
              "--mesh-type", "tet", "--quality", "draft", "--prefer-native"],
    )
    assert r.exit_code == 0
    assert "prefer_native=True" in r.output


def test_pipeline_native_l1_method_returns_valid_mesh(tmp_path) -> None:
    """Preprocessor._l1_repair_native 직접 호출 — cube STL 에서 native 경로 작동."""
    import numpy as np
    import trimesh

    from core.preprocessor.pipeline import Preprocessor
    from core.schemas import Issue, Severity

    cube = trimesh.creation.box()
    pp = Preprocessor()
    issues = [Issue(
        severity=Severity.WARNING, type="non_watertight", count=1,
        description="stub", recommended_action="repair",
    )]
    new_mesh, passed, record = pp._l1_repair_native(cube, issues)
    # cube 는 이미 watertight → native 가 통과
    assert record["method"] == "native_repair"
    assert record["input_faces"] > 0
    assert record["output_faces"] > 0
    # 새 mesh 도 valid
    assert len(new_mesh.vertices) > 0
    assert len(new_mesh.faces) > 0
