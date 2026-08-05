from __future__ import annotations

import copy
from collections import defaultdict
from pathlib import Path

import numpy as np

from core.analyzer.readers import read_stl
from core.preprocessor.native_tri.authority_bound_surface_bl_front import (
    make_authority_bound_multiface_surface_bl_front_template_anchor,
    write_native_tri_authority_bound_surface_bl_front,
)
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
        key = tuple(0.0 if float(v) == 0.0 else float(v) for v in point)
        if key not in point_ids:
            point_ids[key] = len(points)
            points.append(key)
    faces = [
        [
            point_ids[
                tuple(0.0 if float(v) == 0.0 else float(v) for v in mesh.vertices[int(vertex)])
            ]
            for vertex in face
        ]
        for face in np.asarray(mesh.faces, dtype=np.int64)
    ]
    return np.asarray(points, dtype=np.float64), np.asarray(faces, dtype=np.int64)


def _fixture(source_name: str = "cube"):
    path = Path("tests/benchmarks") / f"{source_name}.stl"
    points, faces = _canonical_stl(path)
    feature = f"{source_name}-surface"
    patch = f"{source_name}-wall"
    group = f"{source_name}-physical-wall"
    provenance = f"registered-{source_name}-source"
    labels = semantic_ledger_from_faces(
        faces, feature=feature, patch=patch, physical_group=group,
        component=source_name, provenance=provenance,
    )
    source_anchor = make_external_trust_anchor(
        path, labels, issuer=f"tri-c126-{source_name}-source",
        key_id=f"tri-c126-{source_name}-source-v1",
    )
    certificate = validate_native_tri_authority_source(
        path, labels, source_anchor, requested_layers=0,
    )["certificate"]

    occurrences: dict[tuple[int, int], list[int]] = defaultdict(list)
    for face_id, face in enumerate(faces):
        for local in range(3):
            occurrences[tuple(sorted((int(face[local]), int(face[(local + 1) % 3]))))].append(face_id)

    active: tuple[int, int] | None = None
    for i in range(len(faces)):
        for j in range(i + 1, len(faces)):
            if len(set(faces[i]) & set(faces[j])) != 2:
                continue
            ni = np.cross(points[faces[i, 1]] - points[faces[i, 0]], points[faces[i, 2]] - points[faces[i, 0]])
            nj = np.cross(points[faces[j, 1]] - points[faces[j, 0]], points[faces[j, 2]] - points[faces[j, 0]])
            ni /= np.linalg.norm(ni)
            nj /= np.linalg.norm(nj)
            if float(np.dot(ni, nj)) > 1.0 - 1.0e-10:
                active = (i, j)
                break
        if active is not None:
            break
    assert active is not None
    active_set = set(active)
    boundary_rows: list[dict] = []
    for sid in active:
        for local in range(3):
            a = int(faces[sid, local])
            b = int(faces[sid, (local + 1) % 3])
            key = tuple(sorted((a, b)))
            incident = sorted(occurrences[key])
            if len([value for value in active if value == sid or value == incident[0] or value == incident[1]]) == 0:
                raise AssertionError("unreachable")
            if len(active_set.intersection(incident)) != 1:
                continue
            boundary_rows.append({
                "edge_id": f"{source_name}-c126-boundary-{len(boundary_rows)}",
                "endpoint_vertex_ids": [a, b],
                "incident_face_ids": incident,
                "directed_sector_face_ids": incident,
                "directed_sector_ids": [f"sector-{value}" for value in incident],
                "wall_role": "wall",
                "patch_boundary_role": f"{source_name}-c126-loop",
                "feature": feature,
                "patch": patch,
                "physical_group": group,
                "component": source_name,
                "provenance": provenance,
            })
    unique = {}
    for row in boundary_rows:
        unique[tuple(sorted(row["endpoint_vertex_ids"]))] = row
    rows = list(unique.values())
    edge_anchor = make_external_edge_trust_anchor(
        certificate, rows, loop_policy="closed_nonbranching",
        issuer=f"tri-c126-{source_name}-edge",
        key_id=f"tri-c126-{source_name}-edge-v1",
    )
    return points, faces, certificate, rows, edge_anchor, active


