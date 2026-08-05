"""Fresh-process, producer-independent TRI+QUAD artifact audit adapter."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

from core.layers.native_bl_atomic_certificate import canonical_bytes
from core.utils.native_extensions import import_native_extension


_CHILD = """
import json, sys
from core.utils.native_extensions import import_native_extension
payload = json.load(sys.stdin)
result = import_native_extension("native_tri_quad_independent_quality_readback").audit_artifact(payload)
print(json.dumps(result, sort_keys=True, separators=(",", ":")))
"""


def audit_native_tri_quad_artifact_fresh_process(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Serialize untrusted artifact data and audit it in a new Python process."""
    wire = json.dumps(dict(payload), sort_keys=True, separators=(",", ":"), allow_nan=False)
    root = Path(__file__).resolve().parents[3]
    try:
        completed = subprocess.run(
            [sys.executable, "-c", _CHILD],
            input=wire,
            text=True,
            capture_output=True,
            cwd=root,
            check=False,
            timeout=30,
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "accepted": False,
            "status": "tri_quad_independent_quality_readback_refused",
            "reason": f"fresh_process_unavailable:{type(exc).__name__}",
            "publication_eligible": False,
            "candidate_discarded": True,
        }
    if completed.returncode != 0:
        return {
            "accepted": False,
            "status": "tri_quad_independent_quality_readback_refused",
            "reason": "fresh_process_auditor_failed",
            "stderr_digest": hashlib.sha256(completed.stderr.encode()).hexdigest(),
            "publication_eligible": False,
            "candidate_discarded": True,
        }
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {
            "accepted": False,
            "status": "tri_quad_independent_quality_readback_refused",
            "reason": "fresh_process_certificate_invalid_json",
            "publication_eligible": False,
            "candidate_discarded": True,
        }
    result["fresh_process"] = True
    result["canonical_input_digest"] = hashlib.sha256(wire.encode()).hexdigest()
    # Cover the complete recursively nested certificate body. The digest
    # field itself is excluded so a caller cannot retain an old digest after mutation.
    certificate_body = {
        key: value
        for key, value in result.items()
        if key != "independent_certificate_digest"
    }
    result["independent_certificate_digest"] = hashlib.sha256(
        canonical_bytes(certificate_body)
    ).hexdigest()
    return result


def audit_native_tri_quad_actual_mixed_bl_artifact(
    source_points: Any,
    source_triangles: Any,
    source_quads: Any,
    receipt: Mapping[str, Any],
    wall_loop: Any,
    co_normals: Any,
    layer_heights: Any,
    producer_result: Mapping[str, Any],
    requested_layers: int,
    max_offset: float,
) -> dict[str, Any]:
    """Build the wire payload from an actual producer result without its metrics."""
    payload = {
        "source_points": source_points.tolist() if hasattr(source_points, "tolist") else source_points,
        "source_triangles": source_triangles.tolist() if hasattr(source_triangles, "tolist") else source_triangles,
        "source_quads": source_quads.tolist() if hasattr(source_quads, "tolist") else source_quads,
        "receipt": dict(receipt),
        "wall_loop": wall_loop,
        "co_normals": co_normals,
        "layer_heights": layer_heights,
        "artifact_points": producer_result.get("points", []),
        "artifact_triangles": producer_result.get("triangles", []),
        "artifact_quads": producer_result.get("quads", []),
        "artifact_strip_quads": producer_result.get("strip_quads", []),
        "triangle_map": producer_result.get("triangle_map", []),
        "quad_map": producer_result.get("quad_map", []),
        "strip_map": producer_result.get("strip_map", []),
        "requested_layers": int(requested_layers),
        "actual_layers": int(producer_result.get("actual_layers", -1)),
        "max_offset": float(max_offset),
        "producer_digest": producer_result.get("artifact_digest", "ignored"),
    }
    return audit_native_tri_quad_artifact_fresh_process(payload)


