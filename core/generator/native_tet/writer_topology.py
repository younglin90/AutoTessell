"""Read-only structural census for written OpenFOAM polyMesh cells.

The native-tet generator holds tetra connectivity before writing, while an
OpenFOAM ``polyMesh`` represents cells indirectly through faces and their
owner/neighbour labels.  This module reports that written representation
without inferring geometric validity, repairing connectivity, or changing any
mesh output.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from core.utils.polymesh_reader import (
    parse_foam_faces,
    parse_foam_labels,
)


@dataclass(frozen=True)
class WrittenCellTopology:
    """One cell's face-based encoding, not a cell-validity verdict."""

    cell_id: int
    face_indices: tuple[int, ...]
    face_roles: tuple[str, ...]
    face_arities: tuple[int, ...]
    unique_vertex_ids: tuple[int, ...]
    structural_classification: str

    @property
    def is_tetrahedron_encoding(self) -> bool:
        """Whether the written incidence has the ordinary four-triangle tet form."""
        return self.structural_classification == "tetrahedron_encoding"

    @property
    def has_tetrahedron_vertex_incidence(self) -> bool:
        """Whether exactly four written vertex ids are recoverable for the cell."""
        return len(self.unique_vertex_ids) == 4

    def as_dict(self) -> dict[str, Any]:
        return {
            "cell_id": self.cell_id,
            "face_indices": list(self.face_indices),
            "face_roles": list(self.face_roles),
            "face_arities": list(self.face_arities),
            "unique_vertex_ids": list(self.unique_vertex_ids),
            "n_faces": len(self.face_indices),
            "n_unique_vertices": len(self.unique_vertex_ids),
            "structural_classification": self.structural_classification,
            "is_tetrahedron_encoding": self.is_tetrahedron_encoding,
            "has_tetrahedron_vertex_incidence": self.has_tetrahedron_vertex_incidence,
        }


@dataclass(frozen=True)
class WrittenPolyMeshTopologyAudit:
    """Deterministic report of written cell incidence."""

    n_faces: int
    n_owner_labels: int
    n_neighbour_labels: int
    n_cells: int
    cells: tuple[WrittenCellTopology, ...]

    @property
    def non_tetrahedron_cells(self) -> tuple[WrittenCellTopology, ...]:
        return tuple(cell for cell in self.cells if not cell.is_tetrahedron_encoding)

    @property
    def incomplete_tetrahedron_face_encodings(self) -> tuple[WrittenCellTopology, ...]:
        """Cells with four recoverable vertices but incomplete face incidence."""
        return tuple(
            cell
            for cell in self.cells
            if cell.has_tetrahedron_vertex_incidence and not cell.is_tetrahedron_encoding
        )

    @property
    def non_tetrahedron_vertex_incidence_cells(self) -> tuple[WrittenCellTopology, ...]:
        """Cells for which the legacy vertex-only primal cannot recover a tet."""
        return tuple(cell for cell in self.cells if not cell.has_tetrahedron_vertex_incidence)

    def as_dict(self) -> dict[str, Any]:
        non_tets = self.non_tetrahedron_cells
        incomplete_face_encodings = self.incomplete_tetrahedron_face_encodings
        non_tet_vertex_incidence = self.non_tetrahedron_vertex_incidence_cells
        return {
            "n_faces": self.n_faces,
            "n_owner_labels": self.n_owner_labels,
            "n_neighbour_labels": self.n_neighbour_labels,
            "n_cells": self.n_cells,
            "n_tetrahedron_encodings": self.n_cells - len(non_tets),
            "n_non_tetrahedron_encodings": len(non_tets),
            "non_tetrahedron_cells": [cell.as_dict() for cell in non_tets],
            "n_incomplete_tetrahedron_face_encodings": len(incomplete_face_encodings),
            "incomplete_tetrahedron_face_encodings": [
                cell.as_dict() for cell in incomplete_face_encodings
            ],
            "n_non_tetrahedron_vertex_incidence_cells": len(non_tet_vertex_incidence),
            "non_tetrahedron_vertex_incidence_cells": [
                cell.as_dict() for cell in non_tet_vertex_incidence
            ],
        }


