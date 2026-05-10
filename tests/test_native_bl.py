"""native_bl Phase 2 회귀 테스트.

core/layers/native_bl.py 의 generate_native_bl() 이 base tet polyMesh 에 prism
layer 를 topology/orientation 올바르게 삽입하는지 검증.

검증 기준:
  - NativeMeshChecker: mesh_ok=True, negative_volumes=0
  - cell 수 = n_tet + n_wall_faces * n_layers
  - prism block 의 bl_side patch 가 manifold wall 에선 0 face
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import pytest

from core.evaluator.native_checker import NativeMeshChecker
from core.generator.polymesh_writer import write_generic_polymesh
from core.layers.native_bl import (
    BLConfig,
    _bl_bad_internal_face_histogram,
    _bl_cavity_shell_summary,
    _merge_skewed_bl_internal_quads,
    _apply_tet_cavity_replacement_plan,
    _build_tet_cavity_replacement_plan,
    _detect_wall_owner_cavity_components,
    _owner_centre_wall_motion,
    _tet_wall_cavity_eligibility,
    _tet_wall_cavity_replacement_probe,
    generate_native_bl,
)
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
    quality = json.loads((sphere_baseline / "native_bl_quality.json").read_text())
    pre_bl = quality["pre_bl_bad_internal_faces"]
    assert pre_bl["n_internal_faces"] >= 0
    assert "bulk-bulk" in pre_bl["total_by_class"]
    assert "coverage_single_wall_tet" in quality["tet_wall_cavity"]


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


def test_native_bl_preserves_flat_side_quads_to_avoid_internal_skew(
    tmp_path: Path,
) -> None:
    """Flat BL side quads must stay quads; forced split moves face centroids."""
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

    poly_dir = tmp_path / "constant" / "polyMesh"
    faces = parse_foam_faces(poly_dir / "faces")
    neighbour = parse_foam_labels(poly_dir / "neighbour")
    internal_faces = faces[:len(neighbour)]
    assert any(len(face) == 4 for face in internal_faces)

    chk = NativeMeshChecker().run(tmp_path)
    assert chk.max_internal_skewness < 4.0
    assert chk.min_face_weight > 0.0


def test_native_bl_merges_skewed_feature_edge_seam_quads() -> None:
    """Bad BL-BL feature-edge seams are removed as polyhedral corner cells."""
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 1.0, 0.1],
            [0.0, 0.0, 0.1],
            [1.0, 0.633, 0.0],
            [1.0, 0.633, 0.1],
            [1.01, 0.633, 0.0],
            [1.01, 0.633, 0.1],
        ],
        dtype=np.float64,
    )
    faces = [
        [0, 1, 2, 3],
        [4, 5, 1, 0],
        [6, 7, 2, 3],
    ]
    owner = [1, 1, 2]
    neighbour = [2]
    boundary = [{"name": "wall", "type": "wall", "nFaces": 2, "startFace": 1}]

    out_faces, out_owner, out_nbr, out_boundary, n_removed = (
        _merge_skewed_bl_internal_quads(
            points,
            faces,
            owner,
            neighbour,
            boundary,
            base_n_cells=1,
            skew_threshold=4.0,
        )
    )

    assert n_removed == 1
    assert out_faces == faces[1:]
    assert out_nbr == []
    assert out_owner == [0, 0]
    assert out_boundary[0]["startFace"] == 0


def test_native_bl_bad_internal_face_histogram_classifies_interfaces() -> None:
    """BL diagnostics classify bad faces by bulk/prism owner-neighbour type."""
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
        ],
        dtype=np.float64,
    )
    faces = [[0, 1, 2], [0, 2, 1]]
    owner = [0, 2]
    neighbour = [2, 3]

    hist = _bl_bad_internal_face_histogram(
        points,
        faces,
        owner,
        neighbour,
        base_n_cells=2,
        prism_cell_start=2,
        prism_cell_end=4,
    )

    assert hist["n_internal_faces"] == 2
    assert hist["total_by_class"]["bulk-prism"] == 1
    assert hist["total_by_class"]["prism-prism"] == 1
    assert hist["bad_by_class"]["bulk-prism"] == 1
    assert hist["bad_by_class"]["prism-prism"] == 1
    assert hist["bad_by_reason"]["degenerate"] == 2
    assert hist["components"][0]["n_faces"] == 2
    assert hist["components"][0]["n_cells"] == 3
    assert hist["components"][0]["classes"]["bulk-prism"] == 1
    assert hist["components"][0]["classes"]["prism-prism"] == 1
    assert hist["components"][0]["ids_truncated"] is False
    assert hist["components"][0]["faces"] == [0, 1]
    assert hist["components"][0]["cells"] == [0, 2, 3]
    assert hist["components"][0]["n_inside_internal_faces"] == 2
    assert hist["components"][0]["cavity_shell"]["n_boundary_faces"] == 0
    assert hist["components"][0]["cavity_shell"]["agglomerate_probe"]["passes"] is True


def test_native_bl_bad_component_records_closed_cavity_shell() -> None:
    """Small bad components expose a closed cavity shell for later local refill."""
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, -1.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    faces = [
        [0, 1, 2],  # internal face between the selected bulk/prism cells
        [0, 3, 1],
        [1, 3, 2],
        [2, 3, 0],
        [0, 1, 4],
        [1, 2, 4],
        [2, 0, 4],
    ]
    owner = [0, 0, 0, 0, 2, 2, 2]
    neighbour = [2]

    hist = _bl_bad_internal_face_histogram(
        points,
        faces,
        owner,
        neighbour,
        base_n_cells=2,
        prism_cell_start=2,
        prism_cell_end=3,
        max_non_ortho_deg=-1.0,
    )

    comp = hist["components"][0]
    shell = comp["cavity_shell"]
    assert comp["cells"] == [0, 2]
    assert shell["cell_kinds"] == {"bulk": 1, "prism": 1}
    assert shell["n_internal_faces"] == 1
    assert shell["n_boundary_faces"] == 6
    assert shell["n_physical_boundary_faces"] == 6
    assert shell["boundary_by_class"] == {
        "bulk-physical": 3,
        "prism-physical": 3,
    }
    assert shell["n_open_edges"] == 0
    assert shell["n_nonmanifold_edges"] == 0
    assert shell["n_duplicate_boundary_faces"] == 0
    assert shell["is_closed_2manifold"] is True
    assert shell["small_closed_cavity_candidate"] is True
    assert shell["agglomerate_probe"]["n_interface_faces"] == 0
    assert shell["agglomerate_probe"]["passes"] is True


def test_native_bl_tet_wall_cavity_marks_single_wall_tet_owner() -> None:
    """BL cavity diagnostics identify local tet owner-cell replacement targets."""
    faces = [
        [0, 1, 2],
        [0, 3, 1],
        [1, 3, 2],
        [2, 3, 0],
    ]
    owner = [0, 0, 0, 0]
    neighbour: list[int] = []

    summary = _tet_wall_cavity_eligibility(
        faces,
        owner,
        neighbour,
        [0],
        n_cells=1,
    )

    assert summary["n_wall_owner_cells"] == 1
    assert summary["n_single_wall_owner_cells"] == 1
    assert summary["n_single_wall_tet_owner_cells"] == 1
    assert summary["coverage_single_wall_tet"] == 1.0
    assert summary["sample_single_wall_tet_cells"] == [0]


def test_native_bl_owner_centre_motion_one_tet_wall_fixture() -> None:
    """BLR-8 — owner-centre motion produces finite, single-cell-bounded
    wall-vertex displacements when enabled, and is a no-op when disabled.

    Fixture: a single tetrahedron with vertices forming the wall triangle
    on the z=0 plane and an apex directly above. The owner cell centre
    sits inside the tet, so the new motion direction must point from each
    wall vertex toward the cell centre — bounded inside the tet.
    """
    points = np.array(
        [
            [0.0, 0.0, 0.0],   # wall vertex 0
            [1.0, 0.0, 0.0],   # wall vertex 1
            [0.0, 1.0, 0.0],   # wall vertex 2
            [0.0, 0.0, 1.0],   # apex (interior)
        ],
        dtype=np.float64,
    )
    faces = [
        [0, 1, 2],   # wall face (boundary)
        [0, 3, 1],
        [1, 3, 2],
        [2, 3, 0],
    ]
    owner = np.array([0, 0, 0, 0], dtype=np.int64)
    wall_face_indices = [0]
    wall_vert_indices = [0, 1, 2]
    cell_centres = points.mean(axis=0).reshape(1, 3)
    eligible = {0}
    # Production fallback is ``-vnorm[v]`` (inward, toward the owner cell).
    # The owner cell sits above the wall (z=0.25), so the inward direction is
    # +z.  A sign-consistency guard skips replacements that would invert the
    # prism stack, so the fallback has to point into the same half-space as
    # the owner centre for the centre-pointing direction to be applied.
    fallback = {
        v: np.array([0.0, 0.0, 1.0], dtype=np.float64)
        for v in wall_vert_indices
    }

    # Env ON — should move all three wall vertices toward owner cell centre.
    dirs_on, diag_on = _owner_centre_wall_motion(
        points,
        faces,
        owner,
        wall_vert_indices,
        wall_face_indices,
        cell_centres,
        eligible,
        fallback,
        enabled=True,
    )

    assert diag_on["enabled"] is True
    assert diag_on["n_eligible"] == 3
    assert diag_on["n_moved"] == 3
    assert diag_on["mean_motion"] > 0.0
    assert diag_on["max_motion"] >= diag_on["mean_motion"]

    expected_centre = points.mean(axis=0)
    for v in wall_vert_indices:
        d = dirs_on[v]
        assert d.shape == (3,)
        assert np.all(np.isfinite(d))
        # Unit vector.
        assert abs(float(np.linalg.norm(d)) - 1.0) < 1e-9
        # Direction matches centre - point, normalized — single-cell-bounded.
        expected = expected_centre - points[v]
        expected = expected / np.linalg.norm(expected)
        np.testing.assert_allclose(d, expected, atol=1e-9)

    # Env OFF — must reproduce fallback exactly (no-op).
    dirs_off, diag_off = _owner_centre_wall_motion(
        points,
        faces,
        owner,
        wall_vert_indices,
        wall_face_indices,
        cell_centres,
        eligible,
        fallback,
        enabled=False,
    )
    assert diag_off["enabled"] is False
    assert diag_off["n_eligible"] == 0
    assert diag_off["n_moved"] == 0
    assert diag_off["mean_motion"] == 0.0
    assert diag_off["max_motion"] == 0.0
    for v in wall_vert_indices:
        np.testing.assert_array_equal(dirs_off[v], fallback[v])

    # Empty eligible set with env ON must still be a no-op (no motion).
    dirs_empty, diag_empty = _owner_centre_wall_motion(
        points,
        faces,
        owner,
        wall_vert_indices,
        wall_face_indices,
        cell_centres,
        set(),
        fallback,
        enabled=True,
    )
    assert diag_empty["n_moved"] == 0
    for v in wall_vert_indices:
        np.testing.assert_array_equal(dirs_empty[v], fallback[v])


def test_native_bl_tet_cavity_probe_one_tet_passes() -> None:
    """BLR-9a — dry-run probe on a single eligible tet predicts a valid
    transition tet (positive determinant) when the inward motion points
    into the owner cell.

    Re-uses the BLR-8 fixture: one tet with wall on z=0 and apex above.
    Inward direction = +z. Inner triangle = wall verts + thickness × (+z).
    Transition tet apex = cell centroid (above wall); base = inner
    triangle. Signed volume should be strictly positive.
    """
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    faces = [
        [0, 1, 2],   # wall face
        [0, 3, 1],
        [1, 3, 2],
        [2, 3, 0],
    ]
    owner = np.array([0, 0, 0, 0], dtype=np.int64)
    wall_face_indices = [0]
    cell_centres = points.mean(axis=0).reshape(1, 3)
    eligible = {0}
    motion_dirs = {
        0: np.array([0.0, 0.0, 1.0], dtype=np.float64),
        1: np.array([0.0, 0.0, 1.0], dtype=np.float64),
        2: np.array([0.0, 0.0, 1.0], dtype=np.float64),
    }

    diag_on = _tet_wall_cavity_replacement_probe(
        points,
        faces,
        owner,
        wall_face_indices,
        eligible,
        cell_centres,
        motion_dirs,
        first_thickness=0.05,
        enabled=True,
    )
    assert diag_on["enabled"] is True
    assert diag_on["n_candidates"] == 1
    assert diag_on["n_quality_pass"] == 1
    assert diag_on["n_quality_fail_det"] == 0
    assert diag_on["n_quality_fail_topology"] == 0
    assert diag_on["min_predicted_det"] > 0.0
    assert diag_on["mean_predicted_det"] >= diag_on["min_predicted_det"]

    # Env OFF — diagnostics must be zero-filled.
    diag_off = _tet_wall_cavity_replacement_probe(
        points,
        faces,
        owner,
        wall_face_indices,
        eligible,
        cell_centres,
        motion_dirs,
        first_thickness=0.05,
        enabled=False,
    )
    assert diag_off["enabled"] is False
    assert diag_off["n_candidates"] == 0
    assert diag_off["n_quality_pass"] == 0
    assert diag_off["min_predicted_det"] == 0.0


def test_native_bl_tet_cavity_probe_rejects_outward_motion() -> None:
    """Inward motion pointing OUT of the owner cell yields negative
    transition tet volume — probe must count it as a det failure."""
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    faces = [
        [0, 1, 2],
        [0, 3, 1],
        [1, 3, 2],
        [2, 3, 0],
    ]
    owner = np.array([0, 0, 0, 0], dtype=np.int64)
    cell_centres = points.mean(axis=0).reshape(1, 3)
    # Reverse the motion: -z (away from owner cell which is above the wall).
    motion_dirs = {
        0: np.array([0.0, 0.0, -1.0], dtype=np.float64),
        1: np.array([0.0, 0.0, -1.0], dtype=np.float64),
        2: np.array([0.0, 0.0, -1.0], dtype=np.float64),
    }

    diag = _tet_wall_cavity_replacement_probe(
        points,
        faces,
        owner,
        [0],
        {0},
        cell_centres,
        motion_dirs,
        first_thickness=0.05,
        enabled=True,
    )
    assert diag["n_candidates"] == 1
    assert diag["n_quality_pass"] == 0
    # Outward motion = inner triangle on the WRONG side of the wall →
    # classified as a topology failure (not a determinant failure).
    assert diag["n_quality_fail_topology"] == 1
    assert diag["n_quality_fail_det"] == 0


def test_native_bl_tet_cavity_replacement_plan_one_eligible_cell() -> None:
    """BLR-9b-i — replacement plan builder produces 1 cell to delete +
    1 prism + 1 transition tet + 3 new inner-triangle points for the
    one-tet inward fixture, and is empty when disabled."""
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    faces = [
        [0, 1, 2],
        [0, 3, 1],
        [1, 3, 2],
        [2, 3, 0],
    ]
    owner = np.array([0, 0, 0, 0], dtype=np.int64)
    wall_face_indices = [0]
    cell_centres = points.mean(axis=0).reshape(1, 3)
    motion_dirs = {
        0: np.array([0.0, 0.0, 1.0], dtype=np.float64),
        1: np.array([0.0, 0.0, 1.0], dtype=np.float64),
        2: np.array([0.0, 0.0, 1.0], dtype=np.float64),
    }

    plan_on = _build_tet_cavity_replacement_plan(
        points,
        faces,
        owner,
        wall_face_indices,
        {0},
        cell_centres,
        motion_dirs,
        first_thickness=0.05,
        enabled=True,
    )
    assert plan_on["enabled"] is True
    assert plan_on["n_planned"] == 1
    assert plan_on["cells_to_delete"] == [0]
    assert len(plan_on["new_cells"]) == 1
    new_cell = plan_on["new_cells"][0]
    assert new_cell["deleted_cell_id"] == 0
    # Prism: outer triangle keeps original wall verts (0, 1, 2); inner
    # triangle uses the three freshly minted point ids appended right
    # after the original ``points`` (4) — so 4, 5, 6.
    assert new_cell["prism"] == [0, 1, 2, 4, 5, 6]
    # Transition tet apex id is -1 placeholder; base verts are the
    # same minted ids as the prism inner triangle.
    assert new_cell["transition_tet"][0] == -1
    assert new_cell["transition_tet"][1:] == [4, 5, 6]
    # Apex coordinate equals the original cell centroid = mean(points).
    np.testing.assert_allclose(
        new_cell["transition_tet_apex_xyz"],
        points.mean(axis=0),
        atol=1e-12,
    )
    assert plan_on["new_points"].shape == (3, 3)
    # Inner triangle points = wall verts + (+z * 0.05).
    np.testing.assert_allclose(
        plan_on["new_points"],
        np.array(
            [
                [0.0, 0.0, 0.05],
                [1.0, 0.0, 0.05],
                [0.0, 1.0, 0.05],
            ],
            dtype=np.float64,
        ),
        atol=1e-12,
    )

    # Env OFF — plan must be empty.
    plan_off = _build_tet_cavity_replacement_plan(
        points,
        faces,
        owner,
        wall_face_indices,
        {0},
        cell_centres,
        motion_dirs,
        first_thickness=0.05,
        enabled=False,
    )
    assert plan_off["enabled"] is False
    assert plan_off["n_planned"] == 0
    assert plan_off["cells_to_delete"] == []
    assert plan_off["new_cells"] == []
    assert plan_off["new_points"].shape == (0, 3)


def test_native_bl_tet_cavity_replacement_plan_outward_motion_rejected() -> None:
    """Outward motion → topology rejection at plan-build time, no new
    cells emitted."""
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    faces = [
        [0, 1, 2],
        [0, 3, 1],
        [1, 3, 2],
        [2, 3, 0],
    ]
    owner = np.array([0, 0, 0, 0], dtype=np.int64)
    cell_centres = points.mean(axis=0).reshape(1, 3)
    motion_dirs = {
        0: np.array([0.0, 0.0, -1.0], dtype=np.float64),
        1: np.array([0.0, 0.0, -1.0], dtype=np.float64),
        2: np.array([0.0, 0.0, -1.0], dtype=np.float64),
    }

    plan = _build_tet_cavity_replacement_plan(
        points,
        faces,
        owner,
        [0],
        {0},
        cell_centres,
        motion_dirs,
        first_thickness=0.05,
        enabled=True,
    )
    assert plan["n_planned"] == 0
    assert plan["cells_to_delete"] == []
    assert plan["new_cells"] == []
    assert plan["n_rejected_topology"] == 1
    assert plan["rejected"]["topology"] == [0]


def test_native_bl_apply_tet_cavity_replacement_plan_one_eligible_cell() -> None:
    """BLR-9b-ii — apply the plan in-memory: original 1-tet cell goes to
    0; 2 new cells (prism + transition tet) are emitted.  Points
    grow by 4 (3 inner + 1 apex)."""
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    faces = [
        [0, 1, 2],   # wall (boundary)
        [0, 3, 1],
        [1, 3, 2],
        [2, 3, 0],
    ]
    owner = np.array([0, 0, 0, 0], dtype=np.int64)
    neighbour = np.array([], dtype=np.int64)
    wall_face_indices = [0]
    cell_centres = points.mean(axis=0).reshape(1, 3)
    motion_dirs = {
        0: np.array([0.0, 0.0, 1.0], dtype=np.float64),
        1: np.array([0.0, 0.0, 1.0], dtype=np.float64),
        2: np.array([0.0, 0.0, 1.0], dtype=np.float64),
    }

    plan = _build_tet_cavity_replacement_plan(
        points,
        faces,
        owner,
        wall_face_indices,
        {0},
        cell_centres,
        motion_dirs,
        first_thickness=0.05,
        enabled=True,
    )
    assert plan["n_planned"] == 1

    applied = _apply_tet_cavity_replacement_plan(
        points,
        faces,
        owner,
        neighbour,
        wall_face_indices,
        plan,
        enabled=True,
    )
    assert applied["enabled"] is True
    assert applied["n_replaced"] == 1
    assert applied["n_cells_before"] == 1
    assert applied["n_cells_after"] == 2  # 1 deleted, 2 new (prism + tet)
    # 4 original points + 3 inner triangle + 1 apex = 8.
    assert applied["new_points"].shape == (8, 3)
    assert applied["n_new_points_total"] == 4
    # Apex = original cell centroid.
    np.testing.assert_allclose(
        applied["new_points"][7], points.mean(axis=0), atol=1e-12
    )
    # Inner triangle = wall + 0.05 * +z.
    np.testing.assert_allclose(
        applied["new_points"][4:7],
        np.array([[0, 0, 0.05], [1, 0, 0.05], [0, 1, 0.05]], dtype=np.float64),
        atol=1e-12,
    )
    # Owner array compact: prism = cell 0, transition tet = cell 1.
    assert int(applied["new_owner"].max()) <= 1
    # At least one internal face exists (prism cap shared with transition tet).
    assert applied["new_neighbour"].size >= 1


def test_native_bl_replacement_plan_rejects_wall_owner_with_internal_neighbour() -> None:
    """BLR-9b-iii topology guard: a wall-owner tet with one or more
    internal-face neighbours must be REJECTED by the plan builder
    (the simple 1-prism-+-1-transition-tet rewrite would orphan the
    neighbour cell's shared face).  The candidate is logged in
    ``rejected.neighbour_internal`` so a verifier can count it.

    Fixture: two tets sharing the face (0, 1, 3); the wall face
    (0, 1, 2) belongs only to cell 0, so cell 0 is the wall owner
    and cell 1 is its internal-face neighbour through (0, 1, 3).
    """
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [1.0, 1.0, 1.0],
        ],
        dtype=np.float64,
    )
    faces = [
        [0, 1, 2],   # wall face — boundary, owner=0
        [0, 1, 3],   # internal — owner=0, neighbour=1
        [1, 2, 3],   # boundary — owner=0
        [2, 0, 3],   # boundary — owner=0
        [0, 1, 4],   # boundary — owner=1
        [1, 3, 4],   # boundary — owner=1
        [3, 0, 4],   # boundary — owner=1
    ]
    owner = np.array([0, 0, 0, 0, 1, 1, 1], dtype=np.int64)
    neighbour = np.array([-1, 1, -1, -1, -1, -1, -1], dtype=np.int64)
    wall_face_indices = [0]
    cell_centres = np.array(
        [
            np.array([0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])[:0],  # placeholder unused
            np.array([0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])[:0],
        ],
        dtype=np.float64,
    )
    # Recompute centres simply from the verts.
    cell_centres = np.array(
        [
            points[[0, 1, 2, 3]].mean(axis=0),
            points[[0, 1, 3, 4]].mean(axis=0),
        ],
        dtype=np.float64,
    )
    motion_dirs = {
        0: np.array([0.0, 0.0, 1.0], dtype=np.float64),
        1: np.array([0.0, 0.0, 1.0], dtype=np.float64),
        2: np.array([0.0, 0.0, 1.0], dtype=np.float64),
    }

    plan = _build_tet_cavity_replacement_plan(
        points,
        faces,
        owner,
        wall_face_indices,
        {0},
        cell_centres,
        motion_dirs,
        first_thickness=0.05,
        enabled=True,
        neighbour=neighbour,
    )
    assert plan["n_planned"] == 0
    assert plan["cells_to_delete"] == []
    assert plan["new_cells"] == []
    assert plan["n_rejected_neighbour_internal"] == 1
    assert plan["rejected"]["neighbour_internal"] == [0]


def test_native_bl_detect_wall_owner_cavity_components_isolated() -> None:
    """BLR-9c-a — two wall-owner cells with no internal connection
    form two size-1 components."""
    # 4 cells, 2 wall faces (cell 0 and cell 2), no internal face links
    # the two wall-owner cells. Cells 1, 3 are non-wall.
    owner = np.array([0, 0, 1, 2, 2, 3], dtype=np.int64)
    neighbour = np.array([-1, -1, -1, -1, -1, -1], dtype=np.int64)
    wall_face_indices = [0, 3]  # owner=0 and owner=2

    comps = _detect_wall_owner_cavity_components(
        owner, neighbour, wall_face_indices, n_cells=4
    )
    assert len(comps) == 2
    assert {0} in comps
    assert {2} in comps


def test_native_bl_detect_wall_owner_cavity_components_connected() -> None:
    """Two wall-owner cells (0 and 1) sharing an internal face
    collapse into one size-2 component."""
    # owner / neighbour pair on face 1 → cells 0 and 1 sharing.
    owner = np.array([0, 0, 1], dtype=np.int64)
    neighbour = np.array([-1, 1, -1], dtype=np.int64)
    # Face 0 = owner=0 wall, face 2 = owner=1 wall.  Both cells own
    # a wall face → wall_owner_set = {0, 1}.  Face 1 is internal
    # (owner=0, neighbour=1) → union.
    wall_face_indices = [0, 2]

    comps = _detect_wall_owner_cavity_components(
        owner, neighbour, wall_face_indices, n_cells=2
    )
    assert len(comps) == 1
    assert comps[0] == {0, 1}


def test_native_bl_detect_wall_owner_cavity_components_excludes_non_wall_path() -> None:
    """A non-wall cell sitting between two wall owners must NOT bridge
    them into one component (only direct wall-owner ↔ wall-owner
    internal faces count)."""
    # 3 cells: 0 (wall), 1 (non-wall), 2 (wall).
    # Faces:
    #   0: boundary, owner=0 wall
    #   1: internal, owner=0 nbr=1
    #   2: internal, owner=1 nbr=2
    #   3: boundary, owner=2 wall
    owner = np.array([0, 0, 1, 2], dtype=np.int64)
    neighbour = np.array([-1, 1, 2, -1], dtype=np.int64)
    wall_face_indices = [0, 3]

    comps = _detect_wall_owner_cavity_components(
        owner, neighbour, wall_face_indices, n_cells=3
    )
    # Cell 1 is NOT a wall owner so the path 0—1—2 is broken.
    assert len(comps) == 2
    assert {0} in comps
    assert {2} in comps


def test_native_bl_apply_tet_cavity_replacement_plan_disabled_is_noop() -> None:
    """``enabled=False`` returns a structurally identical copy with no
    cells touched."""
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    faces = [
        [0, 1, 2],
        [0, 3, 1],
        [1, 3, 2],
        [2, 3, 0],
    ]
    owner = np.array([0, 0, 0, 0], dtype=np.int64)
    neighbour = np.array([], dtype=np.int64)
    plan = {"enabled": True, "n_planned": 1, "cells_to_delete": [0], "new_cells": [
        {
            "prism": [0, 1, 2, 4, 5, 6],
            "transition_tet": [-1, 4, 5, 6],
            "transition_tet_apex_xyz": [0.25, 0.25, 0.25],
            "deleted_cell_id": 0,
        }
    ], "new_points": np.zeros((3, 3))}

    applied = _apply_tet_cavity_replacement_plan(
        points,
        faces,
        owner,
        neighbour,
        [0],
        plan,
        enabled=False,
    )
    assert applied["enabled"] is False
    assert applied["n_replaced"] == 0
    assert applied["n_cells_before"] == applied["n_cells_after"] == 1
    np.testing.assert_array_equal(applied["new_points"], points)
    assert applied["new_faces"] == faces


def test_native_bl_cavity_shell_probes_agglomerated_interface_quality() -> None:
    """Cavity diagnostics predict exterior interface quality before agglomeration."""
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, -1.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    faces = [
        [0, 1, 2],  # selected-selected internal face
        [0, 3, 1],  # selected-outside internal face
        [1, 3, 2],
        [2, 3, 0],
        [0, 1, 4],
        [1, 2, 4],
        [2, 0, 4],
    ]
    owner = np.array([0, 0, 0, 0, 2, 2, 2], dtype=np.int64)
    neighbour = np.array([2, 1], dtype=np.int64)

    shell = _bl_cavity_shell_summary(
        points,
        faces,
        owner,
        neighbour,
        {0, 2},
        base_n_cells=2,
        prism_cell_start=2,
        prism_cell_end=3,
    )

    assert shell["is_closed_2manifold"] is True
    assert shell["n_boundary_faces"] == 6
    assert shell["n_physical_boundary_faces"] == 5
    assert shell["boundary_by_class"]["bulk-bulk"] == 1
    assert shell["agglomerate_probe"]["n_interface_faces"] == 1
    assert len(shell["agglomerate_probe"]["worst_faces"]) == 1
