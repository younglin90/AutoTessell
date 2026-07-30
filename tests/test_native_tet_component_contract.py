from __future__ import annotations

import hashlib
import warnings
from dataclasses import asdict
from types import SimpleNamespace

import numpy as np
import pytest

from core.generator.native_tet import rescue_gate
from core.generator.native_tet.rescue_gate import (
    audit_source_component_bijection,
    audit_source_topology,
    restore_source_prefix_roundoff,
)


def _disconnected_tetrahedra(
    count: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    base_points = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )
    base_faces = np.array(
        [[0, 1, 2], [0, 3, 1], [1, 3, 2], [2, 3, 0]],
        dtype=np.int64,
    )
    points = np.vstack(
        [base_points + np.array([3.0 * component, 0.0, 0.0]) for component in range(count)]
    )
    faces = np.vstack([base_faces + 4 * component for component in range(count)])
    tets = np.asarray(
        [[4 * component + local for local in range(4)] for component in range(count)],
        dtype=np.int64,
    )
    return points, faces, tets


@pytest.mark.parametrize("component_count", [1, 2, 5])
def test_exact_disconnected_source_components_are_bijective(
    component_count: int,
) -> None:
    points, faces, tets = _disconnected_tetrahedra(component_count)

    audit = audit_source_component_bijection(points, faces, points.copy(), tets)

    assert audit.bijective
    assert audit.n_source_components == component_count
    assert audit.n_candidate_boundary_components == component_count
    assert audit.n_source_surface_vertices == len(points)
    assert audit.n_source_vertices_on_boundary == len(points)
    assert audit.n_missing_source_vertices == 0
    assert audit.n_matched_source_components == component_count
    assert audit.n_mixed_candidate_components == 0
    assert audit.n_split_source_components == 0
    assert audit.n_unanchored_candidate_components == 0
    assert audit.n_unknown_source_vertex_anchors == 0


@pytest.mark.parametrize("component_count", [1, 2, 5])
def test_source_aware_strict_topology_accepts_disconnected_valid_bodies(
    component_count: int,
) -> None:
    points, faces, tets = _disconnected_tetrahedra(component_count)
    input_bytes = points.tobytes() + faces.tobytes() + tets.tobytes()
    input_hash = hashlib.sha256(input_bytes).hexdigest()

    repeated = [audit_source_topology(points, faces, points, tets) for _ in range(3)]

    assert repeated[0] == repeated[1] == repeated[2]
    assert repeated[0].valid
    assert repeated[0].boundary.valid
    assert repeated[0].boundary.n_boundary_components == component_count
    assert repeated[0].components.bijective
    output_bytes = points.tobytes() + faces.tobytes() + tets.tobytes()
    assert output_bytes == input_bytes
    assert hashlib.sha256(output_bytes).hexdigest() == input_hash


def test_source_aware_strict_topology_rejects_local_or_component_defects() -> None:
    points, faces, tets = _disconnected_tetrahedra(2)
    duplicate = np.vstack([tets, tets[:1]])
    lost = tets[:1]
    inverted = tets.copy()
    inverted[0, [2, 3]] = inverted[0, [3, 2]]

    duplicate_audit = audit_source_topology(points, faces, points, duplicate)
    lost_audit = audit_source_topology(points, faces, points, lost)
    inverted_audit = audit_source_topology(points, faces, points, inverted)

    assert not duplicate_audit.valid
    assert not duplicate_audit.boundary.valid
    assert duplicate_audit.boundary.n_duplicate_tets == 1
    assert not lost_audit.valid
    assert lost_audit.boundary.valid
    assert not lost_audit.components.bijective
    assert lost_audit.components.n_missing_source_vertices == 4
    assert not inverted_audit.valid
    assert not inverted_audit.boundary.valid
    assert inverted_audit.boundary.n_inverted_tets == 1
    assert inverted_audit.components.bijective


