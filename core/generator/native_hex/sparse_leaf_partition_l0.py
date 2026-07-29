"""L0 exact ownership census for a bounded sparse-octree leaf partition.

This is deliberately a small-domain representation check.  It does not
construct an octree from a surface, classify a solid, write cells, or modify
the native-hex generator.  A later sparse path must first produce a complete
partition in this canonical leaf-key form before 2:1 balancing or closed-volume
claims can be evaluated.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import product


@dataclass(frozen=True, order=True)
class SparseLeafKey:
    """One octree leaf in root-cell coordinates at ``level``."""

    level: int
    i: int
    j: int
    k: int


@dataclass(frozen=True)
class SparseLeafPartitionReport:
    """Exact bounded-domain partition and face-owner census."""

    status: str
    leaf_count: int
    fine_cells_expected: int
    fine_cells_covered: int
    overlapping_fine_cells: int
    missing_fine_cells: int
    face_owner_histogram: dict[int, int]
    max_face_neighbor_level_difference: int | None
    face_to_face: bool
    balanced_2to1: bool
    topology_ready: bool
    production_octree_changed: bool


def _leaf_fine_cells(leaf: SparseLeafKey, *, max_level: int) -> tuple[range, range, range]:
    scale = 1 << (max_level - leaf.level)
    return (
        range(leaf.i * scale, (leaf.i + 1) * scale),
        range(leaf.j * scale, (leaf.j + 1) * scale),
        range(leaf.k * scale, (leaf.k + 1) * scale),
    )


def _leaf_faces(
    leaf: SparseLeafKey, *, max_level: int
) -> tuple[tuple[tuple[int, int, int, int], ...], ...]:
    """Return face microtiles keyed by axis, plane, and two fine-grid indices."""
    xs, ys, zs = _leaf_fine_cells(leaf, max_level=max_level)
    x0, x1 = xs.start, xs.stop
    y0, y1 = ys.start, ys.stop
    z0, z1 = zs.start, zs.stop
    return (
        tuple((0, x0, y, z) for y, z in product(ys, zs)),
        tuple((0, x1, y, z) for y, z in product(ys, zs)),
        tuple((1, y0, x, z) for x, z in product(xs, zs)),
        tuple((1, y1, x, z) for x, z in product(xs, zs)),
        tuple((2, z0, x, y) for x, y in product(xs, ys)),
        tuple((2, z1, x, y) for x, y in product(xs, ys)),
    )


def audit_sparse_leaf_partition(
    leaves: tuple[SparseLeafKey, ...],
    *,
    root_shape: tuple[int, int, int],
    max_level: int,
) -> SparseLeafPartitionReport:
    """Measure a complete leaf partition without changing mesh generation.

    The finite ``max_level`` expands only this diagnostic domain to common
    microtiles.  It catches the representation preconditions that a compact
    production structure must preserve: exactly one terminal leaf per point in
    the root domain, one/two owners per tiled face, and at-most-one-level face
    neighbours.
    """
    if max_level < 0 or min(root_shape) <= 0:
        raise ValueError("root shape and max level must be nonnegative/positive")
    if any(leaf.level < 0 or leaf.level > max_level for leaf in leaves):
        raise ValueError("leaf level must be within the bounded audit depth")
    limit = tuple(axis * (1 << max_level) for axis in root_shape)
    coverage: Counter[tuple[int, int, int]] = Counter()
    face_owners: dict[tuple[int, int, int, int], list[SparseLeafKey]] = defaultdict(list)
    for leaf in leaves:
        xs, ys, zs = _leaf_fine_cells(leaf, max_level=max_level)
        outside_domain = (
            xs.start < 0
            or ys.start < 0
            or zs.start < 0
            or xs.stop > limit[0]
            or ys.stop > limit[1]
            or zs.stop > limit[2]
        )
        if outside_domain:
            raise ValueError("leaf lies outside the declared root domain")
        for fine_cell in product(xs, ys, zs):
            coverage[fine_cell] += 1
        for face_tiles in _leaf_faces(leaf, max_level=max_level):
            for tile in face_tiles:
                face_owners[tile].append(leaf)

    expected = limit[0] * limit[1] * limit[2]
    overlaps = sum(count > 1 for count in coverage.values())
    missing = expected - len(coverage)
    owner_counts = Counter(len(owners) for owners in face_owners.values())
    differences = [
        abs(owners[0].level - owners[1].level)
        for owners in face_owners.values()
        if len(owners) == 2
    ]
    face_to_face = bool(face_owners) and all(count in (1, 2) for count in owner_counts)
    balanced = face_to_face and (not differences or max(differences) <= 1)
    complete = overlaps == 0 and missing == 0
    status = (
        "pass_complete_balanced_partition"
        if complete and balanced
        else "reject_partition_contract"
    )
    return SparseLeafPartitionReport(
        status=status,
        leaf_count=len(leaves),
        fine_cells_expected=expected,
        fine_cells_covered=sum(count == 1 for count in coverage.values()),
        overlapping_fine_cells=overlaps,
        missing_fine_cells=missing,
        face_owner_histogram=dict(sorted(owner_counts.items())),
        max_face_neighbor_level_difference=max(differences, default=None),
        face_to_face=face_to_face,
        balanced_2to1=balanced,
        topology_ready=False,
        production_octree_changed=False,
    )
