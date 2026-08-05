from __future__ import annotations

import copy
import math
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
from core.preprocessor.native_tri.planar_triangle_bl_template import (
    make_planar_triangle_template_anchor,
    write_native_tri_planar_triangle_bl,
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
            ids[
                tuple(
                    0.0 if float(v) == 0.0 else float(v)
                    for v in mesh.vertices[int(vertex)]
                )
            ]
            for vertex in face
        ]
        for face in np.asarray(mesh.faces, dtype=np.int64)
    ]
    return np.asarray(points, dtype=np.float64), np.asarray(faces, dtype=np.int64)


def _write_regular_tetra(path: Path) -> None:
    root3 = math.sqrt(3.0)
    root23 = math.sqrt(2.0 / 3.0)
    vertices = np.asarray(
        [
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.5, root3 / 2.0, 0.0),
            (0.5, root3 / 6.0, root23),
        ],
        dtype=np.float64,
    )
    centroid = vertices.mean(axis=0)
    raw_faces = [(0, 1, 2), (0, 3, 1), (1, 3, 2), (2, 3, 0)]
    lines = ["solid regular_tetra"]
    for face in raw_faces:
        tri = vertices[list(face)]
        normal = np.cross(tri[1] - tri[0], tri[2] - tri[0])
        if float(np.dot(normal, tri.mean(axis=0) - centroid)) < 0.0:
            face = (face[0], face[2], face[1])
            tri = vertices[list(face)]
            normal = np.cross(tri[1] - tri[0], tri[2] - tri[0])
        normal = normal / np.linalg.norm(normal)
        lines.append(f"  facet normal {normal[0]} {normal[1]} {normal[2]}")
        lines.append("    outer loop")
        for point in tri:
            lines.append(f"      vertex {point[0]} {point[1]} {point[2]}")
        lines.extend(("    endloop", "  endfacet"))
    lines.append("endsolid regular_tetra")
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def _fixture(source: Path, issuer: str = "tri-planar-test", key: str = "tri-planar-v1"):
    points, faces = _canonical_stl(source)
    ledger = semantic_ledger_from_faces(
        faces,
        feature=f"{source.stem}-surface",
        patch=f"{source.stem}-wall",
        physical_group=f"{source.stem}-physical-wall",
        component=source.stem,
        provenance="registered-planar-template-facet",
    )
    source_anchor = make_external_trust_anchor(
        source, ledger, issuer=issuer, key_id=key
    )
    certificate = validate_native_tri_authority_source(
        source, ledger, source_anchor, requested_layers=0
    )
    assert certificate["accepted"] is True, certificate
    occurrences: dict[tuple[int, int], list[tuple[int, int, int]]] = defaultdict(list)
    for face_id, face in enumerate(faces):
        for local in range(3):
            first = int(face[local])
            second = int(face[(local + 1) % 3])
            occurrences[tuple(sorted((first, second)))].append(
                (face_id, first, second)
            )
    face = faces[0]
    rows: list[dict] = []
    for local in range(3):
        first = int(face[local])
        second = int(face[(local + 1) % 3])
        incident = sorted(
            face_id
            for face_id, _from, _to in occurrences[tuple(sorted((first, second)))]
        )
        rows.append(
            {
                "edge_id": f"{source.stem}-wall-edge-{local}",
                "endpoint_vertex_ids": [first, second],
                "incident_face_ids": incident,
                "directed_sector_face_ids": incident,
                "directed_sector_ids": [f"sector-face-{value}" for value in incident],
                "wall_role": "wall",
                "patch_boundary_role": f"{source.stem}-patch-boundary",
                "feature": f"{source.stem}-surface",
                "patch": f"{source.stem}-wall",
                "physical_group": f"{source.stem}-physical-wall",
                "component": source.stem,
                "provenance": "registered-planar-template-facet",
            }
        )
    return points, faces, certificate, rows


