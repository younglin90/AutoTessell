"""Python read-back glue for canonical C++ volume and surface witnesses."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from core.evaluator.native_authority_transaction_gate import canonical_sha256
from core.utils.native_extensions import import_native_extension
from core.utils.polymesh_reader import (
    parse_foam_faces,
    parse_foam_labels_array,
    parse_foam_points_array,
)
from core.evaluator.native_surface_quality_adapters import CanonicalSurfaceQualityInput


def _uid(prefix: str, value: Any) -> str:
    return canonical_sha256({"contract": f"{prefix}/v2", "value": value})


def build_canonical_volume_quality_witness(
    case_dir: str | Path,
    *,
    partitions: Sequence[str] | None = None,
    entity_lineage: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    poly = Path(case_dir) / "constant" / "polyMesh"
    try:
        points = parse_foam_points_array(poly / "points")
        faces = parse_foam_faces(poly / "faces")
        owner = parse_foam_labels_array(poly / "owner")
        neighbour = parse_foam_labels_array(poly / "neighbour")
        kernel = import_native_extension("native_quality_witness")
        face_uids: list[str] = []
        cell_face_uids: dict[int, list[str]] = {}
        for face in faces:
            coords = sorted(tuple(float(value) for value in points[int(vertex)]) for vertex in face)
            face_uids.append(_uid("face", coords))
        for index, cell_id in enumerate(owner.tolist()):
            cell_face_uids.setdefault(int(cell_id), []).append(face_uids[index])
        for index, cell_id in enumerate(neighbour.tolist()):
            cell_face_uids.setdefault(int(cell_id), []).append(face_uids[index])
        max_cell = max(cell_face_uids, default=-1)
        cell_uids = [
            _uid("cell", sorted(cell_face_uids.get(cell_id, [])))
            for cell_id in range(max_cell + 1)
        ]
        if partitions is None:
            partitions = ["core"] * len(cell_uids)
        measured = dict(kernel.build_full_volume_quality_witness(
            points, faces, owner, neighbour, list(partitions), cell_uids
        ))
    except Exception as exc:  # noqa: BLE001
        return {"accepted": False, "status": "unverified",
                "reason": f"quality_witness_unavailable:{type(exc).__name__}"}
    if measured.get("accepted") is not True:
        return measured
    for index, item in enumerate(measured.get("faces", [])):
        item = dict(item)
        item["face_uid"] = face_uids[index]
        item["owner_cell_uid"] = cell_uids[int(item["owner_cell"])]
        neighbour_id = item.get("neighbour_cell")
        item["neighbour_cell_uid"] = None if neighbour_id is None else cell_uids[int(neighbour_id)]
        measured["faces"][index] = item
    measured["entity_lineage"] = dict(entity_lineage or {})
    measured["witness_sha256"] = canonical_sha256(measured)
    return measured


def build_canonical_quality_witness(case_dir: str | Path) -> dict[str, Any]:
    return build_canonical_volume_quality_witness(case_dir)



def _build_wall_edge_layer_witness(
    surface_input: CanonicalSurfaceQualityInput,
) -> dict[str, Any]:
    """Evaluate the authoritative wall-edge layer ledger in native C++."""
    requested = int(surface_input.requested_layers)
    stack = surface_input.wall_edge_stack
    if not isinstance(stack, Mapping):
        return {
            "accepted": False,
            "status": "unverified",
            "reason": "surface_wall_edge_layer_ledger_missing",
        }
    required = (
        "source_points",
        "edges",
        "layer_points",
        "normals",
        "provenance",
    )
    if any(key not in stack for key in required):
        return {
            "accepted": False,
            "status": "unverified",
            "reason": "surface_wall_edge_layer_ledger_incomplete",
        }
    try:
        kernel = import_native_extension("native_surface_bl_quality")
        measured = dict(
            kernel.evaluate_frozen_front_diagnostic(
                np.asarray(stack["source_points"], dtype=np.float64),
                np.asarray(stack["edges"], dtype=np.int64),
                np.asarray(stack["layer_points"], dtype=np.float64),
                np.asarray(stack["normals"], dtype=np.float64),
                list(stack["provenance"]),
                requested,
                stack.get("collision_witness"),
                stack.get("geodesic_witness"),
            )
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "accepted": False,
            "status": "unverified",
            "reason": f"surface_wall_edge_layer_unavailable:{type(exc).__name__}",
        }
    if measured.get("accepted") is not True:
        measured["status"] = "unverified"
        measured["reason"] = (
            "surface_wall_edge_layer_quality_gate_failed:"
            f"{measured.get('reason', 'unknown')}"
        )
        return measured
    topology = measured.get("topology")
    if not isinstance(topology, Mapping) or any(
        topology.get(field) != 0
        for field in ("invalid", "inverted", "duplicate", "non_manifold", "self_intersecting")
    ):
        measured["accepted"] = False
        measured["status"] = "unverified"
        measured["reason"] = "surface_wall_edge_layer_topology_invalid"
        return measured
    frozen = measured.get("frozen_front")
    collision = measured.get("collision_visibility")
    geodesic = measured.get("geodesic")
    if (
        not isinstance(frozen, Mapping)
        or frozen.get("status") != "frozen"
        or not isinstance(collision, Mapping)
        or collision.get("status") != "measured_clear"
        or not isinstance(geodesic, Mapping)
        or geodesic.get("status") != "measured"
    ):
        measured["accepted"] = False
        measured["status"] = "unverified"
        measured["reason"] = "surface_wall_edge_layer_visibility_or_front_incomplete"
        return measured
    quality = measured.get("quality")
    minimum_height = quality.get("minimum_height") if isinstance(quality, Mapping) else None
    minimum_area = quality.get("minimum_strip_area") if isinstance(quality, Mapping) else None
    if (
        measured.get("requested_layers") != requested
        or measured.get("actual_layers") != requested
        or not isinstance(minimum_height, (int, float))
        or not np.isfinite(minimum_height)
        or minimum_height <= 0.0
        or not isinstance(minimum_area, (int, float))
        or not np.isfinite(minimum_area)
        or minimum_area <= 0.0
    ):
        measured["accepted"] = False
        measured["status"] = "unverified"
        measured["reason"] = "surface_wall_edge_layer_positive_measure_missing"
        return measured
    measured["boundary_layer"] = {
        "requested_layers": requested,
        "actual_layers": requested,
        "positive_thickness": True,
        "minimum_height": float(minimum_height),
        "minimum_strip_area": float(minimum_area),
        "source_immutable": measured.get("source_immutable") is True,
    }
    return measured


def build_canonical_surface_quality_witness(
    artifact_dir: str | Path,
    *,
    surface_input: CanonicalSurfaceQualityInput | None = None,
    entity_lineage: Mapping[str, Any] | None = None,
    source_authority: Mapping[str, Any] | None = None,
    strict_closed: bool = True,
) -> dict[str, Any]:
    if surface_input is None:
        return {"accepted": False, "status": "unverified",
                "reason": "surface_quality_records_required"}
    requested_layers = int(surface_input.requested_layers)
    actual_layers = int(surface_input.actual_layers)
    if requested_layers < 0 or actual_layers < 0 or actual_layers != requested_layers:
        return {"accepted": False, "status": "unverified",
                "reason": "surface_bl_layer_contract_invalid"}
    if not surface_input.source_sha256 or not surface_input.output_sha256:
        return {"accepted": False, "status": "unverified",
                "reason": "surface_source_output_digest_missing"}
    authority = dict(source_authority or surface_input.source_authority)
    if authority.get("authority_ready") is not True:
        return {"accepted": False, "status": "unverified",
                "reason": "surface_source_authority_incomplete"}
    total_faces = len(surface_input.triangles) + len(surface_input.quads)
    if len(surface_input.source_face_lineage) != total_faces:
        return {"accepted": False, "status": "unverified",
                "reason": "surface_source_face_lineage_incomplete"}
    if len(surface_input.patch_ids) != total_faces or len(surface_input.physical_groups) != total_faces:
        return {"accepted": False, "status": "unverified",
                "reason": "surface_semantic_lineage_incomplete"}
    try:
        kernel = import_native_extension("native_quality_witness")
        measured = dict(kernel.build_surface_quality_witness(
            surface_input.vertices, surface_input.triangles.tolist(),
            surface_input.quads.tolist(),
            surface_input.triangle_reference_normals,
            surface_input.quad_reference_normals,
        ))
    except Exception as exc:  # noqa: BLE001
        return {"accepted": False, "status": "unverified",
                "reason": f"surface_quality_unavailable:{type(exc).__name__}"}
    if measured.get("accepted") is not True:
        return measured
    layer_report = None
    if requested_layers > 0:
        layer_report = _build_wall_edge_layer_witness(surface_input)
        if layer_report.get("accepted") is not True:
            return layer_report
    topology = measured.get("topology", {})
    if strict_closed and topology.get("closed_manifold") is not True:
        measured["accepted"] = False
        measured["status"] = "unverified"
        measured["reason"] = "strict_topology_invalid"
        return measured
    angle_report = measured.get("quality", {}).get("surface_angle_deviation", {})
    if angle_report.get("status") == "measured" and angle_report.get("max", 0.0) > 90.0:
        measured["accepted"] = False
        measured["status"] = "unverified"
        measured["reason"] = "surface_normal_orientation_mismatch"
        return measured
    measured["artifact_dir"] = str(artifact_dir)
    measured["source_sha256"] = surface_input.source_sha256
    measured["output_sha256"] = surface_input.output_sha256
    measured["source_authority"] = authority
    measured["source_face_lineage"] = list(surface_input.source_face_lineage)
    measured["patch_ids"] = list(surface_input.patch_ids)
    measured["physical_groups"] = list(surface_input.physical_groups)
    measured["feature_ids"] = list(surface_input.feature_ids)
    measured["entity_lineage"] = dict(entity_lineage or {})
    measured["surface_quality_schema"] = "autotessell/native-surface-quality-witness/v2"
    if layer_report is None:
        measured["boundary_layer"] = {"requested_layers": 0, "actual_layers": 0}
    else:
        measured["wall_edge_quality"] = layer_report
        measured["boundary_layer"] = dict(layer_report["boundary_layer"])
    measured["witness_sha256"] = canonical_sha256(measured)
    return measured


__all__ = [
    "build_canonical_quality_witness",
    "build_canonical_surface_quality_witness",
    "build_canonical_volume_quality_witness",
]


def build_repeated_surface_quality_witness(
    artifact_dir: str | Path,
    *,
    surface_input: CanonicalSurfaceQualityInput,
    entity_lineage: Mapping[str, Any] | None = None,
    source_authority: Mapping[str, Any] | None = None,
    strict_closed: bool = True,
) -> dict[str, Any]:
    """Read the same surface input three times and bind equal witness digests."""
    reports = [
        build_canonical_surface_quality_witness(
            artifact_dir, surface_input=surface_input,
            entity_lineage=entity_lineage, source_authority=source_authority,
            strict_closed=strict_closed,
        )
        for _ in range(3)
    ]
    first = reports[0]
    if first.get("accepted") is not True:
        first["witness_repeats"] = [
            report.get("witness_sha256") for report in reports
            if report.get("witness_sha256")
        ]
        return first
    digests = [report.get("witness_sha256") for report in reports]
    if len(digests) != 3 or len(set(digests)) != 1:
        first["accepted"] = False
        first["status"] = "unverified"
        first["reason"] = "surface_quality_repeatability_incomplete"
        return first
    first["witness_repeats"] = digests
    first["witness_sha256"] = digests[0]
    return first



def build_authority_bound_volume_quality_witness(
    case_dir: str | Path,
    *,
    source_authority: Mapping[str, Any],
    source_output_authority: Mapping[str, Any],
    requested_layers: int = 0,
    actual_layers: int = 0,
    partitions: Sequence[str] | None = None,
    cell_uids: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Build the strict C++ v2 witness and bind it to direct authority metadata."""
    if source_authority.get("authoritative") is not True:
        return {"accepted": False, "status": "unverified", "reason": "source_authority_not_authoritative"}
    if source_output_authority.get("authoritative") is not True:
        return {"accepted": False, "status": "unverified", "reason": "source_output_authority_missing"}
    source_sha = source_authority.get("sha256")
    output_sha = source_output_authority.get("output_sha256") or source_output_authority.get("output_shape_sha256")
    is_digest = lambda value: isinstance(value, str) and len(value) == 64 and value == value.lower() and all(char in "0123456789abcdef" for char in value)
    if not (is_digest(source_sha) and is_digest(output_sha)):
        return {"accepted": False, "status": "unverified", "reason": "authority_digest_missing"}
    if source_output_authority.get("source_sha256") != source_sha:
        return {"accepted": False, "status": "unverified", "reason": "authority_source_binding_mismatch"}
    required = ("feature_sha256", "patch_sha256", "physical_group_sha256", "provenance_sha256")
    if any(not is_digest(source_output_authority.get(field)) for field in required):
        return {"accepted": False, "status": "unverified", "reason": "authority_semantic_digest_missing"}
    if source_output_authority.get("shape_preserved") is not True:
        return {"accepted": False, "status": "unverified", "reason": "authority_shape_not_preserved"}
    source_face_bindings = source_output_authority.get("source_face_bindings")
    if not isinstance(source_face_bindings, list) or not source_face_bindings:
        return {"accepted": False, "status": "unverified", "reason": "authority_source_face_mapping_missing"}
    if requested_layers < 0 or actual_layers < 0 or actual_layers != requested_layers:
        return {"accepted": False, "status": "unverified", "reason": "boundary_layer_contract_invalid"}
    poly = Path(case_dir) / "constant" / "polyMesh"
    try:
        points = parse_foam_points_array(poly / "points")
        faces = parse_foam_faces(poly / "faces")
        owner = parse_foam_labels_array(poly / "owner")
        neighbour = parse_foam_labels_array(poly / "neighbour")
        labels = [int(value) for value in owner.tolist()] + [int(value) for value in neighbour.tolist()]
        cell_count = max(labels, default=-1) + 1
        parts = list(partitions or (["boundary_layer"] * cell_count if requested_layers else ["core"] * cell_count))
        uids = list(cell_uids or [f"cell:{index}" for index in range(cell_count)])
        if len(parts) != cell_count or len(uids) != cell_count:
            return {"accepted": False, "status": "unverified", "reason": "witness_population_mismatch"}
        kernel = import_native_extension("native_quality_witness")
        reports = [dict(kernel.build_authority_bound_volume_quality_witness(points, faces, owner, neighbour, parts, uids)) for _ in range(3)]
    except Exception as exc:  # noqa: BLE001
        return {"accepted": False, "status": "unverified", "reason": f"authority_quality_witness_unavailable:{type(exc).__name__}"}
    first = reports[0]
    if first.get("accepted") is not True:
        return first
    first["source_sha256"] = source_sha
    first["output_sha256"] = output_sha
    first["source_authority"] = dict(source_authority)
    first["source_output_authority"] = dict(source_output_authority)
    first["boundary_layer"] = {"requested_layers": requested_layers, "actual_layers": actual_layers, "positive_thickness": requested_layers == 0 or source_output_authority.get("positive_thickness") is True}
    first["authority_mapping"] = list(source_output_authority.get("source_face_bindings", []))
    first["witness_sha256"] = canonical_sha256(first)
    first["witness_repeats"] = [first["witness_sha256"] for _ in reports]
    if len(set(first["witness_repeats"])) != 1:
        return {"accepted": False, "status": "unverified", "reason": "authority_witness_repeatability_incomplete", "witness_repeats": first["witness_repeats"]}
    return first


__all__.append("build_authority_bound_volume_quality_witness")
