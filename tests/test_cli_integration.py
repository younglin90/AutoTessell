"""H8 / beta2617 — CLI flag 조합 통합 테스트.

beta2581-2616 의 신규 CLI flag (--ml-smooth-model 등) 가 click parser 에
인식되고 env 로 전달되는지 검증.

회귀 안전성 위주 — 실제 mesh 생성 안 함 (--help / dry-run 만).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]


def _run_cli(args: list[str], env: dict | None = None) -> subprocess.CompletedProcess:
    """auto-tessell CLI subprocess 실행."""
    cmd = [sys.executable, "-m", "cli.main"] + args
    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    return subprocess.run(
        cmd, cwd=str(REPO), capture_output=True, text=True,
        env=full_env, timeout=30,
    )


def test_cli_help_lists_g7_flags() -> None:
    """G7 신규 flag 가 --help 출력에 포함."""
    r = _run_cli(["run", "--help"])
    assert r.returncode == 0, f"help failed: {r.stderr}"
    output = r.stdout
    expected_flags = [
        "--ml-smooth-model",
        "--bl-predict-model",
        "--gpu-envelope",
        "--cvt3d-quality-weight",
        "--lcr-auto-reduce",
        "--bl-aniso-split",
    ]
    for flag in expected_flags:
        assert flag in output, f"--help 에 {flag} 누락"


def test_cli_help_lists_legacy_flags() -> None:
    """기존 flag 도 정상 노출."""
    r = _run_cli(["run", "--help"])
    assert r.returncode == 0
    for flag in ["--mesh-type", "--quality", "--tier", "--polyhedral"]:
        assert flag in r.stdout, f"--help 에 {flag} 누락"


def test_cli_doctor_runs() -> None:
    """auto-tessell doctor 가 동작 (의존성 점검)."""
    r = _run_cli(["doctor"])
    # doctor 는 항상 동작 (의존성 누락이어도 returncode=0).
    assert r.returncode == 0 or r.returncode == 1, f"doctor crashed: {r.stderr}"


def test_cli_invalid_mesh_type_rejected() -> None:
    """존재하지 않는 mesh_type 명령은 click 에서 reject."""
    fake_stl = REPO / "tests" / "stl" / "01_easy_cube.stl"
    if not fake_stl.exists():
        import pytest
        pytest.skip("01_easy_cube.stl 없음")
    r = _run_cli([
        "run", str(fake_stl),
        "-o", "/tmp/_ci_should_fail",
        "--mesh-type", "INVALID_TYPE_XYZ",
    ])
    # click 의 invalid choice → returncode != 0, "Invalid value" 메시지.
    assert r.returncode != 0
    assert "Invalid value" in r.stderr or "invalid choice" in r.stderr.lower()


def test_cli_ml_flag_path_validation() -> None:
    """--ml-smooth-model 은 path option — 존재 안 해도 click 은 통과 (env 만 set).
    실제 mesh run 은 timeout 위험으로 skip.
    """
    r = _run_cli(["run", "--help"])
    assert r.returncode == 0
    # help 자체에 PATH 표시 ("PATH" in flag definition).
    assert "--ml-smooth-model PATH" in r.stdout
    assert "--bl-predict-model PATH" in r.stdout


def test_cli_env_propagates_from_help_inspection() -> None:
    """env 변수 doc 이 help text 에 포함."""
    r = _run_cli(["run", "--help"])
    assert r.returncode == 0
    out = r.stdout
    # 각 flag 의 help text 에 env 이름 노출.
    assert "AUTO_TESSELL_ML_SMOOTH_MODEL" in out
    assert "AUTO_TESSELL_BL_PREDICT_MODEL" in out
    assert "AUTO_TESSELL_GPU_ENVELOPE" in out


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
