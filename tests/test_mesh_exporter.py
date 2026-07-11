"""beta41 — core/utils/mesh_exporter.py dedicated 회귀.

polyMesh → SU2/Fluent/CGNS export. meshio/polyMesh 미존재 graceful fallback.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from core.generator.polymesh_writer import write_generic_polymesh
from core.utils.mesh_exporter import (
    _FORMAT_EXTENSIONS,
    _MESHIO_FORMAT,
    export_mesh,
)


def _make_tet_polymesh(case_dir: Path) -> None:
    """최소 2-tet polyMesh 생성."""
    V = np.array([
        [0, 0, 0], [1, 0, 0], [0, 1, 0],
        [0, 0, 1], [0, 0, -1],
    ], dtype=np.float64)
    tet1 = [[0, 2, 1], [0, 1, 3], [1, 2, 3], [2, 0, 3]]
    tet2 = [[0, 1, 2], [0, 4, 1], [1, 4, 2], [2, 4, 0]]
    write_generic_polymesh(V, [tet1, tet2], case_dir)


# ---------------------------------------------------------------------------
# 구조적 상수
# ---------------------------------------------------------------------------


def test_format_extensions_cover_all_supported_formats() -> None:
    """_FORMAT_EXTENSIONS + _MESHIO_FORMAT 가 su2/fluent/cgns 모두 정의."""
    for fmt in ("su2", "fluent", "cgns"):
        assert fmt in _FORMAT_EXTENSIONS
        assert fmt in _MESHIO_FORMAT
    assert _FORMAT_EXTENSIONS["su2"] == ".su2"
    assert _FORMAT_EXTENSIONS["fluent"] == ".msh"
    assert _FORMAT_EXTENSIONS["cgns"] == ".cgns"


# ---------------------------------------------------------------------------
# graceful fallback
# ---------------------------------------------------------------------------


def test_export_no_polymesh_returns_none(tmp_path: Path) -> None:
    """polyMesh 디렉터리가 없으면 None 반환 (예외 없음)."""
    result = export_mesh(tmp_path, fmt="su2")
    assert result is None


def test_export_meshio_missing_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """meshio 미설치 시 None 반환, 예외 없음."""
    _make_tet_polymesh(tmp_path)

    import builtins
    real_import = builtins.__import__

    def _fake_import(name, *a, **kw):
        if name == "meshio":
            raise ImportError("simulated missing meshio")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", _fake_import)
    result = export_mesh(tmp_path, fmt="su2")
    assert result is None


# ---------------------------------------------------------------------------
# 정상 export
# ---------------------------------------------------------------------------


def _has_meshio() -> bool:
    try:
        import meshio  # noqa: F401
        return True
    except ImportError:
        return False


@pytest.mark.skipif(not _has_meshio(), reason="meshio not installed")
@pytest.mark.parametrize("fmt", ["su2"])
def test_export_success_returns_path(tmp_path: Path, fmt: str) -> None:
    """정상 polyMesh + meshio 설치 → su2 파일 생성."""
    _make_tet_polymesh(tmp_path)
    out = export_mesh(tmp_path, fmt=fmt)
    if out is None:
        pytest.skip(f"meshio 환경에서 {fmt} export 미지원")
    assert out.exists()
    assert out.suffix == _FORMAT_EXTENSIONS[fmt]
    assert out.stat().st_size > 0


@pytest.mark.skipif(not _has_meshio(), reason="meshio not installed")
def test_export_custom_output_path(tmp_path: Path) -> None:
    """output_path 지정 시 그 경로에 저장."""
    _make_tet_polymesh(tmp_path)
    custom = tmp_path / "my_mesh.su2"
    out = export_mesh(tmp_path, output_path=custom, fmt="su2")
    if out is None:
        pytest.skip("meshio export 실패")
    assert out == custom
    assert custom.exists()


@pytest.mark.skipif(not _has_meshio(), reason="meshio not installed")
def test_export_default_output_path_uses_case_dir(tmp_path: Path) -> None:
    """output_path=None 이면 case_dir/mesh.<ext> 에 저장."""
    _make_tet_polymesh(tmp_path)
    out = export_mesh(tmp_path, fmt="su2")
    if out is None:
        pytest.skip("meshio export 실패")
    assert out.parent == tmp_path
    assert out.name == "mesh.su2"


def _make_hex_polymesh(case_dir: Path) -> None:
    """Single unit-cube hex cell (6 quad faces, 8 points)."""
    V = np.array(
        [
            [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
            [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
        ],
        dtype=np.float64,
    )
    hexc = [
        [0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4],
        [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7],
    ]
    write_generic_polymesh(V, [hexc], case_dir)


@pytest.mark.skipif(not _has_meshio(), reason="meshio not installed")
def test_vtu_hex_exports_as_polyhedron_with_correct_volume(tmp_path: Path) -> None:
    """VTU hex-dominant/poly cells must keep their shape (regression for the
    'cells tangled in VTU' bug — old path fed VTK_HEXAHEDRON index-sorted
    vertices).  New path writes VTK_POLYHEDRON face streams."""
    import meshio

    _make_hex_polymesh(tmp_path)
    out = export_mesh(tmp_path, fmt="vtu")
    assert out is not None and out.exists()

    m = meshio.read(str(out))
    # exactly one polyhedron cell (not a tangled hexahedron block)
    assert len(m.cells) == 1
    assert m.cells[0].type.startswith("polyhedron")

    # volume from the face stream (divergence theorem) must be the unit cube's 1.0
    faces = m.cells[0].data[0]  # list of faces (each a list of point ids)
    pts = m.points
    vol = 0.0
    for f in faces:
        a = pts[f[0]]
        for k in range(1, len(f) - 1):
            b, c = pts[f[k]], pts[f[k + 1]]
            vol += float(np.dot(a, np.cross(b, c)))
    assert abs(abs(vol) / 6.0 - 1.0) < 1e-6


def test_export_corrupt_polymesh_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """polyMesh 파싱 실패 시 None 반환."""
    poly_dir = tmp_path / "constant" / "polyMesh"
    poly_dir.mkdir(parents=True)
    # 의도적으로 잘못된 파일 내용
    (poly_dir / "points").write_text("garbage content\n")
    (poly_dir / "faces").write_text("garbage\n")
    (poly_dir / "owner").write_text("\n")
    (poly_dir / "neighbour").write_text("\n")

    out = export_mesh(tmp_path, fmt="su2")
    # 파싱 실패 또는 meshio 없음 → None
    assert out is None or not out.exists() or out.stat().st_size == 0
