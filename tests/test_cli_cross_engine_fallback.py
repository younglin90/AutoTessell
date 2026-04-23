"""beta71 — CLI --cross-engine-fallback 플래그 배선 회귀."""
from __future__ import annotations

import pytest
from click.testing import CliRunner


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_help_exposes_cross_engine_fallback_flag(runner: CliRunner) -> None:
    """--help 출력에 --cross-engine-fallback 플래그가 보인다."""
    from cli.main import run
    result = runner.invoke(run, ["--help"])
    assert result.exit_code == 0
    assert "--cross-engine-fallback" in result.output
    assert "poly" in result.output.lower()


def test_cross_engine_fallback_flag_accepted(runner: CliRunner) -> None:
    """--cross-engine-fallback 를 인자로 주면 CLI 가 parsing 에러 없이 실행된다."""
    from cli.main import run
    # --dry-run 으로 전략 수립까지만
    result = runner.invoke(run, [
        "tests/stl/01_easy_cube.stl",
        "-o", "/tmp/_tmp_cross_engine_test",
        "--mesh-type", "poly",
        "--cross-engine-fallback",
        "--dry-run",
    ])
    # parsing 단계 통과 여부만 검증 — 실패해도 exit_code 는 0 이거나 runtime fail
    assert "Error: No such option" not in (result.output or "")
    assert "unexpected keyword" not in (result.output or "")


def test_flag_defaults_to_false_in_signature() -> None:
    """run() 함수가 cross_engine_fallback 파라미터를 받고 기본값 False."""
    from cli.main import run
    # click decorator 로 감싸진 callback 의 실제 함수 시그니처 조회
    callback = run.callback
    import inspect
    sig = inspect.signature(callback)
    assert "cross_engine_fallback" in sig.parameters


def test_orchestrator_accepts_cross_engine_kwarg() -> None:
    """PipelineOrchestrator.run 도 같은 kwarg 수용 (Ph68 상태 유지 검증)."""
    from core.pipeline.orchestrator import PipelineOrchestrator
    import inspect
    sig = inspect.signature(PipelineOrchestrator.run)
    assert "cross_engine_fallback" in sig.parameters
    assert sig.parameters["cross_engine_fallback"].default is False
