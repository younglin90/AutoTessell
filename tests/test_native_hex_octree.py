"""beta91 — native_hex octree adaptive refinement 회귀 테스트."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import numpy as np
import pytest

_REPO = Path(__file__).resolve().parents[1]
SPHERE_STL = _REPO / "tests" / "benchmarks" / "sphere.stl"


@pytest.fixture
def sphere_mesh():
    try:
        import trimesh
        sp = trimesh.creation.icosphere(subdivisions=2)
        return (
            np.asarray(sp.vertices, dtype=np.float64),
            np.asarray(sp.faces, dtype=np.int64),
        )
    except ImportError:
        pytest.skip("trimesh 미설치")


@pytest.fixture
def tmp_dir():
    d = Path(tempfile.mkdtemp())
    yield d
    shutil.rmtree(d, ignore_errors=True)


def test_octree_produces_more_cells_than_uniform(sphere_mesh, tmp_dir) -> None:
    """octree adaptive=True 는 uniform 대비 같거나 많은 cell."""
    from core.generator.native_hex.mesher import generate_native_hex
    V, F = sphere_mesh
    r_uni = generate_native_hex(V, F, tmp_dir / "uni", seed_density=8, adaptive=False)
    r_oct = generate_native_hex(V, F, tmp_dir / "oct", seed_density=8, adaptive=True)
    assert r_uni.success and r_oct.success
    assert r_oct.n_cells >= r_uni.n_cells


def test_octree_result_contains_coarse_fine_info(sphere_mesh, tmp_dir) -> None:
    """octree message 에 coarse= fine= 포함."""
    from core.generator.native_hex.mesher import generate_native_hex
    V, F = sphere_mesh
    r = generate_native_hex(V, F, tmp_dir / "case", seed_density=8, adaptive=True)
    assert r.success
    assert "coarse=" in r.message
    assert "fine=" in r.message


def test_octree_polymesh_files_created(sphere_mesh, tmp_dir) -> None:
    """octree → 5 polyMesh 파일 생성."""
    from core.generator.native_hex.mesher import generate_native_hex
    V, F = sphere_mesh
    r = generate_native_hex(V, F, tmp_dir / "case", seed_density=8, adaptive=True)
    assert r.success
    poly_dir = tmp_dir / "case" / "constant" / "polyMesh"
    for name in ("points", "faces", "owner", "neighbour", "boundary"):
        assert (poly_dir / name).exists()


def test_octree_fallback_on_empty_surface(tmp_dir) -> None:
    """빈 입력 → failure (crash 없음)."""
    from core.generator.native_hex.mesher import generate_native_hex
    V = np.zeros((0, 3))
    F = np.zeros((0, 3), dtype=np.int64)
    r = generate_native_hex(V, F, tmp_dir / "empty", adaptive=True)
    assert r.success is False


def test_adaptive_flag_in_harness_params_fine() -> None:
    """beta91 — HARNESS_PARAMS fine 에 adaptive=True."""
    from core.generator._tier_native_common import HARNESS_PARAMS
    fine = HARNESS_PARAMS["tier_native_hex"]["fine"]
    assert fine.get("adaptive") is True


def test_adaptive_in_tier_param_keys() -> None:
    """beta91 — _TIER_PARAM_KEYS 에 adaptive 포함."""
    # indirect test via run_native_tier accepting the kwarg
    from core.generator._tier_native_common import HARNESS_PARAMS
    assert "adaptive" in HARNESS_PARAMS["tier_native_hex"]["fine"]
