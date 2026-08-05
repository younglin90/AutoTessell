from __future__ import annotations

import copy
from collections import defaultdict
from pathlib import Path

import numpy as np
import pytest

from core.analyzer.readers import read_stl
from core.preprocessor.native_tri.authority_bound_surface_bl_front import (
    make_authority_bound_surface_bl_front_template_anchor,
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


def _fixture(source_name: str = "cylinder") -> tuple[np.ndarray, np.ndarray, dict, list[dict], dict, list[int]]:
    source = Path("tests/benchmarks") / f"{source_name}.stl"
    points, faces = _canonical_stl(source)
    labels = semantic_ledger_from_faces(
        faces,
        feature=f"{source_name}-surface",
        patch=f"{source_name}-wall",
        physical_group=f"{source_name}-physical-wall",
        component=source_name,
        provenance=f"registered-{source_name}-source",
    )
    source_anchor = make_external_trust_anchor(
        source,
        labels,
        issuer=f"tri-c125-{source_name}-source",
        key_id=f"tri-c125-{source_name}-source-v1",
    )
    certificate_result = validate_native_tri_authority_source(
        source, labels, source_anchor, requested_layers=0
    )
    assert certificate_result["accepted"] is True, certificate_result
    certificate = certificate_result["certificate"]

    occurrences: dict[tuple[int, int], list[int]] = defaultdict(list)
    for face_id, face in enumerate(faces):
        for local in range(3):
            a = int(face[local])
            b = int(face[(local + 1) % 3])
            occurrences[tuple(sorted((a, b)))].append(face_id)

    face_id = 0
    rows: list[dict] = []
    for local in range(3):
        a = int(faces[face_id, local])
        b = int(faces[face_id, (local + 1) % 3])
        incident = sorted(occurrences[tuple(sorted((a, b)))])
        assert len(incident) == 2
        rows.append(
            {
                "edge_id": f"{source_name}-face0-wall-edge-{local}",
                "endpoint_vertex_ids": [a, b],
                "incident_face_ids": incident,
                "directed_sector_face_ids": incident,
                "directed_sector_ids": [f"sector-{value}" for value in incident],
                "wall_role": "wall",
                "patch_boundary_role": f"{source_name}-wall-loop",
                "feature": f"{source_name}-surface",
                "patch": f"{source_name}-wall",
                "physical_group": f"{source_name}-physical-wall",
                "component": source_name,
                "provenance": f"registered-{source_name}-source",
            }
        )
    edge_anchor = make_external_edge_trust_anchor(
        certificate,
        rows,
        loop_policy="closed_nonbranching",
        issuer=f"tri-c125-{source_name}-edge",
        key_id=f"tri-c125-{source_name}-edge-v1",
    )
    return points, faces, certificate, rows, edge_anchor, labels


def _registered(layers: int, height: float, source_name: str = "cylinder"):
    points, faces, certificate, rows, edge_anchor, _labels = _fixture(source_name)
    preflight = validate_native_tri_wall_edge_bl_preflight(
        certificate,
        rows,
        edge_anchor,
        requested_layers=layers,
        first_height=height,
        growth_ratio=1.0,
    )
    assert preflight["accepted"] is True, preflight
    template = make_authority_bound_surface_bl_front_template_anchor(
        certificate,
        edge_anchor,
        preflight,
        source_face_ids=[0],
        wall_edge_ids=[row["edge_id"] for row in rows],
        active_sector_face_ids=[0, 0, 0],
        feature=f"{source_name}-surface",
        patch=f"{source_name}-wall",
        physical_group=f"{source_name}-physical-wall",
        component=source_name,
        provenance=f"registered-{source_name}-source",
    )
    return points, faces, certificate, rows, edge_anchor, template


def _run(layers: int, height: float, source_name: str = "cylinder"):
    *prefix, template = _registered(layers, height, source_name)
    result = write_native_tri_authority_bound_surface_bl_front(
        prefix[2],
        prefix[3],
        prefix[4],
        template,
        requested_layers=layers,
        first_height=height,
        growth_ratio=1.0,
    )
    return (*prefix, template, result)


def test_cylinder_bl0_is_exact_identity():
    points, faces, *_rest = _run(0, 0.0)
    result = _rest[-1]
    assert result["accepted"] is True, result
    assert result["bl0_identity"] is True
    assert result["writer_invoked"] is False
    assert np.array_equal(np.asarray(result["output_vertices"]), points)
    assert np.array_equal(np.asarray(result["output_faces"]), faces)
    assert result["generated_faces"] == []



@pytest.mark.parametrize(
    ("source_name", "layers", "height"),
    (
        ("sphere_watertight", 0, 0.0),
        ("sphere_watertight", 1, 0.02),
        ("sphere_watertight", 3, 0.005),
    ),
)
def test_bl_matrix_is_identity_or_strict_atomic_refusal(source_name, layers, height):
    points, faces, *_rest = _run(layers, height, source_name)
    result = _rest[-1]
    if layers == 0:
        assert result["accepted"] is True, result
        assert result["bl0_identity"] is True
        assert result["writer_invoked"] is False
        assert np.array_equal(np.asarray(result["output_vertices"]), points)
        assert np.array_equal(np.asarray(result["output_faces"]), faces)
        return
    assert result["accepted"] is False, result
    assert result["reason"] == "surface_quality_gate_failed"
    assert result["actual_layers"] == 0
    assert result["output_faces"] == []
    assert result["atomic_rollback"] is True
    assert result["actual_face_count"] > 0
    assert all(result["topology"][key] == 0 for key in (
        "invalid", "degenerate", "inverted", "duplicate",
        "open_edges", "non_manifold", "self_intersection",
    ))
    assert result["collision"]["rejected_contacts"] == 0
    assert result["quality"]["raw_quality_gate_pass"] is False


def test_coarse_nonbox_candidate_reaches_strict_gates_without_publication():
    result = _run(
        1, 0.179, "coarse_to_fine_gradation_two_spheres"
    )[-1]
    assert result["accepted"] is False, result
    assert result["reason"] == "surface_quality_gate_failed"
    assert result["atomic_rollback"] is True
    assert result["output_faces"] == []
    assert result["actual_face_count"] > 20000
    assert result["quality"]["raw_skewness_max"] <= 0.50
    assert result["quality"]["raw_angle_nonorthogonality_max_degrees"] > 55.0
    assert result["quality"]["metric_skewness_max"] > 0.35
    assert result["quality"]["metric_aspect_ratio_max"] > 1.60
    assert all(result["topology"][key] == 0 for key in (
        "invalid", "degenerate", "inverted", "duplicate",
        "open_edges", "non_manifold", "self_intersection",
    ))
    assert result["collision"]["rejected_contacts"] == 0




def test_cylinder_positive_refuses_unadmissible_source_without_artifact():
    result = _run(1, 0.02, "cylinder")[-1]
    assert result["accepted"] is False, result
    assert result["reason"] == "surface_source_quality_unadmissible"
    assert result["quality"]["source_raw_physical_aspect_max"] > 5.5
    assert result["quality"]["source_raw_mean_ratio_min"] < 0.30
    assert result["quality"]["source_raw_skewness_max"] > 0.50
    assert result["output_faces"] == []
    assert result["atomic_rollback"] is True


def test_sphere_positive_refusal_is_repeatable():
    first = _run(1, 0.02, "sphere_watertight")[-1]
    second = _run(1, 0.02, "sphere_watertight")[-1]
    assert first["accepted"] is False and second["accepted"] is False
    assert first["reason"] == second["reason"] == "surface_quality_gate_failed"
    assert first["quality"] == second["quality"]
    assert first["topology"] == second["topology"]
    assert first["collision"] == second["collision"]
    assert first["actual_face_count"] == second["actual_face_count"]
    assert first["output_faces"] == second["output_faces"] == []


@pytest.mark.parametrize("tamper", ("edge", "digest", "label"))
def test_sphere_tamper_is_atomic(tamper):
    _points, _faces, certificate, rows, edge_anchor, template, _result = _run(1, 0.02, "sphere_watertight")
    forged_rows = copy.deepcopy(rows)
    forged_template = copy.deepcopy(template)
    if tamper == "edge":
        forged_template["wall_edge_ids"][0] = "forged-edge"
    elif tamper == "digest":
        forged_template["preflight_digest"] = "0" * 64
    else:
        forged_rows[0]["feature"] = "forged"
    result = write_native_tri_authority_bound_surface_bl_front(
        certificate,
        forged_rows,
        edge_anchor,
        forged_template,
        requested_layers=1,
        first_height=0.02,
        growth_ratio=1.0,
    )
    assert result["accepted"] is False, result
    assert result["actual_layers"] == 0
    assert result["output_faces"] == []
    assert result["atomic_rollback"] is True
