"""Exact common-frame S/Z tests on the mixed Case-2 shared face."""

from __future__ import annotations

from fractions import Fraction

from core.generator.native_tet.chen_sz_oriented_face_l0 import (
    certify_oriented_shared_face_sz_pair_l0,
)


_POINTS = (
    (0, 0, 0), (4, 0, 0), (0, 4, 0), (2, 2, 3), (-1, -1, -2),
    (1, 1, -1), (4, 2, 2), (2, Fraction(4, 3), 0),
    (Fraction(5, 4), Fraction(5, 4), 0),
)
_LEFT = (5, 6, 3, 1)
_RIGHT = (5, 6, 3, 2)
_FACE = (5, 6, 3)


def test_same_local_label_is_opposite_semantic_type_across_reversed_face_sides() -> None:
    result = certify_oriented_shared_face_sz_pair_l0(_POINTS, _LEFT, _RIGHT, _FACE, "S", "S")

    assert result.accepted, result.reason
    assert result.left_side_sign == -result.right_side_sign
    assert result.left_semantic_label != result.right_semantic_label
    assert result.compatible


def test_mixed_local_labels_become_same_semantic_type_and_are_incompatible() -> None:
    result = certify_oriented_shared_face_sz_pair_l0(_POINTS, _LEFT, _RIGHT, _FACE, "S", "Z")

    assert result.accepted, result.reason
    assert result.left_semantic_label == result.right_semantic_label
    assert not result.compatible


def test_common_frame_relation_is_symmetric_under_parent_exchange() -> None:
    forward = certify_oriented_shared_face_sz_pair_l0(_POINTS, _LEFT, _RIGHT, _FACE, "Z", "Z")
    reverse = certify_oriented_shared_face_sz_pair_l0(_POINTS, _RIGHT, _LEFT, _FACE, "Z", "Z")

    assert forward.compatible and reverse.compatible
    assert forward.left_semantic_label == reverse.right_semantic_label
    assert forward.right_semantic_label == reverse.left_semantic_label
