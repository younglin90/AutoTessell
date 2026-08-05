"""NativeMeshChecker vs OpenFOAM checkMesh parity tests.

The suite builds one immutable sphere case and snapshots one Native result plus
one verified external OpenFOAM result. Assertions reuse that snapshot so an
expensive geometry/topology check is not launched once per assertion.
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
from core.utils.openfoam_utils import _find_openfoam_bashrc
from tests.native_checker_parity_snapshot import ParitySnapshot, build_parity_snapshot


_REPO = Path(__file__).resolve().parents[1]
SPHERE_STL = _REPO / "tests" / "benchmarks" / "sphere.stl"


def _external_openfoam_available() -> bool:
    """Require both explicit debug opt-in and a discoverable OpenFOAM bashrc."""
    if os.environ.get("AUTO_TESSELL_ALLOW_EXTERNAL_OPENFOAM") != "1":
        return False
    try:
        bashrc = _find_openfoam_bashrc()
    except Exception:
        return False
    return bashrc is not None and Path(bashrc).exists()


@pytest.fixture(scope="module")
def sphere_case() -> Path:
    """Build one wildmesh sphere polyMesh for the module."""
    if not _external_openfoam_available():
        pytest.skip(
            "verified external OpenFOAM unavailable or "
            "AUTO_TESSELL_ALLOW_EXTERNAL_OPENFOAM is not 1"
        )
    if not SPHERE_STL.exists():
        pytest.skip(f"sphere.stl missing: {SPHERE_STL}")

    tmp = tempfile.mkdtemp(prefix="native_parity_")
    case_dir = Path(tmp) / "case"
    cmd = [
        "python3", "-m", "cli.main", "run", str(SPHERE_STL),
        "-o", str(case_dir), "--mesh-type", "tet", "--quality", "draft",
        "--tier", "wildmesh", "--auto-retry", "off",
    ]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_REPO) + os.pathsep + env.get("PYTHONPATH", "")
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=180, env=env, cwd=str(_REPO)
    )
    if result.returncode != 0 or not (case_dir / "constant" / "polyMesh").exists():
        shutil.rmtree(tmp, ignore_errors=True)
        pytest.skip(
            f"fixture mesh generation failed (rc={result.returncode}): "
            f"{(result.stderr or result.stdout)[-300:]}"
        )
    yield case_dir
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture(scope="module")
def parity_snapshot(sphere_case: Path) -> ParitySnapshot:
    native_checker = NativeMeshChecker()
    external_checker = MeshQualityChecker(prefer_native=False)
    snapshot = build_parity_snapshot(
        sphere_case,
        native_runner=native_checker.run,
        external_runner=external_checker,
        clock=__import__("time").perf_counter,
    )
    assert snapshot.external_engine == "openfoam"
    return snapshot


def _rel(a: float, b: float) -> float:
    denom = max(abs(a), abs(b), 1e-9)
    return abs(a - b) / denom


def test_native_vs_openfoam_cells_exact(parity_snapshot: ParitySnapshot) -> None:
    native, openfoam = parity_snapshot.native, parity_snapshot.external
    assert native.cells == openfoam.cells
    assert native.faces == openfoam.faces
    assert native.points == openfoam.points


def test_native_vs_openfoam_non_ortho_max_within_5pct(parity_snapshot: ParitySnapshot) -> None:
    native, openfoam = parity_snapshot.native, parity_snapshot.external
    rel = _rel(native.max_non_orthogonality, openfoam.max_non_orthogonality)
    assert rel < 0.05, (
        f"max_non_ortho mismatch native={native.max_non_orthogonality:.3f} "
        f"of={openfoam.max_non_orthogonality:.3f} rel={rel:.3f}"
    )


def test_native_vs_openfoam_skewness_both_positive(parity_snapshot: ParitySnapshot) -> None:
    native, openfoam = parity_snapshot.native, parity_snapshot.external
    assert native.max_skewness > 0
    assert openfoam.max_skewness >= 0


def test_native_vs_openfoam_aspect_ratio_both_positive(parity_snapshot: ParitySnapshot) -> None:
    native, openfoam = parity_snapshot.native, parity_snapshot.external
    assert native.max_aspect_ratio > 1.0
    assert openfoam.max_aspect_ratio > 1.0


def test_native_vs_openfoam_negative_volumes_exact(parity_snapshot: ParitySnapshot) -> None:
    assert parity_snapshot.native.negative_volumes == parity_snapshot.external.negative_volumes


def test_checker_engine_used_recorded(parity_snapshot: ParitySnapshot) -> None:
    assert parity_snapshot.native_engine == "native"
    assert parity_snapshot.external_engine == "openfoam"
    assert parity_snapshot.timings["native_seconds"] >= 0.0
    assert parity_snapshot.timings["external_seconds"] >= 0.0
