from __future__ import annotations

import hashlib
import re
import struct
from collections import defaultdict
from pathlib import Path
from typing import Any

import pytest

native_ingress = pytest.importorskip("native_surface_stl_authority_ingress")

from core.layers.native_bl_atomic_certificate import canonical_bytes


BENCHMARKS = Path(__file__).parent / "benchmarks"


def _triangles(path: Path) -> tuple[str, list[tuple[bytes, bytes, bytes]]]:
    data = path.read_bytes()
    if len(data) >= 84 and 84 + struct.unpack_from("<I", data, 80)[0] * 50 == len(data):
        count = struct.unpack_from("<I", data, 80)[0]
        return "binary_stl", [
            tuple(data[84 + index * 50 + 12 + vertex * 12 : 84 + index * 50 + 24 + vertex * 12] for vertex in range(3))
            for index in range(count)
        ]
    text = data.decode("ascii")
    values = re.findall(r"vertex\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)", text)
    vertices = [struct.pack("<fff", float(x), float(y), float(z)) for x, y, z in values]
    return "ascii_stl", [tuple(vertices[index : index + 3]) for index in range(0, len(vertices), 3)]


def _sidecar(path: Path) -> dict[str, Any]:
    source_format, raw_triangles = _triangles(path)
    vertex_ids: dict[bytes, int] = {}
    facets: list[tuple[int, int, int]] = []
    edges: dict[tuple[int, int], list[tuple[int, int, int]]] = defaultdict(list)
    for face, triangle in enumerate(raw_triangles):
        ids = []
        for raw in triangle:
            if raw not in vertex_ids:
                vertex_ids[raw] = len(vertex_ids)
            ids.append(vertex_ids[raw])
        facets.append(tuple(ids))
        for index in range(3):
            first, second = ids[index], ids[(index + 1) % 3]
            edges[tuple(sorted((first, second)))].append((face, first, second))
    boundary = [uses[0] for uses in edges.values() if len(uses) == 1]
    sidecar: dict[str, Any] = {
        "schema": "NativeSurfaceAuthoritySidecar/v2",
        "source_kind": "stl",
        "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "source_format": source_format,
        "provenance": f"repository-benchmark:{path.name}",
        "entity_count": len(facets),
        "canonical_facet_count": len(facets),
        "canonical_vertex_count": len(vertex_ids),
        "canonical_boundary_edge_count": len(boundary),
        "canonical_facet_ids": list(range(len(facets))),
        "canonical_vertex_ids": list(range(len(vertex_ids))),
        "entities": [
            {
                "entity_id": index,
                "patch": "wall",
                "feature": "smooth-surface",
                "physical_group": "fluid-wall",
                "component": path.stem,
            }
            for index in range(len(facets))
        ],
        "directed_wall_curves": [
            {
                "curve_id": "rim-0",
                "directed_edges": [[first, second, face] for face, first, second in boundary],
            }
        ] if boundary else [],
        "physical_group_map": {"fluid-wall": 1},
    }
    return sidecar


@pytest.mark.parametrize("name", ["hemisphere_open.stl", "cube.stl"])
def test_native_stl_ingress_recomputes_source_ids_and_directed_rim(name: str) -> None:
    source = BENCHMARKS / name
    sidecar = _sidecar(source)
    sidecar_sha = hashlib.sha256(canonical_bytes(sidecar)).hexdigest()
    first = native_ingress.validate_stl_file(str(source), sidecar, sidecar_sha)
    second = native_ingress.validate_stl_file(str(source), sidecar, sidecar_sha)
    assert first["accepted"] is True, first
    assert first == second
    assert first["canonical_ids_verified"] is True
    assert first["directed_wall_edges_verified"] is True
    assert first["runtime_route"] == "private_default_off"


def test_native_stl_ingress_refuses_tampered_boundary_coverage() -> None:
    source = BENCHMARKS / "hemisphere_open.stl"
    sidecar = _sidecar(source)
    sidecar["canonical_boundary_edge_count"] += 1
    sidecar_sha = hashlib.sha256(canonical_bytes(sidecar)).hexdigest()
    result = native_ingress.validate_stl_file(str(source), sidecar, sidecar_sha)
    assert result["accepted"] is False
    assert result["candidate_discarded"] is True
    assert result["reason"] == "canonical_boundary_edge_count_mismatch"
