"""Measured source/output authority certificate for surface products.

The older source-certificate modules validate declared hashes only.  This
module binds those hashes to actual source bytes and explicit geometry arrays.
It is deliberately product-neutral: it does not route a mesher or silently
infer CAD features, patches, or physical groups.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict, deque
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

_CONTRACT = "autotessell/actual-source-output-certificate/v1"


@dataclass(frozen=True, slots=True)
class ActualSourceOutputCertificate:
    """Evidence that one explicit output surface is bound to one source."""

    status: str
    source_authoritative: bool
    source_sha256: str | None
    source_shape_sha256: str | None
    output_shape_sha256: str | None
    feature_sha256: str | None
    patch_sha256: str | None
    physical_group_sha256: str | None
    provenance_sha256: str | None
    source_face_count: int
    output_face_count: int
    source_vertices_preserved: bool
    source_faces_preserved: bool
    feature_preserved: bool
    patch_preserved: bool
    physical_groups_preserved: bool
    component_bijection: bool
    provenance_complete: bool
    authoritative: bool
    rejection_reason: str | None = None
    contract: str = _CONTRACT

    def as_dict(self) -> dict[str, object]:
        """Return JSON-safe evidence for the release matrix."""
        return {
            "status": self.status,
            "authoritative": self.authoritative,
            "source_sha256": self.source_sha256,
            "source_shape_sha256": self.source_shape_sha256,
            "output_shape_sha256": self.output_shape_sha256,
            "feature_sha256": self.feature_sha256,
            "patch_sha256": self.patch_sha256,
            "physical_group_sha256": self.physical_group_sha256,
            "provenance_sha256": self.provenance_sha256,
            "source_face_count": self.source_face_count,
            "output_face_count": self.output_face_count,
            "source_vertices_preserved": self.source_vertices_preserved,
            "source_faces_preserved": self.source_faces_preserved,
            "feature_preserved": self.feature_preserved,
            "patch_preserved": self.patch_preserved,
            "physical_groups_preserved": self.physical_groups_preserved,
            "component_bijection": self.component_bijection,
            "provenance_complete": self.provenance_complete,
            "rejection_reason": self.rejection_reason,
            "contract": self.contract,
        }


def _empty(reason: str, *, source_face_count: int = 0) -> ActualSourceOutputCertificate:
    return ActualSourceOutputCertificate(
        status="reject_actual_source_output_certificate",
        source_authoritative=False,
        source_sha256=None,
        source_shape_sha256=None,
        output_shape_sha256=None,
        feature_sha256=None,
        patch_sha256=None,
        physical_group_sha256=None,
        provenance_sha256=None,
        source_face_count=source_face_count,
        output_face_count=0,
        source_vertices_preserved=False,
        source_faces_preserved=False,
        feature_preserved=False,
        patch_preserved=False,
        physical_groups_preserved=False,
        component_bijection=False,
        provenance_complete=False,
        authoritative=False,
        rejection_reason=reason,
    )


def _sha256_json(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def _array_sha256(array: np.ndarray) -> str:
    contiguous = np.ascontiguousarray(array)
    descriptor = {
        "dtype": contiguous.dtype.str,
        "shape": tuple(int(value) for value in contiguous.shape),
    }
    digest = hashlib.sha256()
    digest.update(json.dumps(descriptor, separators=(",", ":")).encode("utf-8"))
    digest.update(contiguous.tobytes(order="C"))
    return digest.hexdigest()


def _surface_arrays(
    values: object, *, integer: bool
) -> tuple[np.ndarray, str | None]:
    try:
        array = np.asarray(values)
    except (TypeError, ValueError):
        return np.asarray(()), "array_conversion_failed"
    expected = (3,) if integer else (3,)
    if array.ndim != 2 or tuple(array.shape[1:]) != expected or not len(array):
        return array, "array_shape_invalid"
    if integer:
        if not np.issubdtype(array.dtype, np.integer):
            return array, "face_dtype_invalid"
    elif not np.issubdtype(array.dtype, np.floating) or not np.isfinite(array).all():
        return array, "point_values_invalid"
    return np.asarray(array, dtype=np.int64 if integer else np.float64), None


def _faces_valid(faces: np.ndarray, point_count: int) -> bool:
    return bool(
        np.issubdtype(faces.dtype, np.integer)
        and np.all(faces >= 0)
        and np.all(faces < point_count)
        and all(len(set(int(value) for value in face)) == 3 for face in faces)
    )


def _labels(
    values: Sequence[str] | None, count: int
) -> tuple[str, ...] | None:
    if values is None or len(values) != count:
        return None
    normalized = tuple(str(value).strip() for value in values)
    if not all(normalized):
        return None
    return normalized


def _vertex_correspondence(
    source: np.ndarray, output: np.ndarray
) -> tuple[tuple[int, ...], bool]:
    if len(source) != len(output):
        return (), False
    source_keys = [tuple(float(value) for value in row) for row in source]
    output_keys = [tuple(float(value) for value in row) for row in output]
    if len(set(source_keys)) != len(source_keys) or len(set(output_keys)) != len(output_keys):
        return (), False
    source_indices = {key: index for index, key in enumerate(source_keys)}
    try:
        correspondence = tuple(source_indices[key] for key in output_keys)
    except KeyError:
        return (), False
    return correspondence, len(set(correspondence)) == len(source)


def _edge_components(faces: np.ndarray) -> tuple[int, ...]:
    edge_faces: dict[tuple[int, int], list[int]] = defaultdict(list)
    for face_index, face in enumerate(faces):
        for first, second in ((0, 1), (1, 2), (2, 0)):
            edge_key = (min(int(face[first]), int(face[second])), max(int(face[first]), int(face[second])))  # noqa: E501
            edge_faces[edge_key].append(face_index)
    adjacency: list[set[int]] = [set() for _ in range(len(faces))]
    for incident in edge_faces.values():
        for left in incident:
            adjacency[left].update(right for right in incident if right != left)
    labels = [-1] * len(faces)
    component = 0
    for seed in range(len(faces)):
        if labels[seed] >= 0:
            continue
        pending: deque[int] = deque([seed])
        while pending:
            current = pending.popleft()
            if labels[current] >= 0:
                continue
            labels[current] = component
            pending.extend(neighbor for neighbor in adjacency[current] if labels[neighbor] < 0)
        component += 1
    return tuple(labels)


def certify_exact_surface_output(
    source_path: Path,
    source_points: object,
    source_faces: object,
    output_points: object,
    output_faces: object,
    *,
    source_feature_ids: Sequence[str] | None,
    source_patch_ids: Sequence[str] | None,
    source_physical_groups: Sequence[str] | None,
    output_feature_ids: Sequence[str] | None,
    output_patch_ids: Sequence[str] | None,
    output_physical_groups: Sequence[str] | None,
    output_to_source_faces: Sequence[int] | None,
) -> ActualSourceOutputCertificate:
    """Measure exact source/output and explicit authority bindings.

    Geometry correspondence is accepted only for identical vertex coordinates
    and explicitly supplied face mapping.  Feature, patch, and physical-group
    values are never inferred from geometry; omitted or malformed declarations
    reject the certificate.
    """
    source_points_array, source_point_error = _surface_arrays(source_points, integer=False)
    output_points_array, output_point_error = _surface_arrays(output_points, integer=False)
    source_faces_array, source_face_error = _surface_arrays(source_faces, integer=True)
    output_faces_array, output_face_error = _surface_arrays(output_faces, integer=True)
    if any((source_point_error, output_point_error, source_face_error, output_face_error)):
        return _empty(
            "surface_arrays_invalid",
            source_face_count=int(len(source_faces_array)),
        )
    if not _faces_valid(source_faces_array, len(source_points_array)) or not _faces_valid(
        output_faces_array, len(output_points_array)
    ):
        return _empty("surface_face_incidence_invalid", source_face_count=len(source_faces_array))
    source_file = source_path.resolve()
    if source_file.is_symlink() or not source_file.is_file():
        return _empty("source_file_not_authoritative", source_face_count=len(source_faces_array))
    source_sha256 = hashlib.sha256(source_file.read_bytes()).hexdigest()
    source_features = _labels(source_feature_ids, len(source_faces_array))
    source_patches = _labels(source_patch_ids, len(source_faces_array))
    source_groups = _labels(source_physical_groups, len(source_faces_array))
    output_features = _labels(output_feature_ids, len(output_faces_array))
    output_patches = _labels(output_patch_ids, len(output_faces_array))
    output_groups = _labels(output_physical_groups, len(output_faces_array))
    if any(
        value is None
        for value in (
            source_features,
            source_patches,
            source_groups,
            output_features,
            output_patches,
            output_groups,
        )
    ):
        return _empty("explicit_feature_patch_physical_group_declarations_required", source_face_count=len(source_faces_array))  # noqa: E501
    assert source_features is not None
    assert source_patches is not None
    assert source_groups is not None
    assert output_features is not None
    assert output_patches is not None
    assert output_groups is not None
    vertex_map, vertices_preserved = _vertex_correspondence(
        source_points_array, output_points_array
    )
    if output_to_source_faces is None or len(output_to_source_faces) != len(output_faces_array):
        return _empty("explicit_output_to_source_face_mapping_required", source_face_count=len(source_faces_array))  # noqa: E501
    try:
        face_map = tuple(int(value) for value in output_to_source_faces)
    except (TypeError, ValueError):
        return _empty("output_to_source_face_mapping_invalid", source_face_count=len(source_faces_array))  # noqa: E501
    if len(set(face_map)) != len(source_faces_array) or set(face_map) != set(range(len(source_faces_array))):  # noqa: E501
        return _empty("output_to_source_face_mapping_not_bijective", source_face_count=len(source_faces_array))  # noqa: E501
    mapped_output_faces = np.asarray(
        [[vertex_map[int(vertex)] if vertex_map else -1 for vertex in face] for face in output_faces_array],  # noqa: E501
        dtype=np.int64,
    )
    source_faces_by_key = {
        tuple(sorted(int(vertex) for vertex in face)): index
        for index, face in enumerate(source_faces_array)
    }
    faces_preserved = all(
        source_faces_by_key.get(tuple(sorted(int(vertex) for vertex in face))) == face_map[index]
        for index, face in enumerate(mapped_output_faces)
    )
    feature_preserved = all(output_features[index] == source_features[face_map[index]] for index in range(len(face_map)))  # noqa: E501
    patch_preserved = all(output_patches[index] == source_patches[face_map[index]] for index in range(len(face_map)))  # noqa: E501
    groups_preserved = all(output_groups[index] == source_groups[face_map[index]] for index in range(len(face_map)))  # noqa: E501
    source_components = _edge_components(source_faces_array)
    output_components = _edge_components(mapped_output_faces)
    component_bijection = len(set(source_components)) == len(set(output_components)) and all(
        source_components[face_map[index]] == output_components[index]
        for index in range(len(face_map))
    )
    source_shape_sha256 = _array_sha256(
        np.concatenate((source_points_array, source_faces_array.astype(np.float64)), axis=0)
    )
    output_shape_sha256 = _array_sha256(
        np.concatenate((output_points_array, output_faces_array.astype(np.float64)), axis=0)
    )
    feature_sha256 = _sha256_json({"source": source_features, "output": output_features})
    patch_sha256 = _sha256_json({"source": source_patches, "output": output_patches})
    physical_group_sha256 = _sha256_json({"source": source_groups, "output": output_groups})
    provenance_sha256 = _sha256_json(
        {"output_to_source_faces": face_map, "output_to_source_vertices": vertex_map}
    )
    authoritative = bool(
        vertices_preserved
        and faces_preserved
        and feature_preserved
        and patch_preserved
        and groups_preserved
        and component_bijection
    )
    return ActualSourceOutputCertificate(
        status="measured_authoritative_source_output" if authoritative else "reject_source_output_binding_mismatch",  # noqa: E501
        source_authoritative=True,
        source_sha256=source_sha256,
        source_shape_sha256=source_shape_sha256,
        output_shape_sha256=output_shape_sha256,
        feature_sha256=feature_sha256,
        patch_sha256=patch_sha256,
        physical_group_sha256=physical_group_sha256,
        provenance_sha256=provenance_sha256,
        source_face_count=len(source_faces_array),
        output_face_count=len(output_faces_array),
        source_vertices_preserved=vertices_preserved,
        source_faces_preserved=faces_preserved,
        feature_preserved=feature_preserved,
        patch_preserved=patch_preserved,
        physical_groups_preserved=groups_preserved,
        component_bijection=component_bijection,
        provenance_complete=True,
        authoritative=authoritative,
        rejection_reason=None if authoritative else "source_output_binding_mismatch",
    )


__all__ = ["ActualSourceOutputCertificate", "certify_exact_surface_output"]
