"""Deterministic, report-only STL edge-incidence ledger."""

from __future__ import annotations

import hashlib
import struct
from collections import defaultdict
from pathlib import Path
from typing import Any


def _point_key(point: tuple[float, float, float]) -> tuple[float, float, float]:
    return tuple(float(value) for value in point)


def _parse_stl(path: Path) -> list[tuple[tuple[float, float, float], ...]]:
    data = path.read_bytes()
    if len(data) >= 84:
        count = struct.unpack_from("<I", data, 80)[0]
        if 84 + 50 * count == len(data):
            triangles = []
            for index in range(count):
                offset = 84 + 50 * index + 12
                values = struct.unpack_from("<9f", data, offset)
                triangles.append(tuple(_point_key(tuple(values[3 * i : 3 * i + 3])) for i in range(3)))
            return triangles
    vertices: list[tuple[float, float, float]] = []
    for line in data.decode("utf-8", errors="strict").splitlines():
        fields = line.strip().split()
        if len(fields) == 4 and fields[0].lower() == "vertex":
            vertices.append(_point_key((float(fields[1]), float(fields[2]), float(fields[3]))))
    if len(vertices) == 0 or len(vertices) % 3:
        raise ValueError("malformed_stl_triangle_stream")
    return [tuple(vertices[index : index + 3]) for index in range(0, len(vertices), 3)]


def build_stl_edge_ledger(path: str | Path, *, user_declared_wall: bool = True) -> dict[str, Any]:
    source = Path(path)
    raw = source.read_bytes()
    try:
        triangles = _parse_stl(source)
    except (UnicodeDecodeError, OSError, ValueError, struct.error) as exc:
        return {"status": "REFUSED", "reason": f"stl_parse_failure:{type(exc).__name__}", "release_eligible": False}
    incidences: defaultdict[tuple[tuple[float, float, float], tuple[float, float, float]], list[int]] = defaultdict(list)
    for facet, triangle in enumerate(triangles):
        for first, second in ((triangle[0], triangle[1]), (triangle[1], triangle[2]), (triangle[2], triangle[0])):
            edge = tuple(sorted((_point_key(first), _point_key(second))))
            incidences[edge].append(facet)
    records = []
    for edge, facets in sorted(incidences.items()):
        edge_payload = [list(edge[0]), list(edge[1])]
        edge_id = hashlib.sha256(repr(edge_payload).encode("utf-8")).hexdigest()
        incidence = len(facets)
        records.append({
            "edge_id": edge_id,
            "endpoint_a": list(edge[0]),
            "endpoint_b": list(edge[1]),
            "incident_facets": sorted(facets),
            "incidence": incidence,
            "status": "PROVISIONAL_TOPOLOGICAL_BOUNDARY" if incidence == 1 and user_declared_wall else (
                "NON_MANIFOLD" if incidence > 2 else "MANIFOLD"
            ),
            "feature_authoritative": False,
            "wall_edge_authoritative": False,
        })
    digest = hashlib.sha256(repr(records).encode("utf-8")).hexdigest()
    boundary = sum(record["incidence"] == 1 for record in records)
    nonmanifold = sum(record["incidence"] > 2 for record in records)
    return {
        "status": "USER_DECLARED_PROVISIONAL_EDGE_LEDGER",
        "reason": "topological_incidence_only",
        "source_path": str(source),
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "facet_count": len(triangles),
        "edge_count": len(records),
        "boundary_edge_count": boundary,
        "non_manifold_edge_count": nonmanifold,
        "edge_digest": digest,
        "edges": records,
        "feature_authority": False,
        "wall_edge_authority": False,
        "release_eligible": False,
        "runtime_route": "default_off",
    }
