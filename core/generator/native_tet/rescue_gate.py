"""Fast topology audit used to decide whether native tet needs C++ rescue."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class TetBoundaryAudit:
    n_tets: int
    n_boundary_faces: int
    n_open_edges: int
    n_nonmanifold_edges: int
    n_nonmanifold_faces: int
    n_boundary_components: int
    n_duplicate_tets: int
    n_degenerate_tets: int

    @property
    def valid(self) -> bool:
        return (
            self.n_tets > 0
            and self.n_boundary_faces > 0
            and self.n_open_edges == 0
            and self.n_nonmanifold_edges == 0
            and self.n_nonmanifold_faces == 0
            and self.n_boundary_components == 1
            and self.n_duplicate_tets == 0
            and self.n_degenerate_tets == 0
        )


def audit_tet_boundary(
    points: np.ndarray,
    tets: np.ndarray,
    *,
    relative_volume_tolerance: float = 1e-12,
) -> TetBoundaryAudit:
    """Audit closed-manifold topology without materializing Python face lists."""
    pts = np.asarray(points, dtype=np.float64)
    tet = np.asarray(tets, dtype=np.int64)
    if tet.ndim != 2 or tet.shape[1:] != (4,):
        raise ValueError("tets must have shape (N, 4)")
    if pts.ndim != 2 or pts.shape[1:] != (3,):
        raise ValueError("points must have shape (N, 3)")
    if tet.size and (int(tet.min()) < 0 or int(tet.max()) >= len(pts)):
        raise ValueError("tet vertex index out of range")
    if tet.shape[0] == 0:
        return TetBoundaryAudit(0, 0, 0, 0, 0, 0, 0, 0)

    canonical_tets = np.sort(tet, axis=1)
    duplicate_tets = int(
        canonical_tets.shape[0] - np.unique(canonical_tets, axis=0).shape[0]
    )
    vertices = pts[tet]
    volume6 = np.einsum(
        "ij,ij->i",
        vertices[:, 1] - vertices[:, 0],
        np.cross(
            vertices[:, 2] - vertices[:, 0],
            vertices[:, 3] - vertices[:, 0],
        ),
    )
    diagonal = max(float(np.linalg.norm(np.ptp(pts, axis=0))), np.finfo(float).tiny)
    volume_floor = max(0.0, float(relative_volume_tolerance)) * diagonal**3
    degenerate_tets = int((np.abs(volume6) <= volume_floor).sum())

    faces = np.concatenate(
        [
            tet[:, (0, 1, 2)],
            tet[:, (0, 1, 3)],
            tet[:, (0, 2, 3)],
            tet[:, (1, 2, 3)],
        ],
        axis=0,
    )
    canonical_faces = np.sort(faces, axis=1)
    unique_faces, counts = np.unique(canonical_faces, axis=0, return_counts=True)
    boundary_faces = unique_faces[counts == 1]
    nonmanifold_faces = int((counts > 2).sum())

    if boundary_faces.shape[0] == 0:
        return TetBoundaryAudit(
            int(tet.shape[0]), 0, 0, 0, nonmanifold_faces, 0,
            duplicate_tets, degenerate_tets,
        )

    edges = np.concatenate(
        [
            boundary_faces[:, (0, 1)],
            boundary_faces[:, (1, 2)],
            boundary_faces[:, (0, 2)],
        ],
        axis=0,
    )
    edges = np.sort(edges, axis=1)
    unique_edges, edge_counts = np.unique(edges, axis=0, return_counts=True)
    open_edges = int((edge_counts == 1).sum())
    nonmanifold_edges = int((edge_counts > 2).sum())

    parent = np.arange(boundary_faces.shape[0], dtype=np.int64)

    def find(item: int) -> int:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = int(parent[item])
        return item

    def union(left: int, right: int) -> None:
        a = find(left)
        b = find(right)
        if a != b:
            parent[b] = a

    order = np.lexsort((edges[:, 1], edges[:, 0]))
    sorted_edges = edges[order]
    face_ids = np.tile(
        np.arange(boundary_faces.shape[0], dtype=np.int64), 3
    )[order]
    starts = np.r_[0, 1 + np.flatnonzero(np.any(sorted_edges[1:] != sorted_edges[:-1], axis=1))]
    ends = np.r_[starts[1:], len(sorted_edges)]
    for start, end in zip(starts, ends):
        first = int(face_ids[start])
        for index in range(int(start) + 1, int(end)):
            union(first, int(face_ids[index]))
    components = len({find(index) for index in range(boundary_faces.shape[0])})

    return TetBoundaryAudit(
        n_tets=int(tet.shape[0]),
        n_boundary_faces=int(boundary_faces.shape[0]),
        n_open_edges=open_edges,
        n_nonmanifold_edges=nonmanifold_edges,
        n_nonmanifold_faces=nonmanifold_faces,
        n_boundary_components=int(components),
        n_duplicate_tets=duplicate_tets,
        n_degenerate_tets=degenerate_tets,
    )


__all__ = ["TetBoundaryAudit", "audit_tet_boundary"]
