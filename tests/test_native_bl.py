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
    _build_cavity_fan_transition_tets,
    _build_cavity_prism_inner_triangles,
    _build_cavity_shell_closure_tets,
    _build_tet_cavity_replacement_plan,
    _check_cavity_fan_tet_determinants,
    _check_cavity_fan_tet_pair_non_ortho,
    _check_cavity_fan_tet_pair_skewness,
    _check_cavity_fan_tet_shape_quality,
    _check_cavity_shell_coverage,
    _compute_cavity_centroid,
    _detect_wall_owner_cavity_components,
    _evaluate_cavity_component_candidates,
    _extract_cavity_component_boundary,
    _owner_centre_wall_motion,
    _split_cavity_inner_ids_at_sharp_corners,
    _stitch_cavity_prism_inner_ids_smooth,
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


def test_native_bl_extract_cavity_component_boundary_isolated_tet() -> None:
    """BLR-9c-b — single wall-owner tet has 1 wall face + 3 outward
    crossing faces (here all boundaries since the tet stands alone)."""
    # cell 0 owns 4 faces: 1 wall (boundary), 3 non-wall boundaries.
    owner = np.array([0, 0, 0, 0], dtype=np.int64)
    neighbour = np.array([-1, -1, -1, -1], dtype=np.int64)
    wall_face_indices = [0]

    out = _extract_cavity_component_boundary(
        {0}, owner, neighbour, wall_face_indices
    )
    assert out["wall_faces"] == [0]
    # The other 3 boundary faces are NOT wall — they go into the
    # external-internal pile so the refill caller can decide what to
    # do with them when the cell is removed.
    assert sorted(out["external_internal_faces"]) == [1, 2, 3]
    assert out["internal_faces"] == []


def test_native_bl_extract_cavity_component_boundary_two_tets() -> None:
    """Two-tet component: 1 internal face vanishes; 2 wall faces; the
    rest are external boundaries."""
    # Faces:
    #   0 wall, owner=0
    #   1 internal, owner=0 nbr=1
    #   2 boundary, owner=0 (non-wall — external_internal)
    #   3 wall, owner=1
    #   4 boundary, owner=1 (non-wall — external_internal)
    owner = np.array([0, 0, 0, 1, 1], dtype=np.int64)
    neighbour = np.array([-1, 1, -1, -1, -1], dtype=np.int64)
    wall_face_indices = [0, 3]

    out = _extract_cavity_component_boundary(
        {0, 1}, owner, neighbour, wall_face_indices
    )
    assert sorted(out["wall_faces"]) == [0, 3]
    assert out["internal_faces"] == [1]
    assert sorted(out["external_internal_faces"]) == [2, 4]


def test_native_bl_extract_cavity_component_boundary_external_internal_face() -> None:
    """Internal face whose owner is in the component but neighbour is
    OUT of the component → external_internal."""
    # Faces:
    #   0 wall, owner=0  (boundary)
    #   1 internal, owner=0 nbr=1  (1 is OUTSIDE the component)
    owner = np.array([0, 0], dtype=np.int64)
    neighbour = np.array([-1, 1], dtype=np.int64)
    wall_face_indices = [0]

    out = _extract_cavity_component_boundary(
        {0}, owner, neighbour, wall_face_indices
    )
    assert out["wall_faces"] == [0]
    assert out["internal_faces"] == []
    # Face 1 crosses the component boundary → external_internal.
    assert out["external_internal_faces"] == [1]


def test_native_bl_build_cavity_prism_inner_triangles_two_faces() -> None:
    """BLR-9c-c-i — two wall faces sharing edge (1, 2) yield 2
    independent entries; shared verts are NOT collapsed at this
    stage (BLR-9c-c-ii handles per-vertex sharing)."""
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [1.0, 1.0, 0.0],
        ],
        dtype=np.float64,
    )
    # Two coplanar wall triangles sharing edge (1, 2).
    faces = [[0, 1, 2], [1, 3, 2]]
    motion_dirs = {
        0: np.array([0.0, 0.0, 1.0], dtype=np.float64),
        1: np.array([0.0, 0.0, 1.0], dtype=np.float64),
        2: np.array([0.0, 0.0, 1.0], dtype=np.float64),
        3: np.array([0.0, 0.0, 1.0], dtype=np.float64),
    }

    triangles = _build_cavity_prism_inner_triangles(
        [0, 1], points, faces, motion_dirs, first_thickness=0.05
    )
    assert len(triangles) == 2
    # First triangle: outer (0, 1, 2), inner = those + 0.05 z.
    assert triangles[0]["face_id"] == 0
    assert triangles[0]["outer_verts"] == [0, 1, 2]
    np.testing.assert_allclose(
        triangles[0]["inner_xyz"],
        np.array([[0, 0, 0.05], [1, 0, 0.05], [0, 1, 0.05]], dtype=np.float64),
        atol=1e-12,
    )
    # Second triangle: outer (1, 3, 2).
    assert triangles[1]["face_id"] == 1
    assert triangles[1]["outer_verts"] == [1, 3, 2]
    np.testing.assert_allclose(
        triangles[1]["inner_xyz"],
        np.array([[1, 0, 0.05], [1, 1, 0.05], [0, 1, 0.05]], dtype=np.float64),
        atol=1e-12,
    )


def test_native_bl_build_cavity_prism_inner_triangles_skips_missing_motion() -> None:
    """Wall face with a vertex missing from ``motion_dirs`` is dropped
    silently — BLR-9c-c-ii will detect the missing entry."""
    points = np.array(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0]], dtype=np.float64
    )
    faces = [[0, 1, 2], [1, 3, 2]]
    motion_dirs = {  # vertex 3 deliberately missing
        0: np.array([0.0, 0.0, 1.0], dtype=np.float64),
        1: np.array([0.0, 0.0, 1.0], dtype=np.float64),
        2: np.array([0.0, 0.0, 1.0], dtype=np.float64),
    }

    triangles = _build_cavity_prism_inner_triangles(
        [0, 1], points, faces, motion_dirs, first_thickness=0.05
    )
    assert len(triangles) == 1
    assert triangles[0]["face_id"] == 0


def test_native_bl_build_cavity_prism_inner_triangles_disabled() -> None:
    """``motion_dirs=None`` or empty face list yields an empty result."""
    pts = np.zeros((3, 3), dtype=np.float64)
    faces = [[0, 1, 2]]
    assert (
        _build_cavity_prism_inner_triangles(
            [0], pts, faces, None, first_thickness=0.05
        )
        == []
    )
    assert (
        _build_cavity_prism_inner_triangles(
            [], pts, faces, {0: np.zeros(3)}, first_thickness=0.05
        )
        == []
    )


