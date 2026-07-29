"""L2 raw-fold thickness sweep tests; no shell repair is attempted."""

from __future__ import annotations

from pathlib import Path

from core.analyzer.readers import read_stl
from core.generator.native_hex.source_quad_shell_scale_sweep_l2 import (
    ExactSourceQuadShellScaleSweep,
    audit_exact_source_quad_shell_scale_sweep_l2,
)


_ROOT = Path(__file__).resolve().parents[1]
_SCALES = (0.99, 0.8, 0.2, 0.05)


def _audit(path: Path) -> ExactSourceQuadShellScaleSweep:
    mesh = read_stl(path)
    return audit_exact_source_quad_shell_scale_sweep_l2(
        mesh.vertices,
        mesh.faces,
        (("source", "wall"),) * len(mesh.faces),
        scales=_SCALES,
    )


def test_cube_is_raw_fold_free_at_every_global_centroid_scale() -> None:
    report = _audit(_ROOT / "tests" / "benchmarks" / "cube.stl")

    assert report.status == "pass_centroid_shell_scale_sweep"
    assert tuple(sample.raw_negative_hex_count for sample in report.samples) == (0, 0, 0, 0)
    assert report.all_scales_raw_fold_free
    assert report.source_geometry_unchanged
    assert not report.production_mesh_changed


def test_hard_bracket_fold_count_is_invariant_under_global_thickness_reduction() -> None:
    report = _audit(_ROOT / "tests" / "stl" / "03_hard_bracket.stl")

    assert report.status == "pass_centroid_shell_scale_sweep"
    assert tuple(sample.raw_negative_hex_count for sample in report.samples) == (390, 390, 390, 390)
    assert not report.all_scales_raw_fold_free
    assert report.source_geometry_unchanged
    assert not report.production_mesh_changed


def test_invalid_scale_sweep_rejects_without_constructing_a_shell() -> None:
    mesh = read_stl(_ROOT / "tests" / "benchmarks" / "cube.stl")
    report = audit_exact_source_quad_shell_scale_sweep_l2(
        mesh.vertices, mesh.faces, (("source", "wall"),) * len(mesh.faces), scales=(1.0,)
    )

    assert report.status == "reject_invalid_scale_sweep"
    assert not report.samples
