"""Diagnostic subset matrix for the whole-solid CAD/XDE refusal."""

from __future__ import annotations

import numpy as np
import sys
sys.path.insert(0, "/tmp/autotessell_surface_bl_front_shared_build")

from core.analyzer.readers.step import load_cad_native_with_provenance
from native_surface_bl_front_shared import plan_shared_surface_wall_edge_front
from tests.test_cad_xde_physical_authority import _write_styled_box
from tests.test_native_tet_bl_cad_xde_surface_binding import _cad_inputs


def _run(points, triangles, normals, result, edge_faces, source_faces):
    edges = []
    for face in edge_faces:
        triangle = triangles[2 * face]
        for index in range(3):
            edges.append([face * 10 + index, int(triangle[index]), int(triangle[(index + 1) % 3]), 2 * face])
    selected_triangles = np.concatenate([triangles[2 * face : 2 * face + 2] for face in source_faces], axis=0)
    return plan_shared_surface_wall_edge_front(
        points,
        np.asarray(edges, dtype=np.int64),
        normals,
        [result.provenance.xde_layer_names[index // 2][0] for index in range(12)],
        [f"cad_face_ordinal_{index // 2}" for index in range(12)],
        ["unbound_physical_group"] * 12,
        1,
        0.001,
        1.2,
        selected_triangles,
        max_step_halvings=0,
    )


def test_cad_subset_diagnostic_is_repeatable_and_atomic(tmp_path) -> None:
    source = tmp_path / "styled-box.step"
    _write_styled_box(source)
    result, points, triangles, normals = _cad_inputs(source)
    cases = (
        ((0,), (0,), True),
        ((0, 1), (0, 1), True),
        ((0, 2), (0, 2), False),
        ((0, 1), tuple(range(6)), False),
        (tuple(range(6)), tuple(range(6)), False),
    )
    for edge_faces, source_faces, expected in cases:
        first = _run(points, triangles, normals, result, edge_faces, source_faces)
        second = _run(points, triangles, normals, result, edge_faces, source_faces)
        assert first == second
        assert first["accepted"] is expected, (edge_faces, source_faces, first)
        if expected:
            assert first["actual_layers"] == 1
            assert first["quality"]["max_skewness"] <= 0.50
            assert first["quality"]["max_non_orthogonality"] <= 50.0
        else:
            assert first["reason"] == "collision_or_quality_failure"
            assert first["actual_layers"] == 0
            assert first["generated_vertices"] == []
            assert first["generated_faces"] == []
            assert first["provenance"] == []
