"""Parity and fail-closed checks for the C++23 poly dual-point kernel."""

from __future__ import annotations

import hashlib
import types
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from core.generator.native_poly import dual
from core.utils import native_extensions
from core.utils.polymesh_reader import parse_foam_points_array


def _native_or_skip() -> Any:
    native = native_extensions.load_native_polymesh()
    if native is None or not hasattr(native, "compute_tet_dual_points"):
        pytest.skip("native poly dual-point kernel is not built")
    return native


def _mixed_tets() -> tuple[np.ndarray, np.ndarray]:
    points = np.asarray(
        (
            (1.0, 1.0, 1.0),
            (1.0, -1.0, -1.0),
            (-1.0, 1.0, -1.0),
            (-1.0, -1.0, 1.0),
            (3.0, 0.0, 0.0),
            (4.0, 0.0, 0.0),
            (3.0, 1.0, 0.0),
            (3.0, 0.0, 1.0),
            (6.0, 0.0, 0.0),
            (7.0, 0.0, 0.0),
            (6.0, 1.0, 0.0),
            (7.0, 1.0, 0.0),
        ),
        dtype=np.float64,
    )
    tets = np.asarray(
        ((0, 1, 2, 3), (4, 5, 6, 7), (8, 9, 10, 11)),
        dtype=np.int64,
    )
    return points, tets


def test_native_dual_points_match_python_oracle_and_status() -> None:
    native = _native_or_skip()
    points, tets = _mixed_tets()

    actual_points, actual_status = native.compute_tet_dual_points(points, tets)
    expected_points, expected_status = dual._compute_tet_dual_points_python(points, tets)

    actual_points = np.asarray(actual_points)
    actual_status = np.asarray(actual_status)
    np.testing.assert_allclose(actual_points, expected_points, rtol=2e-14, atol=2e-14)
    assert np.array_equal(np.rint(actual_points * 1e9), np.rint(expected_points * 1e9))
    assert actual_status.tolist() == [0, 1, 2]
    assert np.array_equal(actual_status, expected_status)


def test_native_dual_points_seeded_quantized_key_parity() -> None:
    native = _native_or_skip()
    rng = np.random.default_rng(29)
    n_tets = 2_000
    bases = rng.uniform(-10.0, 10.0, size=(n_tets, 3))
    offsets = np.asarray(
        ((0.0, 0.0, 0.0), (0.017, 0.0, 0.0), (0.0, 0.013, 0.0), (0.0, 0.0, 0.011)),
        dtype=np.float64,
    )
    points = np.ascontiguousarray((bases[:, None, :] + offsets).reshape(-1, 3))
    tets = np.arange(4 * n_tets, dtype=np.int64).reshape(n_tets, 4)

    actual_points, actual_status = native.compute_tet_dual_points(points, tets)
    expected_points, expected_status = dual._compute_tet_dual_points_python(points, tets)

    assert np.array_equal(
        np.rint(np.asarray(actual_points) * 1e9),
        np.rint(expected_points * 1e9),
    )
    assert np.array_equal(np.asarray(actual_status), expected_status)


def test_native_dual_points_near_singular_and_huge_scale_parity() -> None:
    native = _native_or_skip()
    points = np.asarray(
        (
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.25, 0.25, 1e-10),
            (1e100, 1e100, 1e100),
            (1e100, -1e100, -1e100),
            (-1e100, 1e100, -1e100),
            (-1e100, -1e100, 1e100),
        ),
        dtype=np.float64,
    )
    tets = np.asarray(((0, 1, 2, 3), (4, 5, 6, 7)), dtype=np.int64)

    actual_points, actual_status = native.compute_tet_dual_points(points, tets)
    expected_points, expected_status = dual._compute_tet_dual_points_python(points, tets)

    np.testing.assert_allclose(actual_points, expected_points, rtol=5e-13, atol=1e-12)
    assert np.array_equal(np.asarray(actual_status), expected_status)
    assert np.array_equal(
        np.rint(np.asarray(actual_points)[0] * 1e9),
        np.rint(expected_points[0] * 1e9),
    )


def test_native_dual_points_empty_and_three_run_determinism() -> None:
    native = _native_or_skip()
    empty_points = np.empty((0, 3), dtype=np.float64)
    empty_tets = np.empty((0, 4), dtype=np.int64)
    empty_result = native.compute_tet_dual_points(empty_points, empty_tets)
    assert np.asarray(empty_result[0]).shape == (0, 3)
    assert np.asarray(empty_result[1]).shape == (0,)

    points, tets = _mixed_tets()
    repeats = [native.compute_tet_dual_points(points, tets) for _ in range(3)]
    for actual in repeats[1:]:
        assert np.array_equal(np.asarray(actual[0]), np.asarray(repeats[0][0]))
        assert np.array_equal(np.asarray(actual[1]), np.asarray(repeats[0][1]))


def test_native_dual_points_strict_arrays() -> None:
    native = _native_or_skip()
    points, tets = _mixed_tets()

    with pytest.raises(TypeError):
        native.compute_tet_dual_points(points.astype(np.float32), tets)
    with pytest.raises(TypeError):
        native.compute_tet_dual_points(points, tets.astype(np.int32))
    with pytest.raises(TypeError):
        native.compute_tet_dual_points(points[:, ::-1], tets)


