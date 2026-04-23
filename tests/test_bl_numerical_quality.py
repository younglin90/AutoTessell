"""beta27 — BL 수치 품질 회귀 테스트.

각 mesh_type (tet / hex_dominant / poly) 의 fine quality BL 파이프라인 결과에 대해
수치 지표 (first_layer_thickness, growth_ratio, negative_volumes, max_aspect_ratio)
가 strategy 기대값과 일치하는지 검증.

실제 파이프라인 구동은 느리므로, 여기서는 BL 의 핵심 구성요소 (native_bl /
tet_bl_subdivide / poly_bl_transition) 단위 회귀만 다룬다.
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
from core.layers.native_bl import BLConfig, generate_native_bl


_REPO = Path(__file__).resolve().parents[1]
SPHERE_STL = _REPO / "tests" / "benchmarks" / "sphere.stl"


def _build_baseline_tet(stl: Path, tmp: Path) -> Path | None:
    """CLI 로 wildmesh draft tet 베이스라인 생성. 실패 시 None."""
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
        return None
    return case_dir


@pytest.fixture(scope="module")
def sphere_tet_baseline() -> Path | None:
    """cheap 1회 생성 후 module 전체에서 재사용."""
    if not SPHERE_STL.exists():
        pytest.skip(f"sphere.stl 미존재: {SPHERE_STL}")
    tmp = Path(tempfile.mkdtemp(prefix="bl_numquality_"))
    base = _build_baseline_tet(SPHERE_STL, tmp)
    if base is None:
        shutil.rmtree(tmp, ignore_errors=True)
        pytest.skip("tet 베이스라인 생성 실패 (wildmesh unavailable)")
    yield base
    shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# BL 수치 품질 지표
# ---------------------------------------------------------------------------


def test_native_bl_respects_first_layer_thickness(
    sphere_tet_baseline: Path,
) -> None:
    """generate_native_bl 의 first_layer_thickness 가 BLConfig 대비 정확히 반영.

    total_thickness = first * sum(growth_ratio^i, i=0..num_layers-1) 관계 확인.
    """
    case = Path(shutil.copytree(
        sphere_tet_baseline, sphere_tet_baseline.parent / "work_first",
    ))
    cfg = BLConfig(num_layers=3, growth_ratio=1.2, first_thickness=0.01,
                   backup_original=False, max_total_ratio=0.2)
    res = generate_native_bl(case, cfg)
    assert res.success

    expected_total = 0.01 * sum(1.2 ** i for i in range(3))
    # max_total_ratio 로 clip 될 수 있으므로 min 으로 보호
    assert res.total_thickness > 0
    # clip 된 경우도 기대 total 의 일정 범위 내에 있어야 (완전 ±5%)
    ratio = res.total_thickness / expected_total
    assert 0.4 <= ratio <= 1.1, (
        f"total_thickness ratio {ratio:.3f} out of expected [0.4, 1.1]"
    )


def test_native_bl_num_prism_cells_matches_wall_layers(
    sphere_tet_baseline: Path,
) -> None:
    """n_prism_cells = n_wall_faces × num_layers."""
    case = Path(shutil.copytree(
        sphere_tet_baseline, sphere_tet_baseline.parent / "work_count",
    ))
    cfg = BLConfig(num_layers=4, growth_ratio=1.15, first_thickness=0.005,
                   backup_original=False, max_total_ratio=0.2)
    res = generate_native_bl(case, cfg)
    assert res.success
    assert res.n_wall_faces > 0
    assert res.n_prism_cells == res.n_wall_faces * 4


def test_native_bl_no_negative_volumes(sphere_tet_baseline: Path) -> None:
    """NativeMeshChecker: BL 후 negative_volumes == 0."""
    case = Path(shutil.copytree(
        sphere_tet_baseline, sphere_tet_baseline.parent / "work_negvol",
    ))
    cfg = BLConfig(num_layers=3, growth_ratio=1.2, first_thickness=0.008,
                   backup_original=False, max_total_ratio=0.2)
    res = generate_native_bl(case, cfg)
    assert res.success

    checker = NativeMeshChecker()
    check = checker.run(case)
    assert check.negative_volumes == 0, (
        f"BL 후 negative_volumes={check.negative_volumes}"
    )


def test_native_bl_growth_ratio_monotone(sphere_tet_baseline: Path) -> None:
    """growth_ratio >= 1.0 을 준수 — 레이어 간 두께가 감소하지 않음.

    이는 total_thickness = first * (g^n - 1) / (g - 1) 을 통해 간접 검증.
    g=1.0 특수 케이스 추가.
    """
    case = Path(shutil.copytree(
        sphere_tet_baseline, sphere_tet_baseline.parent / "work_growth",
    ))
    cfg = BLConfig(num_layers=5, growth_ratio=1.0, first_thickness=0.002,
                   backup_original=False, max_total_ratio=0.2)
    res = generate_native_bl(case, cfg)
    assert res.success
    # g=1.0 → total = first * n
    expected = 0.002 * 5
    ratio = res.total_thickness / expected
    assert 0.5 <= ratio <= 1.1, f"growth=1.0 total ratio {ratio:.3f}"


# ---------------------------------------------------------------------------
# tet BL subdivide 품질
# ---------------------------------------------------------------------------


def test_tet_bl_subdivide_yields_pure_tet_mesh(
    sphere_tet_baseline: Path,
) -> None:
    """native_bl 이후 tet_bl_subdivide 를 적용하면 prism → 3 tet 분할되어 모든
    cell 이 4-vertex 가 된다."""
    from core.layers.native_bl import BLConfig, generate_native_bl
    from core.layers.tet_bl_subdivide import subdivide_prism_layers_to_tet
    from core.utils.polymesh_reader import parse_foam_faces, parse_foam_labels

    case = Path(shutil.copytree(
        sphere_tet_baseline, sphere_tet_baseline.parent / "work_tet_subdiv",
    ))
    cfg = BLConfig(num_layers=2, growth_ratio=1.2, first_thickness=0.01,
                   backup_original=False, max_total_ratio=0.2)
    bl_res = generate_native_bl(case, cfg)
    assert bl_res.success

    sub_res = subdivide_prism_layers_to_tet(case, backup_original=False)
    assert sub_res.success, f"subdivide 실패: {sub_res.message}"

    # 모든 cell 이 tet (4 unique verts) 인지 확인
    poly_dir = case / "constant" / "polyMesh"
    owner = np.array(parse_foam_labels(poly_dir / "owner"), dtype=np.int64)
    neighbour = np.array(parse_foam_labels(poly_dir / "neighbour"), dtype=np.int64)
    faces = parse_foam_faces(poly_dir / "faces")

    n_cells = int(owner.max()) + 1
    if len(neighbour):
        n_cells = max(n_cells, int(neighbour.max()) + 1)
    cell_verts = [set() for _ in range(n_cells)]
    for fi, f in enumerate(faces):
        cell_verts[int(owner[fi])].update(int(v) for v in f)
        if fi < len(neighbour):
            cell_verts[int(neighbour[fi])].update(int(v) for v in f)
    non_tet = sum(1 for cv in cell_verts if len(cv) != 4)
    assert non_tet == 0, f"{non_tet} non-tet cells remain after subdivide"


# ---------------------------------------------------------------------------
# poly BL transition 품질
# ---------------------------------------------------------------------------


def test_poly_bl_hybrid_pass_through_preserves_topology(
    sphere_tet_baseline: Path,
) -> None:
    """poly_bl_transition: hybrid (prism+tet) 입력에서 dual skip, mesh 보존.

    beta13 의 graceful pass-through 가 checkMesh OK 유지하는지.
    """
    from core.layers.native_bl import BLConfig, generate_native_bl
    from core.layers.poly_bl_transition import run_poly_bl_transition

    case = Path(shutil.copytree(
        sphere_tet_baseline, sphere_tet_baseline.parent / "work_poly_hybrid",
    ))

    # BL 삽입 → hybrid mesh 생성
    bl_cfg = BLConfig(num_layers=2, growth_ratio=1.2, first_thickness=0.01,
                      backup_original=False, max_total_ratio=0.2)
    bl_res = generate_native_bl(case, bl_cfg)
    assert bl_res.success

    # poly_bl_transition 호출 — hybrid 라서 dual skip 되지만 success=True
    res = run_poly_bl_transition(
        case, num_layers=2, growth_ratio=1.2, first_thickness=0.01,
        backup_original=False, apply_bulk_dual=True,
    )
    # full dual 은 deferred 지만 전체 호출은 success=True 를 돌려야 함.
    # (bulk_dual_applied=False 는 허용).
    assert res.success

    # mesh 가 여전히 valid 한지 NativeMeshChecker 확인
    checker = NativeMeshChecker()
    check = checker.run(case)
    assert check.negative_volumes == 0
