"""Parity and degeneracy tests for exact native tetrahedral predicates."""

from __future__ import annotations

from fractions import Fraction
from itertools import permutations

import numpy as np
import pytest


def _module_or_skip():
    from core.utils.native_extensions import load_native_tet_predicates

    module = load_native_tet_predicates()
    if module is None:
        pytest.skip("native_tet_predicates extension is unavailable")
    return module


def _orient3d_double(points: np.ndarray) -> np.ndarray:
    a = points[:, 0] - points[:, 3]
    b = points[:, 1] - points[:, 3]
    c = points[:, 2] - points[:, 3]
    det = np.einsum("ij,ij->i", a, np.cross(b, c))
    return np.sign(det).astype(np.int32)


def _permutation_sign(permutation: tuple[int, ...]) -> int:
    inversions = sum(
        permutation[i] > permutation[j]
        for i in range(len(permutation))
        for j in range(i + 1, len(permutation))
    )
    return -1 if inversions % 2 else 1


def _exact_power_insphere_sign(points: np.ndarray, weights: np.ndarray) -> int:
    matrix = []
    for point, weight in zip(points, weights, strict=True):
        x, y, z = (Fraction.from_float(float(value)) for value in point)
        w = Fraction.from_float(float(weight))
        matrix.append([x, y, z, x * x + y * y + z * z - w, Fraction(1)])
    determinant = sum(
        _permutation_sign(permutation)
        * np.prod([matrix[row][column] for row, column in enumerate(permutation)])
        for permutation in permutations(range(5))
    )
    return (determinant > 0) - (determinant < 0)


def test_orient3d_matches_well_conditioned_double_determinant() -> None:
    module = _module_or_skip()
    rng = np.random.default_rng(20260719)
    points = rng.normal(size=(128, 4, 3))
    expected = _orient3d_double(points)
    assert np.array_equal(module.orient3d_signs(points), expected)


def test_orient3d_recognizes_exact_coplanarity() -> None:
    module = _module_or_skip()
    points = np.array([[
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.25, 0.25, 0.0],
    ]])
    assert module.orient3d_signs(points).tolist() == [0]


def test_insphere_classifies_inside_and_outside() -> None:
    module = _module_or_skip()
    # Sign convention depends on tetrahedron orientation.  Compare magnitudes
    # by placing two query points on opposite sides of its circumsphere.
    points = np.array([
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0],
         [0.0, 0.0, 1.0], [0.5, 0.5, 0.5]],
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0],
         [0.0, 0.0, 1.0], [4.0, 4.0, 4.0]],
    ])
    signs = module.insphere_signs(points)
    assert signs[0] != 0
    assert signs[1] == -signs[0]


def test_predicates_reject_nonfinite_coordinates() -> None:
    module = _module_or_skip()
    points = np.zeros((1, 4, 3))
    points[0, 0, 0] = np.nan
    with pytest.raises(ValueError, match="finite"):
        module.orient3d_signs(points)


def test_native_boundary_audit_matches_numpy_fallback(monkeypatch) -> None:
    module = _module_or_skip()
    from core.generator.native_tet import rescue_gate
    from core.utils import native_extensions

    points = np.array([
        [0.0, 0.0, 0.0], [1.0, 0.0, 0.0],
        [1.0, 1.0, 0.0], [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0], [1.0, 0.0, 1.0],
        [1.0, 1.0, 1.0], [0.0, 1.0, 1.0],
    ])
    base_tets = np.array([
        [0, 1, 2, 6], [0, 2, 3, 6], [0, 3, 7, 6],
        [0, 7, 4, 6], [0, 4, 5, 6], [0, 5, 1, 6],
    ], dtype=np.int64)
    fixtures = (
        base_tets,
        np.vstack([base_tets, base_tets[:1]]),
        base_tets[[0, 3]],
        np.array([[0, 1, 2, 3]], dtype=np.int64),
        np.array([[0, 1, 3, 2]], dtype=np.int64),
    )

    for tets in fixtures:
        native_values = tuple(int(value) for value in module.audit_tet_boundary(points, tets))
        monkeypatch.setattr(native_extensions, "load_native_tet_predicates", lambda: None)
        fallback = rescue_gate.audit_tet_boundary(points, tets)
        fallback_values = tuple(fallback.__dict__.values())
        assert native_values == fallback_values


