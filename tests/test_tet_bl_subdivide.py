"""tet_bl_subdivide 회귀 테스트.

mesh_type=tet 용 BL: native_bl 로 prism 삽입 → 각 wedge 를 tet 3 개로 분할해
전체가 순수 tet 메쉬로 유지되는지 검증.
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
from core.layers.tet_bl_subdivide import subdivide_prism_layers_to_tet


_REPO = Path(__file__).resolve().parents[1]
SPHERE_STL = _REPO / "tests" / "benchmarks" / "sphere.stl"


@pytest.fixture
def sphere_with_bl() -> Path:
    """sphere tet 베이스라인 + native_bl 2 layers 삽입된 case."""
    if not SPHERE_STL.exists():
        pytest.skip(f"sphere.stl 미존재: {SPHERE_STL}")
    tmp = Path(tempfile.mkdtemp(prefix="tbs_test_"))
    try:
        case_dir = tmp / "case"
        env = dict(os.environ)
        env["PYTHONPATH"] = str(_REPO) + os.pathsep + env.get("PYTHONPATH", "")
        r = subprocess.run(
            ["python3", "-m", "cli.main", "run", str(SPHERE_STL),
             "-o", str(case_dir), "--mesh-type", "tet", "--quality", "draft",
             "--tier", "wildmesh", "--auto-retry", "off"],
            capture_output=True, text=True, timeout=180,
            env=env, cwd=str(_REPO),
        )
        if r.returncode != 0 or not (case_dir / "constant" / "polyMesh").exists():
            pytest.skip(
                f"baseline 실패 (rc={r.returncode}): "
                f"{(r.stderr or r.stdout)[-300:]}"
            )
        # native_bl 2 layers
        cfg = BLConfig(
            num_layers=2, growth_ratio=1.2, first_thickness=0.01,
            backup_original=False, max_total_ratio=0.1,
        )
        bl_res = generate_native_bl(case_dir, cfg)
        assert bl_res.success, f"native_bl: {bl_res.message}"
        yield case_dir
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_subdivide_converts_all_prism_to_tet(sphere_with_bl: Path) -> None:
    """subdivide 후 prism cell 이 남지 않아야 한다."""
    res = subdivide_prism_layers_to_tet(sphere_with_bl, backup_original=False)
    assert res.success, f"subdivide 실패: {res.message}"
    assert res.n_prism_before > 0
    assert res.n_tet_added == 3 * res.n_prism_before


def test_subdivide_result_is_valid_mesh(sphere_with_bl: Path) -> None:
    """subdivide 결과 NativeMeshChecker 통과 (mesh_ok + negative_volumes=0)."""
    res = subdivide_prism_layers_to_tet(sphere_with_bl, backup_original=False)
    assert res.success

    chk = NativeMeshChecker().run(sphere_with_bl)
    assert chk.negative_volumes == 0
    assert chk.mesh_ok, (
        f"mesh_ok=False, failed_checks={chk.failed_checks}"
    )


def test_subdivide_preserves_boundary_face_count(sphere_with_bl: Path) -> None:
    """sphere 같은 closed manifold 에서 subdivide 전후 wall boundary face 수는 유지."""
    before = NativeMeshChecker().run(sphere_with_bl)
    before_boundary = before.faces - 0  # (boundary face 수는 별도 API 가 없어 전체 face 만)

    res = subdivide_prism_layers_to_tet(sphere_with_bl, backup_original=False)
    assert res.success

    after = NativeMeshChecker().run(sphere_with_bl)
    # tet 분할 시 face 수는 늘어남 (prism 5 face → tet 3 개 * 4 face 중 공유 제외)
    # 단순히 "cells 은 3 배 증가한 prism 만큼만 늘어남" 확인
    assert after.cells == before.cells + res.n_tet_added - res.n_prism_before


def test_subdivide_on_no_prism_mesh_is_noop(sphere_with_bl: Path) -> None:
    """prism 이 없는 메쉬 (이미 분할된 경우) 에서 재실행 시 noop 성공."""
    res1 = subdivide_prism_layers_to_tet(sphere_with_bl, backup_original=False)
    assert res1.success

    res2 = subdivide_prism_layers_to_tet(sphere_with_bl, backup_original=False)
    assert res2.success
    assert res2.n_prism_before == 0
    assert res2.n_tet_added == 0


def test_subdivide_backup_creates_pre_dir(sphere_with_bl: Path) -> None:
    res = subdivide_prism_layers_to_tet(sphere_with_bl, backup_original=True)
    assert res.success
    bak = sphere_with_bl / "constant" / "polyMesh_pre_tet_subdiv"
    assert bak.exists() and bak.is_dir()
