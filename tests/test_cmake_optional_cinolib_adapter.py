"""CMake contract for optional cinolib adapter.

All build output stays in pytest-provided temporary directories.  The test
never downloads or mutates third-party source.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SOURCE = _ROOT / "auto_tessell_core"
_NATIVE_TARGETS = (
    "native_metrics",
    "native_bl",
    "native_polymesh",
    "native_snap",
    "native_surface_padding",
    "native_hex_quality",
    "native_tet_predicates",
    "native_tet_qopt",
)


def _run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)


def _cmake_prefix() -> str:
    assert shutil.which("cmake") is not None, "cmake unavailable"
    result = _run([sys.executable, "-m", "pybind11", "--cmakedir"], cwd=_ROOT)
    assert result.returncode == 0, (
        "pybind11 CMake package unavailable:\n" + result.stdout + result.stderr
    )
    return result.stdout.strip()


def _configure(build_dir: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return _run(
        [
            "cmake",
            "-S",
            str(_SOURCE),
            "-B",
            str(build_dir),
            "-DCMAKE_BUILD_TYPE=Release",
            f"-Dpybind11_DIR={_cmake_prefix()}",
            "-DBUILD_ROBUSTHEX=OFF",
            "-DBUILD_FTETWILD=OFF",
            "-DBUILD_CFMESH=OFF",
            *arguments,
        ],
        cwd=_ROOT,
    )


def test_native_release_build_excludes_cinolib_by_default(tmp_path: Path) -> None:
    build_dir = tmp_path / "native-core-release"
    configured = _configure(build_dir, "-DBUILD_CINOLIB_HEX=OFF")
    assert configured.returncode == 0, configured.stdout + configured.stderr
    cache = (build_dir / "CMakeCache.txt").read_text(encoding="utf-8")
    assert "BUILD_CINOLIB_HEX:BOOL=OFF" in cache

    built = _run(["cmake", "--build", str(build_dir), "--config", "Release"], cwd=_ROOT)
    assert built.returncode == 0, built.stdout + built.stderr
    for target in _NATIVE_TARGETS:
        assert list(build_dir.glob(f"{target}*")), f"missing native target output: {target}"
    assert not list(build_dir.glob("cinolib_hex*"))


def test_explicit_cinolib_adapter_without_headers_fails_at_configure(tmp_path: Path) -> None:
    missing_source = tmp_path / "missing-cinolib"
    configured = _configure(
        tmp_path / "cinolib-requested",
        "-DBUILD_CINOLIB_HEX=ON",
        f"-DCINOLIB_DIR={missing_source}",
    )
    output = configured.stdout + configured.stderr
    assert configured.returncode != 0
    assert "BUILD_CINOLIB_HEX=ON requires cinolib headers" in output
    assert "CINOLIB_DIR/include/cinolib/geometry/vec_mat.h" in output
