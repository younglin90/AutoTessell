"""Strict shared-facet embedding checks for native tetrahedra."""

from __future__ import annotations

import numpy as np

from core.generator.native_tet.rescue_gate import (
    audit_internal_face_sidedness,
    audit_tet_boundary,
    has_strict_writer_topology,
)


def _shared_face_points(second_apex_z: float) -> np.ndarray:
    return np.asarray(
        (
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
            (0.25, 0.25, second_apex_z),
        ),
        dtype=np.float64,
    )


def test_opposite_apexes_are_a_valid_internal_face() -> None:
    points = _shared_face_points(-1.0)
    tets = np.asarray(((0, 1, 2, 3), (0, 2, 1, 4)), dtype=np.int64)

    sidedness = audit_internal_face_sidedness(points, tets)
    topology = audit_tet_boundary(points, tets)

    assert sidedness.n_internal_faces == 1
    assert sidedness.n_opposite_side_internal_faces == 1
    assert sidedness.n_same_side_internal_faces == 0
    assert sidedness.n_ambiguous_internal_faces == 0
    assert topology.valid
    assert has_strict_writer_topology(points, tets)


def test_same_side_apexes_fail_as_overlapping_tetrahedra() -> None:
    points = _shared_face_points(0.5)
    tets = np.asarray(((0, 1, 2, 3), (0, 1, 2, 4)), dtype=np.int64)

    audits = tuple(audit_tet_boundary(points, tets) for _ in range(3))

    assert all(audit.n_internal_faces == 1 for audit in audits)
    assert all(audit.n_same_side_internal_faces == 1 for audit in audits)
    assert all(audit.n_ambiguous_internal_faces == 0 for audit in audits)
    assert all(not audit.valid for audit in audits)
    assert not has_strict_writer_topology(points, tets)


def test_near_coplanar_apex_is_ambiguous_and_fails_closed() -> None:
    points = _shared_face_points(-1e-15)
    tets = np.asarray(((0, 1, 2, 3), (0, 2, 1, 4)), dtype=np.int64)

    sidedness = audit_internal_face_sidedness(points, tets)
    topology = audit_tet_boundary(points, tets)

    assert sidedness.n_internal_faces == 1
    assert sidedness.n_opposite_side_internal_faces == 0
    assert sidedness.n_same_side_internal_faces == 0
    assert sidedness.n_ambiguous_internal_faces == 1
    assert topology.n_ambiguous_internal_faces == 1
    assert not topology.valid
    assert not has_strict_writer_topology(points, tets)
