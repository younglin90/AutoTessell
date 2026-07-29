"""L1 real-STL source-surface checks for triangle-derived all-quad boundaries."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from core.analyzer.readers import read_stl
from core.generator.native_hex.source_triangle_quadization_l1 import (
    ExactSourceQuadizationAudit,
    audit_exact_source_quadization_l1,
)

_ROOT = Path(__file__).resolve().parents[1]


def _audit_fixture(name: str) -> ExactSourceQuadizationAudit:
    mesh = read_stl(_ROOT / "tests" / "benchmarks" / name)
    entities = tuple((f"source_0_{name}", "wall") for _ in mesh.faces)
    return audit_exact_source_quadization_l1(mesh.vertices, mesh.faces, entities)


def test_cube_triangle_surface_becomes_exact_closed_quad_boundary() -> None:
    report = _audit_fixture("cube.stl")

    assert report.status == "pass_exact_source_quadization"
    assert (report.source_face_count, report.quad_count) == (12, 36)
    assert report.source_vertex_prefix_identical
    assert report.exact_three_quads_per_source_face
    assert report.oriented_closed_quad_surface
    assert report.all_quad_sphere_precheck
    assert report.euler_characteristic == 2
    assert report.max_support_distance == 0.0
    assert report.max_relative_area_error == 0.0
    assert report.source_entities_preserved
    assert not report.production_mesh_changed


def test_cylinder_triangle_surface_remains_exactly_supported_and_closed() -> None:
    report = _audit_fixture("cylinder.stl")

    assert report.status == "pass_exact_source_quadization"
    assert (report.source_face_count, report.quad_count) == (128, 384)
    assert report.source_vertex_prefix_identical
    assert report.exact_three_quads_per_source_face
    assert report.oriented_closed_quad_surface
    assert report.all_quad_sphere_precheck
    assert report.euler_characteristic == 2
    assert report.max_support_distance <= 1.0e-12
    assert report.max_relative_area_error <= 1.0e-12
    assert report.source_entities_preserved


def test_sphere_triangle_surface_has_deterministic_exact_quad_audit() -> None:
    first = _audit_fixture("sphere.stl")
    second = _audit_fixture("sphere.stl")

    assert first.status == "pass_exact_source_quadization"
    assert (first.source_face_count, first.quad_count) == (1280, 3840)
    assert first.oriented_closed_quad_surface
    assert first.all_quad_sphere_precheck
    assert first.max_support_distance <= 1.0e-12
    assert first.max_relative_area_error <= 1.0e-12
    assert first.status == second.status
    assert first.max_support_distance == second.max_support_distance
    assert first.max_relative_area_error == second.max_relative_area_error
    assert np.array_equal(first.quadization.points, second.quadization.points)
    assert np.array_equal(first.quadization.quads, second.quadization.quads)
    assert np.array_equal(first.quadization.source_face_ids, second.quadization.source_face_ids)
