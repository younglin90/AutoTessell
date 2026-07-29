"""QUAD-MESSY-GRID-TOL1 report-only discrepancy ledger tests."""

from __future__ import annotations

import pickle
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from core.preprocessor.native_remesh import isotropic_remesh
from core.preprocessor.native_remesh.messy_grid_ledger import (
    build_messy_grid_discrepancy_ledger,
)
from core.preprocessor.native_remesh.posy_diagnostic import (
    build_position_offset_ledger,
    run_posy_diagnostic,
)
from core.preprocessor.native_remesh.rosy_diagnostic import (
    OrientationSingularity,
    SingularityCensus,
    build_singularity_ledger,
)

STL_DIR = Path(__file__).parent / "stl"
REAL_ASSETS = (
    "01_easy_cube.stl",
    "02_medium_cylinder.stl",
    "03_hard_bracket.stl",
)


def _load_stl(name: str) -> tuple[np.ndarray, np.ndarray]:
    trimesh = pytest.importorskip("trimesh")
    mesh = trimesh.load(str(STL_DIR / name), process=True)
    mesh.merge_vertices()
    return (
        np.asarray(mesh.vertices, dtype=np.float64),
        np.asarray(mesh.faces, dtype=np.int64),
    )


def _single_triangle() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    vertices = np.asarray(
        ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
        dtype=np.float64,
    )
    faces = np.asarray(((0, 1, 2),), dtype=np.int64)
    field = np.asarray(((1.0, 0.0, 0.0),) * 3, dtype=np.float64)
    return vertices, faces, field


def _half_index_source(vertices: np.ndarray, faces: np.ndarray):
    census = SingularityCensus(
        connection="extrinsic",
        euler_characteristic=0,
        closed=True,
        singularities=(OrientationSingularity(face=0, index=2, centroid=(0.0, 0.0, 0.0)),),
    )
    return build_singularity_ledger(vertices, faces, census, census)


def test_half_index_branch_offsets_are_recorded_without_loss() -> None:
    vertices, faces, field = _single_triangle()
    source = _half_index_source(vertices, faces)
    posy = build_position_offset_ledger(vertices, faces, field, source)
    ledger = build_messy_grid_discrepancy_ledger(
        posy, shape_name="synthetic", n_vertices=3, n_sweeps=20
    )

    entry = ledger.entries[0]
    assert entry.expected_branch_indices == (-2, 2)
    assert entry.observed_branch_indices == (-2, 2)
    assert entry.lost_branch_indices == ()
    assert entry.branch_offset_differences == (4,)
    assert entry.branch_offset_span == 4
    assert entry.expected_half_index_branches == (-2, 2)
    assert entry.observed_half_index_branches == (-2, 2)
    assert entry.lost_half_index_branches == ()
    assert ledger.half_index_expected_branch_count == 2
    assert ledger.half_index_observed_branch_count == 2
    assert ledger.half_index_branch_loss_count == 0


def test_branch_loss_is_an_exact_set_difference_and_not_a_tolerance() -> None:
    vertices, faces, field = _single_triangle()
    source = _half_index_source(vertices, faces)
    posy = build_position_offset_ledger(vertices, faces, field, source)
    original = posy.entries[0]
    posy_with_one_missing_branch = replace(
        posy,
        entries=(replace(original, candidates=original.candidates[:1]),),
    )

    ledger = build_messy_grid_discrepancy_ledger(posy_with_one_missing_branch)
    entry = ledger.entries[0]
    assert entry.expected_branch_indices == (-2, 2)
    assert entry.observed_branch_indices == (-2,)
    assert entry.lost_branch_indices == (2,)
    assert entry.lost_half_index_branches == (2,)
    assert ledger.branch_loss_count == 1
    assert ledger.half_index_branch_loss_count == 1


@pytest.fixture(scope="module")
def real_ledgers():
    ledgers = {}
    for name in REAL_ASSETS:
        vertices, faces = _load_stl(name)
        posy = run_posy_diagnostic(vertices, faces, name, n_sweeps=20, seed=0, multires=True)
        ledgers[name] = build_messy_grid_discrepancy_ledger(
            posy.ledger,
            shape_name=name,
            n_vertices=posy.n_vertices,
            n_sweeps=posy.n_sweeps,
            seed=posy.seed,
            multires=posy.multires,
        )
    return ledgers


def test_real_assets_record_posy_discrepancies_without_an_acceptance_cutoff(
    real_ledgers,
) -> None:
    measured = {
        name: (
            ledger.n_faces,
            ledger.position_singularity_face_count,
            ledger.position_singularity_candidate_count,
            ledger.local_integer_discrepancy_l1_total,
            ledger.local_integer_discrepancy_l1_max,
            ledger.branch_entry_count,
            ledger.branch_offset_span_total,
            ledger.branch_offset_span_max,
            ledger.half_index_entry_count,
            ledger.half_index_expected_branch_count,
            ledger.half_index_observed_branch_count,
            ledger.half_index_branch_loss_count,
        )
        for name, ledger in real_ledgers.items()
    }
    assert measured == {
        "01_easy_cube.stl": (12, 12, 16, 39, 4, 4, 4, 1, 0, 0, 0, 0),
        "02_medium_cylinder.stl": (512, 427, 443, 867, 4, 16, 16, 1, 0, 0, 0, 0),
        "03_hard_bracket.stl": (416, 331, 385, 889, 4, 54, 108, 4, 18, 36, 36, 0),
    }


def test_repeated_real_ledger_is_deterministic_at_pickle_boundary() -> None:
    vertices, faces = _load_stl("03_hard_bracket.stl")
    first_posy = run_posy_diagnostic(
        vertices, faces, "03_hard_bracket.stl", n_sweeps=20, seed=0, multires=True
    )
    second_posy = run_posy_diagnostic(
        vertices, faces, "03_hard_bracket.stl", n_sweeps=20, seed=0, multires=True
    )
    first = build_messy_grid_discrepancy_ledger(
        first_posy.ledger,
        shape_name=first_posy.shape_name,
        n_vertices=first_posy.n_vertices,
        n_sweeps=first_posy.n_sweeps,
        seed=first_posy.seed,
        multires=first_posy.multires,
    )
    second = build_messy_grid_discrepancy_ledger(
        second_posy.ledger,
        shape_name=second_posy.shape_name,
        n_vertices=second_posy.n_vertices,
        n_sweeps=second_posy.n_sweeps,
        seed=second_posy.seed,
        multires=second_posy.multires,
    )

    assert first == second
    assert pickle.dumps(first, protocol=5) == pickle.dumps(second, protocol=5)


def test_posy_off_keeps_existing_remesh_bytes_identical(monkeypatch) -> None:
    vertices, faces = _load_stl("01_easy_cube.stl")
    kwargs = {"target_edge_length": 0.7, "n_iter": 1}
    monkeypatch.delenv("AUTO_TESSELL_QUAD_POSY1", raising=False)
    default_vertices, default_faces = isotropic_remesh(vertices, faces, **kwargs)
    monkeypatch.setenv("AUTO_TESSELL_QUAD_POSY1", "0")
    explicit_off_vertices, explicit_off_faces = isotropic_remesh(vertices, faces, **kwargs)

    assert default_vertices.tobytes() == explicit_off_vertices.tobytes()
    assert default_faces.tobytes() == explicit_off_faces.tobytes()
