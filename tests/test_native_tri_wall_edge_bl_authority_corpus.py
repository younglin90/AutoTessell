from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from core.analyzer.readers import read_stl
from core.preprocessor.native_tri.cad_stl_authority_ingress import (
    make_external_trust_anchor,
    semantic_ledger_from_faces,
    validate_native_tri_authority_source,
)
from core.preprocessor.native_tri.wall_edge_bl_preflight import (
    make_external_edge_trust_anchor,
    validate_native_tri_wall_edge_bl_preflight,
)


def _canonical_stl(path: Path) -> tuple[np.ndarray, np.ndarray]:
    mesh = read_stl(path, dedupe=False)
    point_ids: dict[tuple[float, float, float], int] = {}
    points: list[tuple[float, float, float]] = []
    for point in np.asarray(mesh.vertices, dtype=np.float64):
        key = tuple(0.0 if float(value) == 0.0 else float(value) for value in point)
        if key not in point_ids:
            point_ids[key] = len(points)
            points.append(key)
    faces = [
        [
            point_ids[
                tuple(
                    0.0 if float(value) == 0.0 else float(value)
                    for value in mesh.vertices[int(vertex)]
                )
            ]
            for vertex in face
        ]
        for face in np.asarray(mesh.faces, dtype=np.int64)
    ]
    return np.asarray(points, dtype=np.float64), np.asarray(faces, dtype=np.int64)


@pytest.mark.parametrize("name", ("cube.stl", "sphere_watertight.stl", "naca0012.stl"))
def test_actual_source_corpus_requires_explicit_wall_edge_authority(name: str):
    source = Path("tests/benchmarks") / name
    _points, faces = _canonical_stl(source)
    ledger = semantic_ledger_from_faces(
        faces,
        feature=f"{source.stem}-surface",
        patch=f"{source.stem}-wall",
        physical_group=f"{source.stem}-physical-wall",
        component=source.stem,
        provenance="registered-release-stl-facet",
    )
    source_anchor = make_external_trust_anchor(
        source, ledger, issuer="tri-wall-corpus-registry", key_id="tri-corpus-v1"
    )
    certificate = validate_native_tri_authority_source(
        source, ledger, source_anchor, requested_layers=0
    )
    assert certificate["accepted"] is True, certificate
    assert certificate["certificate"]["topology"]["strict_zero"] is True

    edge_anchor = make_external_edge_trust_anchor(
        certificate,
        [],
        loop_policy="closed_nonbranching",
        issuer="tri-wall-corpus-registry",
        key_id="tri-edge-v1",
    )
    result = validate_native_tri_wall_edge_bl_preflight(
        certificate,
        [],
        edge_anchor,
        requested_layers=1,
        first_height=0.02,
        growth_ratio=1.2,
    )
    assert result["accepted"] is False, result
    assert result["reason"] == "tri_wall_edge_ledger_empty"
    assert result["generated_faces"] == []
    assert result["actual_layers"] == 0