def test_source_aware_strict_topology_rejects_open_nonmanifold_boundary() -> None:
    points = np.asarray(
        [[index & 1, (index >> 1) & 1, (index >> 2) & 1] for index in range(8)],
        dtype=np.float64,
    )
    source_faces = np.asarray(
        [[0, 1, 2], [0, 4, 1], [1, 4, 2], [2, 4, 0]],
        dtype=np.int64,
    )
    malformed = np.asarray(
        [[0, 1, 2, 4], [0, 1, 2, 5], [0, 1, 2, 6], [0, 1, 4, 6]],
        dtype=np.int64,
    )

    audit = audit_source_topology(points, source_faces, points, malformed)

    assert not audit.valid
    assert not audit.boundary.valid
    assert audit.boundary.n_open_edges == 1
    assert audit.boundary.n_nonmanifold_edges == 2
    assert audit.boundary.n_nonmanifold_faces == 1


def test_source_prefix_roundoff_is_restored_without_topology_or_input_change() -> None:
    points, faces, tets = _disconnected_tetrahedra(2)
    candidate = points.copy()
    candidate[0, 0] = np.nextafter(candidate[0, 0], 1.0)
    candidate[5, 1] = np.nextafter(candidate[5, 1], 1.0)
    source_bytes = points.tobytes() + faces.tobytes() + tets.tobytes()
    candidate_tets = tets.copy()

    result = restore_source_prefix_roundoff(
        points,
        faces,
        candidate,
        candidate_tets,
        prefix_contract=True,
    )

    assert result.applied
    assert result.reason == "source_prefix_roundoff_restored"
    assert result.restored_count == 2
    assert 0.0 < result.max_delta <= result.cap
    np.testing.assert_array_equal(result.points, points)
    np.testing.assert_array_equal(candidate_tets, tets)
    assert points.tobytes() + faces.tobytes() + tets.tobytes() == source_bytes
    assert audit_source_topology(points, faces, result.points, tets).valid


def test_source_prefix_restore_detects_signed_zero_bit_change() -> None:
    points, faces, tets = _disconnected_tetrahedra(1)
    candidate = points.copy()
    candidate[0, 0] = -0.0

    result = restore_source_prefix_roundoff(
        points, faces, candidate, tets, prefix_contract=True
    )

    assert result.applied
    assert result.restored_count == 1
    assert result.max_delta == 0.0
    assert result.points.tobytes() == points.tobytes()


def test_source_prefix_restore_keeps_huge_finite_scale_cap_finite() -> None:
    points, faces, tets = _disconnected_tetrahedra(1)
    huge = float(np.finfo(np.float64).max)
    points[0, 0] = -huge
    points[1, 0] = huge
    candidate = points.copy()

    result = restore_source_prefix_roundoff(
        points, faces, candidate, tets, prefix_contract=True
    )

    assert np.isfinite(result.cap)
    assert result.reason == "source_prefix_already_exact"
    with pytest.raises(ValueError, match="roundoff cap must be finite"):
        restore_source_prefix_roundoff(
            points,
            faces,
            candidate,
            tets,
            prefix_contract=True,
            epsilon_multiplier=huge,
        )


def test_source_prefix_restore_tiny_scale_emits_no_numeric_warning() -> None:
    points, faces, tets = _disconnected_tetrahedra(1)
    points *= float(np.finfo(np.float64).tiny)

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        result = restore_source_prefix_roundoff(
            points, faces, points.copy(), tets, prefix_contract=True
        )

    assert np.isfinite(result.cap)
    assert result.reason == "source_prefix_already_exact"


def test_source_prefix_restore_refuses_meaningful_motion_or_unknown_order() -> None:
    points, faces, tets = _disconnected_tetrahedra(1)
    moved = points.copy()
    moved[0, 0] += 1e-8

    excessive = restore_source_prefix_roundoff(
        points, faces, moved, tets, prefix_contract=True
    )
    reordered = restore_source_prefix_roundoff(
        points, faces, points[[2, 0, 3, 1]], tets, prefix_contract=False
    )

    assert not excessive.applied
    assert excessive.reason == "source_prefix_delta_exceeds_roundoff_cap"
    np.testing.assert_array_equal(excessive.points, moved)
    assert not reordered.applied
    assert reordered.reason == "prefix_contract_disabled"


