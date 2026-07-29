"""L2 report-only centroid-shell concavity attribution tests."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from core.analyzer.readers import read_stl
from core.generator.native_hex.source_quad_shell_concavity_l2 import (
    ExactSourceQuadShellConcavityAudit,
    audit_exact_source_quad_shell_concavity_l2,
)


_ROOT = Path(__file__).resolve().parents[1]


def _audit(path: Path) -> ExactSourceQuadShellConcavityAudit:
    mesh = read_stl(path)
    return audit_exact_source_quad_shell_concavity_l2(
        mesh.vertices, mesh.faces, (("source", "wall"),) * len(mesh.faces)
    )


def test_convex_cube_and_cylinder_have_no_raw_centroid_shell_folds() -> None:
    for path in (_ROOT / "tests" / "benchmarks" / "cube.stl", _ROOT / "tests" / "benchmarks" / "cylinder.stl"):
        report = _audit(path)

        assert report.status == "pass_centroid_shell_concavity_diagnosis"
        assert report.raw_negative_hex_count == 0
        assert report.raw_negative_source_face_count == 0
        assert report.centroid_concave_source_face_count == 0
        assert not report.raw_negative_faces_all_centroid_concave
        assert report.source_geometry_unchanged
        assert not report.production_mesh_changed


def test_hard_bracket_raw_folds_all_map_to_centroid_concave_source_faces() -> None:
    report = _audit(_ROOT / "tests" / "stl" / "03_hard_bracket.stl")

    assert report.status == "pass_centroid_shell_concavity_diagnosis"
    assert report.raw_negative_hex_count == 390
    assert report.raw_negative_source_face_count == 130
    assert report.centroid_concave_source_face_count == 134
    assert report.raw_negative_faces_all_centroid_concave
    assert report.raw_negative_faces_candidate_adjacent_count == 130
    assert not report.feature_candidates_authoritative
    assert report.source_geometry_unchanged
    assert not report.production_mesh_changed


def test_hard_bracket_concavity_diagnosis_is_value_identical_on_repeat() -> None:
    path = _ROOT / "tests" / "stl" / "03_hard_bracket.stl"
    first = _audit(path)
    second = _audit(path)

    assert (
        first.status,
        first.raw_negative_hex_count,
        first.raw_negative_source_face_count,
        first.centroid_concave_source_face_count,
        first.raw_negative_faces_all_centroid_concave,
        first.raw_negative_faces_candidate_adjacent_count,
    ) == (
        second.status,
        second.raw_negative_hex_count,
        second.raw_negative_source_face_count,
        second.centroid_concave_source_face_count,
        second.raw_negative_faces_all_centroid_concave,
        second.raw_negative_faces_candidate_adjacent_count,
    )
    assert np.array_equal(
        first.shell.surface_audit.quadization.points, second.shell.surface_audit.quadization.points
    )
    assert np.array_equal(
        first.shell.surface_audit.quadization.quads, second.shell.surface_audit.quadization.quads
    )
