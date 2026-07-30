from __future__ import annotations

import numpy as np

from core.generator.native_tet.rescue_gate import (
    audit_tet_boundary,
    drop_duplicate_tet_groups_if_strict_topology_restored,
    has_strict_writer_topology,
)


def _cube() -> tuple[np.ndarray, np.ndarray]:
    points = np.array(
        [
            [0, 0, 0],
            [1, 0, 0],
            [1, 1, 0],
            [0, 1, 0],
            [0, 0, 1],
            [1, 0, 1],
            [1, 1, 1],
            [0, 1, 1],
        ],
        dtype=np.float64,
    )
    tets = np.array(
        [
            [0, 1, 2, 6],
            [0, 2, 3, 6],
            [0, 3, 7, 6],
            [0, 7, 4, 6],
            [0, 4, 5, 6],
            [0, 5, 1, 6],
        ],
        dtype=np.int64,
    )
    return points, tets


def test_closed_cube_tetrahedralization_is_valid() -> None:
    points, tets = _cube()
    audit = audit_tet_boundary(points, tets)
    assert audit.valid
    assert audit.n_boundary_faces == 12
    assert audit.n_open_edges == 0
    assert audit.n_nonmanifold_edges == 0
    assert audit.n_boundary_components == 1


def test_tets_sharing_only_an_edge_are_nonmanifold() -> None:
    points, tets = _cube()
    audit = audit_tet_boundary(points, tets[[0, 3]])
    assert not audit.valid
    assert audit.n_nonmanifold_edges > 0


def test_duplicate_tet_is_rejected() -> None:
    points, tets = _cube()
    audit = audit_tet_boundary(points, np.vstack([tets, tets[:1]]))
    assert not audit.valid
    assert audit.n_duplicate_tets == 1
    assert audit.n_nonmanifold_faces > 0
    assert not has_strict_writer_topology(points, np.vstack([tets, tets[:1]]))


def test_duplicate_group_repair_refuses_boundary_changing_drop() -> None:
    points, tets = _cube()
    duplicated = np.vstack([tets, tets[:1]])

    repair = drop_duplicate_tet_groups_if_strict_topology_restored(
        points,
        duplicated,
    )

    assert not repair.applied
    assert repair.n_duplicate_groups == 1
    assert repair.n_removed_tets == 2
    assert repair.reason == "duplicate_group_drop_changes_boundary"
    assert not repair.boundary_preserved
    np.testing.assert_array_equal(repair.tets, duplicated)


def test_degenerate_tet_is_rejected() -> None:
    points, _ = _cube()
    audit = audit_tet_boundary(points, np.array([[0, 1, 2, 3]], dtype=np.int64))
    assert not audit.valid
    assert audit.n_degenerate_tets == 1


def test_disconnected_tet_components_are_rejected() -> None:
    points, _ = _cube()
    shifted = points[:4] + np.array([3.0, 0.0, 0.0])
    all_points = np.vstack([points[:4], shifted])
    tets = np.array([[0, 1, 2, 3], [4, 5, 6, 7]], dtype=np.int64)
    audit = audit_tet_boundary(all_points, tets)
    assert not audit.valid
    assert audit.n_boundary_components == 2


def test_invalid_indices_raise() -> None:
    points, _ = _cube()
    with np.testing.assert_raises(ValueError):
        audit_tet_boundary(points, np.array([[0, 1, 2, 99]], dtype=np.int64))