def test_source_prefix_restore_refuses_interiorized_source_vertex() -> None:
    points, faces, _ = _disconnected_tetrahedra(1)
    candidate = np.vstack([points, [[0.25, 0.25, 0.25]]])
    interiorized = np.asarray(
        [[3, 1, 2, 4], [0, 3, 2, 4], [0, 1, 3, 4], [0, 1, 2, 3]],
        dtype=np.int64,
    )

    result = restore_source_prefix_roundoff(
        points, faces, candidate, interiorized, prefix_contract=True
    )

    assert not result.applied
    assert result.reason == "source_prefix_not_on_boundary"
    np.testing.assert_array_equal(result.points, candidate)


def test_explicit_ftetwild_topology_failure_writes_zero_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from core.generator import polymesh_writer
    from core.generator.native_tet import ftetwild_main_loop
    from core.generator.native_tet.mesher import generate_native_tet

    points, faces, tets = _disconnected_tetrahedra(2)
    input_bytes = points.tobytes() + faces.tobytes()
    candidate = SimpleNamespace(
        success=True,
        pts=points.copy(),
        tets=tets[:1].copy(),
    )
    writes = 0

    def unexpected_write(*_args, **_kwargs):
        nonlocal writes
        writes += 1
        raise AssertionError("writer ran before source-aware topology acceptance")

    monkeypatch.setenv("AUTO_TESSELL_USE_FTETWILD_LOOP", "1")
    monkeypatch.setattr(
        ftetwild_main_loop,
        "ftetwild_main_loop",
        lambda *_args, **_kwargs: candidate,
    )
    monkeypatch.setattr(polymesh_writer.PolyMeshWriter, "write", unexpected_write)

    case_dir = tmp_path / "invalid_component"
    result = generate_native_tet(points, faces, case_dir)

    assert not result.success
    assert result.message == "ftetwild loop source-aware strict topology is invalid"
    assert writes == 0
    assert not (case_dir / "constant" / "polyMesh").exists()
    assert points.tobytes() + faces.tobytes() == input_bytes


def test_lost_source_component_is_rejected() -> None:
    points, faces, tets = _disconnected_tetrahedra(2)

    audit = audit_source_component_bijection(points, faces, points, tets[:1])

    assert not audit.bijective
    assert audit.n_source_components == 2
    assert audit.n_candidate_boundary_components == 1
    assert audit.n_missing_source_vertices == 4
    assert audit.n_matched_source_components == 1


def test_merged_source_components_are_rejected() -> None:
    points, faces, _ = _disconnected_tetrahedra(2)
    merged = np.array(
        [[0, 1, 2, 3], [0, 1, 4, 5], [4, 5, 6, 7]],
        dtype=np.int64,
    )

    audit = audit_source_component_bijection(points, faces, points, merged)

    assert not audit.bijective
    assert audit.n_mixed_candidate_components > 0


def test_split_source_component_is_rejected() -> None:
    points, faces, _ = _disconnected_tetrahedra(1)
    candidate_points = np.vstack(
        [points, [[5.0, 0.0, 0.0], [5.0, 1.0, 0.0], [5.0, 0.0, 1.0], [6.0, 0.0, 0.0]]]
    )
    split = np.array([[0, 4, 5, 6], [1, 2, 3, 7]], dtype=np.int64)

    audit = audit_source_component_bijection(points, faces, candidate_points, split)

    assert not audit.bijective
    assert audit.n_split_source_components == 1


def test_unanchored_candidate_boundary_component_is_rejected() -> None:
    points, faces, tets = _disconnected_tetrahedra(1)
    extra = np.vstack([points, points + np.array([3.0, 0.0, 0.0])])
    candidate = np.vstack([tets, np.array([[4, 5, 6, 7]], dtype=np.int64)])

    audit = audit_source_component_bijection(points, faces, extra, candidate)

    assert not audit.bijective
    assert audit.n_unanchored_candidate_components == 1


def test_source_vertex_made_interior_is_rejected() -> None:
    points, faces, _ = _disconnected_tetrahedra(1)
    candidate_points = np.vstack([points, [[0.25, 0.25, 0.25]]])
    subdivided = np.array(
        [[3, 1, 2, 4], [0, 3, 2, 4], [0, 1, 3, 4], [0, 1, 2, 3]],
        dtype=np.int64,
    )

    audit = audit_source_component_bijection(points, faces, candidate_points, subdivided)

    assert not audit.bijective
    assert audit.n_missing_source_vertices == 1
    assert audit.n_source_vertices_on_boundary == 3


