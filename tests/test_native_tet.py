"""native_tet MVP 엔진 회귀 테스트."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import numpy as np
import pytest

from core.analyzer.readers import read_stl
from core.generator.native_tet import generate_native_tet

_REPO = Path(__file__).resolve().parents[1]
SPHERE_STL = _REPO / "tests" / "benchmarks" / "sphere.stl"


@pytest.fixture
def sphere_mesh():
    if not SPHERE_STL.exists():
        pytest.skip("sphere.stl 없음")
    return read_stl(SPHERE_STL)


@pytest.fixture
def tmp_case_dir():
    tmp = Path(tempfile.mkdtemp(prefix="native_tet_"))
    try:
        yield tmp
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_native_tet_sphere_produces_cells(sphere_mesh, tmp_case_dir: Path) -> None:
    res = generate_native_tet(
        sphere_mesh.vertices, sphere_mesh.faces, tmp_case_dir,
        seed_density=8,
    )
    assert res.success, f"실패: {res.message}"
    assert res.n_cells > 0
    assert res.n_points > 0


def test_native_tet_writes_polymesh(sphere_mesh, tmp_case_dir: Path) -> None:
    res = generate_native_tet(
        sphere_mesh.vertices, sphere_mesh.faces, tmp_case_dir,
        seed_density=8,
    )
    assert res.success
    poly_dir = tmp_case_dir / "constant" / "polyMesh"
    for name in ("points", "faces", "owner", "neighbour", "boundary"):
        assert (poly_dir / name).exists(), f"{name} 누락"


def test_native_tet_empty_input_fails(tmp_case_dir: Path) -> None:
    V = np.zeros((0, 3))
    F = np.zeros((0, 3), dtype=np.int64)
    res = generate_native_tet(V, F, tmp_case_dir)
    assert res.success is False


def test_native_tet_target_edge_length_override(sphere_mesh, tmp_case_dir: Path) -> None:
    """target_edge_length 를 작게 주면 내부 시드 점이 증가 → cells 증가."""
    res_coarse = generate_native_tet(
        sphere_mesh.vertices, sphere_mesh.faces, tmp_case_dir / "coarse",
        target_edge_length=0.5,
    )
    res_fine = generate_native_tet(
        sphere_mesh.vertices, sphere_mesh.faces, tmp_case_dir / "fine",
        target_edge_length=0.25,
    )
    assert res_coarse.success and res_fine.success
    assert res_fine.n_cells >= res_coarse.n_cells


def test_native_tet_sliver_quality_threshold_loose_keeps_more(
    sphere_mesh, tmp_case_dir: Path,
) -> None:
    """beta62 — sliver_quality_threshold 를 0 (필터 off) 으로 하면 엄격 케이스
    보다 cell 이 많아야 한다. 0.3 은 매우 엄격해서 많이 탈락, 0 은 전부 유지.
    """
    res_strict = generate_native_tet(
        sphere_mesh.vertices, sphere_mesh.faces, tmp_case_dir / "strict",
        seed_density=8, sliver_quality_threshold=0.3,
    )
    res_loose = generate_native_tet(
        sphere_mesh.vertices, sphere_mesh.faces, tmp_case_dir / "loose",
        seed_density=8, sliver_quality_threshold=0.0,
    )
    # 둘 다 성공 (빈 결과가 아니어야)
    assert res_loose.success
    # loose 가 strict 보다 같거나 많은 cell 보유 (sphere 는 일반적으로 많이 유지)
    assert res_loose.n_cells >= res_strict.n_cells


def test_native_tet_harness_params_table_has_q_thresh() -> None:
    """beta62 — HARNESS_PARAMS 3 quality 에 sliver_quality_threshold 키 존재.

    의미론: 낮은 threshold = 관대 (cell 보존, 수렴 쉬움),
            높은 threshold = 엄격 (sliver 제거, 품질↑).
    따라서 draft < standard < fine (엄격도 증가).
    """
    from core.generator._tier_native_common import HARNESS_PARAMS
    tet_table = HARNESS_PARAMS["tier_native_tet"]
    for q in ("draft", "standard", "fine"):
        assert "sliver_quality_threshold" in tet_table[q], q
    assert (
        tet_table["draft"]["sliver_quality_threshold"]
        < tet_table["standard"]["sliver_quality_threshold"]
        < tet_table["fine"]["sliver_quality_threshold"]
    )