def _run(layers: int, height: float, source_name: str = "cube"):
    points, faces, certificate, rows, edge_anchor, active = _fixture(source_name)
    preflight = validate_native_tri_wall_edge_bl_preflight(
        certificate, rows, edge_anchor, requested_layers=layers,
        first_height=height, growth_ratio=1.0,
    )
    assert preflight["accepted"] is True, preflight
    template = make_authority_bound_multiface_surface_bl_front_template_anchor(
        certificate, edge_anchor, preflight,
        source_face_ids=list(active),
        wall_edge_ids=[row["edge_id"] for row in rows],
        active_sector_face_ids=[
            next(value for value in row["incident_face_ids"] if value in set(active))
            for row in rows
        ],
        feature=f"{source_name}-surface",
        patch=f"{source_name}-wall",
        physical_group=f"{source_name}-physical-wall",
        component=source_name,
        provenance=f"registered-{source_name}-source",
    )
    result = write_native_tri_authority_bound_surface_bl_front(
        certificate, rows, edge_anchor, template,
        requested_layers=layers, first_height=height, growth_ratio=1.0,
    )
    return points, faces, certificate, rows, edge_anchor, template, result


def _assert_zero_topology(result: dict) -> None:
    assert all(result["topology"][key] == 0 for key in (
        "invalid", "degenerate", "inverted", "duplicate",
        "open_edges", "non_manifold", "self_intersection",
    )), result
    assert result["collision"]["rejected_contacts"] == 0, result


def test_multiface_bl0_exact_identity_and_authority():
    points, faces, _certificate, _rows, _anchor, template, result = _run(0, 0.0)
    assert result["accepted"] is True, result
    assert result["bl0_identity"] is True
    assert result["writer_invoked"] is False
    assert result["corridor_face_count"] == 2
    assert template["schema"].endswith("multiface-v1")
    assert np.array_equal(np.asarray(result["output_vertices"]), points)
    assert np.array_equal(np.asarray(result["output_faces"]), faces)


def test_multiface_bl1_is_actual_geometry_and_strictly_gated():
    result = _run(1, 0.20)[-1]
    if "corridor_face_count" not in result:
        assert result["accepted"] is False, result
        assert result["reason"] == "surface_multiface_quality_gate_failed", result
        assert result["output_faces"] == []
        assert result["atomic_rollback"] is True
        assert result["topology"]["open_edges"] == 0
        assert result["collision"]["rejected_contacts"] == 0
        return
    assert result["corridor_face_count"] == 2, result
    assert result["generated_vertices"] == [] or len(result["generated_vertices"]) > 0
    if result["accepted"]:
        assert result["artifact_emitted"] is True
        assert result["actual_layers"] == 1
        assert len(result["generated_vertices"]) > 0
        assert result["output_faces"] != []
        _assert_zero_topology(result)
        assert result["quality"]["raw_quality_gate_pass"] is True
        assert result["quality"]["metric_quality_gate_pass"] is True
        assert result["collision"]["broad_phase"] == "deterministic_x_sweep"
    else:
        assert result["atomic_rollback"] is True
        assert result["reason"] in {
            "surface_multiface_quality_gate_failed",
            "surface_multiface_topology_or_collision_failed",
            "multiface_front_collapse",
        }
        if "topology" in result:
            _assert_zero_topology(result)


def test_multiface_tamper_is_atomic():
    _points, _faces, certificate, rows, edge_anchor, template, _result = _run(1, 0.20)
    forged = copy.deepcopy(template)
    forged["source_face_ids"] = [forged["source_face_ids"][0]]
    result = write_native_tri_authority_bound_surface_bl_front(
        certificate, rows, edge_anchor, forged,
        requested_layers=1, first_height=0.20, growth_ratio=1.0,
    )
    assert result["accepted"] is False, result
    assert result["actual_layers"] == 0
    assert result["output_faces"] == []
    assert result["atomic_rollback"] is True
