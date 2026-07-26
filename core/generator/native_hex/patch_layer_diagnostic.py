"""HEX-PATCH-LAYER-DIAG1 report-only patch/layer precondition census.

This module narrows the rejected HEX-SHEET-2 all-wall shrink set to wall
cells that could, in principle, form a per-patch pillowing layer.  It is
deliberately diagnostic-only: it never changes points, cells, faces, or
connectivity and it does not call a pillow or sheet-extraction constructor.

The source cache stores points and cell faces, but not the OpenFOAM boundary
file.  ``reconstruct_native_hex_patch_provenance`` therefore reproduces the
writer's deterministic feature-patch grouping from the cached boundary faces
and attaches the native_hex single-source ``defaultWall`` provenance.  A
caller with an authoritative face-label map may pass it directly instead.
"""

from __future__ import annotations

from collections import Counter, defaultdict, deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np

from core.generator.native_hex.match_diagnostic import _is_clean_hex
from core.generator.native_hex.metrics import CellFaces, _face_key
from core.generator.native_hex.sheet_diagnostic import _face_edges, _face_records

FaceKey = tuple[int, ...]
Histogram = tuple[tuple[int, int], ...]
PatchProvenance = tuple[str, str]
OperationStatus = Literal["approved", "rejected"]


@dataclass(frozen=True)
class PatchLayerComponent:
    """One connected, same-patch candidate interface component."""

    patch: str
    provenance: str
    component_index: int
    n_s: int
    n_q: int
    n_q_nonquad: int
    n_q_bad_owner_count: int
    n_q_vertices: int
    n_q_vertices_on_physical_boundary: int
    edge_incidence_histogram: Histogram
    n_open_edges: int
    n_nonmanifold_edges: int
    predicted_operation: str
    predicted_new_points: int
    predicted_new_cells: int
    operation_status: OperationStatus
    rejection_reasons: tuple[str, ...]


@dataclass(frozen=True)
class PatchLayerDiagnosticReport:
    """Aggregate strict patch/layer classification and operation forecast."""

    shape_name: str
    n_points: int
    n_cells: int
    n_physical_boundary_faces: int
    n_physical_boundary_quads: int
    n_physical_boundary_nonquads: int
    n_wall_exact_one_boundary: int
    n_wall_exact_one_boundary_nonhex: int
    n_interface_faces: int
    n_interface_quads: int
    n_interface_nonquads: int
    n_interface_bad_owner_count: int
    n_wall_one_q: int
    n_eligible_s: int
    n_eligible_q: int
    n_eligible_q_vertices: int
    n_eligible_q_vertices_on_physical_boundary: int
    edge_incidence_histogram: Histogram
    global_edge_incidence_histogram: Histogram
    n_components: int
    n_open_edges: int
    n_nonmanifold_edges: int
    n_valid_subsets: int
    n_predicted_operations: int
    n_approved_operations: int
    predicted_point_growth: int
    predicted_cell_growth: int
    decision: Literal["KILL", "REPORT_ONLY_NEXT_CARD"]
    next_card: str | None
    components: tuple[PatchLayerComponent, ...]


def _histogram(values: Sequence[int]) -> Histogram:
    return tuple(sorted((int(value), int(count)) for value, count in Counter(values).items()))


def reconstruct_native_hex_patch_provenance(
    points: np.ndarray,
    cell_faces: CellFaces,
    *,
    source_provenance: str = "defaultWall",
) -> dict[FaceKey, PatchProvenance]:
    """Reconstruct deterministic writer-equivalent labels for cached meshes.

    ``native_hex`` currently generates one source surface, so the source
    provenance is ``defaultWall``.  The writer may additionally split the
    physical boundary by feature dihedral; reproducing that split preserves
    the patch identity that an actual polyMesh boundary file would expose.
    """
    from core.generator.polymesh_writer import _segment_boundary_by_features

    records = _face_records(cell_faces)
    boundary = [(key, cyclic) for key, (cyclic, owners) in records.items() if len(owners) == 1]
    boundary_faces = [list(cyclic) for _key, cyclic in boundary]
    if not boundary_faces:
        return {}

    groups = _segment_boundary_by_features(
        boundary_faces,
        np.asarray(points, dtype=np.float64),
        0,
        dihedral_deg=30.0,
    )
    labels: dict[FaceKey, PatchProvenance] = {}
    for patch_name, indices in groups:
        for index in indices:
            labels[_face_key(boundary_faces[index])] = (
                str(patch_name),
                str(source_provenance),
            )
    return labels