def test_native_bl_stitch_cavity_prism_inner_ids_smooth_two_faces() -> None:
    """BLR-9c-c-ii-a — two coplanar wall faces sharing edge (1, 2)
    collapse to 4 unique inner ids (verts 0, 1, 2, 3 each get one).
    The shared verts (1, 2) average their predicted positions across
    the two faces — identical for a coplanar smooth case."""
    points = np.array(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0]], dtype=np.float64
    )
    faces = [[0, 1, 2], [1, 3, 2]]
    motion_dirs = {
        v: np.array([0.0, 0.0, 1.0], dtype=np.float64) for v in range(4)
    }
    triangles = _build_cavity_prism_inner_triangles(
        [0, 1], points, faces, motion_dirs, first_thickness=0.05
    )

    out = _stitch_cavity_prism_inner_ids_smooth(triangles)
    assert out["inner_points"].shape == (4, 3)
    # vert_to_inner_id is sorted by wall vert id ascending.
    assert out["vert_to_inner_id"] == {0: 0, 1: 1, 2: 2, 3: 3}
    # Inner positions = wall + 0.05 * +z.
    np.testing.assert_allclose(
        out["inner_points"],
        np.array(
            [
                [0, 0, 0.05],
                [1, 0, 0.05],
                [0, 1, 0.05],
                [1, 1, 0.05],
            ],
            dtype=np.float64,
        ),
        atol=1e-12,
    )
    # Face 0 (outer 0,1,2) → inner ids (0, 1, 2).
    # Face 1 (outer 1,3,2) → inner ids (1, 3, 2).
    assert out["face_inner_ids"] == [[0, 1, 2], [1, 3, 2]]


def test_native_bl_stitch_cavity_prism_inner_ids_smooth_averages_disagreeing_predictions() -> None:
    """When two adjacent faces predict different inner positions for a
    shared vertex (e.g., motion_dirs differs across the cavity), the
    smooth stitcher AVERAGES them — this is the no-dup behaviour and
    will be replaced by per-face dup at sharp corners in
    BLR-9c-c-ii-b."""
    points = np.array(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0]], dtype=np.float64
    )
    faces = [[0, 1, 2], [1, 3, 2]]
    # Vertex 1 and 2 receive a different motion direction from each
    # face — but motion_dirs is per-vertex globally, so to fake the
    # disagreement use per-face entries.  The simplest way: build the
    # inner_triangles list manually with disagreeing predictions.
    triangles = [
        {
            "face_id": 0,
            "outer_verts": [0, 1, 2],
            "inner_xyz": np.array(
                [
                    [0.0, 0.0, 0.05],   # v=0
                    [1.0, 0.0, 0.05],   # v=1
                    [0.0, 1.0, 0.05],   # v=2
                ],
                dtype=np.float64,
            ),
        },
        {
            "face_id": 1,
            "outer_verts": [1, 3, 2],
            "inner_xyz": np.array(
                [
                    [1.0, 0.0, 0.10],   # v=1 — disagrees with face 0
                    [1.0, 1.0, 0.10],   # v=3
                    [0.0, 1.0, 0.10],   # v=2 — disagrees
                ],
                dtype=np.float64,
            ),
        },
    ]

    out = _stitch_cavity_prism_inner_ids_smooth(triangles)
    # Vert 1 mean = ([1,0,0.05] + [1,0,0.10]) / 2 = [1, 0, 0.075]
    np.testing.assert_allclose(
        out["inner_points"][out["vert_to_inner_id"][1]],
        [1.0, 0.0, 0.075],
        atol=1e-12,
    )
    np.testing.assert_allclose(
        out["inner_points"][out["vert_to_inner_id"][2]],
        [0.0, 1.0, 0.075],
        atol=1e-12,
    )
    # Non-shared verts use the single contribution.
    np.testing.assert_allclose(
        out["inner_points"][out["vert_to_inner_id"][0]],
        [0.0, 0.0, 0.05],
        atol=1e-12,
    )
    np.testing.assert_allclose(
        out["inner_points"][out["vert_to_inner_id"][3]],
        [1.0, 1.0, 0.10],
        atol=1e-12,
    )


def test_native_bl_stitch_cavity_prism_inner_ids_smooth_empty() -> None:
    out = _stitch_cavity_prism_inner_ids_smooth([])
    assert out["inner_points"].shape == (0, 3)
    assert out["vert_to_inner_id"] == {}
    assert out["face_inner_ids"] == []


def test_native_bl_split_cavity_inner_ids_at_sharp_corners_smooth_no_split() -> None:
    """BLR-9c-c-ii-b — coplanar adjacent prism caps (cos = 1.0) → no
    sharp verts → output identical to the smooth stitcher."""
    points = np.array(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0]], dtype=np.float64
    )
    faces = [[0, 1, 2], [1, 3, 2]]
    motion_dirs = {
        v: np.array([0.0, 0.0, 1.0], dtype=np.float64) for v in range(4)
    }
    triangles = _build_cavity_prism_inner_triangles(
        [0, 1], points, faces, motion_dirs, first_thickness=0.05
    )
    smooth = _stitch_cavity_prism_inner_ids_smooth(triangles)

    out = _split_cavity_inner_ids_at_sharp_corners(
        triangles, smooth, cos_thresh=0.9
    )
    assert out["n_split"] == 0
    assert out["sharp_verts"] == {}
    np.testing.assert_array_equal(out["inner_points"], smooth["inner_points"])
    assert out["face_inner_ids"] == smooth["face_inner_ids"]


