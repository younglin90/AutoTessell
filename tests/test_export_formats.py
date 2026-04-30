"""I5 / beta2623 — export 6 포맷 통합 회귀.

CCMIO + CGNS + Fluent + VTK + Tecplot + Plot3D 의 round-trip / 구조 검증을
하나의 테스트 모듈로 통합.

각 포맷:
- 동일한 fake polyMesh (cube) 입력.
- write 성공 + 파일 존재 확인.
- 포맷별 특정 marker / 헤더 검증.
"""
from __future__ import annotations

import sys
import tempfile
import types
from pathlib import Path

import numpy as np
import pytest


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


@pytest.fixture
def fake_cube_polymesh(monkeypatch):
    """Cube polyMesh fixture (8 vertex, 1 hex, walls patch)."""
    fake_pm = {
        "points": [
            [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
            [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
        ],
        "faces": [
            [0, 1, 2, 3], [4, 5, 6, 7],
            [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7],
        ],
        "owner": [0, 0, 0, 0, 0, 0],
        "neighbour": [],
        "boundary": [
            {"name": "walls", "type": "wall", "nFaces": 6, "startFace": 0},
        ],
    }
    fake_mod = types.ModuleType("core.utils.poly_mesh_reader")
    fake_mod.read_poly_mesh = lambda _p: fake_pm
    monkeypatch.setitem(sys.modules, "core.utils.poly_mesh_reader", fake_mod)
    return fake_pm


def test_round_trip_ccmio(fake_cube_polymesh):
    """CCMIO HDF5 round-trip — write + read."""
    try:
        import h5py  # noqa: F401
    except ImportError:
        pytest.skip("h5py not installed")
    from core.utils.ccmio_writer import write_ccmio, read_ccmio
    with tempfile.TemporaryDirectory() as td:
        pm = Path(td) / "pm"; pm.mkdir()
        out = Path(td) / "cube.ccm"
        r = write_ccmio(str(pm), str(out))
        assert r.success
        assert r.n_vertices == 8 and r.n_cells == 1
        rd = read_ccmio(str(out))
        assert rd is not None
        assert np.asarray(rd["points"]).shape == (8, 3)


def test_write_cgns(fake_cube_polymesh):
    try:
        import h5py  # noqa: F401
    except ImportError:
        pytest.skip("h5py not installed")
    from core.utils.cgns_writer import write_cgns
    with tempfile.TemporaryDirectory() as td:
        pm = Path(td) / "pm"; pm.mkdir()
        out = Path(td) / "cube.cgns"
        r = write_cgns(str(pm), str(out))
        assert r.success and r.n_nodes == 8


def test_write_fluent_msh(fake_cube_polymesh):
    from core.utils.fluent_writer import write_fluent_msh
    with tempfile.TemporaryDirectory() as td:
        pm = Path(td) / "pm"; pm.mkdir()
        out = Path(td) / "cube.msh"
        r = write_fluent_msh(str(pm), str(out))
        assert r.success
        content = out.read_text(encoding="ascii")
        assert "(2 3)" in content


def test_write_vtu(fake_cube_polymesh):
    from core.utils.vtk_writer import write_vtu
    with tempfile.TemporaryDirectory() as td:
        pm = Path(td) / "pm"; pm.mkdir()
        out = Path(td) / "cube.vtu"
        r = write_vtu(str(pm), str(out))
        assert r.success and r.n_points == 8
        content = out.read_text(encoding="utf-8")
        assert "<VTKFile" in content


def test_write_tecplot_plt(fake_cube_polymesh):
    from core.utils.tecplot_writer import write_tecplot_plt
    with tempfile.TemporaryDirectory() as td:
        pm = Path(td) / "pm"; pm.mkdir()
        out = Path(td) / "cube.plt"
        r = write_tecplot_plt(str(pm), str(out))
        assert r.success
        content = out.read_text(encoding="ascii")
        assert "VARIABLES" in content


def test_write_plot3d_grid(fake_cube_polymesh):
    from core.utils.plot3d_writer import write_plot3d_grid
    with tempfile.TemporaryDirectory() as td:
        pm = Path(td) / "pm"; pm.mkdir()
        out = Path(td) / "grid.x"
        # ASCII for easier validation.
        r = write_plot3d_grid(str(pm), str(out), binary=False)
        assert r.success and r.n_total_points == 8
        content = out.read_text(encoding="ascii")
        # 1 nblocks + ni nj nk + coords.
        assert "1\n" in content


def test_write_nastran_bdf(fake_cube_polymesh):
    """K1 / beta2633 — Nastran .bdf writer."""
    from core.utils.nastran_writer import write_nastran_bdf
    with tempfile.TemporaryDirectory() as td:
        pm = Path(td) / "pm"; pm.mkdir()
        out = Path(td) / "cube.bdf"
        r = write_nastran_bdf(str(pm), str(out))
        assert r.success
        assert r.n_grids == 8
        assert r.n_elements == 1
        content = out.read_text(encoding="ascii")
        assert "BEGIN BULK" in content
        assert "GRID" in content
        assert "ENDDATA" in content


def test_write_avs_ucd(fake_cube_polymesh):
    """J1 / beta2626 — AVS UCD writer."""
    from core.utils.avs_ucd_writer import write_avs_ucd
    with tempfile.TemporaryDirectory() as td:
        pm = Path(td) / "pm"; pm.mkdir()
        out = Path(td) / "cube.ucd"
        r = write_avs_ucd(str(pm), str(out))
        assert r.success and r.n_nodes == 8 and r.n_cells == 1
        content = out.read_text(encoding="ascii")
        # 첫 줄 = header (n_nodes n_cells ...).
        first_line = content.splitlines()[0].strip()
        assert first_line.startswith("8 1")


def test_write_gambit_neu(fake_cube_polymesh):
    """J2 / beta2627 — Gambit .neu writer."""
    from core.utils.gambit_neu_writer import write_gambit_neu
    with tempfile.TemporaryDirectory() as td:
        pm = Path(td) / "pm"; pm.mkdir()
        out = Path(td) / "cube.neu"
        r = write_gambit_neu(str(pm), str(out))
        assert r.success and r.n_nodes == 8
        content = out.read_text(encoding="ascii")
        assert "CONTROL INFO" in content
        assert "NODAL COORDINATES" in content
        assert "ELEMENTS/CELLS" in content
        assert "ELEMENT GROUP" in content


def test_starccm_unified_dispatch(fake_cube_polymesh):
    """write_starccm 의 fmt 분기 통합."""
    from core.utils.mesh_exporter_starccm import write_starccm
    try:
        import h5py  # noqa: F401
        with tempfile.TemporaryDirectory() as td:
            pm = Path(td) / "pm"; pm.mkdir()
            for fmt in ("binary", "ccmio"):
                out = Path(td) / f"cube_{fmt}.ccm"
                r = write_starccm(str(pm), str(out), fmt=fmt)
                assert r.success or "h5py" in (r.message or ""), \
                    f"fmt={fmt} failed: {r.message}"
    except ImportError:
        pytest.skip("h5py not installed")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
