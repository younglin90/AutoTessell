"""Collect measured native release rows; never invent authority claims."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.evaluator.native_release_authority_gate import validate_native_release_authority_matrix
from core.evaluator.native_release_matrix import RELEASE_MATRIX_SCHEMA
from core.evaluator.strict_surface_topology import audit_strict_surface_topology
from core.evaluator.strict_volume_topology import audit_strict_volume_topology


def load(path: Path):
    try:
        v = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return v if isinstance(v, dict) else None


def digest(case: Path):
    root = case / "constant" / "polyMesh"
    if not root.is_dir():
        return None
    h = hashlib.sha256()
    files = sorted(p for p in root.iterdir() if p.is_file())
    if not files:
        return None
    for p in files:
        h.update(p.name.encode())
        h.update(p.read_bytes())
    return h.hexdigest()


def surface_digest(case: Path):
    if not case.is_dir():
        return None
    h = hashlib.sha256()
    files = sorted(p for p in case.iterdir() if p.is_file())
    if not files:
        return None
    for path in files:
        h.update(path.name.encode())
        h.update(path.read_bytes())
    return h.hexdigest()


def surface_audit(case: Path):
    try:
        vertices = np.load(case / "vertices.npy", allow_pickle=False)
        triangles = (
            np.load(case / "triangles.npy", allow_pickle=False)
            if (case / "triangles.npy").is_file()
            else np.empty((0, 3), dtype=np.int64)
        )
        quads = (
            np.load(case / "quads.npy", allow_pickle=False)
            if (case / "quads.npy").is_file()
            else np.empty((0, 4), dtype=np.int64)
        )
        faces = [tuple(int(x) for x in row) for row in triangles]
        for row in quads:
            a, b, c, d = (int(x) for x in row)
            faces.extend(((a, b, c), (a, c, d)))
        return audit_strict_surface_topology(vertices, np.asarray(faces, dtype=np.int64)).as_dict()
    except (OSError, ValueError, TypeError):
        return {"kind": "surface", "status": "unverified", "valid": False}


def collect(case):
    if not isinstance(case, dict):
        return {"id": "<malformed>", "_collector_error": "case_not_object"}
    row = (
        dict(load(Path(case["evidence_path"])) or {})
        if isinstance(case.get("evidence_path"), str)
        else {}
    )
    keys = (
        "id",
        "engine",
        "fixture",
        "route",
        "source_authority",
        "surface",
        "features",
        "boundary_layer",
        "source_output_authority",
    )
    for key in keys:
        if key in case:
            row[key] = case[key]
    row["id"] = case.get("id", row.get("id", "<missing-id>"))
    vals = case.get("case_dirs", [])
    dirs = (
        [Path(x) for x in vals]
        if isinstance(vals, list) and all(isinstance(x, str) for x in vals)
        else []
    )
    kind = case.get("strict_topology_kind", "volume")
    if dirs and kind == "surface":
        audits = [surface_audit(x) for x in dirs]
        hashes = [surface_digest(x) for x in dirs]
        row["strict_topology"] = audits[0]
        declared = case.get("repeatability")
        independent = declared.get("independent_route") if isinstance(declared, dict) else False
        row["repeatability"] = {
            "run_count": len(dirs),
            "byte_identical": bool(len(dirs) >= 3 and None not in hashes and len(set(hashes)) == 1),
            "independent_route": independent if type(independent) is bool else False,
            "artifact_sha256": [audit.get("artifact_sha256") for audit in audits],
            "strict_audits": audits,
        }
    elif dirs:
        audits = [audit_strict_volume_topology(x).as_dict() for x in dirs]
        hashes = [digest(x) for x in dirs]
        row["strict_topology"] = audits[0]
        declared = case.get("repeatability")
        independent = declared.get("independent_route") if isinstance(declared, dict) else False
        row["repeatability"] = {
            "run_count": len(dirs),
            "byte_identical": bool(len(dirs) >= 3 and None not in hashes and len(set(hashes)) == 1),
            "independent_route": independent if type(independent) is bool else False,
            "artifact_sha256": hashes,
            "strict_audits": audits,
        }
    row.setdefault("strict_topology", {"status": "unverified", "valid": False})
    row.setdefault("repeatability", case.get("repeatability", {"status": "unverified"}))
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec", type=Path)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--authority-evidence", type=Path, required=True)
    args = ap.parse_args()
    spec = load(args.spec)
    values = spec.get("cases") if isinstance(spec, dict) else None
    manifest = {
        "schema": RELEASE_MATRIX_SCHEMA,
        "cases": [collect(x) for x in values] if isinstance(values, list) else [],
    }
    audit = validate_native_release_authority_matrix(manifest)
    args.output.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    args.authority_evidence.write_text(
        json.dumps(audit.as_dict(), sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    return 0 if audit.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
