"""QUAD-POSY1 integer-offset ledger tests.

The module is report-only.  These tests pin the explicit branch contract on
synthetic faces and compare the multiresolution default with a deterministic
single-resolution A/B on the real cube, cylinder, and bracket assets.
"""

from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
import pytest

from core.preprocessor.native_remesh.posy_diagnostic import (
    build_position_offset_ledger,
    posy_diagnostic_enabled,
    run_posy_diagnostic,
    run_posy_diagnostic_if_enabled,
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


def _source_ledger(
    vertices: np.ndarray,
    faces: np.ndarray,
    extrinsic: tuple[int, ...],
    intrinsic: tuple[int, ...],
):
    ext = SingularityCensus(
        connection="extrinsic",
        euler_characteristic=0,
        closed=True,
        singularities=tuple(
            OrientationSingularity(face=0, index=index, centroid=(0.0, 0.0, 0.0))
            for index in extrinsic
        ),
    )
    intr = SingularityCensus(
        connection="intrinsic",
        euler_characteristic=0,
        closed=True,
        singularities=tuple(
            OrientationSingularity(face=0, index=index, centroid=(0.0, 0.0, 0.0))
            for index in intrinsic
        ),
    )
    return build_singularity_ledger(vertices, faces, ext, intr)


def test_regular_synthetic_triangle_has_explicit_offsets_rotation_residual_and_det() -> None:
    vertices, faces, field = _single_triangle()
    vertices_before, faces_before, field_before = vertices.copy(), faces.copy(), field.copy()
    ledger = build_position_offset_ledger(vertices, faces, field)
    entry = ledger.entries[0]
    candidate = entry.candidates[0]

    assert entry.admissible_orientation_indices == (0,)
    assert not entry.unresolved
    assert candidate.raw_offsets == ((1, 0), (-1, 1), (0, -1))
    assert candidate.rotations == (0, 0, 0)
    assert candidate.rotated_offsets == candidate.raw_offsets
    assert candidate.regularity_residual == (0, 0)
    assert candidate.orientation_determinant == 1
    assert candidate.regular
    assert candidate.orientation_consistent
    assert not candidate.position_singularity
    assert ledger.position_singularity_count == 0
    assert np.array_equal(vertices, vertices_before)
    assert np.array_equal(faces, faces_before)
    assert np.array_equal(field, field_before)


def test_half_index_keeps_both_signs_and_never_resolves_to_positive() -> None:
    vertices, faces, field = _single_triangle()
    source = _source_ledger(vertices, faces, (2,), (2,))
    ledger = build_position_offset_ledger(vertices, faces, field, source)
    entry = ledger.entries[0]

    assert entry.unresolved
    assert "half-index-ambiguous" in entry.unresolved_reasons
    assert entry.admissible_orientation_indices == (-2, 2)
    assert {candidate.orientation_index for candidate in entry.candidates} == {-2, 2}
    assert entry.resolved_candidate is None


def test_connection_disagreement_keeps_both_explicit_options_unresolved() -> None:
    vertices, faces, field = _single_triangle()
    source = _source_ledger(vertices, faces, (1,), (-1,))
    entry = build_position_offset_ledger(vertices, faces, field, source).entries[0]

    assert entry.unresolved
    assert entry.admissible_orientation_indices == (-1, 1)
    assert "connection-disagreement" in entry.unresolved_reasons
    assert entry.resolved_candidate is None


def test_posy_flag_is_default_off_and_disabled_hook_is_a_noop(monkeypatch) -> None:
    vertices, faces, _field = _single_triangle()
    monkeypatch.delenv("AUTO_TESSELL_QUAD_POSY1", raising=False)
    assert not posy_diagnostic_enabled()
    assert run_posy_diagnostic_if_enabled(vertices, faces, "synthetic") is None
    monkeypatch.setenv("AUTO_TESSELL_QUAD_POSY1", "1")
    assert posy_diagnostic_enabled()


def test_default_off_path_is_byte_identical_to_explicit_zero(monkeypatch) -> None:
    from core.preprocessor.native_remesh import isotropic_remesh

    vertices, faces = _load_stl("01_easy_cube.stl")
    kwargs = {"target_edge_length": 0.7, "n_iter": 1}
    monkeypatch.delenv("AUTO_TESSELL_QUAD_POSY1", raising=False)
    default_vertices, default_faces = isotropic_remesh(vertices, faces, **kwargs)
    monkeypatch.setenv("AUTO_TESSELL_QUAD_POSY1", "0")
    explicit_vertices, explicit_faces = isotropic_remesh(vertices, faces, **kwargs)

    assert default_vertices.tobytes() == explicit_vertices.tobytes()
    assert default_faces.tobytes() == explicit_faces.tobytes()


@pytest.fixture(scope="module")
def real_ab_reports():
    reports = {}
    for name in REAL_ASSETS:
        vertices, faces = _load_stl(name)
        reports[(name, "multires")] = run_posy_diagnostic(
            vertices, faces, name, n_sweeps=20, seed=0, multires=True
        )
        reports[(name, "single")] = run_posy_diagnostic(
            vertices, faces, name, n_sweeps=20, seed=0, multires=False
        )
    return reports


def test_real_assets_have_complete_explicit_ledgers_and_a_b_invariants(real_ab_reports) -> None:
    for name in REAL_ASSETS:
        multi = real_ab_reports[(name, "multires")]
        single = real_ab_reports[(name, "single")]
        for report in (multi, single):
            ledger = report.ledger
            assert ledger.n_faces == report.n_faces
            assert ledger.candidate_count >= report.n_faces
            assert all(len(entry.candidates) >= 1 for entry in ledger.entries)
            assert ledger.position_singularity_count >= 0
            assert ledger.regularity_failure_count <= ledger.position_singularity_count
            assert ledger.orientation_inversion_count <= ledger.position_singularity_count
            assert all(
                candidate.rotations and all(0 <= turn <= 3 for turn in candidate.rotations)
                for entry in ledger.entries
                for candidate in entry.candidates
            )
        assert multi.n_vertices == single.n_vertices
        assert multi.n_faces == single.n_faces
        assert multi.rosy.ledger is not None and single.rosy.ledger is not None
        assert multi.rosy.ledger.poincare_hopf_consistent
        assert single.rosy.ledger.poincare_hopf_consistent


def test_bracket_real_asset_preserves_explicit_half_index_unresolved_state(real_ab_reports) -> None:
    report = real_ab_reports[("03_hard_bracket.stl", "multires")]
    ambiguous = [
        entry
        for entry in report.ledger.entries
        if -2 in entry.admissible_orientation_indices and 2 in entry.admissible_orientation_indices
    ]

    assert ambiguous
    assert all(entry.unresolved for entry in ambiguous)
    assert all(entry.resolved_candidate is None for entry in ambiguous)
    assert report.ledger.unresolved_count >= len(ambiguous)


def test_real_multires_ledger_is_deterministic_at_pickle_boundary() -> None:
    vertices, faces = _load_stl("03_hard_bracket.stl")
    first = run_posy_diagnostic(vertices, faces, "03_hard_bracket.stl", multires=True)
    second = run_posy_diagnostic(vertices, faces, "03_hard_bracket.stl", multires=True)

    assert first.ledger == second.ledger
    assert pickle.dumps(first.ledger, protocol=5) == pickle.dumps(second.ledger, protocol=5)
