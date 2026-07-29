"""L0 geometry-only feature-candidate tests; no CAD provenance is inferred."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from core.analyzer.readers import read_stl
from core.generator.native_hex.source_feature_candidate_l0 import (
    audit_geometric_feature_candidates_l0,
)

_ROOT = Path(__file__).resolve().parents[1]


def test_cube_sharp_edges_are_measurement_candidates_not_cad_entities() -> None:
    mesh = read_stl(_ROOT / "tests" / "benchmarks" / "cube.stl")
    report = audit_geometric_feature_candidates_l0(mesh.vertices, mesh.faces)

    assert report.status == "pass_geometric_candidates_not_authoritative"
    assert report.source_face_count == 12
    assert len(report.candidate_edges) == 12
    assert len(report.candidate_components) == 1
    assert all(
        abs(item.unsigned_dihedral_degrees - 90.0) <= 1.0e-12 for item in report.candidate_edges
    )
    assert not report.candidates_are_authoritative
    assert report.source_geometry_unchanged
    assert not report.production_mesh_changed


def test_cylinder_and_hard_bracket_measure_distinct_candidate_complexity() -> None:
    cylinder = read_stl(_ROOT / "tests" / "benchmarks" / "cylinder.stl")
    bracket = read_stl(_ROOT / "tests" / "stl" / "03_hard_bracket.stl")
    cylinder_report = audit_geometric_feature_candidates_l0(cylinder.vertices, cylinder.faces)
    bracket_report = audit_geometric_feature_candidates_l0(bracket.vertices, bracket.faces)

    assert cylinder_report.status == "pass_geometric_candidates_not_authoritative"
    assert bracket_report.status == "pass_geometric_candidates_not_authoritative"
    assert len(cylinder_report.candidate_edges) > 0
    assert len(bracket_report.candidate_edges) > len(cylinder_report.candidate_edges)
    assert len(bracket_report.candidate_components) >= 1
    assert not cylinder_report.candidates_are_authoritative
    assert not bracket_report.candidates_are_authoritative


def test_open_source_rejects_instead_of_inventing_feature_candidates() -> None:
    vertices = np.asarray(((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)))
    report = audit_geometric_feature_candidates_l0(
        vertices, np.asarray(((0, 1, 2),), dtype=np.int64)
    )

    assert report.status == "reject_source_not_closed_two_manifold"
    assert not report.candidate_edges
    assert not report.candidates_are_authoritative
