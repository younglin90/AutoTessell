"""Measured source/output authority certificate for volume products.

The certificate binds a source file and canonical surface arrays to a written
volume output.  Preservation flags must come from an engine-side measurement;
they are never inferred from hashes or filled with defaults.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np

_CONTRACT = "autotessell/volume-source-output-certificate/v1"


@dataclass(frozen=True, slots=True)
class VolumeSourceOutputCertificate:
    status: str
    source_sha256: str | None
    source_shape_sha256: str | None
    output_shape_sha256: str | None
    feature_sha256: str | None
    patch_sha256: str | None
    physical_group_sha256: str | None
    provenance_sha256: str | None
    source_vertices_preserved: bool
    source_faces_preserved: bool
    feature_preserved: bool
    patch_preserved: bool
    physical_groups_preserved: bool
    component_bijection: bool
    provenance_complete: bool
    authoritative: bool
    source_vertex_count: int
    source_face_count: int
    output_point_count: int
    output_cell_count: int
    rejection_reason: str | None = None
    contract: str = _CONTRACT

    def as_dict(self) -> dict[str, object]:
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
            "source_vertices_preserved": self.source_vertices_preserved,
            "source_faces_preserved": self.source_faces_preserved,
            "feature_preserved": self.feature_preserved,
            "patch_preserved": self.patch_preserved,
            "physical_groups_preserved": self.physical_groups_preserved,
            "component_bijection": self.component_bijection,
            "provenance_complete": self.provenance_complete,
            "source_vertex_count": self.source_vertex_count,
            "source_face_count": self.source_face_count,
            "output_point_count": self.output_point_count,
            "output_cell_count": self.output_cell_count,
            "rejection_reason": self.rejection_reason,
            "contract": self.contract,
        }


def _hash_bytes(*parts: bytes) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part)
    return digest.hexdigest()


def _array_hash(values: np.ndarray) -> str:
    array = np.ascontiguousarray(values)
    return _hash_bytes(
        json.dumps({"dtype": array.dtype.str, "shape": tuple(array.shape)}, sort_keys=True).encode("ascii"),
        array.tobytes(order="C"),
    )


def _payload_hash(values: Sequence[object]) -> str:
    return hashlib.sha256(
        json.dumps(list(values), ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _empty(reason: str, *, source_vertex_count: int = 0, source_face_count: int = 0) -> VolumeSourceOutputCertificate:
    return VolumeSourceOutputCertificate(
        status="reject_volume_source_output_certificate",
        source_sha256=None,
        source_shape_sha256=None,
        output_shape_sha256=None,
        feature_sha256=None,
        patch_sha256=None,
        physical_group_sha256=None,
        provenance_sha256=None,
        source_vertices_preserved=False,
        source_faces_preserved=False,
        feature_preserved=False,
        patch_preserved=False,
        physical_groups_preserved=False,
        component_bijection=False,
        provenance_complete=False,
        authoritative=False,
        source_vertex_count=source_vertex_count,
        source_face_count=source_face_count,
        output_point_count=0,
        output_cell_count=0,
        rejection_reason=reason,
    )


def _surface_arrays(vertices: object, faces: object) -> tuple[np.ndarray, np.ndarray, str | None]:
    try:
        points = np.asarray(vertices, dtype=np.float64)
        surface = np.asarray(faces, dtype=np.int64)
    except (TypeError, ValueError):
        return np.asarray(()), np.asarray(()), "source_arrays_invalid"
    if points.ndim != 2 or points.shape[1] != 3 or not len(points) or not np.isfinite(points).all():
        return points, surface, "source_vertices_invalid"
    if surface.ndim != 2 or surface.shape[1] != 3 or not len(surface):
        return points, surface, "source_faces_invalid"
    if np.any(surface < 0) or np.any(surface >= len(points)):
        return points, surface, "source_face_incidence_invalid"
    if any(len(set(int(value) for value in face)) != 3 for face in surface):
        return points, surface, "source_faces_degenerate"
    return points, surface, None


def _output_arrays(points: object, cells: object) -> tuple[np.ndarray, np.ndarray, str | None]:
    try:
        output_points = np.asarray(points, dtype=np.float64)
        output_cells = np.asarray(cells, dtype=np.int64)
    except (TypeError, ValueError):
        return np.asarray(()), np.asarray(()), "output_arrays_invalid"
    if output_points.ndim != 2 or output_points.shape[1] != 3 or not len(output_points) or not np.isfinite(output_points).all():
        return output_points, output_cells, "output_points_invalid"
    if output_cells.ndim != 2 or output_cells.shape[1] < 4 or not len(output_cells):
        return output_points, output_cells, "output_cells_invalid"
    if np.any(output_cells < 0) or np.any(output_cells >= len(output_points)):
        return output_points, output_cells, "output_cell_incidence_invalid"
    return output_points, output_cells, None


def certify_volume_source_output(
    source_path: Path,
    source_vertices: object,
    source_faces: object,
    output_points: object,
    output_cells: object,
    *,
    source_feature_ids: Sequence[object] | None,
    source_patch_ids: Sequence[object] | None,
    source_physical_groups: Sequence[str] | None,
    provenance: object,
    source_vertices_preserved: bool,
    source_faces_preserved: bool,
    feature_preserved: bool,
    patch_preserved: bool,
    physical_groups_preserved: bool,
    component_bijection: bool,
    provenance_complete: bool,
) -> VolumeSourceOutputCertificate:
    source_points, surface, source_error = _surface_arrays(source_vertices, source_faces)
    volume_points, cells, output_error = _output_arrays(output_points, output_cells)
    source_file = Path(source_path).resolve()
    if source_error or output_error:
        return _empty(
            source_error or output_error or "array_validation_failed",
            source_vertex_count=len(source_points),
            source_face_count=len(surface),
        )
    if source_file.is_symlink() or not source_file.is_file():
        return _empty("source_file_not_authoritative", source_vertex_count=len(source_points), source_face_count=len(surface))
    labels = (source_feature_ids, source_patch_ids, source_physical_groups)
    if any(value is None or len(value) != len(surface) for value in labels):
        return _empty("explicit_feature_patch_physical_group_declarations_required", source_vertex_count=len(source_points), source_face_count=len(surface))
    flags = (
        source_vertices_preserved,
        source_faces_preserved,
        feature_preserved,
        patch_preserved,
        physical_groups_preserved,
        component_bijection,
        provenance_complete,
    )
    if any(type(value) is not bool for value in flags):
        return _empty("explicit_boolean_measurements_required", source_vertex_count=len(source_points), source_face_count=len(surface))
    source_hash = hashlib.sha256(source_file.read_bytes()).hexdigest()
    source_shape = _hash_bytes(_array_hash(source_points).encode("ascii"), _array_hash(surface).encode("ascii"))
    output_shape = _hash_bytes(_array_hash(volume_points).encode("ascii"), _array_hash(cells).encode("ascii"))
    feature_hash = _payload_hash(tuple(source_feature_ids))
    patch_hash = _payload_hash(tuple(source_patch_ids))
    group_hash = _payload_hash(tuple(str(value) for value in source_physical_groups))
    provenance_hash = _hash_bytes(
        json.dumps(provenance, ensure_ascii=True, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    )
    authoritative = all(flags)
    return VolumeSourceOutputCertificate(
        status="measured_authoritative_volume_source_output" if authoritative else "reject_volume_source_output_binding",
        source_sha256=source_hash,
        source_shape_sha256=source_shape,
        output_shape_sha256=output_shape,
        feature_sha256=feature_hash,
        patch_sha256=patch_hash,
        physical_group_sha256=group_hash,
        provenance_sha256=provenance_hash,
        source_vertices_preserved=source_vertices_preserved,
        source_faces_preserved=source_faces_preserved,
        feature_preserved=feature_preserved,
        patch_preserved=patch_preserved,
        physical_groups_preserved=physical_groups_preserved,
        component_bijection=component_bijection,
        provenance_complete=provenance_complete,
        authoritative=authoritative,
        source_vertex_count=len(source_points),
        source_face_count=len(surface),
        output_point_count=len(volume_points),
        output_cell_count=len(cells),
        rejection_reason=None if authoritative else "source_output_preservation_incomplete",
    )


__all__ = ["VolumeSourceOutputCertificate", "certify_volume_source_output"]
