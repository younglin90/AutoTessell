"""Bounded release-route witness for a real complex Poly quality rejection."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from core.analyzer.readers import read_stl
from core.generator.tier_native_poly import _runner


def test_native_poly_release_route_rejects_complex_quality_tail(tmp_path: Path) -> None:
    source = Path("tests/benchmarks/sphere_watertight.stl")
    mesh = read_stl(source)
    result = _runner(
        np.asarray(mesh.vertices),
        np.asarray(mesh.faces),
        tmp_path / "sphere-release",
        release_route=True,
        source_path=source,
    )
    assert result.success is False
    assert result.route == "poly_harness_release"
    assert result.max_non_ortho > 50.0
    assert result.max_skewness > 0.50
    assert result.max_aspect_ratio > 20.0
