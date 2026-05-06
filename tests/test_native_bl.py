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

import numpy as np
import pytest

from core.evaluator.native_checker import NativeMeshChecker
from core.generator.polymesh_writer import write_generic_polymesh
from core.layers.native_bl import BLConfig, generate_native_bl
from core.utils.polymesh_reader import parse_foam_faces, parse_foam_labels


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


def test_native_bl_target_y_plus_overrides_first_thickness(sphere_baseline: Path) -> None:
    """beta2267 — target_y_plus 사용 시 first_thickness 자동 계산 (Schlichting).

    cfMesh / Fluent / Pointwise 동급 CFD-engineer-friendly API.
    """
    cfg = BLConfig(
        num_layers=3, growth_ratio=1.2,
        first_thickness=1.0,  # large value — should be overridden by y+ targeting
        target_y_plus=1.0,
        flow_velocity=10.0,
        flow_kinematic_viscosity=1.5e-5,  # air
        flow_characteristic_length=1.0,  # 1m characteristic
    )
    res = generate_native_bl(sphere_baseline, cfg)
    assert res.success
    # y+ 1, U=10, L=1, nu=1.5e-5 → Re=666666 → Cf=0.00397 → u_tau=0.446 → y1≈3.4e-5
    # total_thickness = y1 × (1 + 1.2 + 1.44) = ~1.24e-4
    assert 1e-5 <= res.total_thickness <= 1e-3, (
        f"y+ targeting 가 first_thickness 를 override 하지 못함: "
        f"total={res.total_thickness}"
    )


def test_native_bl_wall_preserve_within_envelope(sphere_baseline: Path) -> None:
    """beta2256 — wall_preserve_within_envelope=True 가 commercial-grade
    contract. cfMesh / Pointwise T-Rex 동급 wall preservation 보장.

    BL pass 후 lp_ids[0] (boundary face vertex) 가 원본 polyMesh wall 좌표와
    ε=1e-6×bbox_diag 이내 일치해야 함.
    """
    cfg = BLConfig(num_layers=3, growth_ratio=1.2, first_thickness=0.02)
    res = generate_native_bl(sphere_baseline, cfg)
    assert res.success
    # New beta2256 fields must be present.
    assert hasattr(res, "wall_preserve_max_diff")
    assert hasattr(res, "wall_preserve_max_diff_rel")
    assert hasattr(res, "wall_preserve_n_drift")
    assert hasattr(res, "wall_preserve_within_envelope")
    # Commercial-grade contract: wall must be exactly preserved.
    assert res.wall_preserve_within_envelope is True, (
        f"wall preservation envelope violated: max_diff={res.wall_preserve_max_diff}, "
        f"rel={res.wall_preserve_max_diff_rel}, n_drift={res.wall_preserve_n_drift}"
    )
    assert res.wall_preserve_max_diff_rel <= 1e-6
    assert res.wall_preserve_n_drift == 0
    # Wall preservation must hold on a real BL run with prisms.
    assert res.n_prism_cells > 0


def _write_single_hex_quad_case(case_dir: Path) -> None:
    """단일 hexahedron polyMesh. Boundary wall face 는 모두 quad."""
    V = np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
    ], dtype=np.float64)
    cell_faces = [[
        [0, 3, 2, 1],  # z-
        [4, 5, 6, 7],  # z+
        [0, 1, 5, 4],  # y-
        [1, 2, 6, 5],  # x+
        [2, 3, 7, 6],  # y+
        [3, 0, 4, 7],  # x-
    ]]
    write_generic_polymesh(
        V, cell_faces, case_dir,
        patch_name="wall", patch_type="wall",
    )


def test_native_bl_quad_wall_replaces_original_polygon_faces(tmp_path: Path) -> None:
    """quad wall fan-triangulation 후 원본 quad boundary face 를 남기지 않는다."""
    _write_single_hex_quad_case(tmp_path)
    res = generate_native_bl(
        tmp_path,
        BLConfig(
            num_layers=1,
            first_thickness=0.05,
            collision_safety=False,
            backup_original=False,
        ),
    )
    assert res.success
    assert res.n_wall_faces == 12
    assert res.n_prism_cells == 12

    poly_dir = tmp_path / "constant" / "polyMesh"
    faces = parse_foam_faces(poly_dir / "faces")
    neighbour = parse_foam_labels(poly_dir / "neighbour")
    boundary_faces = faces[len(neighbour):]
    assert boundary_faces
    assert all(len(face) == 3 for face in boundary_faces)


def test_native_bl_quad_wall_prefilter_does_not_drop_all_layers(tmp_path: Path) -> None:
    """작은 raw first_thickness 가 BL3 보정 전에 모든 quad fan face 를 거부하지 않는다."""
    _write_single_hex_quad_case(tmp_path)
    res = generate_native_bl(
        tmp_path,
        BLConfig(
            num_layers=3,
            first_thickness=0.0002732960680837174,
            aspect_ratio_threshold=300.0,
            collision_safety=False,
            backup_original=False,
        ),
    )
    assert res.success
    assert res.n_wall_faces == 12
    assert res.n_prism_cells == 36


def test_native_bl_splits_warped_quad_faces_for_fvm_quality(tmp_path: Path) -> None:
    """BL side/interface warped quads are triangulated to avoid concavity/warpage."""
    _write_single_hex_quad_case(tmp_path)
    res = generate_native_bl(
        tmp_path,
        BLConfig(
            num_layers=3,
            first_thickness=0.05,
            collision_safety=False,
            backup_original=False,
        ),
    )
    assert res.success

    chk = NativeMeshChecker().run(tmp_path)
    assert chk.min_face_area > 0.0
    assert chk.max_concavity == 0.0
    assert chk.max_face_warpage <= 1e-12