def test_native_boundary_audit_rejects_invalid_input() -> None:
    module = _module_or_skip()
    points = np.zeros((4, 3), dtype=np.float64)
    with pytest.raises(ValueError, match="index out of range"):
        module.audit_tet_boundary(
            points,
            np.array([[0, 1, 2, 9]], dtype=np.int64),
        )
    points[0, 0] = np.nan
    with pytest.raises(ValueError, match="finite"):
        module.audit_tet_boundary(
            points,
            np.array([[0, 1, 2, 3]], dtype=np.int64),
        )


def test_native_boundary_audit_inversion_matches_fallback_near_degenerate(
    monkeypatch,
) -> None:
    module = _module_or_skip()
    from core.generator.native_tet import rescue_gate
    from core.utils import native_extensions

    points = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0e-18]]
    )
    fixtures = (
        np.array([[0, 1, 2, 3]], dtype=np.int64),
        np.array([[0, 1, 3, 2]], dtype=np.int64),
    )

    for tets in fixtures:
        native_values = tuple(int(value) for value in module.audit_tet_boundary(points, tets))
        monkeypatch.setattr(native_extensions, "load_native_tet_predicates", lambda: None)
        fallback = rescue_gate.audit_tet_boundary(points, tets)
        assert native_values == tuple(fallback.__dict__.values())

    assert module.audit_tet_boundary(points, fixtures[0])[-1] == 0
    assert module.audit_tet_boundary(points, fixtures[1])[-1] == 1


def test_native_exact_batch_preserves_native_tet_volume_convention() -> None:
    _module_or_skip()
    from core.generator.native_tet.validate import orientation_signs

    points = np.array([
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0e-18],
    ])
    signs = orientation_signs(points, np.array([[0, 1, 2, 3]], dtype=np.int64))
    assert signs.tolist() == [1]


def test_power_insphere_matches_exact_python_rational_reference() -> None:
    module = _module_or_skip()
    points = np.array([
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0],
         [0.0, 0.0, 1.0], [0.5, 0.5, 0.5]],
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0],
         [0.0, 0.0, 1.0], [4.0, 4.0, 4.0]],
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0],
         [0.0, 0.0, 1.0], [0.5, 0.5, 0.5]],
    ])
    weights = np.array([
        [0.0, 0.0, 0.0, 0.0, 0.0],
        [0.0, 0.0, 0.0, 0.0, 0.0],
        [0.0, 0.0, 0.0, 0.0, 0.75],
    ])
    expected = [
        _exact_power_insphere_sign(row, row_weights)
        for row, row_weights in zip(points, weights, strict=True)
    ]
    assert module.power_insphere_signs_exact(points, weights).tolist() == expected


def test_weighted_regularization_applies_internal_23_without_boundary_change() -> None:
    module = _module_or_skip()
    points = np.array([
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
        [0.2, 0.2, -0.2],
    ])
    tets = np.array([[0, 1, 2, 3], [0, 2, 1, 4]], dtype=np.int64)
    output, stats = module.regularize_weighted_23(
        points, tets, np.zeros(len(points)), max_passes=2,
    )
    assert stats["applied"] == 1
    assert output.shape == (3, 4)
    assert np.all(np.array([
        np.dot(points[tet[1]] - points[tet[0]], np.cross(
            points[tet[2]] - points[tet[0]], points[tet[3]] - points[tet[0]],
        ))
        for tet in output
    ]) > 0.0)


