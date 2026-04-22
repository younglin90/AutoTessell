"""NativeMeshChecker vs OpenFOAM checkMesh parity 테스트.

v0.4 native-first 정책으로 auto 기본값이 Native 로 전환됨. 이 테스트는 같은
polyMesh 입력에 대해 두 엔진이 동일한 주요 지표 (상대 오차 5% 이내) 를 내는지
검증한다. OpenFOAM 이 가용하지 않으면 skip.

fixture: sphere.stl 을 wildmesh 로 메쉬 생성 → 두 엔진으로 차례대로 run.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from core.evaluator.native_checker import NativeMeshChecker
from core.evaluator.quality_checker import MeshQualityChecker


# ---------------------------------------------------------------------------
# OpenFOAM 감지 (없으면 전체 skip)
# ---------------------------------------------------------------------------


def _openfoam_available() -> bool:
    """OpenFOAM checkMesh 바이너리를 실행할 수 있는지 감지."""
    try:
        from core.utils.openfoam_utils import _find_openfoam_bashrc
    except Exception:
        return False
    try:
        bashrc = _find_openfoam_bashrc()
    except Exception:
        return False
    return bashrc is not None and Path(bashrc).exists()


pytestmark = pytest.mark.skipif(
    not _openfoam_available(),
    reason="OpenFOAM bashrc 미감지 — parity 테스트는 OpenFOAM 환경에서만 실행",
)


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


_REPO = Path(__file__).resolve().parents[1]
SPHERE_STL = _REPO / "tests" / "benchmarks" / "sphere.stl"


@pytest.fixture(scope="module")
def sphere_case() -> Path:
    """sphere.stl 을 wildmesh draft 로 메쉬 생성해 polyMesh 준비."""
    if not SPHERE_STL.exists():
        pytest.skip(f"sphere.stl 미존재: {SPHERE_STL}")

    tmp = tempfile.mkdtemp(prefix="native_parity_")
    case_dir = Path(tmp) / "case"
    cmd = [
        "python3", "-m", "cli.main", "run", str(SPHERE_STL),
        "-o", str(case_dir),
        "--mesh-type", "tet", "--quality", "draft", "--tier", "wildmesh",
        "--auto-retry", "off",
    ]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_REPO) + os.pathsep + env.get("PYTHONPATH", "")
    r = subprocess.run(
        cmd, capture_output=True, text=True, timeout=180, env=env, cwd=str(_REPO),
    )
    if r.returncode != 0 or not (case_dir / "constant" / "polyMesh").exists():
        shutil.rmtree(tmp, ignore_errors=True)
        pytest.skip(
            f"fixture 메쉬 생성 실패 (rc={r.returncode}): "
            f"{(r.stderr or r.stdout)[-300:]}"
        )
    yield case_dir
    shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Parity checks
# ---------------------------------------------------------------------------


def _rel(a: float, b: float) -> float:
    """상대 오차 |a-b| / max(|a|,|b|,eps)."""
    denom = max(abs(a), abs(b), 1e-9)
    return abs(a - b) / denom


def test_native_vs_openfoam_cells_exact(sphere_case: Path) -> None:
    """cells / faces / points 는 완전히 일치해야 한다 (동일 polyMesh 입력)."""
    native = NativeMeshChecker().run(sphere_case)

    of_checker = MeshQualityChecker(prefer_native=False)
    openfoam = of_checker.run(sphere_case)

    assert native.cells == openfoam.cells, (
        f"cells mismatch native={native.cells} of={openfoam.cells}"
    )
    assert native.faces == openfoam.faces
    assert native.points == openfoam.points


def test_native_vs_openfoam_non_ortho_max_within_5pct(sphere_case: Path) -> None:
    """Max non-orthogonality 는 상대 오차 5% 이내이어야 한다."""
    native = NativeMeshChecker().run(sphere_case)
    openfoam = MeshQualityChecker(prefer_native=False).run(sphere_case)
    rel = _rel(native.max_non_orthogonality, openfoam.max_non_orthogonality)
    assert rel < 0.05, (
        f"max_non_ortho 차이 native={native.max_non_orthogonality:.3f} "
        f"of={openfoam.max_non_orthogonality:.3f} rel={rel:.3f}"
    )


def test_native_vs_openfoam_skewness_both_positive(sphere_case: Path) -> None:
    """Max skewness 는 두 엔진 모두 양수 이어야 한다.

    OpenFOAM 과 native 의 skewness 공식은 정확히 일치하지 않음 (OpenFOAM 은 face
    centre 와 cell-cell 접속점 거리 기반, native 는 유사 공식이나 정의 차이 있음).
    정확 일치 대신 "두 엔진 모두 정상적으로 값을 뽑아냄" + "이상치 (negative /
    nan) 없음" 을 검증.
    """
    native = NativeMeshChecker().run(sphere_case)
    openfoam = MeshQualityChecker(prefer_native=False).run(sphere_case)
    assert native.max_skewness > 0, f"native skewness <= 0: {native.max_skewness}"
    assert openfoam.max_skewness >= 0, (
        f"of skewness < 0: {openfoam.max_skewness}"
    )


def test_native_vs_openfoam_aspect_ratio_both_positive(sphere_case: Path) -> None:
    """Max aspect ratio 는 두 엔진 모두 양수 이어야 한다.

    aspect_ratio 정의는 엔진마다 공식이 달라 (native = edge 길이 min/max,
    OpenFOAM = 3D 특수 공식) 숫자 자체의 parity 는 기대하지 않음. 둘 다 > 1 임을
    확인한다.
    """
    native = NativeMeshChecker().run(sphere_case)
    openfoam = MeshQualityChecker(prefer_native=False).run(sphere_case)
    assert native.max_aspect_ratio > 1.0
    assert openfoam.max_aspect_ratio > 1.0


def test_native_vs_openfoam_negative_volumes_exact(sphere_case: Path) -> None:
    """Negative volumes 카운트는 정확히 일치해야 한다."""
    native = NativeMeshChecker().run(sphere_case)
    openfoam = MeshQualityChecker(prefer_native=False).run(sphere_case)
    assert native.negative_volumes == openfoam.negative_volumes


def test_checker_engine_used_recorded(sphere_case: Path) -> None:
    """MeshQualityChecker.last_engine_used 가 실제 사용된 엔진을 기록한다."""
    checker = MeshQualityChecker(prefer_native=True)
    checker.run(sphere_case)
    assert checker.last_engine_used == "native"

    checker2 = MeshQualityChecker(prefer_native=False)
    checker2.run(sphere_case)
    assert checker2.last_engine_used in ("openfoam", "native")
    # OpenFOAM 가용 환경이면 반드시 openfoam 이어야 함.
    assert checker2.last_engine_used == "openfoam"
