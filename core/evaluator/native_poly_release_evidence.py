"""Measured Native Poly boundary-authority certificate."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np

from core.evaluator.gate4_surface_topology import audit_polymesh_surface
from core.evaluator.strict_volume_topology import audit_strict_volume_topology
from core.evaluator.gate4_exact_surface_metrics import measure_gate4_exact_surface_metrics
from core.utils.polymesh_reader import (
    parse_foam_boundary,
    parse_foam_faces,
    parse_foam_labels_array,
    parse_foam_points_array,
)
from core.analyzer.readers import read_stl

_CONTRACT = "autotessell/native-poly-boundary-authority/v1"


@dataclass(frozen=True, slots=True)
class NativePolyBoundaryAuthority:
    status: str
    authoritative: bool
    source_file_sha256: str | None
    output_artifact_sha256: str | None
    source_patch_sha256: str | None
    source_physical_group_sha256: str | None
    boundary_patch_name: str | None
    strict_topology_valid: bool
    gate4_surface_valid: bool
    boundary_source_bound: bool
    feature_preserved: bool
    physical_groups_preserved: bool
    provenance_complete: bool
    rejection_reason: str | None = None
    contract: str = _CONTRACT
    source_shape_sha256: str | None = None
    output_shape_sha256: str | None = None
    shape_preserved: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "authoritative": self.authoritative,
            "source_file_sha256": self.source_file_sha256,
            "output_artifact_sha256": self.output_artifact_sha256,
            "source_patch_sha256": self.source_patch_sha256,
            "source_physical_group_sha256": self.source_physical_group_sha256,
            "boundary_patch_name": self.boundary_patch_name,
            "strict_topology_valid": self.strict_topology_valid,
            "gate4_surface_valid": self.gate4_surface_valid,
            "boundary_source_bound": self.boundary_source_bound,
            "feature_preserved": self.feature_preserved,
            "physical_groups_preserved": self.physical_groups_preserved,
            "provenance_complete": self.provenance_complete,
            "rejection_reason": self.rejection_reason,
            "contract": self.contract,
            "source_shape_sha256": self.source_shape_sha256,
            "output_shape_sha256": self.output_shape_sha256,
            "shape_preserved": self.shape_preserved,
        }


def _sha256_payload(values: Sequence[object]) -> str:
    return hashlib.sha256(
        json.dumps(tuple(values), ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _shape_evidence(
    source_path: Path,
    case_dir: Path,
) -> tuple[str | None, str | None, bool]:
    try:
        source = read_stl(source_path)
        source_points = np.asarray(source.vertices, dtype=np.float64)
        source_faces = np.asarray(source.faces, dtype=np.int64)
        root = case_dir / "constant" / "polyMesh"
        output_points = parse_foam_points_array(root / "points")
        all_faces = parse_foam_faces(root / "faces")
        neighbour = parse_foam_labels_array(root / "neighbour")
        boundary_faces = all_faces[len(neighbour):]
        triangles: list[list[int]] = []
        for face in boundary_faces:
            for index in range(1, len(face) - 1):
                triangles.append([int(face[0]), int(face[index]), int(face[index + 1])])
        output_faces = np.asarray(triangles, dtype=np.int64)
        if output_points.ndim != 2 or not len(output_faces):
            return None, None, False
        def array_hash(array: np.ndarray) -> str:
            digest = hashlib.sha256()
            contiguous = np.ascontiguousarray(array)
            digest.update(str(contiguous.dtype).encode("ascii"))
            digest.update(np.asarray(contiguous.shape, dtype="<i8").tobytes())
            digest.update(contiguous.tobytes())
            return digest.hexdigest()
        source_hash = hashlib.sha256(
            json.dumps((array_hash(source_points), array_hash(source_faces))).encode()
        ).hexdigest()
        output_hash = hashlib.sha256(
            json.dumps((array_hash(output_points), array_hash(output_faces))).encode()
        ).hexdigest()
        scale = max(float(np.linalg.norm(np.ptp(source_points, axis=0))), 1.0)
        vertex_preserved = all(
            np.min(np.linalg.norm(output_points - point[None, :], axis=1)) <= scale * 1e-8
            for point in source_points
        )
        metric = measure_gate4_exact_surface_metrics(
            source_points, source_faces, output_points, output_faces,
            sample_count=min(4096, max(1, len(source_faces) * 2)),
        )
        shape_preserved = bool(
            vertex_preserved
            and metric.symmetric_sampled_max is not None
            and metric.symmetric_sampled_max <= scale * 1e-8
        )
        return source_hash, output_hash, shape_preserved
    except Exception:
        return None, None, False


def certify_native_poly_boundary_authority(
    case_dir: Path,
    source_path: Path,
    *,
    source_patch_ids: Sequence[object],
    source_physical_groups: Sequence[str],
    expected_boundary_patch: str,
    feature_preserved: bool,
    provenance_complete: bool,
) -> NativePolyBoundaryAuthority:
    source_file = Path(source_path)
    if source_file.is_symlink() or not source_file.is_file():
        return NativePolyBoundaryAuthority(
            "reject_native_poly_boundary_authority", False, None, None, None, None,
            None, False, False, False, False, False, False,
            "source_file_not_authoritative",
        )
    source_hash = hashlib.sha256(source_file.read_bytes()).hexdigest()
    source_shape_hash, output_shape_hash, shape_preserved = _shape_evidence(
        source_file, case_dir
    )
    try:
        strict = audit_strict_volume_topology(case_dir)
        surface = audit_polymesh_surface(case_dir)
        patches = parse_foam_boundary(case_dir / "constant" / "polyMesh" / "boundary")
        names = tuple(
            str(patch.get("name"))
            for patch in patches
            if isinstance(patch, dict) and isinstance(patch.get("name"), str)
        )
    except Exception as exc:
        return NativePolyBoundaryAuthority(
            "reject_native_poly_boundary_authority", False, source_hash, None,
            _sha256_payload(source_patch_ids), _sha256_payload(source_physical_groups),
            None, False, False, False, bool(feature_preserved), False,
            bool(provenance_complete), f"measurement_failed:{type(exc).__name__}",
        )
    source_groups = tuple(str(value) for value in source_physical_groups)
    groups_valid = (
        len(source_patch_ids) == len(source_groups) > 0
        and all(isinstance(value, str) and value.strip() for value in source_groups)
    )
    bound = expected_boundary_patch in names
    authoritative = bool(
        strict.valid
        and surface.topology_valid
        and surface.artifact is not None
        and bound
        and groups_valid
        and feature_preserved
        and provenance_complete
        and source_shape_hash is not None
        and output_shape_hash is not None
        and shape_preserved
    )
    return NativePolyBoundaryAuthority(
        "measured_authoritative_native_poly_boundary"
        if authoritative else "reject_native_poly_boundary_authority",
        authoritative,
        source_hash,
        surface.artifact.sha256 if surface.artifact is not None else None,
        _sha256_payload(source_patch_ids),
        _sha256_payload(source_groups),
        expected_boundary_patch if bound else None,
        bool(strict.valid),
        bool(surface.topology_valid),
        bound,
        bool(feature_preserved),
        groups_valid and bound,
        bool(provenance_complete),
        None if authoritative else "native_poly_boundary_authority_incomplete",
        source_shape_sha256=source_shape_hash,
        output_shape_sha256=output_shape_hash,
        shape_preserved=shape_preserved,
    )


__all__ = ["NativePolyBoundaryAuthority", "certify_native_poly_boundary_authority"]