def _components_for_faces(
    faces: Sequence[tuple[FaceKey, tuple[int, ...], int, int]],
) -> list[list[tuple[FaceKey, tuple[int, ...], int, int]]]:
    """Return deterministic shared-edge components for labelled Q faces."""
    if not faces:
        return []
    edge_faces: dict[tuple[int, int], list[int]] = defaultdict(list)
    for index, (_key, cyclic, _owner, _owner_count) in enumerate(faces):
        for edge in _face_edges(cyclic):
            edge_faces[edge].append(index)
    adjacency: list[set[int]] = [set() for _ in faces]
    for edge_face_indices in edge_faces.values():
        for left in edge_face_indices:
            adjacency[left].update(right for right in edge_face_indices if right != left)

    remaining = set(range(len(faces)))
    components: list[list[tuple[FaceKey, tuple[int, ...], int, int]]] = []
    while remaining:
        seed = min(remaining, key=lambda index: faces[index][0])
        remaining.remove(seed)
        queue: deque[int] = deque([seed])
        component_indices: list[int] = []
        while queue:
            current = queue.popleft()
            component_indices.append(current)
            for neighbor in sorted(adjacency[current], key=lambda index: faces[index][0]):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    queue.append(neighbor)
        components.append(
            [faces[index] for index in sorted(component_indices, key=lambda i: faces[i][0])]
        )
    return components


def _component_edge_stats(
    faces: Sequence[tuple[FaceKey, tuple[int, ...], int, int]],
) -> tuple[Histogram, int, int]:
    edge_counts: Counter[tuple[int, int]] = Counter()
    for _key, cyclic, _owner, _owner_count in faces:
        edge_counts.update(_face_edges(cyclic))
    values = list(edge_counts.values())
    return (
        _histogram(values),
        sum(value == 1 for value in values),
        sum(value > 2 for value in values),
    )


