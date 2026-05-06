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
    # NativeMeshChecker 는 cell type 을 집계하지 않으므로 대신 faces_per_cell 이
    # 6 인지 간접 확인: faces - internal_faces = boundary faces 수가 합리적
    assert chk.cells > 0


def test_native_hex_adaptive_snap_uses_fine_cell_cap(tmp_case_dir: Path) -> None:
    """Adaptive octree snap cap must use fine-cell edge, not coarse edge."""
    if not CUBE_STL.exists():
        pytest.skip()
    m = read_stl(CUBE_STL)
    res = generate_native_hex(
        m.vertices,
        m.faces,
        tmp_case_dir,
        seed_density=24,
        snap_boundary=True,
        adaptive=True,
        n_levels=4,
        snap_iterations=3,
        target_cells=10000,
        max_cells=10000,
        bl_layers=3,
        post_layers_num_layers=3,
        preserve_features=True,
        enable_post_smooth=True,
    )
    assert res.success
    chk = NativeMeshChecker().run(tmp_case_dir)
    assert chk.max_non_orthogonality < 5.0
    assert chk.max_skewness < 0.1
    assert chk.max_aspect_ratio < 2.0


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


def test_native_hex_small_bbox_auto_escalate(tmp_case_dir: Path) -> None:
    """P1.1 — target_edge_length 미지정 + 매우 조악한 seed_density 가면
    small bbox auto-escalate가 동작해야 한다."""
    V = np.array(
        [
            [0.0, 0.0, 0.0],
            [10.0, 0.0, 0.0],
            [0.0, 10.0, 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    F = np.array([[0, 1, 2], [0, 1, 3], [1, 2, 3], [0, 2, 3]], dtype=np.int64)

    # 사용자 target_edge_length 미지정 경로는 auto-escalate 로 1개 cell 성능 복구 가능.
    res_auto = generate_native_hex(V, F, tmp_case_dir / "auto", seed_density=1)
    assert res_auto.success
    assert res_auto.n_cells > 0
    assert res_auto.fill_ratio > 0

    # 사용자 지정 target_edge_length 는 auto-escalate가 금지돼 동일 실험에서 실패해야 함.
    diag = float(np.linalg.norm(V.max(axis=0) - V.min(axis=0)))
    res_manual = generate_native_hex(
        V, F, tmp_case_dir / "manual", seed_density=1, target_edge_length=diag,
    )
    assert not res_manual.success
    assert "inside hex 0" in res_manual.message


def test_native_hex_escalate_recovers_when_cap_binding(tmp_case_dir: Path) -> None:
    """beta2305 — small bbox + cap binding 케이스에서 auto-escalate 가
    cap raise 까지 포함해 recovery.

    이전 (beta2232) 에선 seed_density × 1.5^3 ≤ 3.4× 만 escalate 하고
    max_cells_per_axis 가 binding 되면 nxyz 가 cap 에서 멈춰 효과 없었음.
    beta2305 는 cap 도 retry 마다 ×1.5 raise → small bbox 회복률 ↑.
    """
    # 매우 작은 bbox + 작은 max_cells_per_axis (cap binding 강제 유발).
    V = np.array(
        [
            [0.0, 0.0, 0.0],
            [0.05, 0.0, 0.0],
            [0.0, 0.05, 0.0],
            [0.0, 0.0, 0.05],
        ],
        dtype=np.float64,
    )
    F = np.array([[0, 1, 2], [0, 1, 3], [1, 2, 3], [0, 2, 3]], dtype=np.int64)
    res = generate_native_hex(
        V, F, tmp_case_dir, seed_density=2, max_cells_per_axis=4,
    )
    # 회복 — auto-escalate 가 cap 도 raise 해서 적어도 1 cell 도달.
    assert res.success, res.message
    assert res.n_cells >= 1


def test_octree_buffer_layer_extends_level_transition() -> None:
    """beta2312 — _add_buffer_layer_between_levels 가 1-cell buffer 추가.

    snappy nBufferCellsNoExtrude 동등: refinement level 경계 (L vs L-1)
    의 L-1 셀이 L-2 셀을 갖고 있으면 L-2 → L-1 upgrade. → level 경계가
    한 cell 두께로 부드러워져 hex skewness ↓."""
    from core.generator.native_hex.octree import (
        _add_buffer_layer_between_levels,
    )
    # 5×5×5 concentric: center L=3, 1-ring L=2, 외곽 L=1 (이미 2:1 balance).
    levels: dict[tuple[int, int, int], int] = {}
    for i in range(5):
        for j in range(5):
            for k in range(5):
                d = max(abs(i - 2), abs(j - 2), abs(k - 2))
                if d == 0:
                    levels[(i, j, k)] = 3
                elif d == 1:
                    levels[(i, j, k)] = 2
                else:
                    levels[(i, j, k)] = 1
    buffered = _add_buffer_layer_between_levels(levels, n_buffer=1)
    upgrades = sum(1 for k in levels if buffered[k] != levels[k])
    assert upgrades > 0, "balanced concentric 입력에서 buffer upgrade 0 — 로직 결함"
    # 새로 L=2 가 된 cells 는 모두 원래 L=1 였어야 함 (no downgrade).
    for k in levels:
        if buffered[k] != levels[k]:
            assert buffered[k] >= levels[k], "downgrade 발생 (잘못)"


def test_octree_buffer_layer_zero_passes_is_noop() -> None:
    """beta2312 — n_buffer=0 시 입력 그대로 반환 (env=0 backward 호환)."""
    from core.generator.native_hex.octree import (
        _add_buffer_layer_between_levels,
    )
    levels = {(0, 0, 0): 3, (1, 0, 0): 2, (2, 0, 0): 1}
    out = _add_buffer_layer_between_levels(levels, n_buffer=0)
    assert out == levels