def test_backend_independent_preflight_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    native = _native_or_skip()
    points, tets = _mixed_tets()
    cases: list[tuple[np.ndarray, np.ndarray]] = []

    nonfinite = points.copy()
    nonfinite[0, 0] = np.nan
    cases.append((nonfinite, tets))
    negative = tets.copy()
    negative[0, 0] = -1
    cases.append((points, negative))
    out_of_bounds = tets.copy()
    out_of_bounds[0, 0] = len(points)
    cases.append((points, out_of_bounds))
    repeated = tets.copy()
    repeated[0, 1] = repeated[0, 0]
    cases.append((points, repeated))
    cases.append((points[:, :2].copy(), tets))
    cases.append((points, tets[:, :3].copy()))

    for invalid_points, invalid_tets in cases:
        with pytest.raises(ValueError) as native_error:
            native.compute_tet_dual_points(invalid_points, invalid_tets)
        with monkeypatch.context() as patch:
            patch.setattr(native_extensions, "load_native_polymesh", lambda: None)
            with pytest.raises(ValueError) as python_error:
                dual._compute_tet_dual_points_with_status(invalid_points, invalid_tets)
        assert str(native_error.value) == str(python_error.value)


def test_noncontiguous_wrapper_uses_python_oracle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class NativeMustNotRun:
        @staticmethod
        def compute_tet_dual_points(*_args: object) -> None:
            raise AssertionError("non-contiguous arrays must use the Python oracle")

    points, tets = _mixed_tets()
    monkeypatch.setattr(native_extensions, "load_native_polymesh", lambda: NativeMustNotRun())

    variants = (
        (np.asfortranarray(points), np.asfortranarray(tets)),
        (points.astype(np.float32), tets),
        (points, tets.astype(np.int32)),
    )
    for variant_points, variant_tets in variants:
        actual = dual._compute_tet_dual_points_with_status(variant_points, variant_tets)
        expected = dual._compute_tet_dual_points_python(variant_points, variant_tets)
        np.testing.assert_array_equal(actual[0], expected[0])
        np.testing.assert_array_equal(actual[1], expected[1])


def _snapshot_except_points(case_dir: Path) -> dict[str, tuple[str, bytes]]:
    snapshot: dict[str, tuple[str, bytes]] = {}
    for path in sorted(item for item in case_dir.rglob("*") if item.is_file()):
        if path.name == "points" and path.parent.name == "polyMesh":
            continue
        payload = path.read_bytes()
        snapshot[str(path.relative_to(case_dir))] = (
            hashlib.sha256(payload).hexdigest(),
            payload,
        )
    return snapshot


def test_classified_dual_preserves_topology_and_provenance(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    native = _native_or_skip()
    fallback_module = types.SimpleNamespace(
        **{
            name: getattr(native, name)
            for name in (
                "build_tet_incidence_maps",
                "face_flip_mask",
                "face_plane_geometry",
                "star_validity",
            )
        }
    )
    points = np.asarray(
        (
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.3, 0.3, 1.0),
            (0.3, 0.3, -1.0),
        ),
        dtype=np.float64,
    )
    tets = np.asarray(((0, 1, 2, 3), (0, 2, 1, 4)), dtype=np.int64)
    points_hash = hashlib.sha256(points.tobytes()).hexdigest()
    tets_hash = hashlib.sha256(tets.tobytes()).hexdigest()

    monkeypatch.setattr(native_extensions, "load_native_polymesh", lambda: native)
    native_case = tmp_path / "native"
    native_result = dual.tet_to_poly_dual(
        points,
        tets,
        native_case,
        boundary_face_classifier=lambda _triangle, _points: "wall",
    )

    monkeypatch.setattr(native_extensions, "load_native_polymesh", lambda: fallback_module)
    python_case = tmp_path / "python"
    python_result = dual.tet_to_poly_dual(
        points,
        tets,
        python_case,
        boundary_face_classifier=lambda _triangle, _points: "wall",
    )

    assert native_result.success and python_result.success
    assert (
        native_result.n_cells,
        native_result.n_points,
        native_result.n_faces,
        native_result.invalid_star_cells,
        native_result.invalid_star_subtets,
    ) == (
        python_result.n_cells,
        python_result.n_points,
        python_result.n_faces,
        python_result.invalid_star_cells,
        python_result.invalid_star_subtets,
    )
    assert _snapshot_except_points(native_case) == _snapshot_except_points(python_case)
    native_points = parse_foam_points_array(native_case / "constant" / "polyMesh" / "points")
    python_points = parse_foam_points_array(python_case / "constant" / "polyMesh" / "points")
    assert np.array_equal(np.rint(native_points * 1e9), np.rint(python_points * 1e9))
    assert hashlib.sha256(points.tobytes()).hexdigest() == points_hash
    assert hashlib.sha256(tets.tobytes()).hexdigest() == tets_hash
