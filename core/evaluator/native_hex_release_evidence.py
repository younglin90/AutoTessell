"""Measured Native Hex CAD/B-Rep source/output authority adapter."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Sequence

import numpy as np

from core.evaluator.strict_volume_topology import audit_strict_volume_topology
from core.generator.native_hex.output_source_binding import HexMeasuredSourceBinding
from core.utils.native_extensions import import_native_extension
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
    source_face_ordinals: Sequence[int] | None = None,
    requested_layers: int = 0,
    actual_layers: int = 0,
    first_height: float = 0.0,
    positive_layer: bool = True,
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

    writer_order_rows_raw: list[dict[str, object]] | None = None
    writer_order_error: str | None = None
    writer_order_path = case_dir / "native_hex_writer_order.json"
    if writer_order_path.is_file():
        try:
            writer_payload = json.loads(writer_order_path.read_text())
            raw_rows = writer_payload.get("records")
            if not isinstance(raw_rows, list) or len(raw_rows) != len(boundary_faces):
                raise ValueError("writer_order_count_mismatch")
            normalized_rows: list[dict[str, object]] = []
            for index, raw_row in enumerate(raw_rows):
                if not isinstance(raw_row, dict):
                    raise ValueError("writer_order_row_invalid")
                required = (
                    "writer_order", "output_face_id", "source_mesh_face",
                    "source_face", "patch", "direct",
                )
                if any(key not in raw_row for key in required):
                    raise ValueError("writer_order_field_missing")
                order = int(raw_row["writer_order"])
                output_face_id = int(raw_row["output_face_id"])
                source_mesh_face = int(raw_row["source_mesh_face"])
                source_face = int(raw_row["source_face"])
                output_patch = str(raw_row["patch"])
                direct = raw_row["direct"] is True
                if (
                    order != index
                    or output_face_id != len(neighbour) + index
                    or source_mesh_face < 0
                    or (direct and source_face < 0)
                    or (not direct and source_face != -1)
                    or not output_patch
                ):
                    raise ValueError("writer_order_binding_invalid")
                normalized_rows.append({
                    "writer_order": order,
                    "output_face_id": output_face_id,
                    "source_mesh_face": source_mesh_face,
                    "source_face": source_face,
                    "output_patch": output_patch,
                    "direct": direct,
                })
            writer_order_rows_raw = normalized_rows
        except Exception as exc:
            writer_order_error = f"writer_order_invalid:{type(exc).__name__}:{exc}"

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
    if source_face_ordinals is None:
        source_ordinals = np.arange(len(source_faces_array), dtype=np.int64)
    else:
        source_ordinals = np.asarray(source_face_ordinals, dtype=np.int64)
    ordinal_error: str | None = None
    if source_ordinals.ndim != 1 or len(source_ordinals) != len(source_faces_array) or np.any(source_ordinals < 0):
        ordinal_error = "source_face_ordinals_invalid"
        source_ordinals = np.arange(len(source_faces_array), dtype=np.int64)
    face_count = int(source_ordinals.max()) + 1 if len(source_ordinals) else 0
    if set(int(value) for value in source_ordinals) != set(range(face_count)):
        ordinal_error = "source_face_ordinals_not_contiguous"
    semantic_rows: list[dict[str, str]] = []
    for ordinal in range(face_count):
        matches = np.flatnonzero(source_ordinals == ordinal)
        if len(matches) == 0:
            ordinal_error = "source_face_ordinal_missing"
            continue
        index = int(matches[0])
        semantic_rows.append({
            "feature": source_features[index] if index < len(source_features) else "",
            "patch": source_patches[index] if index < len(source_patches) else "",
            "physical_group": source_groups[index] if index < len(source_groups) else "",
            "component": f"source-component-{ordinal}",
            "provenance": f"source-face-{ordinal}",
        })
    ingress_certificate_sha256 = ""
    semantic_ledger_sha256 = ""
    provisioning_manifest_sha256 = ""
    source_map_v3 = False
    source_map_path = case_dir / "native_hex_source_face_map.json"
    if source_map_path.is_file():
        try:
            source_map_payload = json.loads(source_map_path.read_text())
            source_map_v3 = (
                source_map_payload.get("schema")
                == "autotessell/native-hex-source-face-map/v3"
            )
            if source_map_v3:
                ingress_certificate_sha256 = str(
                    source_map_payload.get("ingress_certificate_sha256", "")
                )
                semantic_ledger_sha256 = str(
                    source_map_payload.get("ingress_semantic_ledger_sha256", "")
                )
                provisioning_manifest_sha256 = str(
                    source_map_payload.get(
                        "ingress_occt_provisioning_manifest_sha256", ""
                    )
                )
                if (
                    len(ingress_certificate_sha256) != 64
                    or len(semantic_ledger_sha256) != 64
                    or len(provisioning_manifest_sha256) != 64
                ):
                    writer_order_error = "source_map_v3_ingress_digest_missing"
        except Exception as exc:
            writer_order_error = f"source_map_v3_read_failed:{type(exc).__name__}"

    writer_order_rows: list[dict[str, object]] | None = None
    if writer_order_rows_raw is not None and writer_order_error is None:
        try:
            prepared_rows: list[dict[str, object]] = []
            for raw_row in writer_order_rows_raw:
                source_face = int(raw_row["source_face"])
                if raw_row["direct"] is not True:
                    raise ValueError("writer_order_lateral_face_not_cad_bound")
                if source_face >= len(semantic_rows):
                    raise ValueError("writer_order_source_face_out_of_range")
                if str(raw_row["output_patch"]) not in patch_names:
                    raise ValueError("writer_order_output_patch_not_written")
                row = dict(raw_row)
                row.update({
                    "feature": semantic_rows[source_face]["feature"],
                    "patch": semantic_rows[source_face]["patch"],
                    "output_patch": str(raw_row["output_patch"]),
                    "physical_group": semantic_rows[source_face]["physical_group"],
                    "component": semantic_rows[source_face]["component"],
                    "provenance": semantic_rows[source_face]["provenance"],
                })
                prepared_rows.append(row)
            writer_order_rows = prepared_rows
        except Exception as exc:
            writer_order_error = f"writer_order_semantic_invalid:{type(exc).__name__}:{exc}"

    receipt_mapping = (
        tuple(int(row["source_face"]) for row in writer_order_rows)
        if writer_order_rows is not None
        else (
            ()
            if binding is None
            else tuple(int(value) for value in binding.output_face_to_source_face)
        )
    )
    feature_hash = _payload_hash(source_features)
    patch_hash = _payload_hash(source_patches)
    group_hash = _payload_hash(source_groups)
    provenance_hash = _payload_hash(
        {
            "output_to_source_face": receipt_mapping,
            "writer_order": writer_order_rows or (),
            "output_groups": ()
            if binding is None
            else tuple(binding.output_physical_groups),
        }
    )
    binding_ok = bool(binding is not None and binding.strict_binding_complete)
    strict_ok = bool(strict is not None and strict.valid)
    output_patch_values = (
        tuple(str(row["output_patch"]) for row in writer_order_rows)
        if writer_order_rows is not None
        else (() if binding is None else tuple(binding.output_physical_groups))
    )
    groups_bound = bool(
        binding_ok
        and all(name in patch_names for name in set(output_patch_values))
    )
    receipt: dict[str, object] = {
        "accepted": False,
        "status": "native_hex_brep_boundary_receipt_unavailable",
        "reason": ordinal_error or "receipt_not_run",
    }
    try:
        if writer_order_error is not None:
            receipt = {
                "accepted": False,
                "status": "native_hex_writer_order_receipt_refused",
                "reason": writer_order_error,
            }
        elif ordinal_error is None and binding is not None and len(boundary_faces) > 0:
            output_quads = np.asarray(points[boundary_faces], dtype=np.float64)
            source_triangles = np.asarray(source_vertices_array[source_faces_array], dtype=np.float64)
            kernel = import_native_extension("native_hex_boundary_receipt")
            receipt = dict(kernel.audit_native_hex_brep_boundary(
                output_quads,
                source_triangles,
                np.asarray(source_ordinals, dtype=np.int64),
                np.asarray(receipt_mapping, dtype=np.int64),
                semantic_rows,
                source_sha or "",
                strict.artifact_sha256 if strict is not None else "",
                int(requested_layers),
                int(actual_layers),
                float(first_height),
                bool(positive_layer),
                bool(strict_ok),
                float(binding.tolerance or 0.0),
                0.75,
                None if writer_order_rows is None else writer_order_rows,
                ingress_certificate_sha256,
                semantic_ledger_sha256,
                provisioning_manifest_sha256,
            ))
    except Exception as exc:
        receipt = {
            "accepted": False,
            "status": "native_hex_brep_boundary_receipt_error",
            "reason": f"{type(exc).__name__}:{exc}",
        }
    receipt_ok = receipt.get("accepted") is True
    writer_order_bound = writer_order_rows is not None
    shape_preserved = bool(
        binding_ok
        and strict_ok
        and groups_bound
        and receipt_ok
        and (requested_layers == 0 or writer_order_bound)
    )
    authoritative = bool(
        source_sha is not None
        and shape_preserved
        and binding is not None
        and binding.mapping_complete
        and binding.physical_group_mapping_complete
        and receipt_ok
        and (requested_layers == 0 or writer_order_bound)
        and (
            not source_map_v3
            or (
                receipt.get("ingress_certificate_sha256") == ingress_certificate_sha256
                and receipt.get("semantic_ledger_sha256") == semantic_ledger_sha256
                and receipt.get("provisioning_manifest_sha256")
                == provisioning_manifest_sha256
            )
        )
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
        "ingress_certificate_sha256": ingress_certificate_sha256 or None,
        "semantic_ledger_sha256": semantic_ledger_sha256 or None,
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
        "source_face_provenance": bool(binding_ok and binding.mapping_complete and receipt_ok),
        "boundary_receipt": receipt,
        "boundary_receipt_sha256": receipt.get("receipt_sha256"),
        "writer_order_bound": writer_order_bound,
        "writer_order_sha256": receipt.get("writer_order_sha256"),
        "rejection_reason": (
            None
            if authoritative
            else str(
                receipt.get("reason")
                or writer_order_error
                or measurement_error
                or "native_hex_source_output_authority_incomplete"
            )
        ),
    }


__all__ = ["certify_native_hex_release_output"]