def test_native_bl_split_cavity_inner_ids_at_sharp_corners_perpendicular_caps() -> None:
    """Two prism caps with perpendicular normals (cos = 0) at shared
    edge → both shared verts split into per-face dup ids."""
    points = np.array(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0]], dtype=np.float64
    )
    # Build two prism cap triangles whose normals are perpendicular.
    triangles = [
        {
            "face_id": 0,
            "outer_verts": [0, 1, 2],
            "inner_xyz": np.array(
                [
                    [0.0, 0.0, 0.05],
                    [1.0, 0.0, 0.05],
                    [0.0, 1.0, 0.05],
                ],
                dtype=np.float64,
            ),
            # Implied normal: (1,0,0)×(0,1,0) = (0,0,1) → +z.
        },
        {
            "face_id": 1,
            "outer_verts": [1, 3, 2],
            "inner_xyz": np.array(
                [
                    [1.0, 0.0, 0.0],   # i for v=1
                    [1.0, 1.0, 0.0],   # i for v=3
                    [1.0, 0.0, 1.0],   # i for v=2
                ],
                dtype=np.float64,
            ),
            # Implied normal: (i1-i0)×(i2-i0) = (0,1,0)×(0,0,1) = (1,0,0)
            # → +x, perpendicular to face 0's +z normal.
        },
    ]
    smooth = _stitch_cavity_prism_inner_ids_smooth(triangles)

    out = _split_cavity_inner_ids_at_sharp_corners(
        triangles, smooth, cos_thresh=0.9
    )
    # Verts 1 and 2 are shared → both should split.
    assert out["n_split"] == 2
    assert set(out["sharp_verts"].keys()) == {1, 2}
    # Each split adds 1 new inner id (first face keeps smooth id, second
    # face gets a fresh dup id).  smooth had 4 inner ids → after split
    # should have 4 + 2 = 6.
    assert out["inner_points"].shape == (6, 3)
    # Face 0 still uses smooth ids for verts 1, 2.
    assert out["face_inner_ids"][0] == smooth["face_inner_ids"][0]
    # Face 1 uses dup ids for shared verts 1 and 2.  Vertex 3 is not
    # shared → keeps smooth id.
    assert out["face_inner_ids"][1][0] != smooth["face_inner_ids"][1][0]
    assert out["face_inner_ids"][1][2] != smooth["face_inner_ids"][1][2]
    # Vertex 3 (face 1, position 1) was NOT shared → smooth id retained.
    assert out["face_inner_ids"][1][1] == smooth["face_inner_ids"][1][1]


def test_native_bl_split_cavity_inner_ids_at_sharp_corners_empty() -> None:
    smooth = _stitch_cavity_prism_inner_ids_smooth([])
    out = _split_cavity_inner_ids_at_sharp_corners([], smooth)
    assert out["n_split"] == 0
    assert out["sharp_verts"] == {}
    assert out["inner_points"].shape == (0, 3)
    assert out["face_inner_ids"] == []


def test_native_bl_compute_cavity_centroid_single_tet() -> None:
    """BLR-9c-c-iii-a — single-cell cavity centroid is the mean of
    that cell's 4 unique vertices."""
    points = np.array(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64
    )
    faces = [[0, 1, 2], [0, 3, 1], [1, 3, 2], [2, 3, 0]]
    owner = np.array([0, 0, 0, 0], dtype=np.int64)
    neighbour = np.array([-1, -1, -1, -1], dtype=np.int64)

    apex = _compute_cavity_centroid({0}, faces, points, owner, neighbour)
    np.testing.assert_allclose(apex, points.mean(axis=0), atol=1e-12)


def test_native_bl_compute_cavity_centroid_two_tets_shared_face() -> None:
    """Two-cell cavity centroid is the mean of the union of their
    vertices (shared verts only count once)."""
    points = np.array(
        [
            [0, 0, 0], [1, 0, 0], [0, 1, 0],
            [0, 0, 1], [1, 1, 1],
        ],
        dtype=np.float64,
    )
    # Cell 0 verts: 0,1,2,3 ; cell 1 verts: 0,1,2,4 — union = {0,1,2,3,4}.
    faces = [
        [0, 1, 2],
        [0, 3, 1],
        [1, 3, 2],
        [2, 3, 0],
        [0, 1, 4],
        [1, 2, 4],
        [2, 0, 4],
    ]
    owner = np.array([0, 0, 0, 0, 1, 1, 1], dtype=np.int64)
    neighbour = np.array([-1, -1, -1, -1, -1, -1, -1], dtype=np.int64)

    apex = _compute_cavity_centroid(
        {0, 1}, faces, points, owner, neighbour
    )
    np.testing.assert_allclose(
        apex, points[[0, 1, 2, 3, 4]].mean(axis=0), atol=1e-12
    )


def test_native_bl_compute_cavity_centroid_empty() -> None:
    """Empty component → zero apex (defensive)."""
    apex = _compute_cavity_centroid(
        set(),
        [[0, 1, 2]],
        np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float64),
        np.array([0], dtype=np.int64),
        np.array([], dtype=np.int64),
    )
    np.testing.assert_array_equal(apex, np.zeros(3))


def test_native_bl_build_cavity_fan_transition_tets_smooth_two_faces() -> None:
    """BLR-9c-c-iii-b — two coplanar wall faces yield two fan tets,
    each with apex placeholder ``-1`` and the per-face inner ids
    from the smooth stitcher."""
    points = np.array(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0]], dtype=np.float64
    )
    faces = [[0, 1, 2], [1, 3, 2]]
    motion_dirs = {
        v: np.array([0.0, 0.0, 1.0], dtype=np.float64) for v in range(4)
    }
    triangles = _build_cavity_prism_inner_triangles(
        [0, 1], points, faces, motion_dirs, first_thickness=0.05
    )
    smooth = _stitch_cavity_prism_inner_ids_smooth(triangles)
    split = _split_cavity_inner_ids_at_sharp_corners(triangles, smooth)

    fan = _build_cavity_fan_transition_tets(triangles, split)
    assert len(fan) == 2
    assert fan[0]["face_id"] == 0
    assert fan[0]["tet_verts"] == [-1, 0, 1, 2]
    assert fan[1]["face_id"] == 1
    assert fan[1]["tet_verts"] == [-1, 1, 3, 2]


def test_native_bl_build_cavity_fan_transition_tets_empty() -> None:
    """Empty inputs → empty fan list."""
    assert _build_cavity_fan_transition_tets([], {"face_inner_ids": []}) == []
    assert (
        _build_cavity_fan_transition_tets(
            [{"face_id": 0, "outer_verts": [0, 1, 2], "inner_xyz": np.zeros((3, 3))}],
            {"face_inner_ids": []},
        )
        == []
    )


def test_native_bl_check_cavity_shell_coverage_no_shell_no_op() -> None:
    """BLR-9c-c-iii-c — empty external_internal shell → trivially
    covered."""
    out = _check_cavity_shell_coverage(
        {"external_internal_faces": []},
        [{"face_id": 0, "tet_verts": [-1, 0, 1, 2]}],
        [[0, 1, 2]],
    )
    assert out == {"n_shell_faces": 0, "n_covered": 0, "uncovered": []}


