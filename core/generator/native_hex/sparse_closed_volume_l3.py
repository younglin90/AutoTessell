"""Report-only closure census for selected leaves of a balanced sparse partition.

This module has no octree, cell-construction, or writer side effects.  It
expands a bounded diagnostic selection to finest-level face tiles solely to
prove (or reject) the cubical-union ownership and exterior-boundary contract.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

from .sparse_leaf_partition_l0 import _leaf_faces
from .sparse_partition_provenance_l1 import SparseProvenanceLeaf


@dataclass(frozen=True)
class SparseClosedVolumeReport:
    """Topological census of an inside-or-surface sparse leaf selection."""

    status: str
    selected_leaf_count: int
    selected_provenance_histogram: dict[str, int]
    face_owner_histogram: dict[int, int]
    boundary_face_tiles: int
    boundary_edge_owner_histogram: dict[int, int]
    connected_components: int
    closed_exterior_boundary: bool
    topology_ready: bool
    production_octree_changed: bool


def _tile_corners(tile: tuple[int, int, int, int]) -> tuple[tuple[int, int, int], ...]:
    """Return the four integer-grid corners of one oriented-agnostic face tile."""
    axis, plane, first, second = tile
    if axis == 0:
        return (
            (plane, first, second),
            (plane, first + 1, second),
            (plane, first + 1, second + 1),
            (plane, first, second + 1),
        )
    if axis == 1:
        return (
            (first, plane, second),
            (first + 1, plane, second),
            (first + 1, plane, second + 1),
            (first, plane, second + 1),
        )
    return (
        (first, second, plane),
        (first + 1, second, plane),
        (first + 1, second + 1, plane),
        (first, second + 1, plane),
    )


def _tile_edges(
    tile: tuple[int, int, int, int],
) -> tuple[tuple[tuple[int, int, int], tuple[int, int, int]], ...]:
    corners = _tile_corners(tile)
    return tuple(tuple(sorted((corners[index], corners[(index + 1) % 4]))) for index in range(4))


def audit_sparse_closed_volume(
    leaves: tuple[SparseProvenanceLeaf, ...],
    *,
    max_level: int,
    include_provenance: frozenset[str] = frozenset(("inside", "surface")),
    face_tile_budget: int = 500_000,
) -> SparseClosedVolumeReport:
    """Audit selected leaf ownership and its tiled exterior boundary.

    A finite tile budget makes this explicitly diagnostic: callers receive a
    refusal rather than a partial proof when a large adaptive domain needs a
    compact boundary representation.
    """
    if max_level < 0 or face_tile_budget <= 0:
        raise ValueError("max level and face-tile budget must be positive")
    selected = tuple(item for item in leaves if item.provenance in include_provenance)
    histogram = Counter(item.provenance for item in selected)
    face_owners: dict[tuple[int, int, int, int], list[int]] = defaultdict(list)
    tile_count = 0
    for leaf_id, item in enumerate(selected):
        for side in _leaf_faces(item.key, max_level=max_level):
            for tile in side:
                tile_count += 1
                if tile_count > face_tile_budget:
                    return SparseClosedVolumeReport(
                        status="reject_closed_volume_audit_budget",
                        selected_leaf_count=len(selected),
                        selected_provenance_histogram=dict(sorted(histogram.items())),
                        face_owner_histogram={},
                        boundary_face_tiles=0,
                        boundary_edge_owner_histogram={},
                        connected_components=0,
                        closed_exterior_boundary=False,
                        topology_ready=False,
                        production_octree_changed=False,
                    )
                face_owners[tile].append(leaf_id)

    face_counts = Counter(len(owners) for owners in face_owners.values())
    boundary = tuple(tile for tile, owners in face_owners.items() if len(owners) == 1)
    boundary_edges: Counter[tuple[tuple[int, int, int], tuple[int, int, int]]] = Counter(
        edge for tile in boundary for edge in _tile_edges(tile)
    )
    edge_counts = Counter(boundary_edges.values())
    parent = list(range(len(selected)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(first: int, second: int) -> None:
        first_root, second_root = find(first), find(second)
        if first_root != second_root:
            parent[second_root] = first_root

    for owners in face_owners.values():
        if len(owners) == 2:
            union(owners[0], owners[1])
    components = len({find(index) for index in range(len(selected))})
    valid_face_owners = bool(face_owners) and all(count in (1, 2) for count in face_counts)
    closed = bool(boundary_edges) and all(count == 2 for count in edge_counts)
    accepted = valid_face_owners and closed
    return SparseClosedVolumeReport(
        status="pass_closed_sparse_volume" if accepted else "reject_closed_sparse_volume",
        selected_leaf_count=len(selected),
        selected_provenance_histogram=dict(sorted(histogram.items())),
        face_owner_histogram=dict(sorted(face_counts.items())),
        boundary_face_tiles=len(boundary),
        boundary_edge_owner_histogram=dict(sorted(edge_counts.items())),
        connected_components=components,
        closed_exterior_boundary=closed,
        topology_ready=accepted,
        production_octree_changed=False,
    )
