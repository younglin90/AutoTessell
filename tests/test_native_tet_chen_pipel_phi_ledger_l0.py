"""L0 schedule/conformity certificate for Chen--Zheng Table-5 neighbors."""

from __future__ import annotations

from core.generator.native_tet.chen_pipel_phi_ledger_l0 import (
    certify_one_edge_phi_ledger,
)


def _closed_pipe() -> (
    tuple[tuple[tuple[float, float, float], ...], tuple[tuple[int, int, int, int], ...]]
):
    points = (
        (2.0, 0.0, 0.0),
        (0.0, 0.0, -1.0),
        (-1.0, 2.0, 0.0),
        (0.0, 0.0, 1.0),
        (-1.0, -2.0, 0.0),
        (0.0, 0.0, 0.0),
    )
    return points, ((0, 1, 2, 3), (2, 1, 4, 3), (4, 1, 0, 3))


def test_phi_ledger_agrees_on_every_shared_cut_edge_face() -> None:
    points, parents = _closed_pipe()

    result = certify_one_edge_phi_ledger(points, parents, (1, 3), 5)

    assert result.accepted, result.reason
    assert len(result.face_ledger) == 3
    assert len(result.replacement_tets) == 6
    assert result.local_certificate.external_boundary_preserved


def test_phi_ledger_is_schedule_independent() -> None:
    points, parents = _closed_pipe()

    forward = certify_one_edge_phi_ledger(points, parents, (1, 3), 5)
    reordered = certify_one_edge_phi_ledger(points, parents, (1, 3), 5, processing_order=(2, 0, 1))

    assert forward.accepted and reordered.accepted
    assert forward.face_ledger == reordered.face_ledger
    assert forward.replacement_tets == reordered.replacement_tets


def test_phi_ledger_rejects_non_permutation_schedule_without_replacement() -> None:
    points, parents = _closed_pipe()

    result = certify_one_edge_phi_ledger(points, parents, (1, 3), 5, processing_order=(0, 0, 1))

    assert not result.accepted
    assert result.reason == "invalid_processing_order"
    assert not result.replacement_tets