def test_native_bl_check_cavity_shell_coverage_face_present_in_tet_face() -> None:
    """A shell face whose vertex set matches one of the tet's 4 faces
    is reported as covered."""
    # Single fan tet [apex, 0, 1, 2] has 4 faces (vertex sets):
    #   {apex, 0, 1}, {apex, 1, 2}, {apex, 0, 2}, {0, 1, 2}.
    # Use apex placeholder = 9 so the matching vertex set is (0, 1, 9).
    faces = [[0, 1, 9]]      # face_id 0 uses verts {0, 1, 9}
    fan_tets = [{"face_id": 99, "tet_verts": [9, 0, 1, 2]}]
    out = _check_cavity_shell_coverage(
        {"external_internal_faces": [0]}, fan_tets, faces
    )
    assert out["n_shell_faces"] == 1
    assert out["n_covered"] == 1
    assert out["uncovered"] == []


def test_native_bl_check_cavity_shell_coverage_uncovered_returned() -> None:
    """Shell face whose verts have no match in any tet face → reported
    as uncovered (this is the typical BLR-9c-c-iii-c gap before
    additional transition cells are added)."""
    faces = [[5, 6, 7]]   # external_internal face — no tet face touches these.
    fan_tets = [{"face_id": 0, "tet_verts": [-1, 0, 1, 2]}]
    out = _check_cavity_shell_coverage(
        {"external_internal_faces": [0]}, fan_tets, faces
    )
    assert out["n_shell_faces"] == 1
    assert out["n_covered"] == 0
    assert out["uncovered"] == [0]


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


def test_native_bl_evaluate_cavity_component_candidates_empty_components() -> None:
    """BLR-9c-d — empty component list returns zero-record summary."""
    out = _evaluate_cavity_component_candidates(
        components=[],
        points=np.zeros((0, 3)),
        faces=[],
        owner=np.array([], dtype=np.int64),
        neighbour=np.array([], dtype=np.int64),
        wall_face_indices=[],
        motion_dirs={},
        first_thickness=0.05,
    )
    assert out["n_components"] == 0
    assert out["n_accepted"] == 0
    assert out["n_rejected_uncovered_shell"] == 0
    assert out["components"] == []


def test_native_bl_evaluate_cavity_component_candidates_isolated_tet_accept() -> None:
    """BLR-9c-d — single isolated wall-owner tet without
    external_internal shell: shell coverage = 0 uncovered → ``accept``."""
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
        [0, 1, 2],   # wall (face 0)
        [0, 3, 1],   # wall (face 1)
        [1, 3, 2],   # wall (face 2)
        [2, 3, 0],   # wall (face 3)
    ]
    owner = np.array([0, 0, 0, 0], dtype=np.int64)
    neighbour = np.array([], dtype=np.int64)
    motion_dirs = {
        0: np.array([1.0, 1.0, 1.0]) / np.sqrt(3.0),
        1: np.array([1.0, 1.0, 1.0]) / np.sqrt(3.0),
        2: np.array([1.0, 1.0, 1.0]) / np.sqrt(3.0),
        3: np.array([1.0, 1.0, 1.0]) / np.sqrt(3.0),
    }
    out = _evaluate_cavity_component_candidates(
        components=[{0}],
        points=points,
        faces=faces,
        owner=owner,
        neighbour=neighbour,
        wall_face_indices=[0, 1, 2, 3],
        motion_dirs=motion_dirs,
        first_thickness=0.05,
    )
    assert out["n_components"] == 1
    assert out["n_accepted"] == 1
    assert out["n_rejected_uncovered_shell"] == 0
    rec = out["components"][0]
    assert rec["cells"] == [0]
    assert rec["n_cells"] == 1
    assert rec["n_wall_faces"] == 4
    assert rec["n_shell_faces"] == 0
    assert rec["decision"] == "accept"
    # BLR-9c-d-c — det fields populated and consistent with `accept`.
    assert "n_fan_pos_det" in rec
    assert "n_fan_neg_det" in rec
    assert "n_fan_degenerate_det" in rec
    assert rec["n_fan_bad_indices"] == 0
    assert rec["fan_worst_abs_det"] > 0.0
    # BLR-9c-d-d-2 — Q-shape fields populated and consistent with `accept`.
    assert rec["n_fan_bad_shape_indices"] == 0
    assert rec["fan_q_min"] > 0.0
    assert rec["fan_q_mean"] > 0.0
    # BLR-9c-d-e-2 — non-ortho fields populated. The default
    # ``sharp_cos_thresh = 0.9`` splits each tet vertex per-face,
    # so the fan tets have no shared inner edges and the helper
    # reports zero pairs — accepted as such.
    assert "n_fan_pair_count" in rec
    assert rec["n_fan_pair_bad_non_ortho"] == 0
    assert rec["fan_pair_max_non_ortho_deg"] >= 0.0
    # BLR-9c-d-f-2 — skewness fields populated and consistent with `accept`.
    assert rec["n_fan_pair_bad_skewness"] == 0
    assert rec["fan_pair_max_skew"] >= 0.0
    # BLR-9c-d-h-2 — closure-tet fields populated.  The isolated-tet
    # fixture has no ``external_internal`` shell face so no closure
    # tets are emitted; ``n_total_tets == n_fan_tets``.
    assert rec["n_closure_tets"] == 0
    assert rec["n_total_tets"] == rec["n_fan_tets"]
    assert rec["n_shell_uncovered_pre_closure"] == 0


