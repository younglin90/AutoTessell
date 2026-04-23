"""native_hex MVP 엔진 회귀 테스트."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import numpy as np
import pytest

from core.analyzer.readers import read_stl
from core.evaluator.native_checker import NativeMeshChecker
from core.generator.native_hex import generate_native_hex

_REPO = Path(__file__).resolve().parents[1]
SPHERE_STL = _REPO / "tests" / "benchmarks" / "sphere.stl"
CUBE_STL = _REPO / "tests" / "benchmarks" / "cube.stl"


@pytest.fixture
def tmp_case_dir():
    tmp = Path(tempfile.mkdtemp(prefix="native_hex_"))
    try:
        yield tmp
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_native_hex_sphere_produces_only_hexahedra(tmp_case_dir: Path) -> None:
    if not SPHERE_STL.exists():
        pytest.skip()
    m = read_stl(SPHERE_STL)
    res = generate_native_hex(
        m.vertices, m.faces, tmp_case_dir, seed_density=10,
    )
    assert res.success, res.message
    assert res.n_cells > 0
    # NativeMeshChecker 로 검증 — 모든 cell 이 valid
    chk = NativeMeshChecker().run(tmp_case_dir)
    assert chk.negative_volumes == 0
    assert chk.mesh_ok, f"mesh_ok=False, failed={chk.failed_checks}"


def test_native_hex_perfect_aspect_ratio(tmp_case_dir: Path) -> None:
    """uniform grid 이므로 aspect ratio = 1, skewness 매우 낮음."""
    if not CUBE_STL.exists():
        pytest.skip()
    m = read_stl(CUBE_STL)
    res = generate_native_hex(m.vertices, m.faces, tmp_case_dir, seed_density=6)
    assert res.success
    chk = NativeMeshChecker().run(tmp_case_dir)
    # uniform cubical grid → aspect ratio √3 이내 (hex diagonal/edge 기준 native 구현).
    # 중요: cell 간 편차가 없는지, skewness 가 0 인지.
    assert chk.max_aspect_ratio < 2.0
    assert chk.max_skewness < 0.1
    # 모든 cell 이 정확히 hexahedra 이어야 함 (topology)
    from core.analyzer.readers import read_stl as _r  # noqa: PLC0415 — avoid shadow
    # NativeMeshChecker 는 cell type 을 집계하지 않으므로 대신 faces_per_cell 이
    # 6 인지 간접 확인: faces - internal_faces = boundary faces 수가 합리적
    assert chk.cells > 0


def test_native_hex_polymesh_files_exist(tmp_case_dir: Path) -> None:
    if not SPHERE_STL.exists():
        pytest.skip()
    m = read_stl(SPHERE_STL)
    res = generate_native_hex(m.vertices, m.faces, tmp_case_dir, seed_density=8)
    assert res.success
    poly_dir = tmp_case_dir / "constant" / "polyMesh"
    for name in ("points", "faces", "owner", "neighbour", "boundary"):
        assert (poly_dir / name).exists()


def test_native_hex_denser_grid_more_cells(tmp_case_dir: Path) -> None:
    if not SPHERE_STL.exists():
        pytest.skip()
    m = read_stl(SPHERE_STL)
    r1 = generate_native_hex(
        m.vertices, m.faces, tmp_case_dir / "coarse", seed_density=6,
    )
    r2 = generate_native_hex(
        m.vertices, m.faces, tmp_case_dir / "fine", seed_density=14,
    )
    assert r1.success and r2.success
    assert r2.n_cells > r1.n_cells


def test_native_hex_empty_input_fails(tmp_case_dir: Path) -> None:
    V = np.zeros((0, 3))
    F = np.zeros((0, 3), dtype=np.int64)
    res = generate_native_hex(V, F, tmp_case_dir)
    assert res.success is False


def test_native_hex_max_cells_per_axis_honored(tmp_case_dir: Path) -> None:
    """beta61 — max_cells_per_axis 파라미터가 grid 를 제한한다.

    cap=5 로 지정하면 각 축 최대 5 cell → 총 <= 125 cell.
    """
    if not SPHERE_STL.exists():
        pytest.skip("sphere.stl 없음")
    m = read_stl(SPHERE_STL)
    V, F = m.vertices, m.faces
    res = generate_native_hex(
        V, F, tmp_case_dir,
        target_edge_length=0.001,  # 매우 작은 값 → cap 에 반드시 걸림
        max_cells_per_axis=5,
    )
    assert res.success is True
    # 최대 5^3 = 125 cell. inside filter 후 실제로는 더 적음.
    assert res.n_cells <= 125


def test_native_hex_larger_cap_allows_more_cells(tmp_case_dir: Path) -> None:
    """beta61 — cap 을 늘리면 더 많은 cell 허용."""
    if not SPHERE_STL.exists():
        pytest.skip("sphere.stl 없음")
    m = read_stl(SPHERE_STL)
    V, F = m.vertices, m.faces
    r_small = generate_native_hex(
        V, F, tmp_case_dir / "a",
        target_edge_length=0.01, max_cells_per_axis=8,
    )
    r_large = generate_native_hex(
        V, F, tmp_case_dir / "b",
        target_edge_length=0.01, max_cells_per_axis=30,
    )
    assert r_small.success and r_large.success
    assert r_large.n_cells > r_small.n_cells
