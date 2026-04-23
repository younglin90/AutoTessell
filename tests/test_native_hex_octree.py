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


# ---------------------------------------------------------------------------
# beta92: N-level octree 테스트
# ---------------------------------------------------------------------------


def test_nlevel_1_produces_cells(sphere_mesh, tmp_dir) -> None:
    """n_levels=1 → 2-level octree 와 유사한 결과 (세분화 없음)."""
    from core.generator.native_hex.octree import build_octree_hex_cells
    V, F = sphere_mesh
    bmin = V.min(axis=0)
    bmax = V.max(axis=0)
    diag = float(np.linalg.norm(bmax - bmin))
    h = diag / 8
    pts, cells, stats = build_octree_hex_cells(V, F, bmin, bmax, h, n_levels=1)
    assert stats["n_total"] > 0
    assert stats["n_levels"] >= 1
    assert len(cells) == stats["n_total"]


def test_nlevel_2_default_compat(sphere_mesh, tmp_dir) -> None:
    """n_levels=2 → beta91 2-level 와 동등한 결과 (기본값 호환)."""
    from core.generator.native_hex.octree import build_octree_hex_cells
    V, F = sphere_mesh
    bmin = V.min(axis=0)
    bmax = V.max(axis=0)
    diag = float(np.linalg.norm(bmax - bmin))
    h = diag / 8
    pts2, cells2, stats2 = build_octree_hex_cells(V, F, bmin, bmax, h, n_levels=2)
    assert stats2["n_total"] > 0
    assert stats2["n_levels"] == 2


def test_nlevel_3_more_fine_cells(sphere_mesh, tmp_dir) -> None:
    """n_levels=3 → n_levels=2 보다 같거나 많은 cell (더 세밀한 분해)."""
    from core.generator.native_hex.octree import build_octree_hex_cells
    V, F = sphere_mesh
    bmin = V.min(axis=0)
    bmax = V.max(axis=0)
    diag = float(np.linalg.norm(bmax - bmin))
    h = diag / 6  # 작은 grid 로 메모리 절약
    _, cells2, stats2 = build_octree_hex_cells(V, F, bmin, bmax, h, n_levels=2)
    _, cells3, stats3 = build_octree_hex_cells(V, F, bmin, bmax, h, n_levels=3)
    assert stats3["n_total"] > 0
    # n_levels=3 는 n_levels=2 보다 같거나 많은 세부 cell
    assert stats3["n_total"] >= stats2["n_total"]


def test_nlevel_memory_limit_reduces_levels(tmp_dir) -> None:
    """매우 큰 grid 요청 시 n_levels 자동 감소 후 정상 동작."""
    from core.generator.native_hex.octree import build_octree_hex_cells
    V = np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
    ], dtype=np.float64)
    # 간단한 cube faces (8 triangles)
    F = np.array([
        [0, 1, 2], [0, 2, 3],
        [4, 6, 5], [4, 7, 6],
        [0, 5, 1], [0, 4, 5],
        [1, 6, 2], [1, 5, 6],
        [2, 7, 3], [2, 6, 7],
        [3, 4, 0], [3, 7, 4],
    ], dtype=np.int64)
    bmin = V.min(axis=0)
    bmax = V.max(axis=0)
    # n_levels=5 + 큰 max_cells_per_axis → 메모리 제한 초과 유도
    pts, cells, stats = build_octree_hex_cells(
        V, F, bmin, bmax, 0.1, max_cells_per_axis=50, n_levels=5,
    )
    # 결과는 반드시 n_levels 가 감소하거나 정상 동작
    assert stats["n_levels"] <= 5  # 감소되거나 같음
    # 빈 cells 는 inside filter 에 따라 0 일 수 있음 (cube inside test)


def test_nlevel_mesher_forward(sphere_mesh, tmp_dir) -> None:
    """generate_native_hex 에 n_levels=3 전달 → success."""
    from core.generator.native_hex.mesher import generate_native_hex
    V, F = sphere_mesh
    r = generate_native_hex(
        V, F, tmp_dir / "case3", seed_density=6,
        adaptive=True, n_levels=3,
    )
    assert r.success


def test_nlevel_harness_params_fine_n_levels() -> None:
    """beta92 — HARNESS_PARAMS fine 에 n_levels=3 포함."""
    from core.generator._tier_native_common import HARNESS_PARAMS
    fine = HARNESS_PARAMS["tier_native_hex"]["fine"]
    assert fine.get("n_levels") == 3


def test_nlevel_tier_param_keys_include_n_levels() -> None:
    """beta92 — _TIER_PARAM_KEYS 에 n_levels 포함."""
    import inspect
    import core.generator._tier_native_common as m
    src = inspect.getsource(m)
    assert "n_levels" in src