def test_native_bl_evaluate_cavity_component_candidates_external_shell_closed_by_h1() -> None:
    """BLR-9c-d — wall-owner cell whose neighbour cell is non-wall
    used to be reported as ``reject_uncovered_shell``; the BLR-9c-d-h-1
    closure helper now emits one transition tet per uncovered shell
    face and shell coverage drops to zero, so the component falls
    through the rest of the gates and (for this benign fixture) ends
    up ``accept``.  This test pins the closure end-to-end:

      pre_closure shell_uncovered > 0  →  closure_tets emitted
      → post_closure shell_uncovered == 0  →  decision != reject_uncovered_shell
    """
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [0.5, 0.5, 0.5],
        ],
        dtype=np.float64,
    )
    faces = [
        [0, 1, 2],   # wall
        [0, 3, 1],   # wall
        [1, 3, 2],   # wall
        [2, 3, 0],   # internal (cell 0 ↔ cell 1)
        [2, 3, 4],   # bulk-bulk
    ]
    owner = np.array([0, 0, 0, 0, 1], dtype=np.int64)
    neighbour = np.array([1], dtype=np.int64)
    motion_dirs = {
        i: np.array([1.0, 1.0, 1.0]) / np.sqrt(3.0) for i in range(5)
    }
    out = _evaluate_cavity_component_candidates(
        components=[{0}],
        points=points,
        faces=faces,
        owner=owner,
        neighbour=neighbour,
        wall_face_indices=[0, 1, 2],
        motion_dirs=motion_dirs,
        first_thickness=0.05,
    )
    assert out["n_components"] == 1
    rec = out["components"][0]
    assert rec["n_shell_faces"] >= 1
    # Pre-closure the fan structure leaves the shell open; closure
    # tets close it.
    assert rec["n_shell_uncovered_pre_closure"] >= 1
    assert rec["n_closure_tets"] >= 1
    assert rec["n_shell_uncovered"] == 0
    assert rec["decision"] != "reject_uncovered_shell"
    assert out["n_rejected_uncovered_shell"] == 0


def test_native_bl_evaluate_cavity_component_candidates_reject_bad_det() -> None:
    """BLR-9c-d-c — wall-only component (no external_internal shell)
    whose fan tets are *all* degenerate (apex coincides with all inner
    triangles within tolerance) ends up flagged ``reject_bad_det``,
    not ``accept``.

    Construction: a single wall-owner cell whose 4 wall faces enclose
    a tet, with all motion directions and ``first_thickness`` set to
    zero so ``inner_points`` exactly coincide with the wall vertices.
    The cavity centroid (apex) is the mean of those four wall
    vertices; we then force the test fixture into degeneracy by
    placing all four wall vertices on a common plane that includes
    the centroid — this collapses every fan-tet's signed determinant
    to zero, which is what the bad_det gate is designed to catch.
    """
    # All four "tet" vertices coplanar (z = 0) ⇒ centroid also has
    # z = 0 ⇒ every fan tet has zero signed volume.
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [1.0, 1.0, 0.0],
        ],
        dtype=np.float64,
    )
    faces = [
        [0, 1, 2],
        [0, 2, 3],
        [0, 3, 1],
        [1, 3, 2],
    ]
    owner = np.array([0, 0, 0, 0], dtype=np.int64)
    neighbour = np.array([], dtype=np.int64)
    motion_dirs = {i: np.zeros(3) for i in range(4)}
    out = _evaluate_cavity_component_candidates(
        components=[{0}],
        points=points,
        faces=faces,
        owner=owner,
        neighbour=neighbour,
        wall_face_indices=[0, 1, 2, 3],
        motion_dirs=motion_dirs,
        first_thickness=0.0,
    )
    assert out["n_components"] == 1
    rec = out["components"][0]
    # Wall-only ⇒ no external_internal shell.
    assert rec["n_shell_faces"] == 0
    assert rec["n_shell_uncovered"] == 0
    # All fan tets degenerate.
    assert rec["n_fan_bad_indices"] >= 1
    assert rec["decision"] == "reject_bad_det"
    assert out["n_rejected_bad_det"] == 1
    assert out["n_accepted"] == 0
    assert out["n_rejected_uncovered_shell"] == 0


def test_native_bl_evaluate_cavity_component_candidates_reject_bad_shape() -> None:
    """BLR-9c-d-d-2 — wall-only single-tet component whose geometry
    is *very flat* (one vertex barely above the base plane) produces
    sliver fan tets that pass the determinant gate but fail the
    Klingner Q-shape gate, ending up flagged ``reject_bad_shape``."""
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1e-3],   # near-coplanar with the base ⇒ slivery cavity
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
    motion_dirs = {i: np.zeros(3) for i in range(4)}
    out = _evaluate_cavity_component_candidates(
        components=[{0}],
        points=points,
        faces=faces,
        owner=owner,
        neighbour=neighbour,
        wall_face_indices=[0, 1, 2, 3],
        motion_dirs=motion_dirs,
        first_thickness=0.0,
    )
    assert out["n_components"] == 1
    rec = out["components"][0]
    # Wall-only ⇒ no shell rejection.
    assert rec["n_shell_uncovered"] == 0
    # Cavity is non-degenerate (apex above base plane by 0.25e-3),
    # so determinant gate should *pass* (no bad_indices).
    assert rec["n_fan_bad_indices"] == 0
    # But every fan tet is a slab/sliver ⇒ Q below threshold.
    assert rec["n_fan_bad_shape_indices"] >= 1
    assert rec["fan_q_min"] < 0.1
    assert rec["decision"] == "reject_bad_shape"
    assert out["n_rejected_bad_shape"] == 1
    assert out["n_accepted"] == 0
    assert out["n_rejected_bad_det"] == 0


def test_native_bl_check_cavity_fan_tet_determinants_empty() -> None:
    """BLR-9c-d-b — empty fan list returns zero record."""
    out = _check_cavity_fan_tet_determinants(
        [], np.zeros(3), np.zeros((0, 3))
    )
    assert out["n_tets"] == 0
    assert out["n_pos_det"] == 0
    assert out["n_neg_det"] == 0
    assert out["n_degenerate_det"] == 0
    assert out["worst_abs_det"] == 0.0
    assert out["bad_indices"] == []


def test_native_bl_check_cavity_fan_tet_determinants_consistent_signs_pass() -> None:
    """BLR-9c-d-b — fan tets that all share one sign and have
    non-degenerate determinant produce zero ``bad_indices``."""
    apex = np.array([0.0, 0.0, 0.0])
    inner_points = np.array(
        [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [0.5, 0.5, 0.5],   # off-plane to keep both tets non-degenerate
        ],
        dtype=np.float64,
    )
    # Two fan tets, both with the same winding (consistent-sign
    # determinant in the apex / inner-points frame).
    fan_tets = [
        {"face_id": 0, "tet_verts": [-1, 0, 1, 2]},
        {"face_id": 1, "tet_verts": [-1, 0, 1, 3]},
    ]
    out = _check_cavity_fan_tet_determinants(fan_tets, apex, inner_points)
    assert out["n_tets"] == 2
    assert out["n_degenerate_det"] == 0
    # Either all positive or all negative is fine; what matters is
    # that no tet ends up in `bad_indices`.
    assert out["n_pos_det"] + out["n_neg_det"] == 2
    assert out["bad_indices"] == []


