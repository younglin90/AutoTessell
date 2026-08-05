"""Fail-closed source authority snapshots for the independent surface verifier."""

from __future__ import annotations

import hashlib
import struct
from pathlib import Path
from typing import Any, Mapping


SNAPSHOT_SCHEMA = "STLAuthoritySnapshot/v1"
CAD_SNAPSHOT_SCHEMA = "CADAuthoritySnapshot/v1"
REQUIRED_LEDGER_FIELDS = ("patch", "feature", "physical_group", "component")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _stl_facet_count(data: bytes) -> int | None:
    if len(data) >= 84:
        count = struct.unpack_from("<I", data, 80)[0]
        if 84 + 50 * count == len(data):
            return int(count)
    ascii_count = data.count(b"facet normal")
    return int(ascii_count) if ascii_count else None


def _ledger_status(ledger: Mapping[int, Mapping[str, Any]] | None, facet_count: int | None) -> tuple[bool, str]:
    if ledger is None or facet_count is None:
        return False, "missing_explicit_facet_authority_ledger"
    if set(ledger) != set(range(facet_count)):
        return False, "facet_authority_ledger_not_bijective"
    for record in ledger.values():
        if not isinstance(record, Mapping) or any(
            not isinstance(record.get(field), str) or not record[field].strip()
            for field in REQUIRED_LEDGER_FIELDS
        ):
            return False, "facet_authority_ledger_incomplete"
    return True, "explicit_facet_authority_ledger"


def build_stl_authority_snapshot(path: str | Path, *, ledger: Mapping[int, Mapping[str, Any]] | None = None) -> dict[str, Any]:
    source = Path(path)
    data = source.read_bytes()
    facet_count = _stl_facet_count(data)
    complete, reason = _ledger_status(ledger, facet_count)
    return {
        "schema": SNAPSHOT_SCHEMA,
        "path": str(source),
        "raw_sha256": _sha256_bytes(data),
        "facet_count": facet_count,
        "parser_version": "native-authority-snapshot-1",
        "authority_complete": complete,
        "reason": reason,
        "ledger": [dict(ledger[index]) for index in sorted(ledger)] if complete and ledger is not None else None,
    }


def build_cad_authority_snapshot(path: str | Path, *, mapping: Mapping[str, Any] | None = None) -> dict[str, Any]:
    source = Path(path)
    data = source.read_bytes()
    complete = isinstance(mapping, Mapping) and bool(mapping.get("face_edge_mapping")) and bool(mapping.get("physical_groups"))
    return {
        "schema": CAD_SNAPSHOT_SCHEMA,
        "path": str(source),
        "raw_sha256": _sha256_bytes(data),
        "authority_complete": complete,
        "reason": "explicit_brep_authority_mapping" if complete else "missing_explicit_brep_physical_group_mapping",
        "mapping": dict(mapping) if complete and mapping is not None else None,
        "display_metadata_promoted": False,
    }


def classify_snapshot(snapshot: Mapping[str, Any]) -> str:
    return "PASS_FOR_REVIEW" if snapshot.get("authority_complete") is True else "UNVERIFIED"


def build_real_source_matrix(root: str | Path) -> dict[str, Any]:
    root_path = Path(root)
    candidates = {
        "cube-stl": root_path / "tests/benchmarks/cube.stl",
        "sphere-stl": root_path / "tests/benchmarks/sphere_watertight.stl",
        "naca0012-stl": root_path / "tests/benchmarks/naca0012.stl",
        "complex-duct-stl": root_path / "tests/benchmarks/trimesh_duct.stl",
        "t-junction-cad": root_path / "tests/benchmarks/t_junction.step",
    }
    rows: list[dict[str, Any]] = []
    for case, path in candidates.items():
        if not path.is_file():
            rows.append({"case": case, "path": str(path), "status": "UNVERIFIED", "reason": "source_artifact_missing"})
            continue
        snapshot = (
            build_cad_authority_snapshot(path)
            if path.suffix.lower() in {".step", ".stp", ".xde"}
            else build_stl_authority_snapshot(path)
        )
        rows.append({"case": case, "path": str(path), "status": classify_snapshot(snapshot), "snapshot": snapshot})
    return {"schema": "NativeSurfaceBLRealSourceMatrix/v1", "route": "default_off", "rows": rows}