def _registered(certificate, rows, *, layers: int, height: float, growth: float):
    edge_anchor = make_external_edge_trust_anchor(
        certificate,
        rows,
        loop_policy="closed_nonbranching",
        issuer="tri-planar-edge-registry",
        key_id="tri-planar-edge-v1",
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
    template = make_planar_triangle_template_anchor(
        certificate,
        edge_anchor,
        preflight,
        source_face_id=0,
        wall_edge_ids=[row["edge_id"] for row in rows],
        feature=rows[0]["feature"],
        patch=rows[0]["patch"],
        physical_group=rows[0]["physical_group"],
        component=rows[0]["component"],
        provenance=rows[0]["provenance"],
    )
    return edge_anchor, template


def test_bl0_is_exact_identity_and_authority_bound(tmp_path: Path):
    source = tmp_path / "regular-tetra.stl"
    _write_regular_tetra(source)
    points, faces, certificate, rows = _fixture(source)
    edge_anchor, template = _registered(certificate, rows, layers=0, height=0.0, growth=1.0)
    result = write_native_tri_planar_triangle_bl(
        certificate, rows, edge_anchor, template,
        requested_layers=0, first_height=0.0, growth_ratio=1.0,
    )
    assert result["accepted"] is True, result
    assert result["status"] == "native_tri_planar_triangle_bl_identity"
    assert result["bl0_identity"] is True
    assert result["writer_invoked"] is False
    assert result["artifact_emitted"] is False
    assert np.array_equal(np.asarray(result["output_vertices"]), points)
    assert np.array_equal(np.asarray(result["output_faces"]), faces)
    assert result["generated_faces"] == []
    assert result["publication_eligible"] is False


@pytest.mark.parametrize("layers", (1, 3, 8))
def test_positive_planar_template_uses_exact_schedule_and_quality(tmp_path: Path, layers: int):
    source = tmp_path / "regular-tetra.stl"
    _write_regular_tetra(source)
    _points, faces, certificate, rows = _fixture(source)
    height, growth = 0.02, 1.05
    edge_anchor, template = _registered(
        certificate, rows, layers=layers, height=height, growth=growth
    )
    results = [
        write_native_tri_planar_triangle_bl(
            certificate, rows, edge_anchor, template,
            requested_layers=layers, first_height=height, growth_ratio=growth,
        )
        for _ in range(3)
    ]
    assert all(result["accepted"] for result in results), results
    first = results[0]
    assert first["actual_layers"] == layers
    assert first["layer_heights"] == pytest.approx(
        [height * growth**i for i in range(layers)]
    )
    assert len(first["generated_vertices"]) == 3 * layers
    assert len(first["generated_faces"]) == 6 * layers + 1
    assert len(first["output_faces"]) == len(faces) + 6 * layers
    assert first["quality"]["max_skewness"] <= 0.50 + 1e-12
    assert first["quality"]["max_aspect_ratio"] <= 10.0 + 1e-12
    assert first["quality"]["max_wall_front_non_orthogonality_degrees"] <= 30.0 + 1e-12
    assert first["quality"]["max_physical_aspect_ratio"] >= first["quality"]["max_aspect_ratio"]
    assert first["topology"]["invalid"] == 0
    assert first["topology"]["duplicate"] == 0
    assert first["topology"]["open_edges"] == 0
    assert first["topology"]["non_manifold"] == 0
    assert first["topology"]["inverted"] == 0
    assert first["collision"]["rejected_contacts"] == 0
    assert first["independent_long_double_audit"]["accepted"] is True
    assert len({result["deterministic_digest"] for result in results}) == 1
    assert all(
        all(
            key in row
            for key in (
                "source_face_id",
                "source_wall_edge_ids",
                "feature",
                "patch",
                "physical_group",
                "component",
                "provenance",
            )
        )
        for row in first["generated_provenance"]
    )


def test_actual_cube_planar_triangle_positive_artifact(tmp_path: Path):
    points, faces, certificate, rows = _fixture(Path("tests/benchmarks/cube.stl"))
    edge_anchor, template = _registered(
        certificate, rows, layers=1, height=0.20, growth=1.0
    )
    result = write_native_tri_planar_triangle_bl(
        certificate, rows, edge_anchor, template,
        requested_layers=1, first_height=0.20, growth_ratio=1.0,
    )
    # The actual cube face is a right-isosceles source triangle. The
    # quality-first gate must refuse this one-face template when its local
    # metric skewness cannot meet the strict limit; it must not emit a bad BL.
    assert result["accepted"] is False, result
    assert result["reason"] == "tri_planar_no_quality_admissible_diagonal"
    assert result["actual_layers"] == 0
    assert result["generated_faces"] == []
    assert result["atomic_rollback"] is True
    assert result["quality_candidate_zero"]["skewness"] > 0.50


@pytest.mark.parametrize("tamper", ("face", "edge", "digest", "label", "schedule"))
def test_authority_and_geometry_tamper_is_atomic(tmp_path: Path, tamper: str):
    source = tmp_path / "regular-tetra.stl"
    _write_regular_tetra(source)
    _points, _faces, certificate, rows = _fixture(source)
    height, growth = 0.02, 1.05
    edge_anchor, template = _registered(
        certificate, rows, layers=1, height=height, growth=growth
    )
    forged_rows = copy.deepcopy(rows)
    forged_template = copy.deepcopy(template)
    if tamper == "face":
        forged_template["cavity_source_face_id"] = 1
    elif tamper == "edge":
        forged_template["wall_edge_ids"][0] = "forged-edge"
    elif tamper == "digest":
        forged_template["preflight_digest"] = "0" * 64
    elif tamper == "label":
        forged_rows[0]["feature"] = "forged-feature"
        edge_anchor = make_external_edge_trust_anchor(
            certificate, forged_rows,
            loop_policy="closed_nonbranching",
            issuer="tri-planar-edge-registry",
            key_id="tri-planar-edge-v1",
        )
    elif tamper == "schedule":
        height = 0.20
    result = write_native_tri_planar_triangle_bl(
        certificate, forged_rows, edge_anchor, forged_template,
        requested_layers=1, first_height=height, growth_ratio=growth,
    )
    assert result["accepted"] is False, result
    assert result["actual_layers"] == 0
    assert result["generated_vertices"] == []
    assert result["generated_faces"] == []
    assert result["output_faces"] == []
    assert result["atomic_rollback"] is True
