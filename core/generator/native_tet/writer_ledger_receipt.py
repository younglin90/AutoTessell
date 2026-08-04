"""Bridge writer-owned Tet BL ledger IDs into the receipt graph schema."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def interface_children_from_writer_ledger(path: str | Path) -> list[dict[str, Any]]:
    """Return explicit disk-boundary child rows without geometric matching."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    result: list[dict[str, Any]] = []
    for record in payload.get("records", []):
        children = record.get("children", {})
        boundary_faces = children.get("boundary_faces", [])
        if not isinstance(boundary_faces, list) or not boundary_faces:
            continue
        result.append({
            "source_face": str(record["source_face_id"]),
            "source_vertex_ids": [int(v) for v in record["source_vertex_ids"]],
            "children": [
                {
                    "output_face_id": str(child["output_face_id"]),
                    "disk_face_id": int(child["disk_face_id"]),
                    "output_vertex_ids": [int(v) for v in child["vertex_ids"]],
                }
                for child in boundary_faces
            ],
            "feature": str(record["feature"]),
            "patch": str(record["patch"]),
            "physical_group": str(record["physical_group"]),
            "component": str(record["component"]),
            "provenance": str(record["provenance"]),
        })
    return result


__all__ = ["interface_children_from_writer_ledger"]
