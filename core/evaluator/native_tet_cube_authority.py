"""Pinned cube STL source authority ledger validator."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from core.analyzer.readers.stl import read_stl
from core.evaluator.native_authority_transaction_gate import canonical_sha256

LEDGER_SCHEMA = "autotessell/native-tet-cube-authority/v1"
DEFAULT_LEDGER = Path("docs/qa/authority/native_tet_cube_stl_authority_v1.json")
DEFAULT_SOURCE = Path("tests/benchmarks/cube.stl")


def _refuse(reason: str) -> dict[str, Any]:
    return {"accepted": False, "reason": reason}


def validate_cube_authority_ledger(
    ledger_path: str | Path = DEFAULT_LEDGER,
    source_path: str | Path = DEFAULT_SOURCE,
) -> dict[str, Any]:
    ledger_file = Path(ledger_path)
    source_file = Path(source_path)
    try:
        ledger = json.loads(ledger_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _refuse("ledger_unreadable")
    if ledger.get("schema") != LEDGER_SCHEMA:
        return _refuse("schema")
    source = ledger.get("source")
    if not isinstance(source, Mapping):
        return _refuse("source_record")
    if source.get("raw_sha256") != hashlib.sha256(source_file.read_bytes()).hexdigest():
        return _refuse("raw_sha256_mismatch")
    try:
        mesh = read_stl(source_file, dedupe=True)
    except Exception as error:
        return _refuse(f"source_parse:{type(error).__name__}")
    faces = mesh.faces.tolist()
    geometry_digest = canonical_sha256({
        "vertices": mesh.vertices.tolist(),
        "faces": faces,
    })
    if source.get("facet_count") != len(faces):
        return _refuse("facet_count_mismatch")
    if source.get("canonical_geometry_sha256") != geometry_digest:
        return _refuse("canonical_geometry_mismatch")
    facets = ledger.get("facets")
    if not isinstance(facets, list) or len(facets) != len(faces):
        return _refuse("facet_ledger_count")
    seen: set[int] = set()
    for record in facets:
        if not isinstance(record, Mapping):
            return _refuse("facet_record")
        facet_id = record.get("facet_id")
        if not isinstance(facet_id, int) or facet_id in seen or not 0 <= facet_id < len(faces):
            return _refuse("facet_id")
        seen.add(facet_id)
        if record.get("canonical_vertices") != [int(value) for value in faces[facet_id]]:
            return _refuse("facet_geometry_mismatch")
        if record.get("patch") != "wall" or record.get("physical_group") != "wall":
            return _refuse("facet_binding")
        if record.get("component") != 0:
            return _refuse("facet_component")
    if seen != set(range(len(faces))):
        return _refuse("facet_id_bijection")
    authority = ledger.get("authority")
    if not isinstance(authority, Mapping):
        return _refuse("authority_record")
    if authority.get("patches") != ["wall"] or authority.get("physical_groups") != ["wall"]:
        return _refuse("authority_groups")
    if authority.get("components") != [0]:
        return _refuse("authority_components")
    return {
        "accepted": True,
        "schema": LEDGER_SCHEMA,
        "source_sha256": source["raw_sha256"],
        "canonical_geometry_sha256": geometry_digest,
        "facet_count": len(faces),
        "patches": ["wall"],
        "physical_groups": ["wall"],
        "components": [0],
        "feature_policy": authority.get("feature_policy"),
    }


__all__ = ["DEFAULT_LEDGER", "DEFAULT_SOURCE", "validate_cube_authority_ledger"]