def test_weighted_regularization_applies_internal_32_without_boundary_change() -> None:
    module = _module_or_skip()
    points = np.array([
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
        [0.2, 0.2, -0.2],
    ])
    two_tets = np.array([[0, 1, 2, 3], [0, 2, 1, 4]], dtype=np.int64)
    three_tets, stats_23 = module.regularize_weighted_23(
        points, two_tets, np.zeros(len(points)), max_passes=2,
    )
    assert stats_23["applied"] == 1

    # Lowering upper-apex weight makes the two-tet split regular again.
    weights = np.zeros(len(points))
    weights[3] = -1.0
    output, stats_32 = module.regularize_weighted_32(
        points, three_tets, weights, max_passes=2,
    )
    assert stats_32["applied"] == 1
    assert output.shape == (2, 4)
    assert np.all(np.array([
        np.dot(points[tet[1]] - points[tet[0]], np.cross(
            points[tet[2]] - points[tet[0]], points[tet[3]] - points[tet[0]],
        ))
        for tet in output
    ]) > 0.0)


def test_native_targeted_23_recovery_is_oriented_and_recovers_edge() -> None:
    module = _module_or_skip()
    points = np.array([
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
        [0.2, 0.2, -0.2],
    ])
    tets = np.array([[0, 1, 2, 3], [0, 2, 1, 4]], dtype=np.int64)

    output, stats = module.recover_targeted_edges_23(
        points, tets, np.array([[3, 4]], dtype=np.int64), max_attempts=1,
    )

    assert stats == {"attempted": 1, "recovered": 1}
    assert output.shape == (3, 4)
    assert np.all((output == 3).any(axis=1) & (output == 4).any(axis=1))
    assert np.all(np.array([
        np.dot(points[tet[1]] - points[tet[0]], np.cross(
            points[tet[2]] - points[tet[0]], points[tet[3]] - points[tet[0]],
        ))
        for tet in output
    ]) > 0.0)

    from core.generator.native_tet.edge_flip_recovery import recover_edges_via_flip

    wrapped_output, wrapped_stats = recover_edges_via_flip(
        points, tets, [(3, 4)], max_attempts=1,
    )
    assert wrapped_stats.n_edges_attempted == 1
    assert wrapped_stats.n_edges_recovered == 1
    assert np.array_equal(wrapped_output, output)


def test_sliver_weight_pumping_is_bounded_to_worst_incident_vertices() -> None:
    from core.generator.native_tet.stellar import _sliver_weight_pumping_samples

    points = np.array([
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0e-5],
        [3.0, 0.0, 0.0],
        [2.0, 2.0, 0.0],
        [2.0, 0.0, 2.0],
        [2.0, 2.0, 2.0],
    ])
    tets = np.array([[0, 1, 2, 3], [4, 5, 6, 7]], dtype=np.int64)
    samples = _sliver_weight_pumping_samples(
        points, tets, n_samples=4, alpha=0.4, max_worst_tets=1,
    )

    assert samples.shape == (4, 8)
    assert np.all(samples >= 0.0)
    assert np.all(samples[:, 4:] == 0.0)
    assert np.count_nonzero(samples[-1, :4]) == 4
    assert np.all(samples[-1, :4] <= 0.16 + 1e-15)