def test_point_face_and_tet_order_do_not_change_component_verdict() -> None:
    points, faces, tets = _disconnected_tetrahedra(5)
    expected = audit_source_component_bijection(points, faces, points, tets)
    rng = np.random.default_rng(20260731)

    for _ in range(3):
        point_order = rng.permutation(len(points))
        old_to_new = np.argsort(point_order)
        candidate_points = points[point_order].copy()
        shuffled_faces = faces[rng.permutation(len(faces))].copy()
        shuffled_tets = old_to_new[tets[rng.permutation(len(tets))]].copy()
        for row in shuffled_faces:
            rng.shuffle(row)
        for row in shuffled_tets:
            rng.shuffle(row)
        actual = audit_source_component_bijection(
            points, shuffled_faces, candidate_points, shuffled_tets
        )
        assert actual == expected


def test_native_and_python_component_audits_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core.utils import native_extensions

    native = native_extensions.load_native_tet_predicates()
    if native is None or not hasattr(native, "audit_source_component_bijection"):
        pytest.skip("native source-component audit is unavailable")
    for component_count in (1, 2, 5):
        points, faces, tets = _disconnected_tetrahedra(component_count)
        native_result = audit_source_component_bijection(points, faces, points, tets)
        monkeypatch.setattr(native_extensions, "load_native_tet_predicates", lambda: None)
        python_result = audit_source_component_bijection(points, faces, points, tets)
        assert native_result == python_result
        monkeypatch.undo()


@pytest.mark.parametrize(
    "mutation",
    [
        lambda values: {**values, "n_source_components": 1.5},
        lambda values: {**values, "bijective": 1},
        lambda values: {**values, "n_missing_source_vertices": 1},
        lambda values: {**values, "n_source_components": 10_000},
        lambda values: {key: value for key, value in values.items() if key != "bijective"},
    ],
)
def test_malformed_present_native_backend_fails_closed_without_fallback(
    monkeypatch: pytest.MonkeyPatch,
    mutation,
) -> None:
    from core.utils import native_extensions

    points, faces, tets = _disconnected_tetrahedra(1)
    valid = asdict(
        rescue_gate._audit_source_component_bijection_python(points, faces, points, tets)
    )
    calls = 0

    def backend(*_args):
        nonlocal calls
        calls += 1
        return mutation(valid)

    monkeypatch.setattr(
        native_extensions,
        "load_native_tet_predicates",
        lambda: SimpleNamespace(audit_source_component_bijection=backend),
    )
    monkeypatch.setattr(
        rescue_gate,
        "_audit_source_component_bijection_python",
        lambda *_args, **_kwargs: pytest.fail("malformed native result fell back"),
    )

    with pytest.raises(RuntimeError, match="native source-component audit"):
        audit_source_component_bijection(points, faces, points, tets)
    assert calls == 1


def test_python_contract_rejects_lossy_or_ambiguous_inputs() -> None:
    points, faces, tets = _disconnected_tetrahedra(1)
    with pytest.raises(TypeError, match="dtype float64"):
        audit_source_component_bijection(points.astype(np.float32), faces, points, tets)
    with pytest.raises(TypeError, match="dtype int64"):
        audit_source_component_bijection(points, faces.astype(np.int32), points, tets)
    nonfinite = points.copy()
    nonfinite[0, 0] = np.nan
    with pytest.raises(ValueError, match="finite"):
        audit_source_component_bijection(points, faces, nonfinite, tets)
    duplicate_source = points.copy()
    duplicate_source[1] = duplicate_source[0]
    with pytest.raises(ValueError, match="ambiguous duplicate"):
        audit_source_component_bijection(duplicate_source, faces, points, tets)
    duplicate_candidate = np.vstack([points, points[:1]])
    with pytest.raises(ValueError, match="duplicates a source coordinate"):
        audit_source_component_bijection(points, faces, duplicate_candidate, tets)
    repeated_face = faces.copy()
    repeated_face[0, 1] = repeated_face[0, 0]
    with pytest.raises(ValueError, match="repeated vertex"):
        audit_source_component_bijection(points, repeated_face, points, tets)
