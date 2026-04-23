"""beta39 — CLI --tier-param (beta20) + --prefer-native-tier (beta23) 회귀.

CLI 레벨에서 새 플래그 파싱 + 전파 검증. --dry-run 으로 orchestrator 실행 없이
strategy 조립까지만.
"""
from __future__ import annotations

import re

import pytest
from click.testing import CliRunner


STL_PATH = "tests/stl/01_easy_cube.stl"


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# ---------------------------------------------------------------------------
# --tier-param
# ---------------------------------------------------------------------------


def test_tier_param_integer_parsed(runner: CliRunner) -> None:
    """--tier-param seed_density=20 → int 로 추론되어 tier_specific_params 에 주입."""
    from cli.main import run

    r = runner.invoke(run, [
        STL_PATH, "--dry-run", "--mesh-type", "tet", "--quality", "draft",
        "--tier-param", "seed_density=20",
    ])
    assert r.exit_code == 0
    # 로그 line 에 seed_density 가 등장하면 파싱 성공
    assert "seed_density" in r.output


def test_tier_param_float_parsed(runner: CliRunner) -> None:
    """--tier-param threshold=0.85 → float 추론."""
    from cli.main import run

    r = runner.invoke(run, [
        STL_PATH, "--dry-run", "--mesh-type", "tet", "--quality", "draft",
        "--tier-param", "threshold=0.85",
    ])
    assert r.exit_code == 0


def test_tier_param_bool_parsed(runner: CliRunner) -> None:
    """--tier-param snap_boundary=true → True, snap_boundary=off → False."""
    from cli.main import run

    for val in ("true", "yes", "on"):
        r = runner.invoke(run, [
            STL_PATH, "--dry-run", "--mesh-type", "hex_dominant",
            "--quality", "fine", "--tier-param", f"snap_boundary={val}",
        ])
        assert r.exit_code == 0, f"val={val}: {r.output[-300:]}"

    for val in ("false", "no", "off"):
        r = runner.invoke(run, [
            STL_PATH, "--dry-run", "--mesh-type", "hex_dominant",
            "--quality", "fine", "--tier-param", f"snap_boundary={val}",
        ])
        assert r.exit_code == 0, f"val={val}"


def test_tier_param_multiple_flags(runner: CliRunner) -> None:
    """--tier-param 여러 번 반복해도 모두 수집."""
    from cli.main import run

    r = runner.invoke(run, [
        STL_PATH, "--dry-run", "--mesh-type", "tet", "--quality", "draft",
        "--tier-param", "seed_density=15",
        "--tier-param", "max_iter=4",
        "--tier-param", "snap_boundary=true",
    ])
    assert r.exit_code == 0
    # tier_specific_params_override keys= 로그에 3 개 모두 나와야
    assert "seed_density" in r.output
    assert "max_iter" in r.output
    assert "snap_boundary" in r.output


def test_tier_param_invalid_format_warns_and_continues(runner: CliRunner) -> None:
    """--tier-param 이 KEY=VALUE 형식이 아닐 때 WARN 출력하고 계속 실행."""
    from cli.main import run

    r = runner.invoke(run, [
        STL_PATH, "--dry-run", "--mesh-type", "tet", "--quality", "draft",
        "--tier-param", "malformed_no_equals",
    ])
    # crash 없음
    assert r.exit_code == 0
    # WARN 메시지 포함
    assert re.search(r"잘못된 형식|KEY=VALUE", r.output)


def test_tier_param_empty_key_warns(runner: CliRunner) -> None:
    """--tier-param '=value' (빈 키) → WARN."""
    from cli.main import run

    r = runner.invoke(run, [
        STL_PATH, "--dry-run", "--mesh-type", "tet", "--quality", "draft",
        "--tier-param", "=value_only",
    ])
    assert r.exit_code == 0
    assert re.search(r"빈 키|empty|잘못된", r.output)


def test_tier_param_string_fallback(runner: CliRunner) -> None:
    """int/float/bool 모두 실패하면 string 으로 저장."""
    from cli.main import run

    r = runner.invoke(run, [
        STL_PATH, "--dry-run", "--mesh-type", "tet", "--quality", "draft",
        "--tier-param", "custom_label=hello_world",
    ])
    assert r.exit_code == 0
    # tier_specific_params_override keys= 에 custom_label 포함
    assert "custom_label" in r.output


# ---------------------------------------------------------------------------
# --prefer-native-tier
# ---------------------------------------------------------------------------


def test_prefer_native_tier_promotes_native_primary(runner: CliRunner) -> None:
    """--prefer-native-tier + mesh_type=hex_dominant → Tier: tier_native_hex."""
    from cli.main import run

    r = runner.invoke(run, [
        STL_PATH, "--dry-run", "--mesh-type", "hex_dominant",
        "--quality", "fine", "--prefer-native-tier",
    ])
    assert r.exit_code == 0
    # dry-run 출력에서 "Tier: tier_native_hex" 확인
    assert "tier_native_hex" in r.output


def test_prefer_native_tier_tet(runner: CliRunner) -> None:
    """mesh_type=tet + --prefer-native-tier → tier_native_tet primary."""
    from cli.main import run

    r = runner.invoke(run, [
        STL_PATH, "--dry-run", "--mesh-type", "tet",
        "--quality", "standard", "--prefer-native-tier",
    ])
    assert r.exit_code == 0
    # "Tier: tier_native_tet" 출력
    assert re.search(r"Tier:\s+tier_native_tet\b", r.output)


def test_prefer_native_tier_poly(runner: CliRunner) -> None:
    """mesh_type=poly + --prefer-native-tier → tier_native_poly primary."""
    from cli.main import run

    r = runner.invoke(run, [
        STL_PATH, "--dry-run", "--mesh-type", "poly",
        "--quality", "draft", "--prefer-native-tier",
    ])
    assert r.exit_code == 0
    assert re.search(r"Tier:\s+tier_native_poly\b", r.output)


def test_prefer_native_tier_not_set_uses_legacy_primary(runner: CliRunner) -> None:
    """--prefer-native-tier 없이 mesh_type=tet → legacy primary (e.g. tier2_tetwild
    for draft, tier05_netgen for standard)."""
    from cli.main import run

    r = runner.invoke(run, [
        STL_PATH, "--dry-run", "--mesh-type", "tet", "--quality", "draft",
    ])
    assert r.exit_code == 0
    # draft tet primary = tier2_tetwild
    assert re.search(r"Tier:\s+tier2_tetwild\b", r.output)


def test_prefer_native_tier_keeps_legacy_fallback(runner: CliRunner) -> None:
    """--prefer-native-tier 활성 시 기존 legacy primary 는 fallback 맨 앞에 유지."""
    from cli.main import run

    r = runner.invoke(run, [
        STL_PATH, "--dry-run", "--mesh-type", "hex_dominant",
        "--quality", "fine", "--prefer-native-tier",
    ])
    assert r.exit_code == 0
    # Fallback: 목록 시작이 tier1_snappy (legacy fine primary)
    # 출력 포맷: "Fallback: ['tier1_snappy', ...]"
    assert "tier1_snappy" in r.output
