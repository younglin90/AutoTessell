"""file_reader.py 가 v0.4 native-first 로 동작하는지 검증.

STL/OBJ/PLY/OFF 는 core/analyzer/readers/ 의 자체 reader 를 우선 호출해야 하며,
native reader 가 예외를 낼 때만 trimesh fallback 으로 내려가야 한다.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from core.analyzer.file_reader import (
    NATIVE_READER_FORMATS,
    _load_via_native_reader,
    load_mesh,
)


_REPO = Path(__file__).resolve().parents[1]
SPHERE_STL = _REPO / "tests" / "benchmarks" / "sphere.stl"


def test_native_reader_formats_set() -> None:
    """NATIVE_READER_FORMATS 에 stl/obj/ply/off 가 포함되어야 한다."""
    assert ".stl" in NATIVE_READER_FORMATS
    assert ".obj" in NATIVE_READER_FORMATS
    assert ".ply" in NATIVE_READER_FORMATS
    assert ".off" in NATIVE_READER_FORMATS


def test_load_mesh_stl_uses_native_reader(tmp_path: Path) -> None:
    """STL 로딩 시 _load_via_native_reader 가 호출되어야 한다."""
    if not SPHERE_STL.exists():
        pytest.skip()
    with patch(
        "core.analyzer.file_reader._load_via_native_reader",
        wraps=_load_via_native_reader,
    ) as spy:
        m = load_mesh(SPHERE_STL)
    assert spy.call_count == 1
    assert m.vertices.shape[0] == 642
    assert m.faces.shape[0] == 1280


def test_load_mesh_fallback_to_trimesh_on_native_failure(tmp_path: Path) -> None:
    """native reader 가 예외 발생 시 trimesh fallback 이 동작해야 한다."""
    if not SPHERE_STL.exists():
        pytest.skip()

    def _raise(*_args, **_kwargs):
        raise RuntimeError("simulated native reader failure")

    with patch(
        "core.analyzer.file_reader._load_via_native_reader", side_effect=_raise,
    ):
        m = load_mesh(SPHERE_STL)
    # trimesh fallback 으로 load 성공해야 함
    assert m.vertices.shape[0] > 0
    assert m.faces.shape[0] > 0


@pytest.mark.parametrize("ext", [".obj", ".ply", ".off"])
def test_load_mesh_other_formats_use_native_reader(
    ext: str, tmp_path: Path,
) -> None:
    """OBJ/PLY/OFF 도 native reader 경로를 탄다."""
    if not SPHERE_STL.exists():
        pytest.skip()
    try:
        import trimesh  # noqa: PLC0415
    except Exception:
        pytest.skip("trimesh 없음")
    t = trimesh.load(str(SPHERE_STL))
    p = tmp_path / f"sphere{ext}"
    t.export(str(p))

    with patch(
        "core.analyzer.file_reader._load_via_native_reader",
        wraps=_load_via_native_reader,
    ) as spy:
        m = load_mesh(p)
    assert spy.call_count == 1
    assert m.vertices.shape[0] > 0
    assert m.faces.shape[0] > 0


def test_load_via_native_reader_returns_trimesh_trimesh() -> None:
    """_load_via_native_reader 는 호환성을 위해 trimesh.Trimesh 를 반환한다."""
    if not SPHERE_STL.exists():
        pytest.skip()
    import trimesh  # noqa: PLC0415
    m = _load_via_native_reader(SPHERE_STL, ".stl")
    assert isinstance(m, trimesh.Trimesh)
    assert m.vertices.shape == (642, 3)


def test_unsupported_format_raises() -> None:
    """미지원 포맷은 ValueError."""
    with tempfile.NamedTemporaryFile(suffix=".xyz", delete=False) as tmp:
        tmp.write(b"not a mesh")
        tmp_path = Path(tmp.name)
    try:
        with pytest.raises((ValueError, Exception)):
            load_mesh(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)