def test_native_bl_check_cavity_fan_tet_determinants_flipped_minority_diagnostic() -> None:
    """BLR-9c-d-i-1 — sign-inconsistency is reported as a *diagnostic*
    via ``n_sign_inconsistent`` but is no longer added to
    ``bad_indices``.  The polyMesh writer can re-orient any cell at
    emission time, so a winding mismatch between the BLR-9c-c-iii-b
    fan and the BLR-9c-d-h-1 closure tets is recoverable and must not
    veto an otherwise-valid cavity replacement candidate."""
    apex = np.array([0.0, 0.0, 0.0])
    inner_points = np.array(
        [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [1.0, 1.0, 1.0],
        ],
        dtype=np.float64,
    )
    fan_tets = [
        {"face_id": 0, "tet_verts": [-1, 0, 1, 2]},
        {"face_id": 1, "tet_verts": [-1, 0, 1, 3]},
        # Index swap inverts the sign.
        {"face_id": 2, "tet_verts": [-1, 1, 0, 2]},
    ]
    out = _check_cavity_fan_tet_determinants(fan_tets, apex, inner_points)
    assert out["n_tets"] == 3
    assert out["n_pos_det"] >= 1
    assert out["n_neg_det"] >= 1
    # Diagnostic recorded …
    assert out["n_sign_inconsistent"] >= 1
    # … but no minority-sign tet is reported in ``bad_indices``.
    assert out["bad_indices"] == []


def test_native_bl_check_cavity_fan_tet_pair_non_ortho_empty_or_singleton() -> None:
    """BLR-9c-d-e-1 — fewer than two fan tets ⇒ no internal pair to
    measure ⇒ zero record."""
    apex = np.zeros(3)
    inner_points = np.eye(3)
    out_empty = _check_cavity_fan_tet_pair_non_ortho([], apex, inner_points)
    assert out_empty["n_pairs"] == 0
    assert out_empty["max_angle_deg"] == 0.0
    assert out_empty["bad_pair_indices"] == []
    out_one = _check_cavity_fan_tet_pair_non_ortho(
        [{"face_id": 0, "tet_verts": [-1, 0, 1, 2]}], apex, inner_points
    )
    assert out_one["n_pairs"] == 0
    assert out_one["bad_pair_indices"] == []


def test_native_bl_check_cavity_fan_tet_pair_non_ortho_two_tets_share_edge() -> None:
    """BLR-9c-d-e-1 — two fan tets that share two inner indices form
    one adjacent pair; the helper measures one non-ortho angle."""
    apex = np.array([0.0, 0.0, 1.0])     # apex above the xy-plane
    inner_points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.5, 1.0, 0.0],
            [0.5, -1.0, 0.0],
        ],
        dtype=np.float64,
    )
    fan_tets = [
        # Triangle 1: indices 0, 1, 2
        {"face_id": 0, "tet_verts": [-1, 0, 1, 2]},
        # Triangle 2: indices 0, 1, 3 — shares edge (0, 1) with tri 1
        {"face_id": 1, "tet_verts": [-1, 0, 1, 3]},
    ]
    out = _check_cavity_fan_tet_pair_non_ortho(fan_tets, apex, inner_points)
    assert out["n_pairs"] == 1
    assert out["angles_deg"].shape == (1,)
    assert 0.0 <= out["max_angle_deg"] <= 90.0
    assert out["mean_angle_deg"] == out["max_angle_deg"]


def test_native_bl_check_cavity_fan_tet_pair_non_ortho_no_shared_edge() -> None:
    """BLR-9c-d-e-1 — two fan tets that share no inner edge ⇒ no
    pair counted."""
    apex = np.zeros(3)
    inner_points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [1.0, 1.0, 0.0],
            [1.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    # Two disjoint inner triangles — no shared inner edge.
    fan_tets = [
        {"face_id": 0, "tet_verts": [-1, 0, 1, 2]},
        {"face_id": 1, "tet_verts": [-1, 3, 4, 5]},
    ]
    out = _check_cavity_fan_tet_pair_non_ortho(fan_tets, apex, inner_points)
    assert out["n_pairs"] == 0
    assert out["bad_pair_indices"] == []


def test_native_bl_check_cavity_fan_tet_pair_non_ortho_threshold_flagged() -> None:
    """BLR-9c-d-e-1 — a pair whose angle exceeds the threshold ends
    up in ``bad_pair_indices``.  Use an asymmetric fixture so the
    cell-to-cell vector is not parallel to the shared face normal,
    yielding a positive non-orthogonality angle."""
    apex = np.array([0.0, 0.0, 1.0])
    inner_points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [1.0, 1.0, 0.0],
        ],
        dtype=np.float64,
    )
    fan_tets = [
        # Triangle 1: indices 0, 1, 2
        {"face_id": 0, "tet_verts": [-1, 0, 1, 2]},
        # Triangle 2: indices 1, 3, 2 — shares edge (1, 2) with tri 1
        {"face_id": 1, "tet_verts": [-1, 1, 3, 2]},
    ]
    # Picking 10° as an aggressive cap forces the resulting ~35°
    # pair angle into the bad list.
    out = _check_cavity_fan_tet_pair_non_ortho(
        fan_tets, apex, inner_points, non_ortho_threshold_deg=10.0
    )
    assert out["n_pairs"] == 1
    assert out["max_angle_deg"] > 10.0
    assert out["n_above_threshold"] == 1
    assert len(out["bad_pair_indices"]) == 1


def test_native_bl_build_cavity_shell_closure_tets_empty_uncovered() -> None:
    """BLR-9c-d-h-1 — empty uncovered list ⇒ no closure tet, inner
    points untouched."""
    inner_points = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]], dtype=np.float64
    )
    out = _build_cavity_shell_closure_tets(
        uncovered_face_ids=[],
        boundary={"external_internal_faces": []},
        faces=[],
        points=np.zeros((0, 3)),
        inner_points=inner_points,
    )
    assert out["n_closure_tets"] == 0
    assert out["n_appended_points"] == 0
    assert out["shell_closure_tets"] == []
    np.testing.assert_array_equal(
        out["extended_inner_points"], inner_points
    )


