"""Exact shared-face orientation frame for Chen S/Z compatibility.

Chen's opposite-type rule is stated on a shared facet, whereas Table-6 S/Z
labels live in each parent's local A/B/C/D order.  This read-only adapter
normalizes a local label with the exact side sign of its opposite vertex in a
canonical shared-face frame.  It neither selects a table row nor mutates a
mesh.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Literal

from core.generator.native_tet.chen_penetration_l0 import _point
from core.generator.native_tet.chen_pipe_cluster_l0 import _orient6

SzLabel = Literal["S", "Z"]


@dataclass(frozen=True)
class ChenOrientedSzPairResult:
    """Exact common-frame relation for two parent-local S/Z labels."""

    accepted: bool
    reason: str
    left_side_sign: int
    right_side_sign: int
    left_semantic_label: SzLabel | None
    right_semantic_label: SzLabel | None
    compatible: bool


def _label_bit(label: SzLabel) -> int:
    return 0 if label == "S" else 1


def _semantic_label(label: SzLabel, side_sign: int) -> SzLabel:
    # Crossing a shared face reverses the local facet frame.  Use the exact
    # opposite-vertex side to turn local labels into one common frame.
    bit = _label_bit(label) ^ (1 if side_sign < 0 else 0)
    return "S" if bit == 0 else "Z"


def certify_oriented_shared_face_sz_pair_l0(
    points: Sequence[Sequence[float | int | Fraction]],
    left_parent: Sequence[int],
    right_parent: Sequence[int],
    shared_face: Sequence[int],
    left_label: SzLabel,
    right_label: SzLabel,
) -> ChenOrientedSzPairResult:
    """Require Chen-opposite semantic labels in an exact shared-face frame."""
    face = tuple(sorted(int(vertex) for vertex in shared_face))
    left, right = tuple(int(vertex) for vertex in left_parent), tuple(int(vertex) for vertex in right_parent)
    empty = ChenOrientedSzPairResult(False, "invalid_input", 0, 0, None, None, False)
    if len(face) != 3 or len(set(face)) != 3 or len(left) != 4 or len(set(left)) != 4 or len(right) != 4 or len(set(right)) != 4:
        return empty
    if any(vertex < 0 or vertex >= len(points) for vertex in (*left, *right, *face)):
        return ChenOrientedSzPairResult(False, "vertex_index_out_of_range", 0, 0, None, None, False)
    if not set(face) <= set(left) or not set(face) <= set(right):
        return ChenOrientedSzPairResult(False, "face_not_owned_by_both_parents", 0, 0, None, None, False)
    left_opposite = tuple(set(left) - set(face))
    right_opposite = tuple(set(right) - set(face))
    if len(left_opposite) != 1 or len(right_opposite) != 1 or left_opposite == right_opposite:
        return ChenOrientedSzPairResult(False, "parents_do_not_form_a_two_sided_face", 0, 0, None, None, False)
    rational = tuple(_point(point) for point in points)
    left_orientation = _orient6(rational, (face[0], face[1], face[2], left_opposite[0]))
    right_orientation = _orient6(rational, (face[0], face[1], face[2], right_opposite[0]))
    if left_orientation == 0 or right_orientation == 0:
        return ChenOrientedSzPairResult(False, "degenerate_shared_face_side", 0, 0, None, None, False)
    left_sign, right_sign = (1 if left_orientation > 0 else -1), (1 if right_orientation > 0 else -1)
    if left_sign == right_sign:
        return ChenOrientedSzPairResult(False, "parents_are_not_on_opposite_face_sides", left_sign, right_sign, None, None, False)
    left_semantic = _semantic_label(left_label, left_sign)
    right_semantic = _semantic_label(right_label, right_sign)
    return ChenOrientedSzPairResult(
        True,
        "accepted",
        left_sign,
        right_sign,
        left_semantic,
        right_semantic,
        left_semantic != right_semantic,
    )
