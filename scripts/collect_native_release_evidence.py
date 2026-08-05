"""Collect measured native release rows; never invent authority claims."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.evaluator.native_hex_poly_actual_matrix import (
    audit_actual_native_hex_poly_case,
    validate_actual_native_hex_poly_matrix,
)
from core.evaluator.native_release_authority_gate import (
    validate_native_release_authority_matrix,
    validate_native_surface_quality_binding,
)
from core.evaluator.native_artifact_digest import native_artifact_witness
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
        if path.is_file():
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
        return audit_strict_surface_topology(
            vertices, np.asarray(faces, dtype=np.int64)
        ).as_dict()
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
    if dirs:
        certificate = row.get("source_output_authority")
        if isinstance(certificate, dict):
            certificate = dict(certificate)
            root = Path(".") if kind == "surface" else Path("constant/polyMesh")
            certificate["native_artifact_digest"] = native_artifact_witness(dirs, root)
            row["source_output_authority"] = certificate
    if dirs and kind == "surface":
        audits = [surface_audit(x) for x in dirs]
        hashes = [surface_digest(x) for x in dirs]
        row["strict_topology"] = audits[0]
        declared = case.get("repeatability")
        independent = (
            declared.get("independent_route")
            if isinstance(declared, dict)
            else False
        )
        row["repeatability"] = {
            "run_count": len(dirs),
            "byte_identical": bool(
                len(dirs) >= 3 and None not in hashes and len(set(hashes)) == 1
            ),
            "independent_route": independent if type(independent) is bool else False,
            "artifact_sha256": [audit.get("artifact_sha256") for audit in audits],
            "strict_audits": audits,
        }
    elif dirs:
        audits = [audit_strict_volume_topology(x).as_dict() for x in dirs]
        hashes = [digest(x) for x in dirs]
        row["strict_topology"] = audits[0]
        declared = case.get("repeatability")
        independent = (
            declared.get("independent_route")
            if isinstance(declared, dict)
            else False
        )
        row["repeatability"] = {
            "run_count": len(dirs),
            "byte_identical": bool(
                len(dirs) >= 3 and None not in hashes and len(set(hashes)) == 1
            ),
            "independent_route": independent if type(independent) is bool else False,
            "artifact_sha256": hashes,
            "strict_audits": audits,
        }
    row.setdefault("strict_topology", {"status": "unverified", "valid": False})
    row.setdefault("repeatability", case.get("repeatability", {"status": "unverified"}))
    if kind == "surface":
        row["surface_quality_binding"] = validate_native_surface_quality_binding(row)
    return row


def collect_hex_poly_actual_audit(spec_path: Path) -> dict:
    spec = load(spec_path)
    values = spec.get("cases") if isinstance(spec, dict) else None
    rows = []
    if not isinstance(values, list):
        return validate_actual_native_hex_poly_matrix(rows)
    for item in values:
        if not isinstance(item, dict):
            rows.append({"case_id": "<malformed>", "accepted": False})
            continue
        try:
            result = audit_actual_native_hex_poly_case(
                Path(item["case_dir"]),
                engine=str(item["engine"]),
                source_path=Path(item["source_path"]),
                requested_layers=int(item["requested_layers"]),
                baseline_case_dir=(
                    Path(item["baseline_case_dir"])
                    if item.get("baseline_case_dir")
                    else None
                ),
                cad_authority=item.get("cad_authority"),
            ).as_dict()
            result["case_id"] = item.get("case_id", item.get("case_dir"))
        except (KeyError, TypeError, ValueError, OSError) as exc:
            result = {
                "case_id": item.get("case_id", "<invalid>"),
                "accepted": False,
                "status": "UNVERIFIED",
                "reasons": [f"audit_exception:{type(exc).__name__}"],
            }
        rows.append(result)
    return validate_actual_native_hex_poly_matrix(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec", type=Path)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--authority-evidence", type=Path, required=True)
    ap.add_argument(
        "--hex-poly-actual-audit",
        type=Path,
        help="Optional separate JSON sidecar spec/output for actual Hex/Poly audit.",
    )
    args = ap.parse_args()
    spec = load(args.spec)
    values = spec.get("cases") if isinstance(spec, dict) else None
    manifest = {
        "schema": RELEASE_MATRIX_SCHEMA,
        "cases": [collect(x) for x in values] if isinstance(values, list) else [],
    }
    audit = validate_native_release_authority_matrix(
        manifest, require_quality_witness=True
    )
    args.output.write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    args.authority_evidence.write_text(
        json.dumps(audit.as_dict(), sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    if args.hex_poly_actual_audit:
        actual = collect_hex_poly_actual_audit(args.hex_poly_actual_audit)
        sidecar = args.hex_poly_actual_audit.parent / "native_hex_poly_actual_audit.json"
        sidecar.write_text(
            json.dumps(actual, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
    return 0 if audit.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