def test_native_bl_build_cavity_shell_closure_tets_one_face_extends_inner() -> None:
    """BLR-9c-d-h-1 — one uncovered shell face appends 3 inner points
    and emits one closure tet referring to those new ids."""
    inner_points = np.array(
        [[0.5, 0.5, 0.0]], dtype=np.float64
    )
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    faces = [[0, 1, 2], [0, 1, 3]]
    boundary = {
        "external_internal_faces": [0],
    }
    out = _build_cavity_shell_closure_tets(
        uncovered_face_ids=[0],
        boundary=boundary,
        faces=faces,
        points=points,
        inner_points=inner_points,
    )
    assert out["n_closure_tets"] == 1
    assert out["n_appended_points"] == 3   # verts 0, 1, 2 added
    closure = out["shell_closure_tets"][0]
    assert closure["face_id"] == 0
    assert closure["outer_verts"] == [0, 1, 2]
    assert closure["tet_verts"][0] == -1
    # New inner ids start at 1 (since inner_points had 1 entry).
    assert sorted(closure["tet_verts"][1:]) == [1, 2, 3]
    # Extended inner_points now has 1 (original) + 3 (appended) = 4.
    assert out["extended_inner_points"].shape == (4, 3)


def test_native_bl_build_cavity_shell_closure_tets_shared_verts_dedup() -> None:
    """BLR-9c-d-h-1 — multiple uncovered shell faces sharing vertices
    only append each polyMesh vertex once."""
    inner_points = np.zeros((0, 3), dtype=np.float64)
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [1.0, 1.0, 0.0],
        ],
        dtype=np.float64,
    )
    # Two triangles sharing edge (0, 1).
    faces = [[0, 1, 2], [0, 1, 3]]
    boundary = {"external_internal_faces": [0, 1]}
    out = _build_cavity_shell_closure_tets(
        uncovered_face_ids=[0, 1],
        boundary=boundary,
        faces=faces,
        points=points,
        inner_points=inner_points,
    )
    assert out["n_closure_tets"] == 2
    # Shared vertices 0 and 1 deduplicated ⇒ 4 total appended (0,1,2,3).
    assert out["n_appended_points"] == 4


def test_native_bl_build_cavity_shell_closure_tets_quad_picks_shortest_diagonal() -> None:
    """BLR-9c-d-m-1 — for a quad shell face the helper picks the
    shorter of the two possible diagonals so adjacent closure tets
    don't share the long axis (which produces the wide-angle /
    sliver pairs the BLR-9c-d-l-1 audit flagged)."""
    inner_points = np.zeros((0, 3), dtype=np.float64)
    # Elongated quad on z = 0:  v0 = (0,0), v1 = (4,0), v2 = (4,1),
    # v3 = (0,1).  Diagonal (v0, v2) = sqrt(17) ≈ 4.12, diagonal
    # (v1, v3) = sqrt(17) ≈ 4.12 — equal, default branch wins
    # (v0, v2).  We instead use a *clearly* asymmetric quad to test
    # selection.
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [4.0, 0.0, 0.0],
            [4.0, 0.1, 0.0],
            [0.0, 5.0, 0.0],
        ],
        dtype=np.float64,
    )
    faces = [[0, 1, 2, 3]]
    boundary = {"external_internal_faces": [0]}
    out = _build_cavity_shell_closure_tets(
        uncovered_face_ids=[0],
        boundary=boundary,
        faces=faces,
        points=points,
        inner_points=inner_points,
    )
    assert out["n_closure_tets"] == 2
    # |v0 - v2| = sqrt(16 + 0.01)  ≈ 4.001
    # |v1 - v3| = sqrt(16 + 25)    ≈ 6.40   ⇒ pick (v0, v2)
    # Shared diagonal vertices appear in both tets' tet_verts.
    tv0 = set(out["shell_closure_tets"][0]["tet_verts"][1:])
    tv1 = set(out["shell_closure_tets"][1]["tet_verts"][1:])
    shared = tv0 & tv1
    assert len(shared) == 2
    # Inner ids 0 and 2 correspond to polyMesh verts 0 and 2 — the
    # shorter-diagonal endpoints.
    assert shared == {0, 2}


def test_native_bl_build_cavity_shell_closure_tets_skips_invalid() -> None:
    """BLR-9c-d-h-1 — entries that aren't in ``external_internal_faces``
    or that point at non-triangle / out-of-range faces are skipped
    silently."""
    inner_points = np.zeros((0, 3), dtype=np.float64)
    points = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]], dtype=np.float64)
    faces = [[0, 1], [0, 1, 99]]   # quad and OOB index
    boundary = {"external_internal_faces": [0, 1, 2]}
    out = _build_cavity_shell_closure_tets(
        uncovered_face_ids=[0, 1, 2, 99],   # 99 ≠ valid_shell
        boundary=boundary,
        faces=faces,
        points=points,
        inner_points=inner_points,
    )
    assert out["n_closure_tets"] == 0
    assert out["n_appended_points"] == 0


def test_native_bl_check_cavity_fan_tet_pair_skewness_empty_or_singleton() -> None:
    """BLR-9c-d-f-1 — fewer than two fan tets ⇒ no internal pair to
    measure ⇒ zero record."""
    apex = np.zeros(3)
    inner_points = np.eye(3)
    out_empty = _check_cavity_fan_tet_pair_skewness([], apex, inner_points)
    assert out_empty["n_pairs"] == 0
    assert out_empty["max_skew"] == 0.0
    assert out_empty["bad_pair_indices"] == []
    out_one = _check_cavity_fan_tet_pair_skewness(
        [{"face_id": 0, "tet_verts": [-1, 0, 1, 2]}], apex, inner_points
    )
    assert out_one["n_pairs"] == 0


def test_native_bl_check_cavity_fan_tet_pair_skewness_symmetric_fan_low_skew() -> None:
    """BLR-9c-d-f-1 — a mirror-symmetric fan keeps skewness well
    below the OpenFOAM checkMesh cap (4.0)."""
    apex = np.array([0.0, 0.0, 1.0])
    inner_points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.5, 1.0, 0.0],
            [0.5, -1.0, 0.0],
        ],
        dtype=np.float64,
    )
    fan_tets = [
        {"face_id": 0, "tet_verts": [-1, 0, 1, 2]},
        {"face_id": 1, "tet_verts": [-1, 0, 1, 3]},
    ]
    out = _check_cavity_fan_tet_pair_skewness(fan_tets, apex, inner_points)
    assert out["n_pairs"] == 1
    # Mirror-symmetric about edge (0,1) keeps skewness small. The
    # apex z-coordinate is unequal to the cell-centroid z, so the
    # face centroid is offset from the OF line along z, but the
    # offset is bounded — well under the checkMesh cap of 4.
    assert out["max_skew"] < 1.0
    assert out["bad_pair_indices"] == []


