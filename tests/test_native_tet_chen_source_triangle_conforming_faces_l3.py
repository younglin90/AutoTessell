"""L3 internal two-owner recovered source-face tests."""

from __future__ import annotations

from fractions import Fraction

from core.generator.native_tet.chen_source_triangle_conforming_faces_l3 import (
    certify_conforming_source_triangle_faces_l3,
)


_POINTS = ((0, 0, 0), (4, 0, 0), (0, 4, 0), (2, 2, 3), (-1, -1, -2), (Fraction(1, 5), Fraction(1, 5), 0))
_RECOVERED = (
    (0, 3, 1, 5), (0, 5, 1, 4),
    (1, 3, 2, 5), (1, 5, 2, 4),
    (3, 0, 2, 5), (5, 0, 2, 4),
)


def test_table5_pipe_recovery_is_a_conforming_two_owner_source_face_subdivision() -> None:
    result = certify_conforming_source_triangle_faces_l3(_POINTS, _RECOVERED, (0, 1, 2))

    assert result.accepted, result.reason
    assert {tuple(sorted(face)) for face in result.recovered_faces} == {
        (0, 1, 5), (1, 2, 5), (0, 2, 5)
    }
    assert result.subdivision is not None and result.subdivision.accepted
    assert result.source_points_unchanged
    assert not result.production_mesh_changed


def test_one_missing_source_subface_rejects_the_recovered_face_claim() -> None:
    result = certify_conforming_source_triangle_faces_l3(_POINTS, _RECOVERED[:-2], (0, 1, 2))

    assert not result.accepted
    assert result.reason.startswith("source_face_subdivision_failed:")


def test_conforming_source_face_audit_is_value_identical_on_repeat() -> None:
    first = certify_conforming_source_triangle_faces_l3(_POINTS, _RECOVERED, (0, 1, 2))
    second = certify_conforming_source_triangle_faces_l3(_POINTS, _RECOVERED, (0, 1, 2))

    assert first == second
