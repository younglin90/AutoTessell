"""Immutable read-back witness for native Tet quality and connectivity.

This is evidence code, not a repair path.  It reconstructs the written
polyMesh representation, computes the same geometric quantities used by the
native checker, and records stable digests plus worst-element ids before a
candidate can be considered for a topology-changing operation.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from core.evaluator.native_checker import NativeMeshChecker
from core.generator.native_tet.writer_topology import audit_written_polymesh
from core.utils.polymesh_reader import (
    parse_foam_faces,
    parse_foam_labels_array,
    parse_foam_points_array,
)


def _sha256_json(value: Any) -> str:
    payload = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _p95(values: np.ndarray) -> float:
    return float(np.percentile(values, 95.0)) if values.size else 0.0


def _finite_vector(values: np.ndarray) -> bool:
    return bool(values.size == 0 or np.isfinite(values).all())


@dataclass(frozen=True, slots=True)
class NativeTetQualityWitness:
    """Stable evidence from one written native-Tet artifact."""

    status: str
    points_digest: str | None
    connectivity_digest: str | None
    boundary_faces_digest: str | None
    source_ledger_digest: str | None
    n_points: int
    n_faces: int
    n_cells: int
    p95_non_orthogonality: float | None
    max_non_orthogonality: float | None
    p95_skewness: float | None
    max_skewness: float | None
    p95_aspect_ratio: float | None
    max_aspect_ratio: float | None
    min_positive_volume: float | None
    worst_non_orthogonality_face: int | None
    worst_skewness_face: int | None
    worst_aspect_ratio_cell: int | None
    malformed_reason: str | None = None
    contract: str = "autotessell/native-tet-quality-witness/v1"

    @property
    def valid(self) -> bool:
        values = (
            self.p95_non_orthogonality,
            self.max_non_orthogonality,
            self.p95_skewness,
            self.max_skewness,
            self.p95_aspect_ratio,
            self.max_aspect_ratio,
            self.min_positive_volume,
        )
        return bool(
            self.status == "measured"
            and self.points_digest
            and self.connectivity_digest
            and self.boundary_faces_digest
            and self.n_points > 0
            and self.n_cells > 0
            and all(value is not None and np.isfinite(value) for value in values)
            and float(self.min_positive_volume) > 0.0
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "points_digest": self.points_digest,
            "connectivity_digest": self.connectivity_digest,
            "boundary_faces_digest": self.boundary_faces_digest,
            "source_ledger_digest": self.source_ledger_digest,
            "n_points": self.n_points,
            "n_faces": self.n_faces,
            "n_cells": self.n_cells,
            "p95_non_orthogonality": self.p95_non_orthogonality,
            "max_non_orthogonality": self.max_non_orthogonality,
            "p95_skewness": self.p95_skewness,
            "max_skewness": self.max_skewness,
            "p95_aspect_ratio": self.p95_aspect_ratio,
            "max_aspect_ratio": self.max_aspect_ratio,
            "min_positive_volume": self.min_positive_volume,
            "worst_non_orthogonality_face": self.worst_non_orthogonality_face,
            "worst_skewness_face": self.worst_skewness_face,
            "worst_aspect_ratio_cell": self.worst_aspect_ratio_cell,
            "malformed_reason": self.malformed_reason,
            "contract": self.contract,
            "valid": self.valid,
        }


def _unverified(reason: str) -> NativeTetQualityWitness:
    return NativeTetQualityWitness(
        status="unverified",
        points_digest=None,
        connectivity_digest=None,
        boundary_faces_digest=None,
        source_ledger_digest=None,
        n_points=0,
        n_faces=0,
        n_cells=0,
        p95_non_orthogonality=None,
        max_non_orthogonality=None,
        p95_skewness=None,
        max_skewness=None,
        p95_aspect_ratio=None,
        max_aspect_ratio=None,
        min_positive_volume=None,
        worst_non_orthogonality_face=None,
        worst_skewness_face=None,
        worst_aspect_ratio_cell=None,
        malformed_reason=reason,
    )


def build_native_tet_quality_witness(
    case_dir: Path, *, source_ledger_digest: str | None = None
) -> NativeTetQualityWitness:
    """Read a written Tet artifact and return immutable quality evidence."""
    poly_dir = case_dir / "constant" / "polyMesh"
    try:
        points = parse_foam_points_array(poly_dir / "points")
        faces = parse_foam_faces(poly_dir / "faces")
        owner = parse_foam_labels_array(poly_dir / "owner")
        neighbour = parse_foam_labels_array(poly_dir / "neighbour")
        written = audit_written_polymesh(poly_dir)
    except Exception as exc:  # noqa: BLE001
        return _unverified(f"parse_error:{type(exc).__name__}")

    n_internal = len(neighbour)
    if (
        points.ndim != 2
        or points.shape[1:] != (3,)
        or not len(points)
        or not _finite_vector(points)
        or len(owner) != len(faces)
        or n_internal > len(faces)
        or written.n_cells <= 0
    ):
        return _unverified("invalid_written_incidence")

    checker = NativeMeshChecker()
    face_centres = checker._compute_face_centres(points, faces)
    face_normals, _face_areas = checker._compute_face_normals_areas(points, faces)
    cell_centres = checker._compute_cell_centres_from_vertices(
        points, faces, owner, written.n_cells, neighbour
    )

    internal_owner = owner[:n_internal]
    internal_neighbour = neighbour[:n_internal]
    valid_internal = (
        (internal_owner >= 0)
        & (internal_neighbour >= 0)
        & (internal_owner < written.n_cells)
        & (internal_neighbour < written.n_cells)
    )
    if np.any(valid_internal):
        ids = np.flatnonzero(valid_internal)
        delta = cell_centres[internal_neighbour[ids]] - cell_centres[internal_owner[ids]]
        dnorm = np.linalg.norm(delta, axis=1)
        nnorm = np.linalg.norm(face_normals[ids], axis=1)
        good = (dnorm > 1e-30) & (nnorm > 1e-30)
        angles = np.degrees(
            np.arccos(
                np.clip(
                    np.abs(np.einsum("ij,ij->i", delta[good], face_normals[ids][good]))
                    / (dnorm[good] * nnorm[good]),
                    0.0,
                    1.0,
                )
            )
        )
        non_ortho_ids = ids[good]
    else:
        angles = np.empty(0, dtype=np.float64)
        non_ortho_ids = np.empty(0, dtype=np.int64)

    if np.any(valid_internal):
        ids = np.flatnonzero(valid_internal)
        delta = cell_centres[internal_neighbour[ids]] - cell_centres[internal_owner[ids]]
        d2 = np.einsum("ij,ij->i", delta, delta)
        good = d2 > 1e-30
        diff = face_centres[ids][good] - cell_centres[internal_owner[ids][good]]
        t = np.einsum("ij,ij->i", diff, delta[good]) / d2[good]
        skew_values = np.linalg.norm(
            face_centres[ids][good]
            - (cell_centres[internal_owner[ids][good]] + t[:, None] * delta[good]),
            axis=1,
        ) / np.sqrt(d2[good])
        skew_ids = ids[good]
    else:
        skew_values = np.empty(0, dtype=np.float64)
        skew_ids = np.empty(0, dtype=np.int64)

    cell_ids, aspects = checker._per_cell_aspect_ratios(
        points, faces, owner, written.n_cells, n_internal
    )
    if not (_finite_vector(angles) and _finite_vector(skew_values) and _finite_vector(aspects)):
        return _unverified("nonfinite_quality_measure")

    cell_connectivity = [list(cell.unique_vertex_ids) for cell in written.cells]
    boundary_faces = [
        sorted(int(vertex) for vertex in faces[index])
        for index in range(n_internal, len(faces))
    ]
    volumes = []
    for cell in written.cells:
        ids = np.asarray(cell.unique_vertex_ids, dtype=np.int64)
        if len(ids) != 4:
            return _unverified("non_tetrahedron_written_cell")
        a, b, c, d = points[ids]
        volumes.append(abs(float(np.dot(b - a, np.cross(c - a, d - a)))) / 6.0)
    volumes_array = np.asarray(volumes, dtype=np.float64)
    if volumes_array.size == 0 or not np.isfinite(volumes_array).all() or np.any(volumes_array <= 0.0):
        return _unverified("nonpositive_tet_volume")

    return NativeTetQualityWitness(
        status="measured",
        points_digest=_sha256_json(points.tolist()),
        connectivity_digest=_sha256_json(cell_connectivity),
        boundary_faces_digest=_sha256_json(sorted(boundary_faces)),
        source_ledger_digest=source_ledger_digest,
        n_points=int(len(points)),
        n_faces=int(len(faces)),
        n_cells=int(written.n_cells),
        p95_non_orthogonality=_p95(angles),
        max_non_orthogonality=float(angles.max()) if angles.size else 0.0,
        p95_skewness=_p95(skew_values),
        max_skewness=float(skew_values.max()) if skew_values.size else 0.0,
        p95_aspect_ratio=_p95(aspects),
        max_aspect_ratio=float(aspects.max()) if aspects.size else 1.0,
        min_positive_volume=float(volumes_array.min()),
        worst_non_orthogonality_face=(
            int(non_ortho_ids[int(np.argmax(angles))]) if angles.size else None
        ),
        worst_skewness_face=(
            int(skew_ids[int(np.argmax(skew_values))]) if skew_values.size else None
        ),
        worst_aspect_ratio_cell=(
            int(cell_ids[int(np.argmax(aspects))]) if aspects.size else None
        ),
    )


__all__ = ["NativeTetQualityWitness", "build_native_tet_quality_witness"]
