"""beta53 — Native CAD (STEP/IGES/BREP) reader 회귀.

OCP (python-occ) 기반 native reader 우회 경로 검증.
OCP 미설치 환경에서는 ImportError → graceful fallback 확인.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.analyzer.readers.step import load_cad_native


def _ocp_available() -> bool:
    try:
        from OCP.STEPControl import STEPControl_Reader  # type: ignore  # noqa: F401
        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# graceful fallback (OCP 미설치 환경)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(_ocp_available(), reason="OCP installed — skip missing path")
def test_ocp_missing_raises_import_error(tmp_path: Path) -> None:
    """OCP 없는 환경에서 load_cad_native 가 ImportError raise."""
    # 가짜 STEP 파일
    fake = tmp_path / "x.step"
    fake.write_text("ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n")
    with pytest.raises(ImportError, match="OCP"):
        load_cad_native(fake, ".step")


def test_unsupported_ext_raises_value_error(tmp_path: Path) -> None:
    """알 수 없는 확장자 → ValueError.

    OCP 가 있을 때만 의미가 있는 경로 (OCP 없으면 ImportError 먼저 발생).
    """
    if not _ocp_available():
        pytest.skip("OCP not installed — cannot reach ext validation")

    fake = tmp_path / "x.xyz"
    fake.write_text("garbage")
    with pytest.raises(ValueError, match="지원하지 않는"):
        load_cad_native(fake, ".xyz")


# ---------------------------------------------------------------------------
# file_reader 통합 — graceful fallback
# ---------------------------------------------------------------------------


def test_file_reader_cad_entry_point_exists() -> None:
    """_load_via_cad / _load_via_ocp_native 가 file_reader 에 정의."""
    from core.analyzer import file_reader

    assert hasattr(file_reader, "_load_via_cad")
    assert hasattr(file_reader, "_load_via_ocp_native")


def test_file_reader_cad_fallback_chain(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """_load_via_cad: OCP native → cadquery → gmsh 체인.

    모든 경로를 강제 실패시키면 ValueError 에 세 오류 문자열 모두 포함.
    """
    import core.analyzer.file_reader as fr

    def _fail_ocp(path, fmt):
        raise ImportError("simulated: OCP missing")

    def _fail_cq(path, fmt):
        raise Exception("simulated: cadquery fail")

    def _fail_gmsh(path, fmt):
        raise Exception("simulated: gmsh fail")

    monkeypatch.setattr(fr, "_load_via_ocp_native", _fail_ocp)
    monkeypatch.setattr(fr, "_load_via_cadquery", _fail_cq)
    monkeypatch.setattr(fr, "_load_via_gmsh", _fail_gmsh)

    # 존재하지 않는 더미 경로 — 각 함수는 raise 되므로 경로 내용은 무관.
    fake = tmp_path / "dummy.step"
    fake.write_text("")

    with pytest.raises(ValueError) as ei:
        fr._load_via_cad(fake, ".step")
    msg = str(ei.value)
    assert "OCP" in msg
    assert "cadquery" in msg
    assert "gmsh" in msg


def test_file_reader_cad_ocp_success_skips_fallbacks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """OCP native 가 성공하면 cadquery / gmsh 는 호출되지 않음."""
    import core.analyzer.file_reader as fr
    import trimesh

    # OCP 가 stub 으로 성공 반환
    sentinel = trimesh.Trimesh(
        vertices=[[0, 0, 0], [1, 0, 0], [0, 1, 0]],
        faces=[[0, 1, 2]],
        process=False,
    )
    called = {"cq": 0, "gmsh": 0}

    def _ok_ocp(path, fmt):
        return sentinel

    def _track_cq(path, fmt):
        called["cq"] += 1
        raise RuntimeError("should not be called")

    def _track_gmsh(path, fmt):
        called["gmsh"] += 1
        raise RuntimeError("should not be called")

    monkeypatch.setattr(fr, "_load_via_ocp_native", _ok_ocp)
    monkeypatch.setattr(fr, "_load_via_cadquery", _track_cq)
    monkeypatch.setattr(fr, "_load_via_gmsh", _track_gmsh)

    fake = tmp_path / "dummy.step"
    fake.write_text("")

    result = fr._load_via_cad(fake, ".step")
    assert result is sentinel
    assert called["cq"] == 0
    assert called["gmsh"] == 0


# ---------------------------------------------------------------------------
# 실제 OCP 경로 (설치 시에만)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _ocp_available(), reason="OCP not installed")
def test_ocp_native_loads_cube_step() -> None:
    """tests/benchmarks/box.step 또는 cube.step 이 OCP 로 로딩."""
    for candidate in ("box.step", "cube.step"):
        path = Path("tests/benchmarks") / candidate
        if path.exists():
            V, F = load_cad_native(path, ".step")
            assert V.shape[1] == 3
            assert F.shape[1] == 3
            assert V.shape[0] > 0
            assert F.shape[0] > 0
            return
    pytest.skip("box.step / cube.step 미존재")