def test_native_bl_check_cavity_fan_tet_pair_skewness_threshold_flagged() -> None:
    """BLR-9c-d-f-1 — pairs above the threshold land in
    ``bad_pair_indices``.  Use a tight cap so the (low) skew of a
    benign asymmetric fixture still gets flagged."""
    apex = np.array([0.0, 0.0, 1.0])
    inner_points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [1.0, 1.0, 0.0],
        ],
        dtype=np.float64,
    )
    fan_tets = [
        {"face_id": 0, "tet_verts": [-1, 0, 1, 2]},
        {"face_id": 1, "tet_verts": [-1, 1, 3, 2]},
    ]
    # Aggressive cap so any non-zero skew flags.
    out = _check_cavity_fan_tet_pair_skewness(
        fan_tets, apex, inner_points, skew_threshold=1e-6
    )
    assert out["n_pairs"] == 1
    if out["max_skew"] > 1e-6:
        assert out["n_above_threshold"] == 1
        assert len(out["bad_pair_indices"]) == 1
    else:
        # Symmetric ⇒ degenerate case; should report zero.
        assert out["n_above_threshold"] == 0


def test_native_bl_check_cavity_fan_tet_pair_skewness_no_shared_edge() -> None:
    """BLR-9c-d-f-1 — fan tets that share no inner edge ⇒ no pair
    counted, like the non-ortho helper."""
    apex = np.zeros(3)
    inner_points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [1.0, 1.0, 0.0],
            [1.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    fan_tets = [
        {"face_id": 0, "tet_verts": [-1, 0, 1, 2]},
        {"face_id": 1, "tet_verts": [-1, 3, 4, 5]},
    ]
    out = _check_cavity_fan_tet_pair_skewness(fan_tets, apex, inner_points)
    assert out["n_pairs"] == 0
    assert out["bad_pair_indices"] == []


def test_native_bl_check_cavity_fan_tet_shape_quality_empty() -> None:
    """BLR-9c-d-d-1 — empty fan list returns zero record."""
    out = _check_cavity_fan_tet_shape_quality(
        [], np.zeros(3), np.zeros((0, 3))
    )
    assert out["n_tets"] == 0
    assert out["bad_indices"] == []
    assert out["n_below_threshold"] == 0
    assert out["q_values"].shape == (0,)


def test_native_bl_check_cavity_fan_tet_shape_quality_regular_tet_passes() -> None:
    """BLR-9c-d-d-1 — a near-regular fan tet has Q ≈ 1 ⇒ no bad
    indices."""
    # apex at origin, inner points at the three "regular tet"
    # neighbours of (0,0,0) at unit distance.
    apex = np.array([0.0, 0.0, 0.0])
    inner_points = np.array(
        [
            [1.0, 0.0, 0.0],
            [0.5, np.sqrt(3.0) / 2.0, 0.0],
            [0.5, np.sqrt(3.0) / 6.0, np.sqrt(2.0 / 3.0)],
        ],
        dtype=np.float64,
    )
    fan_tets = [{"face_id": 0, "tet_verts": [-1, 0, 1, 2]}]
    out = _check_cavity_fan_tet_shape_quality(fan_tets, apex, inner_points)
    assert out["n_tets"] == 1
    assert out["q_min"] > 0.5         # near-regular ⇒ Q close to 1
    assert out["bad_indices"] == []
    assert out["n_below_threshold"] == 0


def test_native_bl_check_cavity_fan_tet_shape_quality_sliver_flagged() -> None:
    """BLR-9c-d-d-1 — a needle/sliver fan tet (Q ≈ 0) is reported
    as bad."""
    apex = np.array([0.0, 0.0, 0.0])
    # All three inner points nearly collinear with apex at origin,
    # off-axis only by 1e-3 ⇒ near-zero volume / huge edge ratio.
    inner_points = np.array(
        [
            [1.0, 0.0, 0.0],
            [2.0, 1e-3, 0.0],
            [3.0, 0.0, 1e-3],
        ],
        dtype=np.float64,
    )
    fan_tets = [{"face_id": 0, "tet_verts": [-1, 0, 1, 2]}]
    out = _check_cavity_fan_tet_shape_quality(
        fan_tets, apex, inner_points, q_min_threshold=0.1
    )
    assert out["n_tets"] == 1
    assert out["q_min"] < 0.1
    assert out["bad_indices"] == [0]
    assert out["n_below_threshold"] == 1


def test_native_bl_check_cavity_fan_tet_shape_quality_invalid_tet_flagged() -> None:
    """BLR-9c-d-d-1 — a fan tet with malformed tet_verts (apex
    placeholder missing or out-of-range index) is marked bad."""
    apex = np.array([0.0, 0.0, 0.0])
    inner_points = np.array([[1.0, 0.0, 0.0]], dtype=np.float64)
    fan_tets = [
        {"face_id": 0, "tet_verts": [0, 0, 0, 0]},          # no -1 placeholder
        {"face_id": 1, "tet_verts": [-1, 0, 99, 0]},        # OOB index 99
    ]
    out = _check_cavity_fan_tet_shape_quality(fan_tets, apex, inner_points)
    assert out["n_tets"] == 2
    assert set(out["bad_indices"]) == {0, 1}


def test_native_bl_check_cavity_fan_tet_determinants_degenerate_flagged() -> None:
    """BLR-9c-d-b — a degenerate (zero-volume) tet, e.g. when the apex
    lies on the inner triangle plane, is reported regardless of sign."""
    apex = np.array([0.0, 0.0, 0.0])
    inner_points = np.array(
        [
            [1.0, 0.0, 0.0],
            [2.0, 0.0, 0.0],
            [3.0, 0.0, 0.0],   # all on z=0, degenerate with apex
        ],
        dtype=np.float64,
    )
    fan_tets = [{"face_id": 0, "tet_verts": [-1, 0, 1, 2]}]
    out = _check_cavity_fan_tet_determinants(fan_tets, apex, inner_points)
    assert out["n_tets"] == 1
    assert out["n_degenerate_det"] == 1
    assert out["bad_indices"] == [0]
    assert out["worst_abs_det"] < 1e-9
