"""L0 Du--Wang direct-constraint protection audit tests."""

from __future__ import annotations

from core.generator.native_tet.duwang_constraint_protection_l0 import (
    audit_direct_constraint_face_protection_l0,
)


def test_flip_candidate_that_recovers_an_edge_but_deletes_a_direct_source_face_rejects() -> None:
    before = ((0, 1, 2, 3), (0, 1, 2, 4))
    # A 2-to-3 swap creates edge (3, 4), but removes the shared direct face.
    after = ((0, 1, 3, 4), (1, 2, 3, 4), (2, 0, 3, 4))

    result = audit_direct_constraint_face_protection_l0(before, after, ((0, 1, 2),))

    assert not result.accepted
    assert result.reason == "would_delete"
    assert result.present_before == ((0, 1, 2),)
    assert result.would_delete == ((0, 1, 2),)
    assert not result.production_mesh_changed


def test_absent_input_constraint_is_never_misreported_as_preserved() -> None:
    result = audit_direct_constraint_face_protection_l0(
        ((0, 1, 2, 3),), ((0, 1, 2, 3),), ((4, 5, 6),)
    )

    assert not result.accepted
    assert result.reason == "missing_before"
    assert result.missing_before == ((4, 5, 6),)
    assert not result.production_mesh_changed


def test_unchanged_direct_constraint_passes_and_is_deterministic() -> None:
    before = ((0, 1, 2, 3), (0, 1, 2, 4))
    first = audit_direct_constraint_face_protection_l0(before, before, ((2, 1, 0),))
    second = audit_direct_constraint_face_protection_l0(before, before, ((0, 1, 2),))

    assert first.accepted and first.reason == "preserved"
    assert first == second


def test_cavity_retri_rejects_direct_source_face_deletion() -> None:
    """The Q2 2-to-3 route cannot trade a source face for a missing edge."""
    import numpy as np

    from core.generator.native_tet.cavity_retri import cavity_retri_for_missing_edges

    points = np.asarray(
        ((0, 0, 0), (4, 0, 0), (0, 4, 0), (0.2, 0.3, 3), (-0.4, 0.5, -3)),
        dtype=float,
    )
    before = np.asarray(((0, 1, 2, 3), (0, 1, 2, 4)), dtype=np.int64)

    ungated, ungated_result = cavity_retri_for_missing_edges(
        points, before, [(3, 4)], min_quality=-1.0
    )
    ungated_audit = audit_direct_constraint_face_protection_l0(
        before.tolist(), ungated.tolist(), ((0, 1, 2),)
    )
    assert ungated_result.n_recovered == 1
    assert not ungated_audit.accepted
    assert ungated_audit.reason == "would_delete"

    after, result = cavity_retri_for_missing_edges(
        points,
        before,
        [(3, 4)],
        min_quality=-1.0,
        protected_faces=((0, 1, 2),),
    )

    assert result.n_recovered == 0
    assert np.array_equal(after, before)
