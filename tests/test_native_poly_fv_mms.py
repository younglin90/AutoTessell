"""Tests for the report-only POLY-FVERR-RANDPERT1 MMS prerequisite."""

from __future__ import annotations

import numpy as np

from core.generator.native_poly.fv_mms import (
    build_cartesian_hex_grid,
    convergence_orders,
    run_laplacian_mms,
)


def test_regular_cartesian_mms_is_second_order_and_deterministic() -> None:
    first = run_laplacian_mms((4, 8, 16), perturb_fraction=0.0, seed=17)
    second = run_laplacian_mms((4, 8, 16), perturb_fraction=0.0, seed=17)

    assert first == second
    assert all(result.max_non_ortho_deg < 1e-12 for result in first)
    assert all(result.max_skew_proxy < 1e-12 for result in first)
    assert all(order > 1.8 for order in convergence_orders(first))


def test_random_perturbation_keeps_cells_valid_and_is_reproducible() -> None:
    points_a, cells_a = build_cartesian_hex_grid(8, perturb_fraction=0.25, seed=17)
    points_b, cells_b = build_cartesian_hex_grid(8, perturb_fraction=0.25, seed=17)
    assert np.array_equal(points_a, points_b)
    assert cells_a == cells_b

    results = run_laplacian_mms((4, 8, 16), perturb_fraction=0.25, seed=17)
    assert all(np.isfinite(result.l2_error) for result in results)
    assert all(result.max_non_ortho_deg < 90.0 for result in results)
    assert all(result.max_skew_proxy < 1.0 for result in results)


def test_report_only_nonorthogonal_correction_recovers_random_perturbation_order() -> None:
    results = run_laplacian_mms(
        (4, 8, 16),
        perturb_fraction=0.25,
        seed=17,
        nonorthogonal_correction=True,
    )

    assert all(np.isfinite(result.l2_error) for result in results)
    assert all(order > 1.8 for order in convergence_orders(results))
