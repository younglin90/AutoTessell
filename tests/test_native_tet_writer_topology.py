"""Read-only written-polyMesh topology census tests."""

from __future__ import annotations

import numpy as np
import pytest

from core.generator.polymesh_writer import PolyMeshWriter
from core.generator.native_tet.writer_topology import (
    audit_written_cell_topology,
    audit_written_polymesh,
)


def test_audit_reports_face_ownership_and_non_tet_structure() -> None:
    # Faces 0--2 are internal and use the OpenFOAM neighbour-prefix convention.
    faces = [
        [0, 2, 1],
        [0, 1, 3],
        [1, 2, 3],
        [2, 0, 3],
        [4, 5, 6, 7],
        [4, 8, 5],
        [5, 8, 6],
        [6, 8, 7],
        [7, 8, 4],
    ]
    owner = [0, 0, 0, 0, 1, 1, 1, 1, 1]
    neighbour = [1, 1, 1]

    audit = audit_written_cell_topology(faces, owner, neighbour)

    assert audit.n_cells == 2
    assert audit.cells[0].is_tetrahedron_encoding
    assert audit.cells[0].face_indices == (0, 1, 2, 3)
    assert audit.cells[0].face_roles == ("owner", "owner", "owner", "owner")
    assert audit.cells[0].face_arities == (3, 3, 3, 3)
    assert audit.cells[1].face_indices == (0, 1, 2, 4, 5, 6, 7, 8)
    assert audit.cells[1].face_roles[:3] == ("neighbour", "neighbour", "neighbour")
    assert audit.cells[1].structural_classification == (
        "non_tetrahedron:face_count+non_triangular_face+unique_vertex_count"
    )
    assert audit.as_dict()["n_non_tetrahedron_encodings"] == 1
    assert audit.as_dict()["n_non_tetrahedron_vertex_incidence_cells"] == 1


def test_audit_distinguishes_missing_faces_from_missing_tet_vertices() -> None:
    audit = audit_written_cell_topology(
        [[0, 1, 2], [0, 3, 1], [1, 3, 2]],
        [0, 0, 0],
        [],
    )

    assert not audit.cells[0].is_tetrahedron_encoding
    assert audit.cells[0].has_tetrahedron_vertex_incidence
    assert len(audit.incomplete_tetrahedron_face_encodings) == 1
    assert not audit.non_tetrahedron_vertex_incidence_cells


def test_audit_fails_closed_on_incomplete_owner_labels() -> None:
    with pytest.raises(ValueError, match="exactly one label per face"):
        audit_written_cell_topology([[0, 1, 2]], [], [])


def test_native_tet_writer_rejects_non_manifold_face_before_write(tmp_path) -> None:
    """A tet-only writer must not discard extra cell incidences."""
    vertices = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [0.0, 0.0, -1.0],
            [0.2, 0.2, 2.0],
        ]
    )
    tets = np.asarray([[0, 1, 2, 3], [0, 1, 2, 4], [0, 1, 2, 5]])

    with pytest.raises(ValueError, match="non-manifold face references"):
        PolyMeshWriter().write(vertices, tets, tmp_path)

    assert not (tmp_path / "constant" / "polyMesh").exists()


def test_native_tet_writer_preserves_valid_single_tet_encoding(tmp_path) -> None:
    vertices = np.asarray(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    )

    stats = PolyMeshWriter().write(vertices, np.asarray([[0, 1, 2, 3]]), tmp_path)
    audit = audit_written_polymesh(
        tmp_path / "constant" / "polyMesh"
    )

    assert stats["num_cells"] == 1
    assert audit.cells[0].is_tetrahedron_encoding