def analyze_patch_layer_subsets(
    shape_name: str,
    points: np.ndarray,
    cell_faces: CellFaces,
    *,
    boundary_patch_provenance: Mapping[FaceKey, PatchProvenance] | None = None,
    log_only: bool = True,
) -> PatchLayerDiagnosticReport:
    """Classify strict wall/interface subsets without performing an operation.

    The initial shrink population is the owner of every physical boundary
    face, narrowed to clean hex cells with exactly one physical boundary face.
    ``Q`` is measured against the complement of that initial population, so a
    cell is eligible only when it has exactly one such interface face.  This
    avoids silently changing the definition of ``Q`` while filtering out
    edge/corner cells.  The remaining faces are split by exact
    patch/provenance identity and then checked component-by-component for a
    closed all-quad manifold with no physical-boundary Q vertex.
    """
    pts = np.asarray(points, dtype=np.float64)
    cells = [[[int(vertex) for vertex in face] for face in cell] for cell in cell_faces]
    records = _face_records(cells)

    boundary = {
        key: (cyclic, owners[0]) for key, (cyclic, owners) in records.items() if len(owners) == 1
    }
    if boundary_patch_provenance is None:
        boundary_patch_provenance = reconstruct_native_hex_patch_provenance(pts, cells)

    boundary_by_cell: dict[int, list[tuple[FaceKey, tuple[int, ...]]]] = defaultdict(list)
    for key, (cyclic, owner) in boundary.items():
        boundary_by_cell[owner].append((key, cyclic))
    boundary_vertices = {vertex for cyclic, _owner in boundary.values() for vertex in cyclic}

    wall_cells = {
        owner
        for owner, faces in boundary_by_cell.items()
        if len(faces) == 1 and _is_clean_hex(cells[owner])
    }
    wall_exact_one_nonhex = sum(
        len(faces) == 1 and not _is_clean_hex(cells[owner])
        for owner, faces in boundary_by_cell.items()
    )
    core_cells = set(range(len(cells))) - wall_cells

    interface_records: list[tuple[FaceKey, tuple[int, ...], tuple[int, ...], int]] = []
    interface_by_wall: dict[int, list[int]] = defaultdict(list)
    for key, (cyclic, owners) in records.items():
        wall_owners = [owner for owner in owners if owner in wall_cells]
        core_owners = [owner for owner in owners if owner in core_cells]
        if not wall_owners or not core_owners:
            continue
        for wall_owner in sorted(set(wall_owners)):
            index = len(interface_records)
            interface_records.append((key, cyclic, owners, wall_owner))
            interface_by_wall[wall_owner].append(index)

    eligible_wall: set[int] = set()
    eligible_interface_indices: list[int] = []
    for owner in sorted(wall_cells):
        indices = interface_by_wall.get(owner, [])
        if len(indices) != 1:
            continue
        index = indices[0]
        _key, cyclic, owners, _wall_owner = interface_records[index]
        if len(cyclic) != 4 or len(owners) != 2:
            continue
        if set(cyclic) & boundary_vertices:
            continue
        eligible_wall.add(owner)
        eligible_interface_indices.append(index)

    eligible_q = [interface_records[index] for index in eligible_interface_indices]
    labels_by_wall: dict[int, PatchProvenance] = {}
    for owner in sorted(eligible_wall):
        boundary_key = boundary_by_cell[owner][0][0]
        labels_by_wall[owner] = boundary_patch_provenance.get(
            boundary_key,
            ("unlabelled", "unlabelled"),
        )

    grouped: dict[PatchProvenance, list[tuple[FaceKey, tuple[int, ...], int, int]]] = defaultdict(
        list
    )
    for key, cyclic, owner_tuple, wall_owner in eligible_q:
        grouped[labels_by_wall[wall_owner]].append((key, cyclic, wall_owner, len(owner_tuple)))

    components: list[PatchLayerComponent] = []
    component_index = 0
    component_edge_histogram: Counter[int] = Counter()
    component_open_edges = 0
    component_nonmanifold_edges = 0
    for patch_provenance in sorted(grouped):
        patch, provenance = patch_provenance
        for component_faces in _components_for_faces(grouped[patch_provenance]):
            component_index += 1
            owner_ids = {owner for _key, _cyclic, owner, _owner_count in component_faces}
            q_vertices = {
                vertex
                for _key, cyclic, _owner, _owner_count in component_faces
                for vertex in cyclic
            }
            edge_hist, open_edges, nonmanifold_edges = _component_edge_stats(component_faces)
            component_edge_histogram.update(dict(edge_hist))
            component_open_edges += open_edges
            component_nonmanifold_edges += nonmanifold_edges
            n_nonquad = sum(len(cyclic) != 4 for _key, cyclic, _owner, _count in component_faces)
            n_bad_owner = sum(count != 2 for _key, _cyclic, _owner, count in component_faces)
            q_boundary_vertices = len(q_vertices & boundary_vertices)
            reasons: list[str] = []
            if n_nonquad:
                reasons.append("nonquad_Q")
            if n_bad_owner:
                reasons.append("Q_owner_count_not_two")
            if open_edges:
                reasons.append("Q_open_edges")
            if nonmanifold_edges:
                reasons.append("Q_nonmanifold_edges")
            if q_boundary_vertices:
                reasons.append("Q_vertex_on_physical_boundary")
            if len(owner_ids) != len(component_faces):
                reasons.append("S_to_Q_not_one_to_one")
            valid = not reasons and bool(component_faces)
            components.append(
                PatchLayerComponent(
                    patch=str(patch),
                    provenance=str(provenance),
                    component_index=component_index,
                    n_s=len(owner_ids),
                    n_q=len(component_faces),
                    n_q_nonquad=n_nonquad,
                    n_q_bad_owner_count=n_bad_owner,
                    n_q_vertices=len(q_vertices),
                    n_q_vertices_on_physical_boundary=q_boundary_vertices,
                    edge_incidence_histogram=edge_hist,
                    n_open_edges=open_edges,
                    n_nonmanifold_edges=nonmanifold_edges,
                    predicted_operation="pillow",
                    predicted_new_points=len(q_vertices),
                    predicted_new_cells=len(component_faces),
                    operation_status="approved" if valid else "rejected",
                    rejection_reasons=tuple(reasons),
                )
            )

    edge_counts: Counter[tuple[int, int]] = Counter()
    for _key, cyclic, _owners, _wall_owner in eligible_q:
        edge_counts.update(_face_edges(cyclic))
    edge_values = list(edge_counts.values())
    global_edge_histogram = _histogram(edge_values)
    valid_count = sum(component.operation_status == "approved" for component in components)
    q_vertices = {vertex for _key, cyclic, _owners, _wall_owner in eligible_q for vertex in cyclic}
    report = PatchLayerDiagnosticReport(
        shape_name=str(shape_name),
        n_points=int(pts.shape[0]),
        n_cells=len(cells),
        n_physical_boundary_faces=len(boundary),
        n_physical_boundary_quads=sum(len(cyclic) == 4 for cyclic, _owner in boundary.values()),
        n_physical_boundary_nonquads=sum(len(cyclic) != 4 for cyclic, _owner in boundary.values()),
        n_wall_exact_one_boundary=len(wall_cells),
        n_wall_exact_one_boundary_nonhex=wall_exact_one_nonhex,
        n_interface_faces=len(interface_records),
        n_interface_quads=sum(
            len(cyclic) == 4 for _key, cyclic, _owners, _owner in interface_records
        ),
        n_interface_nonquads=sum(
            len(cyclic) != 4 for _key, cyclic, _owners, _owner in interface_records
        ),
        n_interface_bad_owner_count=sum(
            len(owners) != 2 for _key, _cyclic, owners, _owner in interface_records
        ),
        n_wall_one_q=sum(len(interface_by_wall.get(owner, [])) == 1 for owner in wall_cells),
        n_eligible_s=len(eligible_wall),
        n_eligible_q=len(eligible_q),
        n_eligible_q_vertices=len(q_vertices),
        n_eligible_q_vertices_on_physical_boundary=len(q_vertices & boundary_vertices),
        edge_incidence_histogram=tuple(sorted(component_edge_histogram.items())),
        global_edge_incidence_histogram=global_edge_histogram,
        n_components=len(components),
        n_open_edges=component_open_edges,
        n_nonmanifold_edges=component_nonmanifold_edges,
        n_valid_subsets=valid_count,
        n_predicted_operations=len(components),
        n_approved_operations=valid_count,
        predicted_point_growth=sum(component.predicted_new_points for component in components),
        predicted_cell_growth=sum(component.predicted_new_cells for component in components),
        decision="REPORT_ONLY_NEXT_CARD" if valid_count else "KILL",
        next_card="HEX-PATCH-LAYER-OPS1" if valid_count else None,
        components=tuple(components),
    )
    if log_only:
        from core.utils.logging import get_logger

        get_logger(__name__).info(
            "native_hex_patch_layer_diag1",
            shape=report.shape_name,
            eligible_s=report.n_eligible_s,
            eligible_q=report.n_eligible_q,
            components=report.n_components,
            valid_subsets=report.n_valid_subsets,
            decision=report.decision,
        )
    return report
