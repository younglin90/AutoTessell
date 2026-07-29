"""L1/L2 report-only shell tests; the core is deliberately never filled."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from core.analyzer.readers import read_stl
from core.generator.native_hex.source_quad_shell_l1 import (
    ExactSourceQuadShellAudit,
    audit_exact_source_quad_shell_l1,
)

_ROOT = Path(__file__).resolve().parents[1]


def _audit(path: Path) -> ExactSourceQuadShellAudit:
    mesh = read_stl(path)
    entities = tuple((f"source_0_{path.name}", "wall") for _ in mesh.faces)
    return audit_exact_source_quad_shell_l1(mesh.vertices, mesh.faces, entities)


def test_cube_and_cylinder_have_valid_exact_outer_shells_with_open_cores() -> None:
    cube = _audit(_ROOT / "tests" / "benchmarks" / "cube.stl")
    cylinder = _audit(_ROOT / "tests" / "benchmarks" / "cylinder.stl")

    for report, expected_hexes in ((cube, 36), (cylinder, 384)):
        assert report.status == "pass_exact_outer_shell_open_core"
        assert report.hex_count == expected_hexes
        assert report.flipped_cell_count == 0
        assert report.degenerate_cell_count == 0
        assert report.outer_quad_set_preserved
        assert report.source_vertex_prefix_identical
        assert report.cavity_unfilled
        assert not report.production_mesh_changed


def test_sphere_shell_is_deterministic_with_exact_outer_surface() -> None:
    path = _ROOT / "tests" / "benchmarks" / "sphere.stl"
    first = _audit(path)
    second = _audit(path)

    assert first.status == "pass_exact_outer_shell_open_core"
    assert first.hex_count == 3840
    assert first.flipped_cell_count == 0
    assert first.degenerate_cell_count == 0
    assert first.outer_quad_set_preserved
    assert first.cavity_unfilled
    assert first.status == second.status
    assert first.hex_count == second.hex_count
    assert first.flipped_cell_count == second.flipped_cell_count
    assert first.degenerate_cell_count == second.degenerate_cell_count
    assert np.array_equal(
        first.surface_audit.quadization.points, second.surface_audit.quadization.points
    )
    assert np.array_equal(
        first.surface_audit.quadization.quads, second.surface_audit.quadization.quads
    )


def test_hard_bracket_rejects_global_centroid_shell_before_any_writer_use() -> None:
    report = _audit(_ROOT / "tests" / "stl" / "03_hard_bracket.stl")

    assert report.status == "reject_shell_validity_or_contract"
    assert report.flipped_cell_count > 0
    assert report.degenerate_cell_count == 0
    assert report.outer_quad_set_preserved
    assert report.source_vertex_prefix_identical
    assert report.cavity_unfilled
    assert not report.production_mesh_changed
