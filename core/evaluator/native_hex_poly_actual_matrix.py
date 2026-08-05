"""Read-only actual Hex/Poly artifact audit.

This module deliberately separates measured mesh facts from release authority.
It never repairs a mesh, invents labels, promotes a route, or treats a sidecar
as proof of geometry.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from core.evaluator.strict_volume_topology import audit_strict_volume_topology
from core.evaluator.native_canonical_quality_witness import build_canonical_volume_quality_witness


_WITNESS_NAMES = ("native_quality_witness.json", "quality_witness.json")
_BL_STATE = "native_bl_state.json"
_BL_QUALITY = "native_bl_quality.json"


def _sha256_path(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except (OSError, ValueError):
        return None


def _load(path: Path) -> Mapping[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, Mapping) else None


def _digest(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and value == value.lower()
        and all(c in "0123456789abcdef" for c in value)
    )


def _positive(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def _artifact_digest(case_dir: Path) -> str | None:
    audit = audit_strict_volume_topology(case_dir)
    return audit.artifact_sha256


def _find_witness(case_dir: Path) -> tuple[Path | None, Mapping[str, Any] | None]:
    for name in _WITNESS_NAMES:
        path = case_dir / name
        if path.is_file():
            return path, _load(path)
    return None, None


def _quality_record(
    case_dir: Path,
    witness: Mapping[str, Any] | None,
    artifact_sha256: str | None,
    source_sha256: str | None,
) -> tuple[dict[str, Any], list[str]]:
    reasons: list[str] = []
    path, payload = _find_witness(case_dir)
    result: dict[str, Any] = {
        "witness_path": str(path) if path else None,
        "witness_present": payload is not None,
        "cpp": False,
    }
    if payload is None:
        measured = build_canonical_volume_quality_witness(case_dir)
        if measured.get("accepted") is True:
            metrics = measured.get("quality", {})
            non_ortho = metrics.get("internal_non_orthogonality", {})
            skew = metrics.get("release_skew", {})
            aspect = metrics.get("aspect_ratio", {})
            native_summary = dict(measured)
            native_summary.pop("faces", None)
            volume_summary = dict(native_summary.get("volume_quality", {}))
            volume_summary.pop("cells", None)
            native_summary["volume_quality"] = volume_summary
            metric_values = {
                "p95_non_ortho_deg": non_ortho.get("p95"),
                "p99_non_ortho_deg": non_ortho.get("p99"),
                "max_non_ortho_deg": non_ortho.get("max"),
                "p95_skewness": skew.get("p95"),
                "p99_skewness": skew.get("p99"),
                "max_skewness": skew.get("max"),
                "p95_aspect_ratio": aspect.get("p95"),
                "p99_aspect_ratio": aspect.get("p99"),
                "max_aspect_ratio": aspect.get("max"),
                "worst_uid": aspect.get("worst_uid"),
                "mapping_coverage": measured.get("full_population") is True,
            }
            result.update({
                "witness_present": True,
                "witness_source": "on_readback_cpp",
                "cpp": True,
                "digest": measured.get("witness_sha256"),
                "metrics": metric_values,
                "native_measurement": native_summary,
                **{key: value for key, value in metric_values.items()
                   if key != "mapping_coverage"},
            })
            return result, reasons
        reasons.append("quality_cpp_witness_unavailable")
        result["witness_reason"] = measured.get("reason", "unavailable")
        return result, reasons
    schema = payload.get("schema")
    if not isinstance(schema, str) or not schema.startswith("autotessell/"):
        reasons.append("quality_witness_schema")
    if payload.get("implementation") not in {"cpp", "c++", "native_cpp"}:
        reasons.append("quality_cpp_witness_not_cpp")
    witness_digest = payload.get("digest", payload.get("witness_digest"))
    if not _digest(witness_digest):
        reasons.append("quality_witness_digest")
    if source_sha256 and payload.get("source_sha256") != source_sha256:
        reasons.append("quality_source_binding")
    if artifact_sha256 and payload.get("output_artifact_sha256") != artifact_sha256:
        reasons.append("quality_output_binding")
    metrics = payload.get("metrics")
    metrics = metrics if isinstance(metrics, Mapping) else payload
    required = ("p95_non_ortho_deg", "p99_non_ortho_deg", "max_non_ortho_deg",
                "p95_skewness", "p99_skewness", "max_skewness",
                "p95_aspect_ratio", "p99_aspect_ratio", "max_aspect_ratio",
                "worst_uid", "mapping_coverage")
    for key in required:
        if key not in metrics:
            reasons.append("quality_metric_missing:" + key)
    for key in required[0:9]:
        value = metrics.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            reasons.append("quality_metric_invalid:" + key)
    if metrics.get("mapping_coverage") is not True:
        reasons.append("quality_mapping_coverage")
    result.update({
        "cpp": not reasons,
        "digest": witness_digest,
        "metrics": dict(metrics) if isinstance(metrics, Mapping) else {},
    })
    if isinstance(metrics, Mapping):
        result["max_non_ortho_deg"] = metrics.get("max_non_ortho_deg")
        result["max_skewness"] = metrics.get("max_skewness")
        result["max_aspect_ratio"] = metrics.get("max_aspect_ratio")
        result["worst_uid"] = metrics.get("worst_uid")
    return result, reasons


def _authority_record(
    engine: str,
    source_path: Path,
    source_sha256: str | None,
    authority: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], list[str]]:
    reasons: list[str] = []
    result = {
        "engine": engine,
        "source_path": str(source_path),
        "source_exists": source_path.is_file(),
        "source_sha256": source_sha256,
        "authority_ready": False,
        "mapping_digest": None,
    }
    if source_sha256 is None:
        reasons.append("source_bytes_missing")
        return result, reasons
    if not isinstance(authority, Mapping):
        reasons.append("source_authority_mapping_missing")
        return result, reasons
    if authority.get("authority_ready") is not True:
        reasons.append("source_authority_not_ready")
    if authority.get("source_sha256") != source_sha256:
        reasons.append("source_authority_sha_mismatch")
    mapping_digest = authority.get("mapping_sha256",
                                  authority.get("label_mapping_sha256"))
    if not _digest(mapping_digest):
        reasons.append("source_authority_mapping_digest_missing")
    if authority.get("mapping_complete") is not True:
        reasons.append("source_authority_mapping_incomplete")
    if authority.get("canonical_geometry_sha256") is not None and not _digest(
        authority.get("canonical_geometry_sha256")
    ):
        reasons.append("source_authority_geometry_digest")
    result.update({
        "authority_ready": not reasons,
        "mapping_digest": mapping_digest,
        "canonical_geometry_sha256": authority.get("canonical_geometry_sha256"),
    })
    return result, reasons


def _bl_record(
    case_dir: Path,
    requested_layers: int,
    artifact_sha256: str | None,
    baseline_case_dir: Path | None,
) -> tuple[dict[str, Any], list[str]]:
    reasons: list[str] = []
    state = _load(case_dir / _BL_STATE)
    quality = _load(case_dir / _BL_QUALITY)
    result: dict[str, Any] = {
        "requested_layers": requested_layers,
        "actual_layers": state.get("actual_layers") if state else None,
        "state": state.get("state") if state else None,
        "state_present": state is not None,
        "quality_present": quality is not None,
        "quality": dict(quality) if quality else None,
    }
    if requested_layers < 0:
        reasons.append("bl_requested_invalid")
        return result, reasons
    if state is None:
        reasons.append("bl_state_missing")
        return result, reasons
    actual = state.get("actual_layers")
    if not isinstance(actual, int) or isinstance(actual, bool) or actual < 0:
        reasons.append("bl_actual_invalid")
    elif actual != requested_layers:
        reasons.append("bl_count_mismatch")
    if requested_layers == 0:
        if state.get("state") not in {"disabled", "disabled_identity", "completed"}:
            reasons.append("bl0_state")
        if baseline_case_dir is None:
            reasons.append("bl0_baseline_missing")
        else:
            baseline_digest = _artifact_digest(baseline_case_dir)
            result["baseline_artifact_sha256"] = baseline_digest
            if baseline_digest is None or baseline_digest != artifact_sha256:
                reasons.append("bl0_disabled_identity")
    else:
        if state.get("state") != "completed":
            reasons.append("bl_positive_not_completed")
        if quality is None:
            reasons.append("bl_quality_missing")
        else:
            if not _positive(quality.get("total_thickness")):
                reasons.append("bl_nonpositive_thickness")
            if not isinstance(quality.get("n_prism_cells"), int) or quality.get("n_prism_cells") <= 0:
                reasons.append("bl_nonpositive_cell_count")
            bad = quality.get("bad_internal_faces")
            if not isinstance(bad, Mapping):
                reasons.append("bl_partition_quality_missing")
            elif bad.get("n_bad_faces") != 0:
                reasons.append("bl_quality_failure")
            if quality.get("wall_preserve", {}).get("within_envelope") is not True:
                reasons.append("bl_wall_preservation")
    return result, reasons


@dataclass(frozen=True, slots=True)
class ActualHexPolyAudit:
    engine: str
    case_dir: str
    status: str
    accepted: bool
    reasons: tuple[str, ...]
    artifact_sha256: str | None
    source: Mapping[str, Any]
    topology: Mapping[str, Any]
    authority: Mapping[str, Any]
    boundary_layer: Mapping[str, Any]
    quality: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": "autotessell/native-hex-poly-actual-audit/v1",
            "engine": self.engine,
            "case_dir": self.case_dir,
            "status": self.status,
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "artifact_sha256": self.artifact_sha256,
            "source": dict(self.source),
            "topology": dict(self.topology),
            "authority": dict(self.authority),
            "boundary_layer": dict(self.boundary_layer),
            "quality": dict(self.quality),
        }


def audit_actual_native_hex_poly_case(
    case_dir: Path,
    *,
    engine: str,
    source_path: Path,
    requested_layers: int,
    baseline_case_dir: Path | None = None,
    cad_authority: Mapping[str, Any] | None = None,
) -> ActualHexPolyAudit:
    case_dir = Path(case_dir)
    source_path = Path(source_path)
    reasons: list[str] = []
    artifact_sha256 = _artifact_digest(case_dir)
    topology_obj = audit_strict_volume_topology(case_dir)
    topology = topology_obj.as_dict()
    if not topology_obj.valid:
        reasons.append("topology_not_strict")
    source_sha256 = _sha256_path(source_path)
    source, source_reasons = _authority_record(
        engine, source_path, source_sha256, cad_authority
    )
    reasons.extend(source_reasons)
    authority = source
    bl, bl_reasons = _bl_record(
        case_dir, requested_layers, artifact_sha256, baseline_case_dir
    )
    reasons.extend(bl_reasons)
    quality, quality_reasons = _quality_record(
        case_dir, None, artifact_sha256, source_sha256
    )
    reasons.extend(quality_reasons)
    unique_reasons = tuple(sorted(set(reasons)))
    refused_prefixes = ("topology_", "bl_quality", "bl_nonpositive",
                        "quality_metric_", "quality_mapping_")
    status = "ACCEPTED" if not unique_reasons else (
        "REFUSED" if any(
            reason.startswith(refused_prefixes) for reason in unique_reasons
        ) else "UNVERIFIED"
    )
    return ActualHexPolyAudit(
        engine=engine,
        case_dir=str(case_dir),
        status=status,
        accepted=not unique_reasons,
        reasons=unique_reasons,
        artifact_sha256=artifact_sha256,
        source=source,
        topology=topology,
        authority=authority,
        boundary_layer=bl,
        quality=quality,
    )


def validate_actual_native_hex_poly_matrix(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Validate repeatability and independent authority across audited rows."""
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        key = str(row.get("case_id", row.get("case_dir", "")))
        grouped.setdefault(key, []).append(row)
    reasons: list[str] = []
    accepted_rows = 0
    for key, group in sorted(grouped.items()):
        if not group:
            reasons.append(key + ":empty")
            continue
        if any(row.get("accepted") is not True for row in group):
            reasons.append(key + ":row_not_accepted")
        digests = [row.get("artifact_sha256") for row in group]
        if len(group) < 3 or None in digests or len(set(digests)) != 1:
            reasons.append(key + ":nondeterministic_or_less_than_three_runs")
        for row in group:
            if row.get("authority", {}).get("authority_ready") is not True:
                reasons.append(key + ":authority_not_ready")
        if all(row.get("accepted") is True for row in group):
            accepted_rows += 1
    return {
        "schema": "autotessell/native-hex-poly-actual-matrix/v1",
        "accepted": not reasons and bool(grouped),
        "status": "measured_complete" if not reasons and grouped else "unverified",
        "case_count": len(grouped),
        "accepted_case_count": accepted_rows if not reasons else 0,
        "reasons": sorted(set(reasons)),
        "rows": [dict(row) for row in rows],
    }


__all__ = [
    "ActualHexPolyAudit",
    "audit_actual_native_hex_poly_case",
    "validate_actual_native_hex_poly_matrix",
]
