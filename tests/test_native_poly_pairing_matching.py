"""Exactness and termination checks for native poly face-pair matching."""

from __future__ import annotations

import itertools
import time
from typing import Any

import numpy as np
import pytest

from core.evaluator import poly_quality_metrics as pqm
from core.utils.native_extensions import load_native_metrics


def _native_metrics_or_skip() -> Any:
    module = load_native_metrics()
    if module is None:
        pytest.skip("native weighted-pairing kernel is not built")
    assert hasattr(
        module, "minimum_pairing_sum"
    ), "loaded native_metrics is stale: minimum_pairing_sum ABI missing"
    return module


def test_native_pairing_matches_exhaustive_oracle_through_14_vectors() -> None:
    module = _native_metrics_or_skip()
    rng = np.random.default_rng(20260731)

    for vector_count in range(15):
        for case_index in range(100):
            vectors = rng.normal(size=(vector_count, 3))
            variant = case_index % 5
            if variant == 0:
                vectors *= 10.0 ** rng.uniform(-12.0, 12.0)
            elif variant == 1 and vector_count:
                vectors[:, 1:] *= 1.0e-12
            elif variant == 2 and vector_count >= 2:
                vectors[1::2] = -vectors[: len(vectors[1::2]) * 2 : 2]
            elif variant == 3:
                vectors = np.round(vectors, decimals=1)
            elif variant == 4 and vector_count:
                scales = 10.0 ** rng.uniform(-12.0, 12.0, size=(vector_count, 1))
                vectors *= scales
            expected = pqm._minimum_pairing_sum_exhaustive(vectors)
            actual = float(module.minimum_pairing_sum(vectors))
            assert actual == pytest.approx(expected, rel=1.0e-12, abs=1.0e-12)


@pytest.mark.parametrize(
    "vectors",
    [
        np.ones((64, 3), dtype=np.float64),
        np.tile(np.asarray(((1.0, 0.0, 0.0), (-1.0, 0.0, 0.0))), (32, 1)),
        np.column_stack(
            (
                np.ones(48),
                np.linspace(-1.0e-12, 1.0e-12, 48),
                np.linspace(1.0e-12, -1.0e-12, 48),
            )
        ),
        np.random.default_rng(20260731).normal(size=(37, 3)),
        np.vstack(
            (
                np.tile(np.asarray((1.0, 0.0, 0.0)), (35, 1)),
                np.tile(np.asarray((-1.0, 0.0, 0.0)), (2, 1)),
            )
        ),
    ],
    ids=[
        "equal-dense",
        "antipodal-dense",
        "near-tie-dense",
        "odd-random-dense",
        "sparse-positive-saving-core",
    ],
)
def test_native_pairing_dense_cases_terminate_and_ignore_order(
    vectors: np.ndarray,
) -> None:
    module = _native_metrics_or_skip()
    rng = np.random.default_rng(31072026)

    started = time.perf_counter()
    expected = float(module.minimum_pairing_sum(vectors))
    for _ in range(8):
        permutation = rng.permutation(len(vectors))
        actual = float(module.minimum_pairing_sum(vectors[permutation]))
        assert actual == pytest.approx(expected, rel=1.0e-12, abs=1.0e-12)
    assert time.perf_counter() - started < 2.0


def test_python_pairing_fallback_keeps_exact_small_oracle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vectors = np.random.default_rng(31).normal(size=(12, 3))
    expected = pqm._minimum_pairing_sum_exhaustive(vectors)
    monkeypatch.setattr(pqm, "load_native_metrics", lambda: None)

    assert pqm._minimum_pairing_sum(vectors) == pytest.approx(expected, rel=0.0, abs=0.0)


def test_python_pairing_rejects_loaded_stale_native_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stale_module = object()
    monkeypatch.setattr(pqm, "load_native_metrics", lambda: stale_module)

    with pytest.raises(RuntimeError, match="missing required minimum_pairing_sum ABI"):
        pqm._minimum_pairing_sum(np.zeros((2, 3), dtype=np.float64))


