from __future__ import annotations

import copy
from collections import defaultdict
from pathlib import Path

import numpy as np
import pytest

from core.analyzer.readers import read_stl
from core.preprocessor.native_tri.cad_stl_authority_ingress import (
    make_external_trust_anchor,
    semantic_ledger_from_faces,
    validate_native_tri_authority_source,
)
from core.preprocessor.native_tri.planar_face_pair_bl_template import (
    make_planar_face_pair_template_anchor,
    write_native_tri_planar_face_pair_bl,
)
from core.preprocessor.native_tri.wall_edge_bl_preflight import (
    make_external_edge_trust_anchor,
    validate_native_tri_wall_edge_bl_preflight,
)


def _canonical_stl(path: Path) -> tuple[np.ndarray, np.ndarray]:
    mesh = read_stl(path, dedupe=False)
    ids: dict[tuple[float, float, float], int] = {}
    points: list[tuple[float, float, float]] = []
    for point in np.asarray(mesh.vertices, dtype=np.float64):
        key = tuple(0.0 if float(v) == 0.0 else float(v) for v in point)
        if key not in ids:
            ids[key] = len(points)
            points.append(key)
    faces = [
        [
            ids[tuple(0.0 if float(v) == 0.0 else float(v) for v in mesh.vertices[int(vertex)])]
            for vertex in face
        ]
        for face in np.asarray(mesh.faces, dtype=np.int64)
    ]
    return np.asarray(points), np.asarray(faces, dtype=np.int64)


def _fixture(path: Path):
    points, faces = _canonical_stl(path)
    labels = semantic_ledger_from_faces(
        faces,
        feature="cube-wall",
        patch="cube-pair-wall",
        physical_group="cube-physical-wall",
        component="cube",
        provenance="registered-face-pair",
    )
    source_anchor = make_external_trust_anchor(
        path, labels, issuer="tri-pair-test", key_id="tri-pair-v1"
    )
    certificate = validate_native_tri_authority_source(
        path, labels, source_anchor, requested_layers=0
    )
    assert certificate["accepted"] is True, certificate

    occurrences: dict[tuple[int, int], list[int]] = defaultdict(list)
    for face_id, face in enumerate(faces):
        for local in range(3):
            a = int(face[local])
            b = int(face[(local + 1) % 3])
            occurrences[tuple(sorted((a, b)))].append(face_id)

    pair_faces = (0, 2)
    directed: list[tuple[int, int, int]] = []
    for face_id in pair_faces:
        face = faces[face_id]
        for local in range(3):
            a = int(face[local])
            b = int(face[(local + 1) % 3])
            if len(occurrences[tuple(sorted((a, b)))]) == 2:
                other = occurrences[tuple(sorted((a, b)))]
                if not all(value in pair_faces for value in other):
                    directed.append((a, b, face_id))
    assert len(directed) == 4
    start = min(directed)
    loop = [start]
    while len(loop) < 4:
        current = loop[-1][1]
        choices = [value for value in directed if value[0] == current and value not in loop]
        assert len(choices) == 1
        loop.append(choices[0])
    assert loop[-1][1] == loop[0][0]

    rows = []
    active = []
    for index, (a, b, active_face) in enumerate(loop):
        incident = sorted(occurrences[tuple(sorted((a, b)))])
        rows.append(
            {
                "edge_id": f"cube-pair-edge-{index}",
                "endpoint_vertex_ids": [a, b],
                "incident_face_ids": incident,
                "directed_sector_face_ids": incident,
                "directed_sector_ids": [f"sector-{value}" for value in incident],
                "wall_role": "wall",
                "patch_boundary_role": "cube-pair-boundary",
                "feature": "cube-wall",
                "patch": "cube-pair-wall",
                "physical_group": "cube-physical-wall",
                "component": "cube",
                "provenance": "registered-face-pair",
            }
        )
        active.append(active_face)
    return points, faces, certificate, rows, pair_faces, active


