"""L3 test-only atomic staging tests for an exact cavity-boundary subdivision."""

from __future__ import annotations

from fractions import Fraction

from core.generator.native_tet.chen_staged_state_l0 import certify_atomic_staged_replacement
from core.generator.native_tet.chen_subdivided_staged_state_l3 import (
    certify_atomic_subdivided_boundary_replacement_l3,
)


def _thr_fou_cavity() -> tuple[
    tuple[tuple[Fraction | int, Fraction | int, Fraction | int], ...],
    dict[int, tuple[int, int, int, int]],
    tuple[tuple[int, int, int], ...],
    dict[int, tuple[tuple[int, int, int, int], ...]],
]:
    # The exact two-parent L2 seam fixture, with all derived P points made
    # explicit only for this off-mesh L3 staging certificate.
    points = (
        (-1, 0, Fraction(-1, 2)),
        (1, 0, Fraction(1, 2)),
        (0, -1, -1),
        (0, 1, -1),
        (0, 0, 1),
        (Fraction(-2, 3), 0, 0),  # THR P1
        (0, Fraction(-1, 2), 0),  # THR P2 = FOU P3
        (0, Fraction(1, 2), 0),  # THR P3 = FOU P2
        (Fraction(2, 3), Fraction(1, 3), 0),  # FOU P1
        (Fraction(2, 3), Fraction(-1, 3), 0),  # FOU P4
    )
    parents = {0: (0, 2, 3, 4), 1: (1, 4, 2, 3)}
    boundary = ((0, 3, 4), (0, 2, 4), (0, 2, 3), (1, 2, 3), (1, 3, 4), (1, 2, 4))
    children = {
        0: ((0, 2, 3, 5), (5, 2, 3, 6), (5, 6, 3, 7), (5, 6, 7, 4)),
        1: ((7, 8, 6, 3), (6, 8, 2, 3), (6, 8, 9, 2), (6, 8, 7, 4), (9, 8, 6, 1), (4, 1, 6, 8)),
    }
    return points, parents, boundary, children


def test_parallel_l3_staging_accepts_exact_thr_fou_cavity_boundary_subdivision() -> None:
    points, parents, boundary, children = _thr_fou_cavity()

    result = certify_atomic_subdivided_boundary_replacement_l3(points, parents, boundary, children)

    assert result.accepted, result.reason
    assert len(result.committed_tets) == 10
    assert result.source_boundary_subdivision_preserved
    assert result.volume_preserved
    assert result.all_positive
    assert result.child_face_incidence_valid
    assert not result.production_mesh_changed


def test_permanent_raw_key_gate_still_rejects_the_same_valid_subdivision() -> None:
    points, parents, boundary, children = _thr_fou_cavity()

    raw = certify_atomic_staged_replacement(points, parents, boundary, children)
    subdivided = certify_atomic_subdivided_boundary_replacement_l3(
        points, parents, boundary, children
    )

    assert not raw.accepted
    assert not raw.boundary_preserved
    assert subdivided.accepted


def test_l3_subdivided_staging_rejects_a_partial_cavity_replacement() -> None:
    points, parents, boundary, children = _thr_fou_cavity()

    result = certify_atomic_subdivided_boundary_replacement_l3(
        points, parents, boundary, {0: children[0]}
    )

    assert not result.accepted
    assert result.reason == "candidate_must_replace_entire_active_cavity"
    assert not result.committed_tets