def test_native_44_flip_uses_link_cycle_and_preserves_boundary() -> None:
    module = _module_or_skip()
    points = np.array([
        [0.9456802790428398, 0.0, -0.04655845840920658],
        [0.0, 1.6479366850027746, -0.03823035091197147],
        [-0.2497516847115035, 0.0, 0.41327366476728133],
        [0.0, -1.0711435281879165, -0.17910100279165853],
        [0.0, 0.0, -1.0],
        [0.0, 0.0, 1.0],
    ])
    tets = np.array([
        [4, 5, 0, 1], [4, 5, 1, 2], [4, 5, 2, 3], [4, 5, 3, 0],
    ], dtype=np.int64)

    def boundary_faces(cells: np.ndarray) -> set[tuple[int, int, int]]:
        counts: dict[tuple[int, int, int], int] = {}
        for tet in cells:
            for excluded in range(4):
                face = tuple(sorted(np.delete(tet, excluded).tolist()))
                counts[face] = counts.get(face, 0) + 1
        return {face for face, count in counts.items() if count == 1}

    before_boundary = boundary_faces(tets)
    output, stats = module.flip_44_quality(
        points, tets, max_passes=1, min_quality_improvement=1e-6,
    )
    assert stats["applied"] == 1
    assert output.shape == tets.shape
    assert boundary_faces(output) == before_boundary
    assert np.all(np.array([
        np.dot(points[tet[1]] - points[tet[0]], np.cross(
            points[tet[2]] - points[tet[0]], points[tet[3]] - points[tet[0]],
        ))
        for tet in output
    ]) > 0.0)


def test_native_quality_metrics_match_python_fallback_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module_or_skip()
    from core.generator.native_tet import quality

    rng = np.random.default_rng(20260720)
    points = rng.normal(size=(32, 3))
    tets = np.array(
        [rng.choice(len(points), size=4, replace=False) for _ in range(96)],
        dtype=np.int64,
    )

    shape, aspect, dihedral, volume6 = module.tet_quality_metrics(points, tets)
    native_snapshot = quality.snapshot(points, tets)

    monkeypatch.setattr(quality, "_native_tet_quality_metrics", lambda *_: None)
    fallback_snapshot = quality.snapshot(points, tets)

    assert np.allclose(shape, quality.tet_shape_quality(points, tets), rtol=1e-12, atol=1e-12)
    assert np.allclose(aspect, quality.tet_aspect_ratio(points, tets), rtol=1e-12, atol=1e-12)
    assert np.allclose(dihedral, quality.tet_min_dihedral_deg(points, tets), rtol=1e-11, atol=1e-11)
    assert np.all(volume6 > 0.0)
    for field in (
        "min_q", "mean_q", "median_q", "max_aspect", "mean_aspect",
        "min_dihedral_deg", "median_dihedral_deg", "vol_weighted_mean_q",
        "p10_q", "p10_dihedral_deg",
    ):
        assert np.isclose(
            getattr(native_snapshot, field), getattr(fallback_snapshot, field),
            rtol=1e-11, atol=1e-11,
        ), field


def test_native_cdt_audit_matches_python_oracle_randomized() -> None:
    module = _module_or_skip()
    from core.generator.native_tet.cdt_check import _check_edge_recovery_python

    rng = np.random.default_rng(20260730)
    for _ in range(100):
        faces = rng.integers(0, 48, size=(24, 3), dtype=np.int64)
        tets = rng.integers(0, 64, size=(32, 4), dtype=np.int64)
        expected = _check_edge_recovery_python(faces, tets)
        actual = module.audit_cdt_constraints(faces, tets)
        assert int(actual["n_surface_edges"]) == expected.n_surface_edges
        assert (
            int(actual["n_present_as_tet_edges"])
            == expected.n_present_as_tet_edges
        )
        assert int(actual["n_missing"]) == expected.n_missing
        assert np.asarray(actual["missing_edges"]).tolist() == [
            list(edge) for edge in expected.missing_edges
        ]
        assert int(actual["n_surface_faces"]) == expected.n_surface_faces
        assert (
            int(actual["n_present_as_tet_faces"])
            == expected.n_present_as_tet_faces
        )
        assert int(actual["n_missing_faces"]) == expected.n_missing_faces