def _registered(certificate, rows, pair_faces, active, *, layers, height, growth):
    edge_anchor = make_external_edge_trust_anchor(
        certificate,
        rows,
        loop_policy="closed_nonbranching",
        issuer="tri-pair-edge-registry",
        key_id="tri-pair-edge-v1",
    )
    preflight = validate_native_tri_wall_edge_bl_preflight(
        certificate,
        rows,
        edge_anchor,
        requested_layers=layers,
        first_height=height,
        growth_ratio=growth,
    )
    assert preflight["accepted"] is True, preflight
    template = make_planar_face_pair_template_anchor(
        certificate,
        edge_anchor,
        preflight,
        source_face_ids=pair_faces,
        wall_edge_ids=[row["edge_id"] for row in rows],
        active_sector_face_ids=active,
        feature="cube-wall",
        patch="cube-pair-wall",
        physical_group="cube-physical-wall",
        component="cube",
        provenance="registered-face-pair",
    )
    return edge_anchor, template


def test_bl0_is_exact_identity(tmp_path: Path):
    points, faces, certificate, rows, pair_faces, active = _fixture(
        Path("tests/benchmarks/cube.stl")
    )
    edge_anchor, template = _registered(
        certificate, rows, pair_faces, active, layers=0, height=0.0, growth=1.0
    )
    result = write_native_tri_planar_face_pair_bl(
        certificate, rows, edge_anchor, template,
        requested_layers=0, first_height=0.0, growth_ratio=1.0,
    )
    assert result["accepted"] is True, result
    assert result["status"] == "native_tri_planar_face_pair_bl_identity"
    assert result["bl0_identity"] is True
    assert result["writer_invoked"] is False
    assert np.array_equal(np.asarray(result["output_vertices"]), points)
    assert np.array_equal(np.asarray(result["output_faces"]), faces)
    assert result["generated_faces"] == []


def test_cube_bl1_refuses_when_strict_raw_metric_gate_is_unachievable():
    _points, _faces, certificate, rows, pair_faces, active = _fixture(
        Path("tests/benchmarks/cube.stl")
    )
    edge_anchor, template = _registered(
        certificate, rows, pair_faces, active, layers=1, height=0.20, growth=1.0
    )
    result = write_native_tri_planar_face_pair_bl(
        certificate, rows, edge_anchor, template,
        requested_layers=1, first_height=0.20, growth_ratio=1.0,
    )
    assert result["accepted"] is False, result
    assert result["reason"] == "pair_no_quality_admissible_ring"
    assert result["actual_layers"] == 0
    assert result["generated_faces"] == []
    assert result["output_faces"] == []
    assert result["atomic_rollback"] is True
    assert result["best_ring_mask"] == 15
    assert all(
        witness["raw_angle_nonorthogonality_degrees"] >= 75.0 - 1e-12
        or witness["metric_aspect_ratio"] > 1.60
        for witness in result["quality_witness"]
    )


def test_cube_bl3_refuses_when_requested_schedule_cannot_meet_raw_quality():
    _points, _faces, certificate, rows, pair_faces, active = _fixture(
        Path("tests/benchmarks/cube.stl")
    )
    edge_anchor, template = _registered(
        certificate, rows, pair_faces, active, layers=3, height=0.15, growth=1.0
    )
    result = write_native_tri_planar_face_pair_bl(
        certificate, rows, edge_anchor, template,
        requested_layers=3, first_height=0.15, growth_ratio=1.0,
    )
    assert result["accepted"] is False, result
    assert result["actual_layers"] == 0
    assert result["generated_faces"] == []
    assert result["atomic_rollback"] is True


@pytest.mark.parametrize("tamper", ("face", "edge", "digest", "label"))
def test_authority_tamper_is_atomic(tamper: str):
    _points, _faces, certificate, rows, pair_faces, active = _fixture(
        Path("tests/benchmarks/cube.stl")
    )
    edge_anchor, template = _registered(
        certificate, rows, pair_faces, active, layers=1, height=0.20, growth=1.0
    )
    forged_rows = copy.deepcopy(rows)
    forged_template = copy.deepcopy(template)
    if tamper == "face":
        forged_template["source_face_ids"] = [0, 1]
    elif tamper == "edge":
        forged_template["wall_edge_ids"][0] = "forged-edge"
    elif tamper == "digest":
        forged_template["preflight_digest"] = "0" * 64
    else:
        forged_rows[0]["feature"] = "forged"
    result = write_native_tri_planar_face_pair_bl(
        certificate, forged_rows, edge_anchor, forged_template,
        requested_layers=1, first_height=0.20, growth_ratio=1.0,
    )
    assert result["accepted"] is False, result
    assert result["actual_layers"] == 0
    assert result["output_faces"] == []
    assert result["atomic_rollback"] is True
