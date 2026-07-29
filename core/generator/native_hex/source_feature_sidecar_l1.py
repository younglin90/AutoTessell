"""Fail-closed authoritative source-feature sidecar contract.

Current STL/OBJ/PLY readers provide triangles but do not preserve CAD
patch/ridge/corner identities.  This test-only ingress contract permits an
external importer to supply those identities without inferring them from
geometry.  The manifest is bound to both the original file bytes and the
reader's ordered face-coordinate stream, so face reordering or a different
source file cannot silently relabel exact source quads.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

import numpy as np

from .source_feature_provenance_l0 import (
    SourceEntity,
    SourceFeatureProvenanceAudit,
    audit_source_entity_boundaries_l0,
)


@dataclass(frozen=True)
class AuthoritativeSourceFeatureManifest:
    """Caller/importer authority bound to one file and one ordered face stream."""

    source_file_sha256: str
    ordered_triangle_coordinate_sha256: str
    face_entities: tuple[SourceEntity, ...]


@dataclass(frozen=True)
class SourceFeatureSidecarAudit:
    """Read-only sidecar validation; no reader or mesh state is modified."""

    status: str
    source_file_hash_matches: bool
    ordered_face_coordinate_hash_matches: bool
    provenance: SourceFeatureProvenanceAudit | None
    source_geometry_unchanged: bool
    production_mesh_changed: bool


def ordered_triangle_coordinate_sha256(vertices: np.ndarray, faces: np.ndarray) -> str:
    """Hash the reader-visible ordered triangle coordinate stream exactly."""
    points = np.asarray(vertices, dtype="<f8")
    triangles = np.asarray(faces, dtype=np.int64)
    if (
        points.ndim != 2
        or points.shape[1] != 3
        or triangles.ndim != 2
        or triangles.shape[1] != 3
        or np.any(triangles < 0)
        or np.any(triangles >= len(points))
        or not np.all(np.isfinite(points))
    ):
        raise ValueError("vertices and faces must form finite indexed triangles")
    return sha256(np.ascontiguousarray(points[triangles], dtype="<f8").tobytes()).hexdigest()


def _file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def audit_authoritative_source_feature_sidecar_l1(
    vertices: np.ndarray,
    faces: np.ndarray,
    *,
    source_path: str | Path,
    manifest: AuthoritativeSourceFeatureManifest | None,
) -> SourceFeatureSidecarAudit:
    """Accept only an intact caller-supplied feature manifest for this source."""
    points = np.asarray(vertices, dtype=np.float64)
    triangles = np.asarray(faces, dtype=np.int64)
    points_before, faces_before = points.copy(), triangles.copy()
    unchanged = bool(np.array_equal(points, points_before) and np.array_equal(triangles, faces_before))
    if manifest is None:
        return SourceFeatureSidecarAudit(
            "reject_missing_authoritative_feature_manifest", False, False, None, unchanged, False
        )
    path = Path(source_path)
    if not path.is_file():
        return SourceFeatureSidecarAudit(
            "reject_source_file_not_found", False, False, None, unchanged, False
        )
    try:
        coordinate_hash = ordered_triangle_coordinate_sha256(points, triangles)
    except ValueError:
        return SourceFeatureSidecarAudit(
            "reject_invalid_source_geometry", False, False, None, unchanged, False
        )
    file_matches = _file_sha256(path) == manifest.source_file_sha256
    coordinate_matches = coordinate_hash == manifest.ordered_triangle_coordinate_sha256
    if not file_matches or not coordinate_matches:
        return SourceFeatureSidecarAudit(
            "reject_manifest_source_identity_mismatch",
            file_matches,
            coordinate_matches,
            None,
            unchanged,
            False,
        )
    provenance = audit_source_entity_boundaries_l0(points, triangles, manifest.face_entities)
    return SourceFeatureSidecarAudit(
        (
            "pass_authoritative_feature_sidecar"
            if provenance.status == "pass_authoritative_source_entity_boundaries"
            else "reject_manifest_entity_payload"
        ),
        True,
        True,
        provenance,
        unchanged,
        False,
    )
