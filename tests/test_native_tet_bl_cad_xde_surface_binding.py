"""Actual CAD/XDE face-to-C++ surface-front binding evidence."""

from __future__ import annotations

from pathlib import Path
import sys
sys.path.insert(0, "/tmp/autotessell_surface_bl_front_shared_build")

import numpy as np

from core.analyzer.readers.step import load_cad_native_with_provenance
from native_surface_bl_front_shared import plan_shared_surface_wall_edge_front
from tests.test_cad_xde_physical_authority import _write_styled_box


def _cad_inputs(path: Path):
    result = load_cad_native_with_provenance(path, ".step")
    points = np.asarray(result.vertices, dtype=float)
    triangles = np.asarray(result.faces, dtype=np.int64)
    normals = []
    for triangle in triangles:
        a, b, c = (points[int(index)] for index in triangle)
        normal = np.cross(b - a, c - a)
        normals.append(normal / np.linalg.norm(normal))
    return result, points, triangles, np.asarray(normals, dtype=float)


def _one_face_candidate(path: Path, layers: int):
    result, points, triangles, normals = _cad_inputs(path)
    source_face = 0
    triangle = triangles[0]
    edges = np.asarray(
        [[100 + index, int(triangle[index]), int(triangle[(index + 1) % 3]), source_face] for index in range(3)],
        dtype=np.int64,
    )
    return result, plan_shared_surface_wall_edge_front(
        points,
        edges,
        np.asarray([normals[0]], dtype=float),
        [result.provenance.xde_layer_names[source_face][0]],
        ["cad_face_ordinal_0"],
        ["unbound_physical_group"],
        layers,
        0.2,
        1.2,
        triangles[[0, 1]],
        max_step_halvings=3,
    )


def test_actual_cad_face_binds_xde_ordinal_to_cxx_provenance(tmp_path: Path) -> None:
    source = tmp_path / "styled-box.step"
    _write_styled_box(source)
    for layers in (0, 1, 3):
        first_result, first = _one_face_candidate(source, layers)
        second_result, second = _one_face_candidate(source, layers)
        assert first_result.provenance.xde_metadata_sha256 == second_result.provenance.xde_metadata_sha256
        assert first == second
        if layers == 0:
            assert first["accepted"] is True and first["status"] == "disabled_identity"
            continue
        assert first["accepted"] is True
        assert first["quality"]["metric_aspect_ratio"] < 40.0
        assert first["quality"]["max_skewness"] <= 0.50
        assert first["quality"]["max_non_orthogonality"] <= 50.0
        assert len(first["provenance"]) == 3 * layers
        assert {(item["source_face"], item["patch"], item["feature"], item["physical_group"]) for item in first["provenance"]} == {
            (0, "boundary-0", "cad_face_ordinal_0", "unbound_physical_group")
        }


def test_whole_cad_solid_collision_refuses_without_partial_output(tmp_path: Path) -> None:
    source = tmp_path / "styled-box.step"
    _write_styled_box(source)
    result, points, triangles, normals = _cad_inputs(source)
    edges = []
    for face in range(6):
        triangle = triangles[2 * face]
        for index in range(3):
            edges.append([face * 10 + index, int(triangle[index]), int(triangle[(index + 1) % 3]), 2 * face])
    candidate = plan_shared_surface_wall_edge_front(
        points,
        np.asarray(edges, dtype=np.int64),
        normals,
        [result.provenance.xde_layer_names[index // 2][0] for index in range(12)],
        [f"cad_face_ordinal_{index // 2}" for index in range(12)],
        ["unbound_physical_group"] * 12,
        1,
        0.001,
        1.2,
        triangles,
        max_step_halvings=0,
    )
    assert candidate["accepted"] is False
    assert candidate["reason"] == "collision_or_quality_failure"
    assert candidate["actual_layers"] == 0
    assert candidate["generated_vertices"] == []
    assert candidate["generated_faces"] == []
    assert candidate["provenance"] == []
