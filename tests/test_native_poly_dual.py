"""native_poly dual 변환 + harness 회귀 테스트."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import numpy as np
import pytest

from core.analyzer.readers import read_stl
from core.evaluator.native_checker import NativeMeshChecker
from core.generator.native_poly import (
    run_native_poly_harness,
    tet_to_poly_dual,
)
from core.generator.native_tet import generate_native_tet

_REPO = Path(__file__).resolve().parents[1]
SPHERE_STL = _REPO / "tests" / "benchmarks" / "sphere.stl"


@pytest.fixture
def tmp_case_dir():
    tmp = Path(tempfile.mkdtemp(prefix="poly_dual_"))
    try:
        yield tmp
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_tet_to_poly_dual_from_sphere(tmp_case_dir: Path) -> None:
    if not SPHERE_STL.exists():
        pytest.skip()
    m = read_stl(SPHERE_STL)
    base = tmp_case_dir / "base_tet"
    tet_res = generate_native_tet(
        m.vertices, m.faces, base, seed_density=8,
    )
    assert tet_res.success
    assert tet_res.tets is not None
    assert tet_res.tet_points is not None

    out = tmp_case_dir / "dual"
    res = tet_to_poly_dual(
        tet_res.tet_points, tet_res.tets, out,
    )
    assert res.success, res.message
    assert res.n_cells > 0
    assert res.n_points > 0
    # polyMesh 파일 생성 확인
    for name in ("points", "faces", "owner", "neighbour", "boundary"):
        assert (out / "constant" / "polyMesh" / name).exists()


def test_tet_to_poly_dual_polymesh_valid(tmp_case_dir: Path) -> None:
    """dual 결과가 NativeMeshChecker 로 검증되고 negative_volumes=0."""
    if not SPHERE_STL.exists():
        pytest.skip()
    m = read_stl(SPHERE_STL)
    base = tmp_case_dir / "base_tet"
    tet_res = generate_native_tet(
        m.vertices, m.faces, base, seed_density=10,
    )
    assert tet_res.success and tet_res.tets is not None

    out = tmp_case_dir / "dual"
    res = tet_to_poly_dual(tet_res.tet_points, tet_res.tets, out)
    assert res.success

    chk = NativeMeshChecker().run(out)
    assert chk.negative_volumes == 0, (
        f"negative_volumes = {chk.negative_volumes}"
    )


def test_native_poly_harness_passes_on_sphere(tmp_case_dir: Path) -> None:
    """harness 가 sphere 에서 negative_volumes=0 + cells>0 으로 PASS 한다."""
    if not SPHERE_STL.exists():
        pytest.skip()
    m = read_stl(SPHERE_STL)
    res = run_native_poly_harness(
        m.vertices, m.faces, tmp_case_dir,
        seed_density=10, max_iter=3,
    )
    assert res.success, res.message
    assert res.iterations >= 1
    assert res.n_cells > 0
    assert res.negative_volumes == 0


def test_native_poly_harness_empty_input_fails(tmp_case_dir: Path) -> None:
    V = np.zeros((0, 3))
    F = np.zeros((0, 3), dtype=np.int64)
    res = run_native_poly_harness(V, F, tmp_case_dir, max_iter=1)
    assert res.success is False


def test_tet_to_poly_dual_writes_polymesh_structure(tmp_case_dir: Path) -> None:
    """dual 결과 polyMesh 가 읽을 수 있는 format 인지 확인."""
    if not SPHERE_STL.exists():
        pytest.skip()
    from core.utils.polymesh_reader import (
        parse_foam_boundary, parse_foam_faces,
        parse_foam_labels, parse_foam_points,
    )
    m = read_stl(SPHERE_STL)
    base = tmp_case_dir / "base_tet"
    tet_res = generate_native_tet(
        m.vertices, m.faces, base, seed_density=8,
    )
    assert tet_res.success and tet_res.tets is not None
    out = tmp_case_dir / "dual"
    tet_to_poly_dual(tet_res.tet_points, tet_res.tets, out)
    poly_dir = out / "constant" / "polyMesh"
    pts = parse_foam_points(poly_dir / "points")
    faces = parse_foam_faces(poly_dir / "faces")
    owner = parse_foam_labels(poly_dir / "owner")
    nbr = parse_foam_labels(poly_dir / "neighbour")
    bnd = parse_foam_boundary(poly_dir / "boundary")
    assert len(pts) > 0
    assert len(faces) > 0
    assert len(owner) == len(faces)
    assert len(nbr) < len(faces)  # boundary faces 는 neighbour 에 없음
    assert len(bnd) >= 1