__all__ = [
    "audit_native_tri_quad_artifact_fresh_process",
    "audit_native_tri_quad_actual_mixed_bl_artifact",
]


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def commit_native_tri_quad_producer_auditor_quality_gate(
    source_points: Any,
    source_triangles: Any,
    source_quads: Any,
    receipt: Mapping[str, Any],
    wall_loop: Any,
    co_normals: Any,
    layer_heights: Any,
    producer_result: Mapping[str, Any],
    certificate: Mapping[str, Any],
    requested_layers: int,
    max_offset: float,
) -> dict[str, Any]:
    candidate = dict(producer_result)
    source_points = source_points.tolist() if hasattr(source_points, "tolist") else source_points
    source_triangles = source_triangles.tolist() if hasattr(source_triangles, "tolist") else source_triangles
    source_quads = source_quads.tolist() if hasattr(source_quads, "tolist") else source_quads
    payload = {
        "source_points": source_points, "source_triangles": source_triangles, "source_quads": source_quads, "receipt": dict(receipt),
        "wall_loop": wall_loop, "co_normals": co_normals, "layer_heights": layer_heights,
        "artifact_points": candidate.get("points", []), "artifact_triangles": candidate.get("triangles", []),
        "artifact_quads": candidate.get("quads", []), "artifact_strip_quads": candidate.get("strip_quads", []),
        "triangle_map": candidate.get("triangle_map", []), "quad_map": candidate.get("quad_map", []), "strip_map": candidate.get("strip_map", []),
        "requested_layers": int(requested_layers), "actual_layers": int(candidate.get("actual_layers", -1)),
        "max_offset": float(max_offset), "producer_digest": candidate.get("artifact_digest", "ignored"),
    }
    canonical_input_digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    fresh = audit_native_tri_quad_artifact_fresh_process(payload)
    if not fresh.get("accepted", False):
        return {**fresh, "status": "tri_quad_producer_auditor_quality_gate_rolled_back", "committed": False, "actual_layers": 0}
    if fresh.get("canonical_input_digest") != certificate.get("canonical_input_digest"):
        return {
            "accepted": False, "status": "tri_quad_producer_auditor_quality_gate_rolled_back",
            "reason": "certificate_input_digest_mismatch", "committed": False,
            "candidate_discarded": True, "publication_eligible": False,
            "runtime_route": "private_default_off", "route_calls": 0, "actual_layers": 0,
        }
    if (fresh.get("independent_certificate_digest") != certificate.get("independent_certificate_digest") or
            canonical_bytes(dict(fresh)) != canonical_bytes(dict(certificate))):
        return {
            "accepted": False, "status": "tri_quad_producer_auditor_quality_gate_rolled_back",
            "reason": "independent_certificate_content_mismatch", "committed": False,
            "candidate_discarded": True, "publication_eligible": False,
            "runtime_route": "private_default_off", "route_calls": 0, "actual_layers": 0,
        }
    certificate = fresh
    bindings = {
        "source_digest": _digest({"points": source_points, "triangles": source_triangles, "quads": source_quads}),
        "receipt_digest": _digest(dict(receipt)),
        "candidate_digest": _digest({k: candidate.get(k) for k in ("points", "triangles", "quads", "strip_quads")}),
        "lineage_digest": _digest({k: candidate.get(k) for k in ("triangle_map", "quad_map", "strip_map")}),
        "schedule_digest": _digest({"wall_loop": wall_loop, "co_normals": co_normals, "layer_heights": layer_heights, "requested_layers": int(requested_layers), "max_offset": float(max_offset)}),
        "threshold_profile_digest": _digest({"skew_p95": .25, "skew_p99": .40, "skew_max": .50, "aspect_max": 10., "wall_max": 25., "adjacent_max": 50.}),
        "canonical_input_digest": canonical_input_digest,
    }
    try:
        kernel = import_native_extension("native_tri_quad_producer_auditor_quality_gate")
        return dict(kernel.commit(candidate, dict(certificate), bindings, int(requested_layers), float(max_offset)))
    except Exception as exc:  # noqa: BLE001
        return {
            "accepted": False,
            "status": "tri_quad_producer_auditor_quality_gate_rolled_back",
            "reason": f"gate_unavailable:{type(exc).__name__}",
            "committed": False,
            "candidate_discarded": True,
            "publication_eligible": False,
            "runtime_route": "private_default_off",
            "route_calls": 0,
            "actual_layers": 0,
        }
