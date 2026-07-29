from __future__ import annotations

import numpy as np


def _triangular_edge_cavity() -> tuple[np.ndarray, np.ndarray, tuple[int, int]]:
    pts = np.array(
        [
            [0.0, 0.0, 0.12],
            [0.0, 0.0, -0.12],
            [1.0, 0.0, 0.0],
            [-0.5, 0.8660254, 0.0],
            [-0.5, -0.8660254, 0.0],
        ],
        dtype=np.float64,
    )
    tets = np.array(
        [
            [0, 1, 2, 3],
            [0, 1, 3, 4],
            [0, 1, 4, 2],
        ],
        dtype=np.int64,
    )
    return pts, tets, (0, 1)


def _quad_edge_cavity() -> tuple[np.ndarray, np.ndarray, tuple[int, int]]:
    pts = np.array(
        [
            [0.0, 0.0, 0.25],
            [0.0, 0.0, -0.25],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [-1.0, 0.0, 0.0],
            [0.0, -1.0, 0.0],
        ],
        dtype=np.float64,
    )
    tets = np.array(
        [
            [0, 1, 2, 3],
            [0, 1, 3, 4],
            [0, 1, 4, 5],
            [0, 1, 5, 2],
        ],
        dtype=np.int64,
    )
    return pts, tets, (0, 1)


def test_extract_edge_cavity_orders_closed_ring() -> None:
    from core.generator.native_tet.mfrc import extract_edge_cavity

    _pts, tets, edge = _triangular_edge_cavity()
    cavity = extract_edge_cavity(tets, edge)

    assert cavity is not None
    assert cavity.edge == (0, 1)
    assert cavity.owner_tet_ids == (0, 1, 2)
    assert set(cavity.ring_vertices) == {2, 3, 4}
    assert len(cavity.boundary_faces) == 6


def test_enumerate_edge_mfrc_preserves_boundary_and_volume() -> None:
    from core.generator.native_tet.mfrc import enumerate_edge_mfrc_candidates

    pts, tets, edge = _triangular_edge_cavity()
    candidates = enumerate_edge_mfrc_candidates(
        pts,
        tets,
        edge,
        min_quality_improvement=-1.0,
    )

    assert len(candidates) == 1
    cand = candidates[0]
    assert cand.accepted, cand.reason
    assert cand.new_tets.shape == (2, 4)
    assert cand.min_quality_after > cand.min_quality_before
    assert cand.boundary_faces


def test_apply_edge_mfrc_replaces_only_cavity_tets() -> None:
    from core.generator.native_tet.mfrc import apply_edge_mfrc

    pts, tets, edge = _triangular_edge_cavity()
    extra = np.array([[2, 3, 4, 0]], dtype=np.int64)
    all_tets = np.vstack([tets, extra])

    out, candidate = apply_edge_mfrc(
        pts,
        all_tets,
        edge,
        min_quality_improvement=-1.0,
    )

    assert candidate is not None
    assert out.shape[0] == 3
    assert any(np.array_equal(row, extra[0]) for row in out)


def test_propose_edge_mfrc_respects_quality_gate() -> None:
    from core.generator.native_tet.mfrc import propose_edge_mfrc

    pts, tets, edge = _triangular_edge_cavity()
    candidate = propose_edge_mfrc(
        pts,
        tets,
        edge,
        min_quality_improvement=10.0,
    )

    assert candidate is None


def test_quad_ring_enumerates_bounded_candidates() -> None:
    from core.generator.native_tet.mfrc import enumerate_edge_mfrc_candidates

    pts, tets, edge = _quad_edge_cavity()
    candidates = enumerate_edge_mfrc_candidates(
        pts,
        tets,
        edge,
        min_quality_improvement=-1.0,
    )

    assert len(candidates) == 2
    assert {candidate.new_tets.shape[0] for candidate in candidates} == {4}
    assert all(candidate.reason in {"accepted", "quality_not_improved"} for candidate in candidates)
