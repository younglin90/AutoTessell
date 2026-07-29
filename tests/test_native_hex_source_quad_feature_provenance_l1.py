"""L1 exact source entity-boundary propagation tests."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from core.analyzer.readers import read_stl
from core.generator.native_hex.source_quad_feature_provenance_l1 import (
    audit_quadized_entity_boundaries_l1,
)

_ROOT = Path(__file__).resolve().parents[1]


def _cube_face_entities(vertices: np.ndarray, faces: np.ndarray) -> tuple[tuple[str, str], ...]:
    labels: list[tuple[str, str]] = []
    for face in faces:
        centre = np.mean(vertices[face], axis=0)
        axis = int(np.argmax(np.abs(centre)))
        labels.append(("cube", f"axis_{axis}_{'high' if centre[axis] > 0.0 else 'low'}"))
    return tuple(labels)


def test_cube_patch_edges_become_exactly_two_quad_feature_segments() -> None:
    mesh = read_stl(_ROOT / "tests" / "benchmarks" / "cube.stl")
    report = audit_quadized_entity_boundaries_l1(
        mesh.vertices,
        mesh.faces,
        _cube_face_entities(mesh.vertices, mesh.faces),
    )

    assert report.status == "pass_exact_quad_entity_boundary_provenance"
    assert report.source_entity_boundary_edge_count == 12
    assert report.expected_quad_entity_boundary_segment_count == 24
    assert report.observed_quad_entity_boundary_segment_count == 24
    assert report.every_source_boundary_split_exactly_twice
    assert report.no_spurious_quad_entity_boundaries
    assert report.source_vertex_prefix_identical
    assert not report.production_mesh_changed


def test_one_entity_cube_has_no_invented_quad_feature_boundaries() -> None:
    mesh = read_stl(_ROOT / "tests" / "benchmarks" / "cube.stl")
    report = audit_quadized_entity_boundaries_l1(
        mesh.vertices,
        mesh.faces,
        (("source", "wall"),) * len(mesh.faces),
    )

    assert report.status == "pass_exact_quad_entity_boundary_provenance"
    assert report.source_entity_boundary_edge_count == 0
    assert report.observed_quad_entity_boundary_segment_count == 0
    assert report.every_source_boundary_split_exactly_twice
    assert report.no_spurious_quad_entity_boundaries
