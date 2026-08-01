"""Independent strict topology audit for release ``polyMesh`` artifacts.

The native generators check in-memory candidates while they are running.  A
release claim also needs a second observation of the written artifact, after
the generator's state is gone.  This module is read-only and never repairs,
routes, or accepts a mesh.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from core.evaluator.gate4_fidelity_substrate import inspect_gate4_output_artifact
from core.evaluator.gate4_surface_topology import audit_polymesh_surface
from core.evaluator.native_checker import NativeMeshChecker
from core.generator.native_tet.writer_topology import audit_written_polymesh
from core.utils.polymesh_reader import (
    parse_foam_faces,
    parse_foam_labels_array,
    parse_foam_points_array,
)


@dataclass(frozen=True, slots=True)
class StrictVolumeTopologyAudit:
    """Evidence from one immutable written volume-mesh artifact."""

    status: str
    artifact_sha256: str | None
    n_points: int
    n_faces: int
    n_cells: int
    n_duplicate_faces: int | None
    n_nonmanifold_faces: int | None
    n_nonmanifold_cell_edges: int | None
    n_open_cell_edges: int | None
    n_inverted_cells: int | None
    min_cell_volume: float | None
    boundary_surface_valid: bool
    boundary_duplicate_faces: int | None
    boundary_nonmanifold_edges: int | None
    boundary_nonmanifold_vertices: int | None
    malformed_reason: str | None = None
    contract: str = "autotessell/strict-volume-topology/v1"

    @property
    def valid(self) -> bool:
        """Return true only when every release-critical count is measured zero."""
        counts = (
            self.n_duplicate_faces,
            self.n_nonmanifold_faces,
            self.n_nonmanifold_cell_edges,
            self.n_open_cell_edges,
            self.n_inverted_cells,
            self.boundary_duplicate_faces,
            self.boundary_nonmanifold_edges,
            self.boundary_nonmanifold_vertices,
        )
        return bool(
            self.status == "measured"
            and self.artifact_sha256
            and self.n_points > 0
            and self.n_faces > 0
            and self.n_cells > 0
            and all(value == 0 for value in counts)
            and self.boundary_surface_valid
            and self.min_cell_volume is not None
            and np.isfinite(self.min_cell_volume)
            and self.min_cell_volume > 0.0
        )

    def as_dict(self) -> dict[str, object]:
        """Return JSON-safe evidence for a release report."""
        return {
            "status": self.status,
            "artifact_sha256": self.artifact_sha256,
            "n_points": self.n_points,
            "n_faces": self.n_faces,
            "n_cells": self.n_cells,
            "n_duplicate_faces": self.n_duplicate_faces,
            "n_nonmanifold_faces": self.n_nonmanifold_faces,
            "n_nonmanifold_cell_edges": self.n_nonmanifold_cell_edges,
            "n_open_cell_edges": self.n_open_cell_edges,
            "n_inverted_cells": self.n_inverted_cells,
            "min_cell_volume": self.min_cell_volume,
            "boundary_surface_valid": self.boundary_surface_valid,
            "boundary_duplicate_faces": self.boundary_duplicate_faces,
            "boundary_nonmanifold_edges": self.boundary_nonmanifold_edges,
            "boundary_nonmanifold_vertices": self.boundary_nonmanifold_vertices,
            "malformed_reason": self.malformed_reason,
            "contract": self.contract,
            "valid": self.valid,
        }


def _canonical_face(face: list[int]) -> tuple[int, ...]:
    sequence = tuple(int(value) for value in face)
    rotations = [sequence[index:] + sequence[:index] for index in range(len(sequence))]
    reversed_sequence = tuple(reversed(sequence))
    rotations.extend(
        reversed_sequence[index:] + reversed_sequence[:index]
        for index in range(len(reversed_sequence))
    )
    return min(rotations)


def _cell_edge_debt(
    faces: list[list[int]], written: object
) -> tuple[int, int]:
    """Count unclosed local cell edges in the written face incidence."""
    nonmanifold = 0
    open_edges = 0
    for cell in written.cells:  # type: ignore[attr-defined]
        edge_counts: Counter[tuple[int, int]] = Counter()
        for face_index in cell.face_indices:
            face = faces[face_index]
            for index, first in enumerate(face):
                second = face[(index + 1) % len(face)]
                edge_key = (min(int(first), int(second)), max(int(first), int(second)))
                edge_counts[edge_key] += 1
        nonmanifold += sum(count - 2 for count in edge_counts.values() if count > 2)
        open_edges += sum(1 for count in edge_counts.values() if count < 2)
    return nonmanifold, open_edges


def _unverified(
    *,
    artifact_sha256: str | None,
    reason: str,
    n_points: int = 0,
    n_faces: int = 0,
    n_cells: int = 0,
    n_duplicate_faces: int | None = None,
    n_nonmanifold_faces: int | None = None,
    n_nonmanifold_cell_edges: int | None = None,
    n_open_cell_edges: int | None = None,
    n_inverted_cells: int | None = None,
    min_cell_volume: float | None = None,
    boundary_surface_valid: bool = False,
    boundary_duplicate_faces: int | None = None,
    boundary_nonmanifold_edges: int | None = None,
    boundary_nonmanifold_vertices: int | None = None,
) -> StrictVolumeTopologyAudit:
    return StrictVolumeTopologyAudit(
        status="unverified",
        artifact_sha256=artifact_sha256,
        n_points=n_points,
        n_faces=n_faces,
        n_cells=n_cells,
        n_duplicate_faces=n_duplicate_faces,
        n_nonmanifold_faces=n_nonmanifold_faces,
        n_nonmanifold_cell_edges=n_nonmanifold_cell_edges,
        n_open_cell_edges=n_open_cell_edges,
        n_inverted_cells=n_inverted_cells,
        min_cell_volume=min_cell_volume,
        boundary_surface_valid=boundary_surface_valid,
        boundary_duplicate_faces=boundary_duplicate_faces,
        boundary_nonmanifold_edges=boundary_nonmanifold_edges,
        boundary_nonmanifold_vertices=boundary_nonmanifold_vertices,
        malformed_reason=reason,
    )


def audit_strict_volume_topology(case_dir: Path) -> StrictVolumeTopologyAudit:
    """Audit one written volume mesh without mutating or routing it."""
    artifact = inspect_gate4_output_artifact(case_dir)
    if artifact is None:
        return _unverified(artifact_sha256=None, reason="artifact_missing_or_unsafe")

    poly_mesh = Path(artifact.poly_mesh_path)
    try:
        points = parse_foam_points_array(poly_mesh / "points")
        faces = parse_foam_faces(poly_mesh / "faces")
        owner = parse_foam_labels_array(poly_mesh / "owner")
        neighbour = parse_foam_labels_array(poly_mesh / "neighbour")
        written = audit_written_polymesh(poly_mesh)
    except Exception as exc:  # noqa: BLE001
        return _unverified(
            artifact_sha256=artifact.sha256,
            reason=f"parse_error:{type(exc).__name__}",
        )

    if (
        points.ndim != 2
        or points.shape[1:] != (3,)
        or not len(points)
        or not np.isfinite(points).all()
        or len(owner) != len(faces)
        or len(neighbour) > len(faces)
        or any(len(face) < 3 for face in faces)
        or any(vertex < 0 or vertex >= len(points) for face in faces for vertex in face)
    ):
        return _unverified(
            artifact_sha256=artifact.sha256,
            reason="invalid_written_incidence",
            n_points=int(len(points)),
            n_faces=len(faces),
            n_cells=written.n_cells,
        )

    edge_nonmanifold, edge_open = _cell_edge_debt(faces, written)
    face_counts = Counter(_canonical_face(face) for face in faces)
    duplicate_faces = sum(count - 1 for count in face_counts.values() if count > 1)
    nonmanifold_faces = sum(count - 2 for count in face_counts.values() if count > 2)
    boundary = audit_polymesh_surface(case_dir)

    try:
        check = NativeMeshChecker().run(case_dir)
    except Exception as exc:  # noqa: BLE001
        return _unverified(
            artifact_sha256=artifact.sha256,
            reason=f"independent_volume_check_error:{type(exc).__name__}",
            n_points=len(points),
            n_faces=len(faces),
            n_cells=written.n_cells,
            n_duplicate_faces=duplicate_faces,
            n_nonmanifold_faces=nonmanifold_faces,
            n_nonmanifold_cell_edges=edge_nonmanifold,
            n_open_cell_edges=edge_open,
            boundary_surface_valid=bool(boundary.topology_valid),
            boundary_duplicate_faces=boundary.duplicate_face_count,
            boundary_nonmanifold_edges=boundary.nonmanifold_edge_count,
            boundary_nonmanifold_vertices=boundary.nonmanifold_vertex_count,
        )

    return StrictVolumeTopologyAudit(
        status="measured",
        artifact_sha256=artifact.sha256,
        n_points=len(points),
        n_faces=len(faces),
        n_cells=written.n_cells,
        n_duplicate_faces=duplicate_faces,
        n_nonmanifold_faces=nonmanifold_faces,
        n_nonmanifold_cell_edges=edge_nonmanifold,
        n_open_cell_edges=edge_open,
        n_inverted_cells=int(check.negative_volumes),
        min_cell_volume=float(check.min_cell_volume),
        boundary_surface_valid=bool(boundary.topology_valid),
        boundary_duplicate_faces=boundary.duplicate_face_count,
        boundary_nonmanifold_edges=boundary.nonmanifold_edge_count,
        boundary_nonmanifold_vertices=boundary.nonmanifold_vertex_count,
    )


__all__ = ["StrictVolumeTopologyAudit", "audit_strict_volume_topology"]
