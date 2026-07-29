"""L1 exact owner-consistent source-face subdivision tests."""

from __future__ import annotations

from fractions import Fraction

from core.generator.native_tet.duwang_constraint_subdivision_l1 import (
    audit_constraint_face_subdivision_l1,
)
from core.generator.native_tet.edge_flip_recovery import recover_edges_via_flip


_POINTS = (
    (0, 0, 0), (4, 0, 0), (0, 4, 0), (0, 0, 3), (0, 0, -3),
    (Fraction(1), Fraction(1), 0),
)
_BEFORE = ((0, 1, 2, 3), (0, 2, 1, 4))


def test_exact_three_subface_split_preserves_an_internal_source_constraint() -> None:
    after = (
        (0, 1, 5, 3), (1, 2, 5, 3), (2, 0, 5, 3),
        (0, 5, 1, 4), (1, 5, 2, 4), (2, 5, 0, 4),
    )

    result = audit_constraint_face_subdivision_l1(_POINTS, _BEFORE, after, ((0, 1, 2),))

    assert result.accepted, result.reason
    assert result.faces[0].owner_count_before == 2
    assert result.faces[0].candidate_subfaces == ((0, 1, 5), (0, 2, 5), (1, 2, 5))
    assert result.faces[0].subdivision is not None and result.faces[0].subdivision.accepted
    assert result.source_points_unchanged
    assert not result.production_mesh_changed


def test_one_sided_subdivision_rejects_for_an_internal_source_constraint() -> None:
    after = ((0, 1, 5, 3), (1, 2, 5, 3), (2, 0, 5, 3))

    result = audit_constraint_face_subdivision_l1(_POINTS, _BEFORE, after, ((0, 1, 2),))

    assert not result.accepted
    assert result.faces[0].reason == "no_owner_consistent_after_subfaces"


def test_l1_is_value_identical_on_repeat() -> None:
    after = (
        (0, 1, 5, 3), (1, 2, 5, 3), (2, 0, 5, 3),
        (0, 5, 1, 4), (1, 5, 2, 4), (2, 5, 0, 4),
    )
    first = audit_constraint_face_subdivision_l1(_POINTS, _BEFORE, after, ((0, 1, 2),))
    second = audit_constraint_face_subdivision_l1(_POINTS, _BEFORE, after, ((2, 0, 1),))

    assert first == second


def test_two_face_source_patch_is_protected_as_one_candidate_transaction() -> None:
    """A candidate cannot preserve one source face while dropping its neighbour."""
    points = (
        (0, 0, 0), (4, 0, 0), (4, 4, 0), (0, 4, 0),
        (0, 0, 3), (0, 0, -3),
        (Fraction(3), Fraction(1), 0), (Fraction(1), Fraction(3), 0),
    )
    before = (
        (0, 1, 2, 4), (0, 2, 3, 4),
        (0, 2, 1, 5), (0, 3, 2, 5),
    )
    after = (
        (0, 1, 6, 4), (1, 2, 6, 4), (2, 0, 6, 4),
        (0, 6, 1, 5), (1, 6, 2, 5), (2, 6, 0, 5),
        (0, 2, 7, 4), (2, 3, 7, 4), (3, 0, 7, 4),
        (0, 7, 2, 5), (2, 7, 3, 5), (3, 7, 0, 5),
    )

    result = audit_constraint_face_subdivision_l1(
        points, before, after, ((0, 1, 2), (0, 2, 3))
    )

    assert result.accepted, result.reason
    assert tuple(face.source_face for face in result.faces) == ((0, 1, 2), (0, 2, 3))
    assert all(face.owner_count_before == 2 and face.accepted for face in result.faces)


def test_current_edge_flip_candidate_exposes_a_source_face_deletion_before_gate_wiring() -> None:
    """L3 measurement: a real edge-recovery proposal can violate L1."""
    import numpy as np

    points = np.asarray(((0, 0, 0), (4, 0, 0), (0, 4, 0), (0, 0, 3), (0, 0, -3)), dtype=float)
    before = np.asarray(((0, 1, 2, 3), (0, 1, 2, 4)), dtype=np.int64)

    after, flip = recover_edges_via_flip(points, before, [(3, 4)])
    audit = audit_constraint_face_subdivision_l1(
        points.tolist(), before.tolist(), after.tolist(), ((0, 1, 2),)
    )

    assert flip.n_edges_recovered == 1
    assert not audit.accepted
    assert audit.faces[0].reason == "no_owner_consistent_after_subfaces"


def test_edge_flip_gate_rejects_the_same_surface_deleting_candidate() -> None:
    import numpy as np

    points = np.asarray(((0, 0, 0), (4, 0, 0), (0, 4, 0), (0, 0, 3), (0, 0, -3)), dtype=float)
    before = np.asarray(((0, 1, 2, 3), (0, 1, 2, 4)), dtype=np.int64)

    after, flip = recover_edges_via_flip(
        points, before, [(3, 4)], protected_faces=((0, 1, 2),)
    )

    assert flip.n_edges_recovered == 0
    assert np.array_equal(after, before)


def test_bowyer_watson_gate_rejects_off_surface_point_that_deletes_source_face() -> None:
    import numpy as np

    from core.generator.native_tet.bowyer_watson import bowyer_watson_insert

    points = np.asarray(((0, 0, 0), (4, 0, 0), (0, 4, 0), (0, 0, 3), (0, 0, -3)), dtype=float)
    before = np.asarray(((0, 1, 2, 3), (0, 1, 2, 4)), dtype=np.int64)
    after_points, after_tets, insertion = bowyer_watson_insert(
        points,
        before,
        np.asarray(((1, 1, 0.1),), dtype=float),
        protected_edges={(0, 1), (1, 2), (0, 2)},
        protected_faces=((0, 1, 2),),
    )

    assert insertion.n_inserted == 0
    assert np.array_equal(after_points, points)
    assert np.array_equal(after_tets, before)


def test_bowyer_watson_gate_allows_exact_on_surface_subdivision() -> None:
    import numpy as np

    from core.generator.native_tet.bowyer_watson import bowyer_watson_insert

    points = np.asarray(((0, 0, 0), (4, 0, 0), (0, 4, 0), (0, 0, 3), (0, 0, -3)), dtype=float)
    before = np.asarray(((0, 1, 2, 3), (0, 1, 2, 4)), dtype=np.int64)
    after_points, after_tets, insertion = bowyer_watson_insert(
        points,
        before,
        np.asarray(((1, 1, 0),), dtype=float),
        protected_edges={(0, 1), (1, 2), (0, 2)},
        protected_faces=((0, 1, 2),),
    )
    audit = audit_constraint_face_subdivision_l1(
        after_points.tolist(), before.tolist(), after_tets.tolist(), ((0, 1, 2),)
    )

    assert insertion.n_inserted == 1
    assert audit.accepted, audit.reason