@pytest.mark.parametrize(
    ("vectors", "expected"),
    [
        (
            np.asarray(
                (
                    (1.0e9, 0.0, 0.0),
                    (-1.0e9, 0.0, 0.0),
                    (2.0e-7, 0.0, 0.0),
                    (2.0e-7, 0.0, 0.0),
                    (-2.0e-7, 0.0, 0.0),
                    (-2.0e-7, 0.0, 0.0),
                ),
                dtype=np.float64,
            ),
            0.0,
        ),
        (
            np.asarray(
                (
                    (1.0e9, 0.0, 0.0),
                    (-1.0e9, 0.0, 0.0),
                    (1.0e-7, 0.0, 0.0),
                    (0.0, 1.0e-7, 0.0),
                    (0.0, 0.0, 0.0),
                ),
                dtype=np.float64,
            ),
            np.sqrt(2.0) * 1.0e-7,
        ),
        (
            np.asarray(
                (
                    (1.0e150, 0.0, 0.0),
                    (-1.0e150, 0.0, 0.0),
                    (1.0e-150, 0.0, 0.0),
                    (-1.0e-150, 0.0, 0.0),
                    (2.0e-150, 0.0, 0.0),
                    (-2.0e-150, 0.0, 0.0),
                ),
                dtype=np.float64,
            ),
            0.0,
        ),
    ],
    ids=["mixed-scale-even", "mixed-scale-odd", "wide-binary64-exponent-span"],
)
def test_native_pairing_mixed_scale_is_exact_and_permutation_invariant(
    vectors: np.ndarray,
    expected: float,
) -> None:
    module = _native_metrics_or_skip()
    assert pqm._minimum_pairing_sum_exhaustive(vectors) == pytest.approx(
        expected, rel=0.0, abs=1.0e-22
    )
    observed = [
        float(module.minimum_pairing_sum(vectors[list(permutation)]))
        for permutation in itertools.permutations(range(len(vectors)))
    ]
    assert observed == pytest.approx([expected] * len(observed), rel=0.0, abs=1.0e-22)


def test_native_pairing_odd_blossom_regression_matches_every_permutation() -> None:
    module = _native_metrics_or_skip()
    vectors = np.asarray(
        (
            (1.22535748e-5, -1.83079027e-5, 9.95455674e-6),
            (4.54103343e-6, 1.09611877e-5, 3.06626045e-6),
            (-7.56579825e-6, 1.03895936e-5, -7.09208456e-6),
            (-6.97157287e-6, 1.06062336e-5, 1.27465311e-5),
            (-2.68934213e-5, 4.59077906e-6, -1.63868275e-5),
        ),
        dtype=np.float64,
    )
    expected = pqm._minimum_pairing_sum_exhaustive(vectors)
    observed = [
        float(module.minimum_pairing_sum(vectors[list(permutation)]))
        for permutation in itertools.permutations(range(len(vectors)))
    ]

    assert max(observed) == min(observed)
    assert observed[0] == pytest.approx(expected, rel=1.0e-15, abs=1.0e-20)


def test_native_pairing_rejects_invalid_or_excessive_inputs() -> None:
    module = _native_metrics_or_skip()
    with pytest.raises(ValueError, match="shape"):
        module.minimum_pairing_sum(np.zeros((4, 2), dtype=np.float64))
    with pytest.raises(ValueError, match="finite"):
        module.minimum_pairing_sum(np.asarray(((0.0, np.nan, 0.0),)))
    with pytest.raises(ValueError, match="at most 256"):
        module.minimum_pairing_sum(np.zeros((257, 3), dtype=np.float64))

    class ExplodingFloat:
        def __float__(self) -> float:
            raise AssertionError("oversized input was cast before its row-count check")

    oversized = np.empty((257, 3), dtype=object)
    oversized.fill(ExplodingFloat())
    with pytest.raises(ValueError, match="at most 256"):
        module.minimum_pairing_sum(oversized)
