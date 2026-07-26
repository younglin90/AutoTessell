"""HEX-SHEET-2 report-only layer-wide pillow precondition census.

The candidate shrink set ``S`` is every owner cell of a physical-boundary
quadrilateral.  The candidate interface ``Q`` is every face with exactly one
owner in ``S`` and one owner in the core.  This module measures that topology
without changing points, cells, face order, or connectivity.

Ledoux and Shepherd's pillowing guarantee applies only when ``Q`` is a
manifold quadrilateral set.  The stricter AutoTessell wall-layer contract also
requires every shrink cell to be a clean hex with exactly one physical-boundary
face and exactly one interface face.  The latter condition must be measured:
edge and corner cells of a Cartesian shell do not satisfy it in general.
"""

from __future__ import annotations

from collections import Counter, deque
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from core.generator.native_hex.match_diagnostic import _is_clean_hex
from core.generator.native_hex.metrics import CellFaces, _face_key
from core.utils.logging import get_logger

log = get_logger(__name__)

Histogram = tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class Sheet2DiagnosticReport:
    """Measured preconditions and exact topology-growth prediction."""

    shape_name: str
    n_points: int
    n_cells: int
    n_boundary_faces: int
    n_boundary_quads: int
    n_boundary_nonquads: int
    n_shrink: int
    n_shrink_nonhex: int
    n_core: int
    n_interface_faces: int
    n_interface_quads: int
    n_interface_nonquads: int
    n_interface_bad_owner_count: int
    n_interface_vertices: int
    n_interface_vertices_on_boundary: int
    edge_incidence_histogram: Histogram
    n_components: int
    n_open_edges: int
    n_nonmanifold_edges: int
    shrink_boundary_face_histogram: Histogram
    shrink_interface_face_histogram: Histogram
    shrink_boundary_interface_histogram: tuple[tuple[int, int, int], ...]
    expected_point_growth: int
    expected_cell_growth: int
    q_closed_manifold_quad_set: bool
    wall_cell_incidence_contract: bool
    topology_ready: bool


def _histogram(values: Sequence[int]) -> Histogram:
    return tuple(sorted((int(value), int(count)) for value, count in Counter(values).items()))


def _face_records(
    cell_faces: CellFaces,
) -> dict[tuple[int, ...], tuple[tuple[int, ...], tuple[int, ...]]]:
    """Return deterministic cyclic face representatives and owner tuples."""
    cyclic: dict[tuple[int, ...], tuple[int, ...]] = {}
    owners: dict[tuple[int, ...], list[int]] = {}
    for cell_index, cell in enumerate(cell_faces):
        for face in cell:
            key = _face_key(face)
            cyclic.setdefault(key, tuple(int(vertex) for vertex in face))
            owners.setdefault(key, []).append(int(cell_index))
    return {key: (cyclic[key], tuple(owners[key])) for key in sorted(owners)}


def _face_edges(face: Sequence[int]) -> tuple[tuple[int, int], ...]:
    edges: list[tuple[int, int]] = []
    for index in range(len(face)):
        left = int(face[index])
        right = int(face[(index + 1) % len(face)])
        edges.append((min(left, right), max(left, right)))
    return tuple(edges)


def _component_count(face_edges: Sequence[set[tuple[int, int]]]) -> int:
    """Count interface-face components under shared-edge adjacency."""
    if not face_edges:
        return 0
    edge_faces: dict[tuple[int, int], list[int]] = {}
    for face_index, edges in enumerate(face_edges):
        for edge in edges:
            edge_faces.setdefault(edge, []).append(face_index)
    adjacency: list[set[int]] = [set() for _ in face_edges]
    for indices in edge_faces.values():
        for left in indices:
            adjacency[left].update(right for right in indices if right != left)

    remaining = set(range(len(face_edges)))
    components = 0
    while remaining:
        components += 1
        seed = min(remaining)
        remaining.remove(seed)
        queue: deque[int] = deque([seed])
        while queue:
            current = queue.popleft()
            for neighbor in sorted(adjacency[current]):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    queue.append(neighbor)
    return components