def _structural_classification(
    face_arities: tuple[int, ...], unique_vertex_ids: tuple[int, ...]
) -> str:
    """Name only observable incidence differences from a tetrahedron encoding."""
    reasons: list[str] = []
    if len(face_arities) != 4:
        reasons.append("face_count")
    if any(arity != 3 for arity in face_arities):
        reasons.append("non_triangular_face")
    if len(unique_vertex_ids) != 4:
        reasons.append("unique_vertex_count")
    if not reasons:
        return "tetrahedron_encoding"
    return "non_tetrahedron:" + "+".join(reasons)


def audit_written_cell_topology(
    faces: Sequence[Sequence[int]], owner: Sequence[int], neighbour: Sequence[int]
) -> WrittenPolyMeshTopologyAudit:
    """Classify every written cell from face ownership and arity alone.

    ``owner`` must label every face.  ``neighbour`` labels the leading internal
    faces according to the OpenFOAM convention.  Invalid label-array structure
    is rejected because a partial census could misidentify a cell; this does
    not assess whether a structurally complete cell is geometrically valid.
    """
    owner_arr = np.asarray(owner, dtype=np.int64).reshape(-1)
    neighbour_arr = np.asarray(neighbour, dtype=np.int64).reshape(-1)
    if owner_arr.size != len(faces):
        raise ValueError("owner must contain exactly one label per face")
    if neighbour_arr.size > len(faces):
        raise ValueError("neighbour cannot contain more labels than faces")
    if owner_arr.size and int(owner_arr.min()) < 0:
        raise ValueError("owner contains a negative cell label")
    if neighbour_arr.size and int(neighbour_arr.min()) < 0:
        raise ValueError("neighbour contains a negative cell label")

    max_owner = int(owner_arr.max()) if owner_arr.size else -1
    max_neighbour = int(neighbour_arr.max()) if neighbour_arr.size else -1
    n_cells = max(max_owner, max_neighbour) + 1
    face_refs: list[list[tuple[int, str]]] = [[] for _ in range(n_cells)]
    for face_index, cell_id in enumerate(owner_arr):
        face_refs[int(cell_id)].append((face_index, "owner"))
    for face_index, cell_id in enumerate(neighbour_arr):
        face_refs[int(cell_id)].append((face_index, "neighbour"))

    cells: list[WrittenCellTopology] = []
    for cell_id, refs in enumerate(face_refs):
        refs.sort()
        face_indices = tuple(face_index for face_index, _ in refs)
        face_roles = tuple(role for _, role in refs)
        face_arities = tuple(len(faces[face_index]) for face_index in face_indices)
        unique_vertex_ids = tuple(
            sorted({int(vertex) for face_index in face_indices for vertex in faces[face_index]})
        )
        cells.append(
            WrittenCellTopology(
                cell_id=cell_id,
                face_indices=face_indices,
                face_roles=face_roles,
                face_arities=face_arities,
                unique_vertex_ids=unique_vertex_ids,
                structural_classification=_structural_classification(
                    face_arities, unique_vertex_ids
                ),
            )
        )
    return WrittenPolyMeshTopologyAudit(
        n_faces=len(faces),
        n_owner_labels=int(owner_arr.size),
        n_neighbour_labels=int(neighbour_arr.size),
        n_cells=n_cells,
        cells=tuple(cells),
    )


def audit_written_polymesh(poly_mesh_dir: Path) -> WrittenPolyMeshTopologyAudit:
    """Load and audit any written OpenFOAM ``constant/polyMesh`` directory."""
    return audit_written_cell_topology(
        parse_foam_faces(poly_mesh_dir / "faces"),
        parse_foam_labels(poly_mesh_dir / "owner"),
        parse_foam_labels(poly_mesh_dir / "neighbour"),
    )
