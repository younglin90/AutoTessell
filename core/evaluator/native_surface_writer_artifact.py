"""Private deterministic artifact adapter for the native surface strip writer."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from core.evaluator.native_surface_bl_strip_writer import write_authoritative_surface_wall_edge_strip
from core.evaluator.native_surface_staged_runner import StagedSurfaceArtifactEvidence, run_surface_artifact_in_private_stage


def stage_native_surface_strip_evidence(
    destination: str | Path,
    points: Any,
    source_triangles: Any,
    wall_edges: Any,
    layer_point_ids: Any,
    face_normals: Any,
    source_authority: Mapping[str, Any],
    edge_provenance: Sequence[Mapping[str, Any]],
    requested_layers: int,
) -> StagedSurfaceArtifactEvidence:
    """Stage the actual C++ writer receipt without claiming public release."""
    point_array = np.ascontiguousarray(np.asarray(points, dtype=np.float64))
    edge_array = np.ascontiguousarray(np.asarray(wall_edges, dtype=np.int64))
    layer_array = np.ascontiguousarray(np.asarray(layer_point_ids, dtype=np.int64))

    def writer(stage: Path, _run_index: int) -> Mapping[str, Any]:
        result = write_authoritative_surface_wall_edge_strip(
            point_array, source_triangles, edge_array, layer_array, face_normals,
            source_authority, edge_provenance, requested_layers,
        )
        result = dict(result)
        result.setdefault("actual_layers", requested_layers if result.get("accepted") else 0)
        result.setdefault("source_authority_bound", result.get("accepted") is True)
        result.setdefault("bl_sidecar_created", requested_layers > 0)
        if requested_layers > 0 and result.get("accepted") is True and len(layer_array):
            edge_points = point_array[edge_array[:, 1:3]]
            layer_points = point_array[layer_array[0]]
            result["positive_thickness"] = float(np.min(np.linalg.norm(layer_points - edge_points, axis=2)))
        artifact = {
            "schema": "AutoTessell/NativeSurfaceStripEvidence/v1",
            "requested_layers": requested_layers,
            "actual_layers": result.get("actual_layers", 0),
            "generated_faces": result.get("generated_faces", []),
            "provenance": result.get("provenance", []),
            "diagonal_decisions": result.get("diagonal_decisions", []),
            "topology": {
                key: result.get(key, 0)
                for key in ("topology_invalid", "topology_inverted", "topology_duplicate", "topology_non_manifold")
            },
        }
        (stage / "surface-bl-strip.json").write_text(
            json.dumps(artifact, sort_keys=True, separators=(",", ":")), encoding="utf-8"
        )
        return result

    def audit(stage: Path, result: Mapping[str, Any]) -> Mapping[str, Any]:
        artifact_path = stage / "surface-bl-strip.json"
        def canonical(value: Any) -> Any:
            return json.loads(json.dumps(value, sort_keys=True, default=list))

        try:
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"accepted": False, "reason": "surface_strip_artifact_unreadable"}
        topology = artifact.get("topology", {})
        topology_ok = all(topology.get(key) == 0 for key in (
            "topology_invalid", "topology_inverted", "topology_duplicate", "topology_non_manifold",
        ))
        receipt_ok = (
            artifact.get("schema") == "AutoTessell/NativeSurfaceStripEvidence/v1"
            and artifact.get("generated_faces") == canonical(result.get("generated_faces", []))
            and artifact.get("provenance") == canonical(result.get("provenance", []))
            and topology_ok
        )
        return {"accepted": bool(receipt_ok), "independent_structural_audit": True, "reason": "receipt_and_topology_passed" if receipt_ok else "receipt_or_topology_mismatch"}

    return run_surface_artifact_in_private_stage(
        destination, writer_callback=writer, audit_callback=audit,
        source_authority=source_authority, requested_layers=requested_layers,
    )


__all__ = ["stage_native_surface_strip_evidence"]
