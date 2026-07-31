"""Fail-closed evidence verifier for a first-party native release corpus.

This script consumes only an explicit JSON manifest and explicitly supplied
artifact directories.  It never runs a generator, checker, or evaluator and
can never emit a release ``PASS``.  Every malformed, missing, unsafe, or
non-matching datum is represented as ``UNVERIFIED`` evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

_REQUIRED_POLYMESH_FILES = ("points", "faces", "owner", "neighbour", "boundary")
_MANIFEST_SCHEMA = "autotessell/release-native-corpus/v1"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha256(value: object) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == 64
        and value == value.lower()
        and all(character in "0123456789abcdef" for character in value)
    )


def _safe_relative_path(value: object) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        return None
    return path


def _allowed_artifact_dirs(values: object) -> dict[str, Path] | None:
    if not isinstance(values, list) or not values:
        return None
    allowed: dict[str, Path] = {}
    for value in values:
        if not isinstance(value, (str, Path)):
            return None
        path = Path(value)
        if not path.is_dir() or path.is_symlink():
            return None
        resolved = path.resolve()
        key = str(resolved)
        if key in allowed:
            return None
        allowed[key] = resolved
    return allowed


def _manifest_artifact_dir(value: object, allowed: dict[str, Path]) -> Path | None:
    if not isinstance(value, str):
        return None
    path = Path(value)
    if not path.is_absolute() or path.is_symlink() or not path.is_dir():
        return None
    return allowed.get(str(path.resolve()))


def _safe_file(root: Path, relative: object) -> Path | None:
    path = _safe_relative_path(relative)
    if path is None:
        return None
    candidate = root / path
    if not candidate.is_file() or candidate.is_symlink():
        return None
    try:
        candidate.resolve().relative_to(root)
    except ValueError:
        return None
    return candidate


def _polymesh_identity(root: Path) -> dict[str, object] | None:
    poly_mesh = root / "constant" / "polyMesh"
    if not poly_mesh.is_dir() or poly_mesh.is_symlink():
        return None
    files: dict[str, str] = {}
    for name in _REQUIRED_POLYMESH_FILES:
        candidate = poly_mesh / name
        if not candidate.is_file() or candidate.is_symlink():
            return None
        files[name] = _sha256(candidate)
    return {
        "file_sha256": files,
        "sha256": hashlib.sha256(
            json.dumps(files, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
    }


def _expected_polymesh_identity(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    aggregate = value.get("sha256")
    files = value.get("file_sha256")
    if not _canonical_sha256(aggregate) or not isinstance(files, dict):
        return None
    if set(files) != set(_REQUIRED_POLYMESH_FILES) or not all(
        _canonical_sha256(digest) for digest in files.values()
    ):
        return None
    return {"sha256": aggregate, "file_sha256": dict(files)}


def _unverified_gate4_fields(value: object) -> tuple[str, ...] | None:
    if not isinstance(value, dict) or value.get("gate4_pass") is not False:
        return None
    current_metrics = value.get("actual_surface_metrics")
    legacy_fields = value.get("unverified_fields")
    if current_metrics is not None and legacy_fields is not None:
        return None
    if current_metrics is not None:
        if not isinstance(current_metrics, dict):
            return None
        fields = current_metrics.get("unverified_fields")
    else:
        fields = legacy_fields
    if (
        not isinstance(fields, list)
        or not fields
        or any(not isinstance(field, str) or not field for field in fields)
        or len(set(fields)) != len(fields)
    ):
        return None
    return tuple(fields)


def _quality_report_evidence(value: object) -> tuple[int, tuple[str, ...]] | None:
    """Extract checker and Gate-4 evidence from one exact quality report."""
    if not isinstance(value, dict) or not isinstance(value.get("evaluation_summary"), dict):
        return None
    summary = value["evaluation_summary"]
    checkmesh = summary.get("checkmesh")
    if not isinstance(checkmesh, dict):
        return None
    negative_volumes = checkmesh.get("negative_volumes")
    if isinstance(negative_volumes, bool) or not isinstance(negative_volumes, int):
        return None
    unverified_fields = _unverified_gate4_fields(summary.get("gate4_evidence"))
    if unverified_fields is None:
        return None
    return negative_volumes, unverified_fields


def _verify_case(case: object, allowed: dict[str, Path]) -> dict[str, object]:
    if not isinstance(case, dict) or not isinstance(case.get("id"), str) or not case["id"]:
        return {"status": "UNVERIFIED", "reason": "invalid_case_id"}
    source = case.get("source_snapshot")
    if not isinstance(source, dict):
        return {"id": case["id"], "status": "UNVERIFIED", "reason": "invalid_source_snapshot"}
    source_root = _manifest_artifact_dir(source.get("artifact_dir"), allowed)
    source_path = _safe_file(source_root, source.get("path")) if source_root else None
    expected_source_hash = source.get("sha256")
    if source_path is None or not _canonical_sha256(expected_source_hash):
        return {"id": case["id"], "status": "UNVERIFIED", "reason": "invalid_source_snapshot"}
    if _sha256(source_path) != expected_source_hash:
        return {"id": case["id"], "status": "UNVERIFIED", "reason": "source_snapshot_hash_mismatch"}

    runs = case.get("runs")
    if not isinstance(runs, list) or len(runs) < 3:
        return {"id": case["id"], "status": "UNVERIFIED", "reason": "repeat_runs_required"}
    observed: list[dict[str, object]] = []
    used_dirs: set[str] = set()
    for run in runs:
        if not isinstance(run, dict):
            return {"id": case["id"], "status": "UNVERIFIED", "reason": "invalid_run"}
        artifact_dir = _manifest_artifact_dir(run.get("artifact_dir"), allowed)
        if artifact_dir is None or str(artifact_dir) in used_dirs:
            return {
                "id": case["id"],
                "status": "UNVERIFIED",
                "reason": "invalid_or_duplicate_artifact_dir",
            }
        used_dirs.add(str(artifact_dir))
        expected_mesh = _expected_polymesh_identity(run.get("poly_mesh"))
        actual_mesh = _polymesh_identity(artifact_dir)
        if expected_mesh is None or actual_mesh is None or actual_mesh != expected_mesh:
            return {
                "id": case["id"],
                "status": "UNVERIFIED",
                "reason": "polymesh_identity_mismatch",
            }
        expected_quality_report_hash = run.get("quality_report_sha256")
        if not _canonical_sha256(expected_quality_report_hash):
            return {
                "id": case["id"],
                "status": "UNVERIFIED",
                "reason": "quality_report_hash_required",
            }
        quality_report_path = _safe_file(artifact_dir, run.get("quality_report"))
        if quality_report_path is None:
            return {"id": case["id"], "status": "UNVERIFIED", "reason": "missing_quality_report"}
        actual_quality_report_hash = _sha256(quality_report_path)
        if actual_quality_report_hash != expected_quality_report_hash:
            return {
                "id": case["id"],
                "status": "UNVERIFIED",
                "reason": "quality_report_hash_mismatch",
            }
        try:
            quality_report = json.loads(quality_report_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {"id": case["id"], "status": "UNVERIFIED", "reason": "malformed_quality_report"}
        quality_evidence = _quality_report_evidence(quality_report)
        if quality_evidence is None:
            return {
                "id": case["id"],
                "status": "UNVERIFIED",
                "reason": "invalid_quality_report_schema",
            }
        negative_volumes, unverified_fields = quality_evidence
        if negative_volumes != 0:
            return {"id": case["id"], "status": "UNVERIFIED", "reason": "negative_volumes_not_zero"}
        observed.append(
            {
                "artifact_dir": str(artifact_dir),
                "poly_mesh_sha256": actual_mesh["sha256"],
                "quality_report_sha256": actual_quality_report_hash,
                "gate4_unverified_fields": unverified_fields,
            }
        )
    identities = {str(item["poly_mesh_sha256"]) for item in observed}
    if len(identities) != 1:
        return {"id": case["id"], "status": "UNVERIFIED", "reason": "repeat_polymesh_hash_mismatch"}
    return {
        "id": case["id"],
        "status": "UNVERIFIED",
        "reason": "measured_evidence_release_incomplete",
        "source_sha256": expected_source_hash,
        "repeat_poly_mesh_sha256": next(iter(identities)),
        "runs": tuple(observed),
    }


def verify_release_native_corpus(manifest: object, artifact_dirs: object) -> dict[str, object]:
    """Verify bounded evidence, always returning an ``UNVERIFIED`` release state."""
    allowed = _allowed_artifact_dirs(artifact_dirs)
    if (
        allowed is None
        or not isinstance(manifest, dict)
        or manifest.get("schema") != _MANIFEST_SCHEMA
        or not isinstance(manifest.get("cases"), list)
        or not manifest["cases"]
    ):
        return {"status": "UNVERIFIED", "reason": "invalid_manifest_or_artifact_dirs", "cases": ()}
    cases = tuple(_verify_case(case, allowed) for case in manifest["cases"])
    return {
        "status": "UNVERIFIED",
        "reason": "release_gate_evidence_incomplete",
        "cases": cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("artifact_dirs", nargs="+", type=Path)
    parser.add_argument("--evidence", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        manifest = json.loads(arguments.manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        manifest = None
    result = verify_release_native_corpus(manifest, arguments.artifact_dirs)
    arguments.evidence.write_text(json.dumps(result, sort_keys=True), encoding="utf-8")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
