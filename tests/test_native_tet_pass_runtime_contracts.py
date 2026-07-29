"""Runtime contracts for optional native-tet post-processing passes."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from core.analyzer.file_reader import load_mesh
from core.generator.native_tet.mesher import (
    _best_of_candidate_meets_target_floor,
    _native_tet_large_pass_enabled,
    _optional_pass_result,
    generate_native_tet,
)
from core.generator.native_tet.quality import tet_shape_quality
from core.generator.native_tet.stellar import _priority_queue_main_loop
from core.utils.polymesh_reader import (
    parse_foam_faces,
    parse_foam_labels,
    parse_foam_points,
)

_OBSERVED_RUNTIME_ERRORS = (
    "cannot unpack non-iterable NoneType object",
    "name 'N' is not defined",
    "'cof_F'",
    "'QualitySnapshot' object has no attribute 'q_per_tet'",
    "cannot access local variable '_n_sliver_pre' where it is not associated with a value",
)
_CYLINDER = Path(__file__).resolve().parent / "benchmarks" / "cylinder.stl"


def _unit_cube() -> tuple[np.ndarray, np.ndarray]:
    vertices = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [1.0, 1.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [1.0, 0.0, 1.0],
            [1.0, 1.0, 1.0],
            [0.0, 1.0, 1.0],
        ],
        dtype=np.float64,
    )
    faces = np.array(
        [
            [0, 2, 1],
            [0, 3, 2],
            [4, 5, 6],
            [4, 6, 7],
            [0, 1, 5],
            [0, 5, 4],
            [2, 3, 7],
            [2, 7, 6],
            [1, 2, 6],
            [1, 6, 5],
            [0, 4, 7],
            [0, 7, 3],
        ],
        dtype=np.int64,
    )
    return vertices, faces


def test_large_pass_guard_includes_500_tets() -> None:
    assert not _native_tet_large_pass_enabled(499)
    assert _native_tet_large_pass_enabled(500)


def test_optional_pass_result_treats_none_as_guarded_noop() -> None:
    assert _optional_pass_result(None, 3) == (None, "helper_returned_none")
    assert _optional_pass_result((1, 2), 3) == (
        None,
        "helper_return_contract_mismatch",
    )
    assert _optional_pass_result((1, 2, 3), 3) == ((1, 2, 3), None)


def test_best_of_candidate_target_floor_is_inclusive() -> None:
    assert _best_of_candidate_meets_target_floor(212, 2000) is False
    assert _best_of_candidate_meets_target_floor(599, 2000) is False
    assert _best_of_candidate_meets_target_floor(600, 2000) is True
    assert _best_of_candidate_meets_target_floor(1869, 2000) is True
    assert _best_of_candidate_meets_target_floor(1, None) is True


def test_disabled_priority_queue_contract_returns_seven_items() -> None:
    points = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    qualities = tet_shape_quality(points, tets)

    result = _priority_queue_main_loop(points, tets, qualities)

    assert len(result) == 7
    assert np.array_equal(result[0], points)
    assert np.array_equal(result[1], tets)


def test_small_mesh_run_has_no_observed_pass_runtime_errors(
    tmp_path,
    capsys,
    monkeypatch,
) -> None:
    for name in (
        "AUTO_TESSELL_OFFPLANE_STEINER",
        "AUTO_TESSELL_VVV9H_APPLY",
        "AUTO_TESSELL_VVV9J_APPLY",
        "AUTO_TESSELL_VVV9K_APPLY",
        "AUTO_TESSELL_VVV9P_APPLY",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AUTO_TESSELL_P4C_PYTETWILD", "0")
    vertices, faces = _unit_cube()

    result = generate_native_tet(
        vertices,
        faces,
        tmp_path / "cube",
        seed_density=3,
        sliver_quality_threshold=0.0,
        enable_phase_a=False,
        enable_phase_b=False,
        enable_phase_c=False,
    )
    captured = capsys.readouterr()
    log_text = captured.out + captured.err

    assert result.success, result.message
    assert 0 < result.n_cells < 500
    assert "vvv12_skipped_small_mesh" in log_text
    for reason in _OBSERVED_RUNTIME_ERRORS:
        assert reason not in log_text


def test_cylinder_rejects_under_budget_alt_and_persists_final_mesh(
    tmp_path,
    capsys,
    monkeypatch,
) -> None:
    for name in (
        "AUTO_TESSELL_OFFPLANE_STEINER",
        "AUTO_TESSELL_VVV9H_APPLY",
        "AUTO_TESSELL_VVV9J_APPLY",
        "AUTO_TESSELL_VVV9K_APPLY",
        "AUTO_TESSELL_VVV9P_APPLY",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AUTO_TESSELL_P4C_PYTETWILD", "0")
    monkeypatch.setenv("AUTO_TESSELL_CONVEX_EXTRUSION_RESCUE", "0")
    mesh = load_mesh(_CYLINDER)
    case_dir = tmp_path / "cylinder"

    result = generate_native_tet(
        np.asarray(mesh.vertices, dtype=np.float64),
        np.asarray(mesh.faces, dtype=np.int64),
        case_dir,
        target_cells=2000,
    )
    captured = capsys.readouterr()
    log_text = captured.out + captured.err

    assert result.success, result.message
    assert result.tet_points is not None
    assert result.tets is not None
    assert result.n_cells >= 600
    assert "native_tet_best_of_candidate_rejected" in log_text
    assert "below_target_cell_floor" in log_text
    assert log_text.count("polymesh_writer_start") == 1
    assert "native_tet_polymesh_write_final" in log_text
    for reason in _OBSERVED_RUNTIME_ERRORS:
        assert reason not in log_text

    poly_dir = case_dir / "constant" / "polyMesh"
    disk_points = np.asarray(parse_foam_points(poly_dir / "points"), dtype=float)
    disk_faces = parse_foam_faces(poly_dir / "faces")
    owner = np.asarray(parse_foam_labels(poly_dir / "owner"), dtype=np.int64)
    neighbour = np.asarray(
        parse_foam_labels(poly_dir / "neighbour"),
        dtype=np.int64,
    )

    assert disk_points.shape == result.tet_points.shape
    # PolyMeshWriter serializes points with nine significant digits.
    assert np.allclose(disk_points, result.tet_points, rtol=0.0, atol=1e-8)

    n_disk_cells = int(max(owner.max(), neighbour.max())) + 1
    assert n_disk_cells == result.n_cells == int(result.tets.shape[0])
    assert len(disk_faces) == owner.size
    assert neighbour.size <= owner.size
    assert int(owner.min()) >= 0
    assert int(owner.max()) < result.n_cells
    assert int(neighbour.min()) >= 0
    assert int(neighbour.max()) < result.n_cells
