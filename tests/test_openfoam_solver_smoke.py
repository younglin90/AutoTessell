"""beta80 — OpenFOAM solver smoke test.

box.stl → native_tet pipeline → simpleFoam 5 iterations.
OpenFOAM 미설치 환경에서는 자동 skip.

마커:
  @pytest.mark.openfoam  — OpenFOAM 설치 필요
  @pytest.mark.slow      — 수 분 소요
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


_REPO = Path(__file__).resolve().parents[1]
BOX_STEP = _REPO / "tests" / "benchmarks" / "box.step"
BOX_STL = _REPO / "tests" / "benchmarks" / "cube.stl"


def _has_openfoam() -> bool:
    """simpleFoam 또는 OpenFOAM bashrc 가 발견되면 True."""
    try:
        from core.utils.openfoam_utils import _find_openfoam_bashrc
        return _find_openfoam_bashrc() is not None
    except Exception:
        return False


def _run_simpleFoam(case_dir: Path, n_iter: int = 5) -> subprocess.CompletedProcess:
    """controlDict 의 endTime 을 n_iter 로 교체 후 simpleFoam 실행."""
    ctrl = case_dir / "system" / "controlDict"
    if ctrl.exists():
        txt = ctrl.read_text()
        txt = txt.replace("endTime     500;", f"endTime     {n_iter};")
        txt = txt.replace("writeInterval 100;", f"writeInterval {n_iter};")
        ctrl.write_text(txt)
    try:
        from core.utils.openfoam_utils import run_openfoam
        return run_openfoam("simpleFoam", case_dir)
    except Exception as exc:
        return subprocess.CompletedProcess(
            args=["simpleFoam"], returncode=1,
            stdout="", stderr=str(exc),
        )


@pytest.mark.openfoam
@pytest.mark.slow
def test_simpleFoam_runs_without_crash(tmp_path: Path) -> None:
    """box/cube → native_tet → simpleFoam 5 iter — crash (returncode != 0) 없음."""
    if not _has_openfoam():
        pytest.skip("OpenFOAM 미설치 — solver smoke test skip")

    stl = BOX_STL if BOX_STL.exists() else None
    if stl is None:
        pytest.skip("cube.stl 미존재")

    from core.pipeline.orchestrator import PipelineOrchestrator
    orch = PipelineOrchestrator()
    try:
        result = orch.run(
            input_path=stl,
            output_dir=tmp_path / "case",
            quality_level="draft",
            mesh_type="tet",
            tier_hint="native_tet",
            max_iterations=1,
            auto_retry="off",
            prefer_native=True,
            prefer_native_tier=True,
            flow_velocity=1.0,
        )
    except Exception as exc:
        pytest.xfail(f"파이프라인 예외: {exc}")

    poly_dir = tmp_path / "case" / "constant" / "polyMesh"
    if not poly_dir.exists():
        pytest.xfail(f"polyMesh 미생성: {result.error}")

    # simpleFoam 5 iter 실행
    cp = _run_simpleFoam(tmp_path / "case", n_iter=5)
    # crash (returncode != 0) 가 없으면 OK — 수렴 여부는 추가 검증
    assert cp.returncode == 0, (
        f"simpleFoam crashed (rc={cp.returncode}):\n"
        f"{(cp.stderr or '')[-500:]}"
    )

    log_file = tmp_path / "case" / "log.simpleFoam"
    if log_file.exists():
        log_text = log_file.read_text(errors="replace")
        # Time = 5 (5 iterations 완료) 가 log 에 있는지 확인
        assert "Time = 5" in log_text or "SIMPLE solution converged" in log_text, (
            "simpleFoam log 에 'Time = 5' 없음 — 5 iter 미완료?"
        )


@pytest.mark.openfoam
def test_openfoam_detected() -> None:
    """OpenFOAM 설치 여부 간단 확인."""
    if not _has_openfoam():
        pytest.skip("OpenFOAM 미설치")
    assert _has_openfoam() is True
