"""native_bl Phase 2 회귀 테스트.

core/layers/native_bl.py 의 generate_native_bl() 이 base tet polyMesh 에 prism
layer 를 topology/orientation 올바르게 삽입하는지 검증.

검증 기준:
  - NativeMeshChecker: mesh_ok=True, negative_volumes=0
  - cell 수 = n_tet + n_wall_faces * n_layers
  - prism block 의 bl_side patch 가 manifold wall 에선 0 face
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from core.evaluator.native_checker import NativeMeshChecker
from core.layers.native_bl import BLConfig, generate_native_bl


_REPO = Path(__file__).resolve().parents[1]
SPHERE_STL = _REPO / "tests" / "benchmarks" / "sphere.stl"


def _build_baseline(stl: Path, tmp: Path) -> Path:
    """CLI 를 통해 sphere tet 메쉬 베이스라인 생성 (wildmesh draft)."""
    case_dir = tmp / "base"
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_REPO) + os.pathsep + env.get("PYTHONPATH", "")
    cmd = [
        "python3", "-m", "cli.main", "run", str(stl),
        "-o", str(case_dir),
        "--mesh-type", "tet", "--quality", "draft", "--tier", "wildmesh",
        "--auto-retry", "off",
    ]
    r = subprocess.run(
        cmd, capture_output=True, text=True, timeout=180, env=env, cwd=str(_REPO),
    )
    if r.returncode != 0 or not (case_dir / "constant" / "polyMesh").exists():
        pytest.skip(
            f"native_bl baseline 생성 실패 (rc={r.returncode}): "
            f"{(r.stderr or r.stdout)[-300:]}"
        )
    return case_dir


@pytest.fixture
def sphere_baseline() -> Path:
    if not SPHERE_STL.exists():
        pytest.skip(f"sphere.stl 미존재: {SPHERE_STL}")
    tmp = Path(tempfile.mkdtemp(prefix="native_bl_test_"))
    try:
        base = _build_baseline(SPHERE_STL, tmp)
        # copy to work case for mutation
        work = tmp / "work"
        shutil.copytree(base, work)
        yield work
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# 1) Success path + counts
# ---------------------------------------------------------------------------


def test_native_bl_inserts_prism_cells(sphere_baseline: Path) -> None:
    """3 layers × n_wall_faces 만큼 prism cell 이 추가되고 success=True."""
    cfg = BLConfig(
        num_layers=3, growth_ratio=1.2, first_thickness=0.01,
        backup_original=False, max_total_ratio=0.1,
    )
    res = generate_native_bl(sphere_baseline, cfg)
    assert res.success, f"native_bl 실패: {res.message}"
    assert res.n_wall_faces > 0
    assert res.n_prism_cells == res.n_wall_faces * 3
    assert res.total_thickness > 0
    assert res.n_new_points > 0


def test_native_bl_manifold_has_no_bl_side(sphere_baseline: Path) -> None:
    """sphere 는 closed manifold 이므로 bl_side patch 가 0 face 여야 한다."""
    cfg = BLConfig(
        num_layers=3, growth_ratio=1.2, first_thickness=0.01,
        backup_original=False, max_total_ratio=0.1,
    )
    res = generate_native_bl(sphere_baseline, cfg)
    assert res.success
    # message 에 bl_side_faces=0 이 포함되어야 한다.
    assert "bl_side_faces=0" in res.message


# ---------------------------------------------------------------------------
# 2) Resulting polyMesh 가 NativeMeshChecker 통과
# ---------------------------------------------------------------------------


def test_native_bl_result_passes_native_checker(sphere_baseline: Path) -> None:
    """BL 삽입 후 NativeMeshChecker 가 mesh_ok=True, negative_volumes=0."""
    cfg = BLConfig(
        num_layers=3, growth_ratio=1.2, first_thickness=0.01,
        backup_original=False, max_total_ratio=0.1,
    )
    res = generate_native_bl(sphere_baseline, cfg)
    assert res.success

    checker_result = NativeMeshChecker().run(sphere_baseline)
    assert checker_result.negative_volumes == 0, (
        f"negative volumes: {checker_result.negative_volumes}"
    )
    assert checker_result.mesh_ok, (
        f"mesh_ok=False, failed_checks={checker_result.failed_checks}"
    )


def test_native_bl_preserves_wall_and_adds_prism(sphere_baseline: Path) -> None:
    """total cell 수 = original tet + prism. original tet 수는 유지."""
    # baseline cell 수 사전 측정
    base_checker = NativeMeshChecker().run(sphere_baseline)
    base_cells = base_checker.cells

    cfg = BLConfig(
        num_layers=3, growth_ratio=1.2, first_thickness=0.01,
        backup_original=False, max_total_ratio=0.1,
    )
    res = generate_native_bl(sphere_baseline, cfg)
    assert res.success

    after_checker = NativeMeshChecker().run(sphere_baseline)
    assert after_checker.cells == base_cells + res.n_prism_cells, (
        f"expected {base_cells} + {res.n_prism_cells} = "
        f"{base_cells + res.n_prism_cells}, got {after_checker.cells}"
    )


# ---------------------------------------------------------------------------
# 3) 파라미터 스윕
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("num_layers", [1, 2, 5])
def test_native_bl_various_layer_counts(sphere_baseline: Path, num_layers: int) -> None:
    cfg = BLConfig(
        num_layers=num_layers, growth_ratio=1.1, first_thickness=0.005,
        backup_original=False, max_total_ratio=0.1,
    )
    res = generate_native_bl(sphere_baseline, cfg)
    assert res.success, f"num_layers={num_layers} 실패: {res.message}"
    assert res.n_prism_cells == res.n_wall_faces * num_layers


# ---------------------------------------------------------------------------
# 4) Backup
# ---------------------------------------------------------------------------


def test_native_bl_backup_creates_pre_bl_dir(sphere_baseline: Path) -> None:
    cfg = BLConfig(
        num_layers=2, growth_ratio=1.2, first_thickness=0.01,
        backup_original=True, max_total_ratio=0.1,
    )
    res = generate_native_bl(sphere_baseline, cfg)
    assert res.success
    bak = sphere_baseline / "constant" / "polyMesh_pre_bl"
    assert bak.exists() and bak.is_dir()
    assert (bak / "points").exists()
    assert (bak / "faces").exists()
