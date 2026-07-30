"""Exactness and termination checks for native poly face-pair matching."""

from __future__ import annotations

import time
from typing import Any

import numpy as np
import pytest

from core.evaluator import poly_quality_metrics as pqm
from core.utils.native_extensions import load_native_metrics


def _native_metrics_or_skip() -> Any:
    module = load_native_metrics()
    if module is None or not hasattr(module, "minimum_pairing_sum"):
        pytest.skip("native weighted-pairing kernel is not built")
    return module


def test_native_pairing_matches_exhaustive_oracle_through_14_vectors() -> None:
    module = _native_metrics_or_skip()
    rng = np.random.default_rng(20260731)

    for vector_count in range(15):
        for _ in range(12):
            vectors = rng.normal(size=(vector_count, 3))
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
    ],
    ids=["equal-dense", "antipodal-dense", "near-tie-dense", "odd-random-dense"],
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


def test_native_pairing_rejects_invalid_or_excessive_inputs() -> None:
    module = _native_metrics_or_skip()
    with pytest.raises(ValueError, match="shape"):
        module.minimum_pairing_sum(np.zeros((4, 2), dtype=np.float64))
    with pytest.raises(ValueError, match="finite"):
        module.minimum_pairing_sum(np.asarray(((0.0, np.nan, 0.0),)))
    with pytest.raises(ValueError, match="at most 256"):
        module.minimum_pairing_sum(np.zeros((257, 3), dtype=np.float64))
