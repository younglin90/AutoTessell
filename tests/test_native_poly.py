"""native_poly MVP (scipy Voronoi) 회귀 테스트.

MVP 특성상 OpenFOAM checkMesh 로는 open cell 경고가 남을 수 있으나 (boundary
clipping 미완성), polyMesh 파일 생성 + cell 수 > 0 + cells=polyhedra 만 확인.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import numpy as np
import pytest

from core.analyzer.readers import read_stl
from core.generator.native_poly import generate_native_poly_voronoi

_REPO = Path(__file__).resolve().parents[1]
SPHERE_STL = _REPO / "tests" / "benchmarks" / "sphere.stl"


@pytest.fixture
def tmp_case_dir():
    tmp = Path(tempfile.mkdtemp(prefix="native_poly_"))
    try:
        yield tmp
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_native_poly_sphere_produces_cells(tmp_case_dir: Path) -> None:
    if not SPHERE_STL.exists():
        pytest.skip()
    m = read_stl(SPHERE_STL)
    res = generate_native_poly_voronoi(
        m.vertices, m.faces, tmp_case_dir, seed_density=10,
    )
    assert res.success, res.message
    assert res.n_cells > 0


def test_native_poly_polymesh_files_exist(tmp_case_dir: Path) -> None:
    if not SPHERE_STL.exists():
        pytest.skip()
    m = read_stl(SPHERE_STL)
    res = generate_native_poly_voronoi(
        m.vertices, m.faces, tmp_case_dir, seed_density=8,
    )
    assert res.success
    poly_dir = tmp_case_dir / "constant" / "polyMesh"
    for name in ("points", "faces", "owner", "neighbour", "boundary"):
        assert (poly_dir / name).exists()


def test_native_poly_denser_seed_more_cells(tmp_case_dir: Path) -> None:
    if not SPHERE_STL.exists():
        pytest.skip()
    m = read_stl(SPHERE_STL)
    r1 = generate_native_poly_voronoi(
        m.vertices, m.faces, tmp_case_dir / "coarse", seed_density=8,
    )
    r2 = generate_native_poly_voronoi(
        m.vertices, m.faces, tmp_case_dir / "fine", seed_density=14,
    )
    assert r1.success and r2.success
    assert r2.n_cells >= r1.n_cells


def test_native_poly_empty_input_fails(tmp_case_dir: Path) -> None:
    V = np.zeros((0, 3))
    F = np.zeros((0, 3), dtype=np.int64)
    res = generate_native_poly_voronoi(V, F, tmp_case_dir)
    assert res.success is False


# ---------------------------------------------------------------------------
# beta98 Task B: n_lloyd 파라미터 + 3D Lloyd CVT 개선 테스트
# ---------------------------------------------------------------------------


def test_native_poly_lloyd_zero_same_as_default(tmp_case_dir: Path) -> None:
    """n_lloyd=0 은 Lloyd 정제 없이 기존 동작과 동일 — 성공해야 함."""
    if not SPHERE_STL.exists():
        pytest.skip()
    m = read_stl(SPHERE_STL)
    res = generate_native_poly_voronoi(
        m.vertices, m.faces, tmp_case_dir, seed_density=8, n_lloyd=0,
    )
    assert res.success, res.message
    assert res.n_cells > 0


def test_native_poly_lloyd_positive_succeeds(tmp_case_dir: Path) -> None:
    """n_lloyd=2 (기본값) 는 성공하고 cell 을 생성해야 함."""
    if not SPHERE_STL.exists():
        pytest.skip()
    m = read_stl(SPHERE_STL)
    res = generate_native_poly_voronoi(
        m.vertices, m.faces, tmp_case_dir, seed_density=8, n_lloyd=2,
    )
    assert res.success, res.message
    assert res.n_cells > 0


def test_native_poly_lloyd_signature_accepts_n_lloyd() -> None:
    """generate_native_poly_voronoi 가 n_lloyd keyword 를 받아야 함."""
    import inspect
    sig = inspect.signature(generate_native_poly_voronoi)
    assert "n_lloyd" in sig.parameters, "n_lloyd 파라미터 누락"
    assert sig.parameters["n_lloyd"].default == 2
