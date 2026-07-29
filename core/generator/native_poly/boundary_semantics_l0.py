"""Read-only L0 audit for entity-classified native-poly boundary caps.

The classified dual route must preserve more than a patch-name count: every
exported boundary cap must lie on exactly one primal boundary triangle, carry
that triangle's entity label, have one valid owner, and collectively cover the
source triangle area.  This audit consumes already-written polyMesh arrays and
never changes dual geometry or connectivity.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from core.generator.native_poly.dual import _normalise_entity_label


@dataclass(frozen=True)
class PolyDualBoundarySemanticsResult:
    """Exact entity/cap semantic census; all failures are report-only."""

    accepted: bool
    reason: str
    boundary_face_count: int
    mapped_faces: int
    unmapped_face_indices: tuple[int, ...]
    ambiguous_face_indices: tuple[int, ...]
    label_mismatch_face_indices: tuple[int, ...]
    invalid_owner_face_indices: tuple[int, ...]
    zero_area_face_indices: tuple[int, ...]
    max_relative_source_area_error: float | None
    production_mesh_changed: bool


def _primal_boundary_faces(tetrahedra: np.ndarray) -> tuple[tuple[int, int, int], ...]:
    owners: Counter[tuple[int, int, int]] = Counter()
    for tet in tetrahedra:
        if len(set(map(int, tet))) != 4:
            raise ValueError("primal tetrahedra must have four distinct vertices")
        for omitted in range(4):
            values = sorted(int(tet[index]) for index in range(4) if index != omitted)
            face: tuple[int, int, int] = values[0], values[1], values[2]
            owners[face] += 1
    return tuple(sorted(face for face, count in owners.items() if count == 1))


def _face_area(points: np.ndarray) -> float:
    if len(points) < 3:
        return 0.0
    origin = points[0]
    return float(sum(
        np.linalg.norm(np.cross(points[index] - origin, points[index + 1] - origin)) * 0.5
        for index in range(1, len(points) - 1)
    ))


def _lies_in_source_triangle(
    candidate: np.ndarray,
    triangle: np.ndarray,
    tolerance: float,
) -> bool:
    origin, second, third = triangle
    first_vector = second - origin
    second_vector = third - origin
    normal = np.cross(first_vector, second_vector)
    normal_norm = float(np.linalg.norm(normal))
    if normal_norm <= tolerance:
        return False
    gram = np.array(
        [[np.dot(first_vector, first_vector), np.dot(first_vector, second_vector)],
         [np.dot(first_vector, second_vector), np.dot(second_vector, second_vector)]],
        dtype=np.float64,
    )
    if abs(float(np.linalg.det(gram))) <= tolerance:
        return False
    for point in candidate:
        if abs(float(np.dot(normal, point - origin))) > tolerance * normal_norm:
            return False
        coefficients = np.linalg.solve(gram, np.array(
            [np.dot(point - origin, first_vector), np.dot(point - origin, second_vector)],
            dtype=np.float64,
        ))
        if coefficients[0] < -tolerance or coefficients[1] < -tolerance:
            return False
        if coefficients[0] + coefficients[1] > 1.0 + tolerance:
            return False
    return True


def _boundary_labels(
    n_faces: int,
    n_internal: int,
    entries: Sequence[Mapping[str, Any]],
) -> tuple[tuple[str, str] | None, ...] | None:
    labels: list[tuple[str, str] | None] = [None] * n_faces
    for entry in entries:
        try:
            start = int(entry["startFace"])
            count = int(entry["nFaces"])
        except (KeyError, TypeError, ValueError):
            return None
        label = _normalise_entity_label(entry)
        if start < n_internal or count < 0 or start + count > n_faces:
            return None
        for index in range(start, start + count):
            if labels[index] is not None:
                return None
            labels[index] = label
    return tuple(labels)


def audit_classified_dual_boundary_l0(
    primal_points: np.ndarray,
    primal_tetrahedra: np.ndarray,
    dual_points: np.ndarray,
    dual_faces: Sequence[Sequence[int]],
    owner: Sequence[int],
    neighbour: Sequence[int],
    boundary_entries: Sequence[Mapping[str, Any]],
    source_entities: Mapping[tuple[int, int, int], Any],
    *,
    tolerance: float = 1e-8,
) -> PolyDualBoundarySemanticsResult:
    """Audit geometry, source entity, owner, and area of every boundary cap."""
    primal = np.asarray(primal_points, dtype=np.float64)
    tets = np.asarray(primal_tetrahedra, dtype=np.int64)
    dual = np.asarray(dual_points, dtype=np.float64)
    faces = tuple(tuple(int(vertex) for vertex in face) for face in dual_faces)
    if (
        primal.ndim != 2 or primal.shape[1] != 3 or tets.ndim != 2 or tets.shape[1] != 4
        or dual.ndim != 2 or dual.shape[1] != 3 or len(faces) != len(owner)
        or len(neighbour) > len(faces)
    ):
        return PolyDualBoundarySemanticsResult(
            False, "invalid_mesh_arrays", 0, 0, (), (), (), (), (), None, False
        )
    try:
        source_faces = _primal_boundary_faces(tets)
    except ValueError:
        return PolyDualBoundarySemanticsResult(
            False, "invalid_primal_tetrahedra", 0, 0, (), (), (), (), (), None, False
        )
    if any(vertex < 0 or vertex >= len(primal) for face in source_faces for vertex in face):
        return PolyDualBoundarySemanticsResult(
            False, "primal_index_out_of_range", 0, 0, (), (), (), (), (), None, False
        )
    n_internal = len(neighbour)
    labels = _boundary_labels(len(faces), n_internal, boundary_entries)
    if labels is None or any(label is None for label in labels[n_internal:]):
        return PolyDualBoundarySemanticsResult(
            False, "boundary_entry_partition_invalid", len(faces) - n_internal, 0, (), (), (), (), (), None, False
        )
    source_triangles = {face: primal[np.asarray(face, dtype=np.int64)] for face in source_faces}
    expected_labels = {
        face: _normalise_entity_label(source_entities.get(face)) for face in source_faces
    }
    cap_area: defaultdict[tuple[int, int, int], float] = defaultdict(float)
    unmapped: list[int] = []
    ambiguous: list[int] = []
    mismatch: list[int] = []
    invalid_owner: list[int] = []
    zero_area: list[int] = []
    mapped = 0
    for face_index in range(n_internal, len(faces)):
        face = faces[face_index]
        if len(face) < 3 or len(set(face)) != len(face) or any(vertex < 0 or vertex >= len(dual) for vertex in face):
            unmapped.append(face_index)
            continue
        if int(owner[face_index]) < 0:
            invalid_owner.append(face_index)
        geometry = dual[np.asarray(face, dtype=np.int64)]
        area = _face_area(geometry)
        if area <= tolerance:
            zero_area.append(face_index)
            continue
        matches = [
            source_face for source_face, triangle in source_triangles.items()
            if _lies_in_source_triangle(geometry, triangle, tolerance)
        ]
        if not matches:
            unmapped.append(face_index)
            continue
        if len(matches) != 1:
            ambiguous.append(face_index)
            continue
        source_face = matches[0]
        cap_area[source_face] += area
        if labels[face_index] != expected_labels[source_face]:
            mismatch.append(face_index)
            continue
        mapped += 1
    relative_errors = [
        abs(cap_area[face] - _face_area(triangle)) / max(_face_area(triangle), tolerance)
        for face, triangle in source_triangles.items()
    ]
    max_error = max(relative_errors, default=None)
    accepted = not (unmapped or ambiguous or mismatch or invalid_owner or zero_area) and bool(max_error is not None and max_error <= tolerance)
    if not accepted:
        reason = "boundary_cap_semantics_failed"
    else:
        reason = "accepted"
    return PolyDualBoundarySemanticsResult(
        accepted,
        reason,
        len(faces) - n_internal,
        mapped,
        tuple(unmapped),
        tuple(ambiguous),
        tuple(mismatch),
        tuple(invalid_owner),
        tuple(zero_area),
        max_error,
        False,
    )
