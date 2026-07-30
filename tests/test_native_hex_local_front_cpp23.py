"""C++23 parity and ABI guards for report-only local-front backtracking."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from core.analyzer.readers import read_stl
from core.generator.native_hex import quality
from core.generator.native_hex.source_feature_sidecar_l1 import (
    AuthoritativeSourceFeatureManifest,
    ordered_triangle_coordinate_sha256,
)
from core.generator.native_hex.source_quad_inward_clearance_l0 import (
    audit_sampled_inward_clearance_l0,
)
from core.generator.native_hex.source_quad_normal_front_l1 import _inner_front_pair_counts
from core.generator.native_hex.source_quad_shell_concavity_l2 import (
    _raw_negative_hex_indices,
)
from core.generator.native_hex.source_triangle_quadization_l1 import (
    audit_exact_source_quadization_l1,
)
from core.layers.native_hex_inward_validity import signed_hex_corner_determinants

_ROOT = Path(__file__).resolve().parents[1]


def _native_or_skip() -> Any:
    module = quality._load_native_hex_quality()
    if module is None or not hasattr(module, "local_front_backtrack_steps"):
        pytest.skip("native_hex_quality local-front extension is not built")
    return module


def _fixture(
    path: Path,
    requested_thickness: float,
) -> tuple[
    np.ndarray,
    np.ndarray,
    np.ndarray,
    float,
    float,
    float,
    np.ndarray,
    np.ndarray,
    str,
]:
    mesh = read_stl(path)
    source_points = mesh.vertices.copy()
    source_faces = mesh.faces.copy()
    source_hash = sha256(path.read_bytes()).hexdigest()
    entities = (("fixture", "wall"),) * len(source_faces)
    manifest = AuthoritativeSourceFeatureManifest(
        source_hash,
        ordered_triangle_coordinate_sha256(source_points, source_faces),
        entities,
    )
    surface = audit_exact_source_quadization_l1(source_points, source_faces, entities)
    assert surface.status == "pass_exact_source_quadization"
    clearance = audit_sampled_inward_clearance_l0(
        source_points,
        source_faces,
        source_path=path,
        manifest=manifest,
        required_clearance=requested_thickness,
    )
    assert clearance.ray_hit_face_count == len(source_faces)
    assert clearance.minimum_clearance is not None

    outer = np.ascontiguousarray(surface.quadization.points, dtype=np.float64)
    quads = np.ascontiguousarray(surface.quadization.quads, dtype=np.int64)
    source_triangles = source_points[source_faces]
    face_normals = np.cross(
        source_triangles[:, 1] - source_triangles[:, 0],
        source_triangles[:, 2] - source_triangles[:, 0],
    )
    face_normals /= np.linalg.norm(face_normals, axis=1)[:, None]
    normals = np.zeros_like(outer)
    for quad, source_face in zip(
        quads,
        surface.quadization.source_face_ids,
        strict=True,
    ):
        normals[quad] += face_normals[int(source_face)]
    normals /= np.linalg.norm(normals, axis=1)[:, None]
    normals = np.ascontiguousarray(normals, dtype=np.float64)

    diagonal = float(np.linalg.norm(np.ptp(outer, axis=0)))
    geometry_tolerance = 64.0 * np.finfo(float).eps * max(1.0, diagonal)
    determinant_tolerance = 64.0 * np.finfo(float).eps * max(1.0, diagonal**3)
    initial_step = min(requested_thickness, 0.45 * clearance.minimum_clearance)
    return (
        outer,
        quads,
        normals,
        initial_step,
        geometry_tolerance,
        determinant_tolerance,
        source_points,
        source_faces,
        source_hash,
    )


def _points_and_hexes(
    outer: np.ndarray,
    quads: np.ndarray,
    normals: np.ndarray,
    steps: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    inner = outer - steps[:, None] * normals
    ordered_outer = quads[:, ::-1]
    hexes = np.hstack((ordered_outer, ordered_outer + len(outer)))
    return inner, np.vstack((outer, inner)), hexes


def _python_reference(
    outer: np.ndarray,
    quads: np.ndarray,
    normals: np.ndarray,
    initial_step: float,
    geometry_tolerance: float,
    determinant_tolerance: float,
    maximum_iterations: int = 32,
) -> tuple[np.ndarray, dict[str, int | float | bool]]:
    steps = np.full(len(outer), initial_step, dtype=np.float64)
    collapsed = np.empty(0, dtype=np.int64)
    for iteration in range(maximum_iterations + 1):
        _, points, hexes = _points_and_hexes(outer, quads, normals, steps)
        raw_negative = _raw_negative_hex_indices(points, hexes)
        determinants = signed_hex_corner_determinants(points, hexes)
        nonpositive = np.flatnonzero(np.any(determinants <= determinant_tolerance, axis=1))
        failing = np.union1d(raw_negative, nonpositive)
        if len(failing) == 0 or iteration == maximum_iterations:
            break
        affected = np.unique(quads[failing])
        proposed = steps[affected] * 0.5
        collapsed = affected[proposed <= geometry_tolerance]
        if len(collapsed):
            break
        steps[affected] = proposed
    return steps, {
        "iterations": iteration,
        "reduced_vertices": int(np.count_nonzero(steps < initial_step)),
        "collapsed_vertices": len(collapsed),
        "raw_negative_hexes": len(raw_negative),
        "nonpositive_corner_hexes": len(nonpositive),
        "minimum_corner_determinant": float(np.min(determinants)),
        "converged": len(failing) == 0,
    }


def _run_native(
    outer: np.ndarray,
    quads: np.ndarray,
    normals: np.ndarray,
    initial_step: float,
    geometry_tolerance: float,
    determinant_tolerance: float,
) -> dict[str, Any]:
    return dict(
        _native_or_skip().local_front_backtrack_steps(
            outer,
            quads,
            normals,
            initial_step,
            geometry_tolerance,
            determinant_tolerance,
            32,
        )
    )


def test_cpp23_cube_matches_independent_python_reference() -> None:
    path = _ROOT / "tests" / "benchmarks" / "cube.stl"
    (
        outer,
        quads,
        normals,
        initial_step,
        geometry_tolerance,
        determinant_tolerance,
        source_points,
        source_faces,
        source_hash,
    ) = _fixture(path, 0.1)
    outer_before, quads_before, normals_before = outer.copy(), quads.copy(), normals.copy()
    expected_steps, expected = _python_reference(
        outer,
        quads,
        normals,
        initial_step,
        geometry_tolerance,
        determinant_tolerance,
    )

    actual = _run_native(
        outer,
        quads,
        normals,
        initial_step,
        geometry_tolerance,
        determinant_tolerance,
    )

    assert isinstance(actual["local_steps"], np.ndarray)
    assert actual["local_steps"].dtype == np.dtype(np.float64)
    assert actual["local_steps"].flags.c_contiguous
    assert np.array_equal(actual["local_steps"], expected_steps)
    for key in expected:
        assert actual[key] == pytest.approx(expected[key], rel=0.0, abs=1.0e-18)
    assert actual["iterations"] == 0
    assert actual["reduced_vertices"] == 0
    assert actual["minimum_step"] == actual["maximum_step"] == 0.1
    assert actual["unit_normal_tolerance"] == 256.0 * np.finfo(np.float64).eps
    assert np.array_equal(outer, outer_before)
    assert np.array_equal(quads, quads_before)
    assert np.array_equal(normals, normals_before)
    assert np.array_equal(source_points, source_points.copy())
    assert np.array_equal(source_faces, source_faces.copy())
    assert sha256(path.read_bytes()).hexdigest() == source_hash


def test_cpp23_hard_bracket_preserves_frozen_metrics_and_determinism() -> None:
    path = _ROOT / "tests" / "stl" / "03_hard_bracket.stl"
    (
        outer,
        quads,
        normals,
        initial_step,
        geometry_tolerance,
        determinant_tolerance,
        source_points,
        source_faces,
        source_hash,
    ) = _fixture(path, 0.05)
    outer_before, quads_before, normals_before = outer.copy(), quads.copy(), normals.copy()
    expected_steps, expected = _python_reference(
        outer,
        quads,
        normals,
        initial_step,
        geometry_tolerance,
        determinant_tolerance,
    )
    requested_steps = np.full(len(outer), 0.05, dtype=np.float64)
    baseline_inner, baseline_points, baseline_hexes = _points_and_hexes(
        outer, quads, normals, requested_steps
    )
    assert len(_raw_negative_hex_indices(baseline_points, baseline_hexes)) == 160
    assert _inner_front_pair_counts(baseline_inner, quads) == (4161, 4)

    reports = tuple(
        _run_native(
            outer,
            quads,
            normals,
            initial_step,
            geometry_tolerance,
            determinant_tolerance,
        )
        for _ in range(3)
    )
    first = reports[0]
    assert initial_step == pytest.approx(0.01818845869286433, rel=0.0, abs=1.0e-17)
    assert np.array_equal(first["local_steps"], expected_steps)
    for key in expected:
        assert first[key] == pytest.approx(expected[key], rel=0.0, abs=1.0e-18)
    assert first["iterations"] == 8
    assert first["reduced_vertices"] == 740
    assert first["collapsed_vertices"] == 0
    assert first["raw_negative_hexes"] == 0
    assert first["nonpositive_corner_hexes"] == 0
    assert first["minimum_step"] == pytest.approx(7.104866676900129e-05, rel=0.0, abs=1.0e-18)
    assert first["minimum_step"] > geometry_tolerance
    assert first["minimum_corner_determinant"] == pytest.approx(
        7.581467097331643e-12, rel=2.0e-13, abs=1.0e-20
    )
    inner, points, hexes = _points_and_hexes(outer, quads, normals, first["local_steps"])
    assert len(_raw_negative_hex_indices(points, hexes)) == 0
    assert not np.any(signed_hex_corner_determinants(points, hexes) <= determinant_tolerance)
    assert _inner_front_pair_counts(inner, quads) == (0, 0)
    for report in reports[1:]:
        assert np.array_equal(report["local_steps"], first["local_steps"])
        assert {key: value for key, value in report.items() if key != "local_steps"} == {
            key: value for key, value in first.items() if key != "local_steps"
        }
    assert np.array_equal(outer, outer_before)
    assert np.array_equal(quads, quads_before)
    assert np.array_equal(normals, normals_before)
    assert source_points.tobytes() == source_points.copy().tobytes()
    assert source_faces.tobytes() == source_faces.copy().tobytes()
    assert sha256(path.read_bytes()).hexdigest() == source_hash


def test_cpp23_exact_contiguous_abi_and_validation_fail_before_input_mutation() -> None:
    path = _ROOT / "tests" / "benchmarks" / "cube.stl"
    outer, quads, normals, initial_step, geometry_tolerance, determinant_tolerance, *_ = _fixture(
        path, 0.1
    )
    native = _native_or_skip()
    outer_before, quads_before, normals_before = outer.copy(), quads.copy(), normals.copy()

    def call(points: np.ndarray, cells: np.ndarray, directions: np.ndarray, **kwargs: Any) -> Any:
        return native.local_front_backtrack_steps(
            points,
            cells,
            directions,
            kwargs.get("initial_step", initial_step),
            kwargs.get("geometry_tolerance", geometry_tolerance),
            kwargs.get("determinant_tolerance", determinant_tolerance),
            kwargs.get("maximum_iterations", 32),
        )

    with pytest.raises(TypeError):
        call(outer.astype(np.float32), quads, normals)
    with pytest.raises(TypeError):
        call(outer[:, ::-1], quads, normals)
    with pytest.raises(TypeError):
        call(outer, quads.astype(np.int32), normals)
    with pytest.raises(ValueError, match="shape"):
        call(outer.reshape(-1), quads, normals)
    duplicate = quads.copy()
    duplicate[0, 1] = duplicate[0, 0]
    with pytest.raises(ValueError, match="unique"):
        call(outer, duplicate, normals)
    out_of_range = quads.copy()
    out_of_range[0, 0] = len(outer)
    with pytest.raises(IndexError):
        call(outer, out_of_range, normals)
    nonunit = normals.copy()
    nonunit[0] *= 0.5
    with pytest.raises(ValueError, match="unit length"):
        call(outer, quads, nonunit)
    nonfinite = normals.copy()
    nonfinite[0, 0] = np.nan
    with pytest.raises(ValueError, match="finite"):
        call(outer, quads, nonfinite)
    with pytest.raises(ValueError, match="greater than"):
        call(outer, quads, normals, initial_step=geometry_tolerance)
    with pytest.raises(ValueError, match="finite and positive"):
        call(outer, quads, normals, geometry_tolerance=0.0)
    with pytest.raises(ValueError, match="non-negative"):
        call(outer, quads, normals, determinant_tolerance=-1.0)
    with pytest.raises(ValueError, match="finite and non-negative"):
        call(outer, quads, normals, determinant_tolerance=np.inf)
    with pytest.raises(ValueError, match=r"\[1, 64\]"):
        call(outer, quads, normals, maximum_iterations=0)
    with pytest.raises(ValueError, match=r"\[1, 64\]"):
        call(outer, quads, normals, maximum_iterations=65)

    assert np.array_equal(outer, outer_before)
    assert np.array_equal(quads, quads_before)
    assert np.array_equal(normals, normals_before)