def analyze_layer_wide_shrink_set(
    shape_name: str,
    points: np.ndarray,
    cell_faces: CellFaces,
    *,
    log_only: bool = True,
) -> Sheet2DiagnosticReport:
    """Measure the proposed layer-wide wall pillow without mutating the mesh."""
    pts = np.asarray(points)
    cells = [[list(map(int, face)) for face in cell] for cell in cell_faces]
    records = _face_records(cells)

    boundary = {key: record for key, record in records.items() if len(record[1]) == 1}
    boundary_quads = {key: record for key, record in boundary.items() if len(record[0]) == 4}
    shrink = {record[1][0] for record in boundary_quads.values()}
    core = set(range(len(cells))) - shrink

    interface: dict[tuple[int, ...], tuple[tuple[int, ...], tuple[int, ...]]] = {}
    interface_bad_owner_count = 0
    for key, record in records.items():
        owner_set = set(record[1])
        if not (owner_set & shrink and owner_set & core):
            continue
        interface[key] = record
        if len(record[1]) != 2:
            interface_bad_owner_count += 1

    interface_vertices = {
        int(vertex) for cyclic, _owners in interface.values() for vertex in cyclic
    }
    boundary_vertices = {int(vertex) for cyclic, _owners in boundary.values() for vertex in cyclic}

    edge_counts: Counter[tuple[int, int]] = Counter()
    interface_face_edges: list[set[tuple[int, int]]] = []
    for cyclic, _owners in interface.values():
        edges = set(_face_edges(cyclic))
        interface_face_edges.append(edges)
        edge_counts.update(edges)

    boundary_count_by_cell = Counter(record[1][0] for record in boundary.values())
    interface_count_by_cell: Counter[int] = Counter()
    for _cyclic, owner_list in interface.values():
        for owner in owner_list:
            if owner in shrink:
                interface_count_by_cell[owner] += 1

    boundary_counts = [int(boundary_count_by_cell[cell]) for cell in sorted(shrink)]
    interface_counts = [int(interface_count_by_cell[cell]) for cell in sorted(shrink)]
    pair_hist = Counter(zip(boundary_counts, interface_counts, strict=True))

    n_interface_quads = sum(len(cyclic) == 4 for cyclic, _owners in interface.values())
    edge_hist = _histogram(list(edge_counts.values()))
    q_closed = bool(interface) and (
        n_interface_quads == len(interface)
        and interface_bad_owner_count == 0
        and all(count == 2 for count in edge_counts.values())
    )
    wall_contract = bool(shrink) and (
        all(_is_clean_hex(cells[cell]) for cell in shrink)
        and all(boundary == 1 for boundary in boundary_counts)
        and all(interface_count == 1 for interface_count in interface_counts)
    )
    n_q_boundary_vertices = len(interface_vertices & boundary_vertices)
    topology_ready = q_closed and wall_contract and n_q_boundary_vertices == 0

    report = Sheet2DiagnosticReport(
        shape_name=str(shape_name),
        n_points=int(pts.shape[0]),
        n_cells=len(cells),
        n_boundary_faces=len(boundary),
        n_boundary_quads=len(boundary_quads),
        n_boundary_nonquads=len(boundary) - len(boundary_quads),
        n_shrink=len(shrink),
        n_shrink_nonhex=sum(not _is_clean_hex(cells[cell]) for cell in shrink),
        n_core=len(core),
        n_interface_faces=len(interface),
        n_interface_quads=n_interface_quads,
        n_interface_nonquads=len(interface) - n_interface_quads,
        n_interface_bad_owner_count=interface_bad_owner_count,
        n_interface_vertices=len(interface_vertices),
        n_interface_vertices_on_boundary=n_q_boundary_vertices,
        edge_incidence_histogram=edge_hist,
        n_components=_component_count(interface_face_edges),
        n_open_edges=sum(count == 1 for count in edge_counts.values()),
        n_nonmanifold_edges=sum(count > 2 for count in edge_counts.values()),
        shrink_boundary_face_histogram=_histogram(boundary_counts),
        shrink_interface_face_histogram=_histogram(interface_counts),
        shrink_boundary_interface_histogram=tuple(
            sorted(
                (int(boundary), int(q_faces), int(count))
                for (boundary, q_faces), count in pair_hist.items()
            )
        ),
        expected_point_growth=len(interface_vertices),
        expected_cell_growth=len(interface),
        q_closed_manifold_quad_set=q_closed,
        wall_cell_incidence_contract=wall_contract,
        topology_ready=topology_ready,
    )
    if log_only:
        log.info(
            "native_hex_sheet2_diagnostic",
            shape=report.shape_name,
            n_shrink=report.n_shrink,
            n_shrink_nonhex=report.n_shrink_nonhex,
            q_quads=report.n_interface_quads,
            q_nonquads=report.n_interface_nonquads,
            q_components=report.n_components,
            q_open_edges=report.n_open_edges,
            q_nonmanifold_edges=report.n_nonmanifold_edges,
            wall_contract=report.wall_cell_incidence_contract,
            topology_ready=report.topology_ready,
        )
    return report