def test_native_cdt_audit_preserves_sparse_int64_indices() -> None:
    module = _module_or_skip()
    from core.generator.native_tet.cdt_check import _check_edge_recovery_python

    high = np.int64(3_100_000_000)
    faces = np.array([
        [high, high + 1, high + 2],
        [9, 7, 8],
        [high + 2, high, high + 1],
    ], dtype=np.int64)
    tets = np.array([
        [high, high + 1, high + 2, high + 3],
        [7, 8, 10, 11],
    ], dtype=np.int64)
    expected = _check_edge_recovery_python(faces, tets)
    actual = module.audit_cdt_constraints(faces, tets)
    assert np.asarray(actual["missing_edges"]).tolist() == [
        list(edge) for edge in expected.missing_edges
    ]
    assert (
        int(actual["n_present_as_tet_faces"])
        == expected.n_present_as_tet_faces
    )
    assert int(actual["n_missing_faces"]) == expected.n_missing_faces


def test_native_cdt_audit_requires_exact_contiguous_int64_abi() -> None:
    module = _module_or_skip()
    faces = np.array([[0, 1, 2]], dtype=np.int64)
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)

    with pytest.raises(TypeError, match="dtype int64"):
        module.audit_cdt_constraints(faces.astype(np.int32), tets)
    with pytest.raises(TypeError):
        module.audit_cdt_constraints([[0, 1, 2]], tets)
    with pytest.raises(ValueError, match="C-contiguous"):
        module.audit_cdt_constraints(np.vstack([faces] * 4)[::2], tets)
    with pytest.raises(ValueError, match="negative index"):
        module.audit_cdt_constraints(
            np.array([[-1, 1, 2]], dtype=np.int64), tets
        )
    with pytest.raises(ValueError, match="shape"):
        module.audit_cdt_constraints(
            np.array([[0, 1]], dtype=np.int64), tets
        )


def test_native_cdt_audit_missing_edges_are_deterministic_and_sorted() -> None:
    module = _module_or_skip()
    faces = np.array([[8, 4, 6], [2, 1, 0], [6, 4, 8]], dtype=np.int64)
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    outputs = [
        np.asarray(
            module.audit_cdt_constraints(faces, tets)["missing_edges"]
        ).tolist()
        for _ in range(3)
    ]
    assert outputs[0] == sorted(outputs[0])
    assert outputs[0] == outputs[1] == outputs[2]


def test_native_source_component_audit_requires_exact_contiguous_abi() -> None:
    module = _module_or_skip()
    points = np.asarray(
        ((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)),
        dtype=np.float64,
    )
    faces = np.asarray(
        ((0, 1, 2), (0, 1, 3), (0, 2, 3), (1, 2, 3)),
        dtype=np.int64,
    )
    tets = np.asarray(((0, 1, 2, 3),), dtype=np.int64)

    assert module.audit_source_component_bijection(
        points, faces, points.copy(), tets
    )["bijective"]
    with pytest.raises(TypeError, match="dtype float64"):
        module.audit_source_component_bijection(
            points.astype(np.float32), faces, points, tets
        )
    with pytest.raises(TypeError, match="dtype int64"):
        module.audit_source_component_bijection(
            points, faces.astype(np.int32), points, tets
        )
    with pytest.raises(ValueError, match="C-contiguous"):
        module.audit_source_component_bijection(
            np.asfortranarray(points), faces, points, tets
        )
    with pytest.raises(ValueError, match="C-contiguous"):
        module.audit_source_component_bijection(
            points, np.vstack([faces, faces])[::2], points, tets
        )
    nonfinite = points.copy()
    nonfinite[0, 0] = np.inf
    with pytest.raises(ValueError, match="finite"):
        module.audit_source_component_bijection(points, faces, nonfinite, tets)
    duplicate_source = points.copy()
    duplicate_source[1] = duplicate_source[0]
    with pytest.raises(ValueError, match="ambiguous duplicate"):
        module.audit_source_component_bijection(
            duplicate_source, faces, points, tets
        )
    with pytest.raises(ValueError, match="duplicates a source coordinate"):
        module.audit_source_component_bijection(
            points, faces, np.vstack([points, points[:1]]), tets
        )
    with pytest.raises(ValueError, match="out of range"):
        module.audit_source_component_bijection(
            points, faces, points, np.asarray(((0, 1, 2, 9),), dtype=np.int64)
        )
