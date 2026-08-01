"""Measured Native Hex CAD/B-Rep source/output authority adapter."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Sequence

import numpy as np

from core.evaluator.strict_volume_topology import audit_strict_volume_topology
from core.generator.native_hex.output_source_binding import HexMeasuredSourceBinding
from core.utils.polymesh_reader import (
    parse_foam_boundary,
    parse_foam_faces,
    parse_foam_labels_array,
    parse_foam_points_array,
)


def _array_hash(value: object) -> str:
    array = np.ascontiguousarray(np.asarray(value))
    digest = hashlib.sha256()
    digest.update(array.dtype.str.encode("ascii"))
    digest.update(np.asarray(array.shape, dtype="<i8").tobytes())
    digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def _payload_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def certify_native_hex_release_output(
    case_dir: Path,
    source_path: Path,
    source_vertices: object,
    source_faces: object,
    binding: HexMeasuredSourceBinding | None,
    *,
    source_feature_ids: Sequence[object],
    source_patch_ids: Sequence[object],
    source_physical_groups: Sequence[str],
) -> dict[str, object]:
    """Convert measured Hex boundary binding into common authority evidence.

    Hex grids generally approximate curved CAD faces and therefore cannot claim
    source point identity. shape_preserved is consequently the measured
    boundary-to-B-Rep binding predicate; it is never substituted for missing
    binding or strict topology.
    """
    source_file = Path(source_path)
    source_sha = (
        hashlib.sha256(source_file.read_bytes()).hexdigest()
        if source_file.is_file() and not source_file.is_symlink()
        else None
    )
    try:
        strict = audit_strict_volume_topology(case_dir)
        root = case_dir / "constant" / "polyMesh"
        points = parse_foam_points_array(root / "points")
        faces = parse_foam_faces(root / "faces")
        neighbour = parse_foam_labels_array(root / "neighbour")
        boundary_faces = np.asarray(faces[len(neighbour):], dtype=np.int64)
        boundary = parse_foam_boundary(root / "boundary")
        patch_names = tuple(str(item.get("name")) for item in boundary)
    except Exception as exc:
        strict = None
        points = np.empty((0, 3), dtype=np.float64)
        boundary_faces = np.empty((0, 4), dtype=np.int64)
        patch_names = ()
        measurement_error = f"measurement_failed:{type(exc).__name__}"
    else:
        measurement_error = None

    source_vertices_array = np.asarray(source_vertices, dtype=np.float64)
    source_faces_array = np.asarray(source_faces, dtype=np.int64)
    source_shape = _payload_hash(
        {"vertices": _array_hash(source_vertices_array), "faces": _array_hash(source_faces_array)}
    )
    output_shape = _payload_hash(
        {"points": _array_hash(points), "boundary_faces": _array_hash(boundary_faces)}
    )
    source_features = tuple(str(value) for value in source_feature_ids)
    source_patches = tuple(str(value) for value in source_patch_ids)
    source_groups = tuple(str(value) for value in source_physical_groups)
    feature_hash = _payload_hash(source_features)
    patch_hash = _payload_hash(source_patches)
    group_hash = _payload_hash(source_groups)
    provenance_hash = _payload_hash(
        {
            "output_to_source_face": ()
            if binding is None
            else tuple(int(value) for value in binding.output_face_to_source_face),
            "output_groups": ()
            if binding is None
            else tuple(binding.output_physical_groups),
        }
    )
    binding_ok = bool(binding is not None and binding.strict_binding_complete)
    strict_ok = bool(strict is not None and strict.valid)
    groups_bound = bool(
        binding_ok
        and all(name in patch_names for name in set(binding.output_physical_groups))
    )
    shape_preserved = bool(binding_ok and strict_ok and groups_bound)
    authoritative = bool(
        source_sha is not None
        and shape_preserved
        and binding is not None
        and binding.mapping_complete
        and binding.physical_group_mapping_complete
        and len(source_feature_ids) == len(source_faces_array)
        and len(source_patch_ids) == len(source_faces_array)
        and len(source_physical_groups) == len(source_faces_array)
    )
    return {
        "status": (
            "measured_authoritative_native_hex"
            if authoritative
            else "reject_native_hex_source_output_authority"
        ),
        "authoritative": authoritative,
        "source_sha256": source_sha,
        "source_shape_sha256": source_shape,
        "output_shape_sha256": output_shape,
        "feature_sha256": feature_hash,
        "patch_sha256": patch_hash,
        "physical_group_sha256": group_hash,
        "provenance_sha256": provenance_hash,
        "shape_preserved": shape_preserved,
        "source_vertices_preserved": False,
        "source_faces_preserved": bool(binding_ok and binding.mapping_complete),
        "feature_preserved": bool(binding_ok),
        "patch_preserved": groups_bound,
        "physical_groups_preserved": bool(
            binding_ok and binding.physical_group_mapping_complete
        ),
        "component_bijection": bool(binding_ok and binding.mapping_complete),
        "provenance_complete": bool(binding_ok),
        "source_face_provenance": bool(binding_ok and binding.mapping_complete),
        "rejection_reason": (
            None
            if authoritative
            else measurement_error or "native_hex_source_output_authority_incomplete"
        ),
    }


__all__ = ["certify_native_hex_release_output"]
