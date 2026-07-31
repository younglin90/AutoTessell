"""Fail-closed topology audit for an explicit OpenFOAM boundary surface.

The audit deliberately records self-intersection as unverified.  It validates
only the parsed polyMesh artifact and its combinatorial boundary topology; it
does not promote Gate 4 or infer source/patch authority.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from core.utils.polymesh_reader import (
    parse_foam_boundary,
    parse_foam_faces,
    parse_foam_labels_array,
    parse_foam_points_array,
)

_REQUIRED_FILES = ("points", "faces", "owner", "neighbour", "boundary")


@dataclass(frozen=True)
class PolyMeshArtifactIdentity:
    """Exact identity of the mandatory non-symlink polyMesh files."""

    poly_mesh_path: str
    file_sha256: tuple[tuple[str, str], ...]
    sha256: str


@dataclass(frozen=True)
class Gate4SurfaceTopologyAudit:
    """Combinatorial output-surface report; never a Gate-4 verdict."""

    status: str
    artifact: PolyMeshArtifactIdentity | None
    topology_valid: bool
    self_intersection_status: str
    boundary_face_count: int | None = None
    component_count: int | None = None
    boundary_loop_count: int | None = None
    euler_characteristic: int | None = None
    genus: int | None = None
    open_edge_count: int | None = None
    nonmanifold_edge_count: int | None = None
    nonmanifold_vertex_count: int | None = None
    duplicate_face_count: int | None = None
    orientation_mismatch_count: int | None = None
    malformed_reason: str | None = None


def _artifact_identity(case_dir: Path) -> PolyMeshArtifactIdentity | None:
    poly_mesh = case_dir / "constant" / "polyMesh"
    if not poly_mesh.is_dir() or poly_mesh.is_symlink():
        return None

    file_hashes: list[tuple[str, str]] = []
    for name in _REQUIRED_FILES:
        path = poly_mesh / name
        if not path.is_file() or path.is_symlink():
            return None
        file_hashes.append((name, hashlib.sha256(path.read_bytes()).hexdigest()))
    aggregate = hashlib.sha256(
        json.dumps(file_hashes, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return PolyMeshArtifactIdentity(
        poly_mesh_path=str(poly_mesh.resolve()),
        file_sha256=tuple(file_hashes),
        sha256=aggregate,
    )


def _canonical_cycle(face: list[int]) -> tuple[int, ...]:
    sequence = tuple(face)
    candidates = [sequence[index:] + sequence[:index] for index in range(len(sequence))]
    reversed_sequence = tuple(reversed(sequence))
    candidates.extend(
        reversed_sequence[index:] + reversed_sequence[:index]
        for index in range(len(reversed_sequence))
    )
    return min(candidates)


def _malformed(
    artifact: PolyMeshArtifactIdentity,
    reason: str,
) -> Gate4SurfaceTopologyAudit:
    return Gate4SurfaceTopologyAudit(
        status="unverified_output_artifact_malformed",
        artifact=artifact,
        topology_valid=False,
        self_intersection_status="unverified_not_checked",
        malformed_reason=reason,
    )


def _boundary_face_indices(
    *,
    faces: list[list[int]],
    owner: np.ndarray,
    neighbour: np.ndarray,
    patches: list[dict[str, object]],
) -> tuple[list[int], str | None]:
    if len(owner) != len(faces):
        return [], "owner_count_mismatch"
    if len(neighbour) > len(faces) or np.any(owner < 0) or np.any(neighbour < 0):
        return [], "invalid_owner_or_neighbour"
    expected_start = int(len(neighbour))
    indices: list[int] = []
    names: set[str] = set()
    for patch in patches:
        name = patch.get("name")
        start = patch.get("startFace")
        count = patch.get("nFaces")
        if (
            not isinstance(name, str)
            or not name
            or name in names
            or isinstance(start, bool)
            or not isinstance(start, int)
            or isinstance(count, bool)
            or not isinstance(count, int)
            or count < 0
            or start != expected_start
            or start + count > len(faces)
        ):
            return [], "invalid_patch_ranges"
        names.add(name)
        indices.extend(range(start, start + count))
        expected_start += count
    if expected_start != len(faces):
        return [], "patches_do_not_partition_boundary_faces"
    return indices, None


def _vertex_nonmanifold_count(faces: list[list[int]]) -> int:
    link_edges: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for face in faces:
        for index, vertex in enumerate(face):
            link_edges[vertex].append((face[index - 1], face[(index + 1) % len(face)]))

    invalid = 0
    for links in link_edges.values():
        adjacency: dict[int, set[int]] = defaultdict(set)
        for first, second in links:
            adjacency[first].add(second)
            adjacency[second].add(first)
        if not adjacency:
            invalid += 1
            continue
        pending = [next(iter(adjacency))]
        visited: set[int] = set()
        while pending:
            current = pending.pop()
            if current in visited:
                continue
            visited.add(current)
            pending.extend(adjacency[current] - visited)
        degrees = [len(neighbours) for neighbours in adjacency.values()]
        boundary_link = degrees.count(1) == 2 and all(degree in (1, 2) for degree in degrees)
        interior_link = all(degree == 2 for degree in degrees)
        if len(visited) != len(adjacency) or not (boundary_link or interior_link):
            invalid += 1
    return invalid


def _component_count(face_count: int, edge_faces: dict[tuple[int, int], list[int]]) -> int:
    adjacency: list[set[int]] = [set() for _ in range(face_count)]
    for incident in edge_faces.values():
        if len(incident) == 2:
            first, second = incident
            adjacency[first].add(second)
            adjacency[second].add(first)
    components = 0
    visited: set[int] = set()
    for seed in range(face_count):
        if seed in visited:
            continue
        components += 1
        pending: deque[int] = deque([seed])
        while pending:
            current = pending.popleft()
            if current in visited:
                continue
            visited.add(current)
            pending.extend(adjacency[current] - visited)
    return components


def _boundary_loop_count(open_edges: list[tuple[int, int]]) -> int | None:
    if not open_edges:
        return 0
    adjacency: dict[int, set[int]] = defaultdict(set)
    for first, second in open_edges:
        adjacency[first].add(second)
        adjacency[second].add(first)
    if any(len(neighbours) != 2 for neighbours in adjacency.values()):
        return None
    loops = 0
    visited: set[int] = set()
    for seed in adjacency:
        if seed in visited:
            continue
        loops += 1
        pending = [seed]
        while pending:
            current = pending.pop()
            if current in visited:
                continue
            visited.add(current)
            pending.extend(adjacency[current] - visited)
    return loops


def audit_polymesh_surface(case_dir: Path) -> Gate4SurfaceTopologyAudit:
    """Audit one explicit polyMesh boundary surface without a Gate verdict."""
    artifact = _artifact_identity(case_dir)
    if artifact is None:
        return Gate4SurfaceTopologyAudit(
            status="unverified_output_artifact_missing_or_unsafe",
            artifact=None,
            topology_valid=False,
            self_intersection_status="unverified_not_checked",
        )

    poly_mesh = Path(artifact.poly_mesh_path)
    try:
        points = parse_foam_points_array(poly_mesh / "points")
        faces = parse_foam_faces(poly_mesh / "faces")
        owner = parse_foam_labels_array(poly_mesh / "owner")
        neighbour = parse_foam_labels_array(poly_mesh / "neighbour")
        patches = parse_foam_boundary(poly_mesh / "boundary")
    except Exception as exc:  # noqa: BLE001
        return _malformed(artifact, f"parse_error:{type(exc).__name__}")

    if (
        points.ndim != 2
        or points.shape[1:] != (3,)
        or not len(points)
        or not np.isfinite(points).all()
    ):
        return _malformed(artifact, "invalid_points")
    if not faces:
        return _malformed(artifact, "no_faces")
    for face in faces:
        if (
            len(face) < 3
            or len(set(face)) != len(face)
            or any(index < 0 or index >= len(points) for index in face)
        ):
            return _malformed(artifact, "invalid_face_vertices")

    boundary_indices, reason = _boundary_face_indices(
        faces=faces,
        owner=owner,
        neighbour=neighbour,
        patches=patches,
    )
    if reason is not None:
        return _malformed(artifact, reason)
    boundary_faces = [faces[index] for index in boundary_indices]
    if not boundary_faces:
        return _malformed(artifact, "no_boundary_faces")

    face_keys = [_canonical_cycle(face) for face in boundary_faces]
    duplicate_faces = sum(count - 1 for count in Counter(face_keys).values() if count > 1)
    edge_faces: dict[tuple[int, int], list[int]] = defaultdict(list)
    edge_directions: dict[tuple[int, int], list[bool]] = defaultdict(list)
    for face_index, face in enumerate(boundary_faces):
        for index, first in enumerate(face):
            second = face[(index + 1) % len(face)]
            key = (min(first, second), max(first, second))
            edge_faces[key].append(face_index)
            edge_directions[key].append((first, second) == key)

    open_edges = [edge for edge, incident in edge_faces.items() if len(incident) == 1]
    nonmanifold_edges = [edge for edge, incident in edge_faces.items() if len(incident) > 2]
    orientation_mismatches = sum(
        1
        for edge, directions in edge_directions.items()
        if len(edge_faces[edge]) == 2 and directions[0] == directions[1]
    )
    nonmanifold_vertices = _vertex_nonmanifold_count(boundary_faces)
    loop_count = _boundary_loop_count(open_edges)
    component_count = _component_count(len(boundary_faces), edge_faces)
    n_vertices = len({vertex for face in boundary_faces for vertex in face})
    euler = n_vertices - len(edge_faces) + len(boundary_faces)
    valid = (
        duplicate_faces == 0
        and not nonmanifold_edges
        and nonmanifold_vertices == 0
        and orientation_mismatches == 0
        and loop_count is not None
    )
    genus: int | None = None
    if valid:
        numerator = 2 * component_count - int(loop_count) - euler
        if numerator >= 0 and numerator % 2 == 0:
            genus = numerator // 2
        else:
            valid = False

    return Gate4SurfaceTopologyAudit(
        status=(
            "unverified_self_intersection_not_checked"
            if valid
            else "unverified_surface_topology_invalid"
        ),
        artifact=artifact,
        topology_valid=valid,
        self_intersection_status="unverified_not_checked",
        boundary_face_count=len(boundary_faces),
        component_count=component_count,
        boundary_loop_count=loop_count,
        euler_characteristic=euler,
        genus=genus,
        open_edge_count=len(open_edges),
        nonmanifold_edge_count=len(nonmanifold_edges),
        nonmanifold_vertex_count=nonmanifold_vertices,
        duplicate_face_count=duplicate_faces,
        orientation_mismatch_count=orientation_mismatches,
    )
