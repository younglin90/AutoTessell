"""L0 contracts for row-aligned pinned seeds during Lloyd compaction."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pytest

from core.generator.native_poly import voronoi as poly_voronoi

_DELTA = np.array([0.25, 0.0, 0.0], dtype=np.float64)
_OFFSETS = np.array(
    [
        [0.125, 0.0, 0.0],
        [-0.125, 0.0, 0.0],
        [0.0, 0.125, 0.0],
        [0.0, -0.125, 0.0],
    ],
    dtype=np.float64,
)
_SURFACE_VERTICES = np.array(
    [
        [-10.0, -10.0, -10.0],
        [10.0, -10.0, -10.0],
        [-10.0, 10.0, -10.0],
        [-10.0, -10.0, 10.0],
    ],
    dtype=np.float64,
)
_SURFACE_FACES = np.array([[0, 1, 2], [0, 3, 1], [0, 2, 3], [1, 3, 2]], dtype=np.int64)


class _DeterministicVoronoi:
    """Minimal closed-region oracle with an exact per-iteration displacement."""

    def __init__(self, points: np.ndarray) -> None:
        rows = np.asarray(points, dtype=np.float64)
        self.point_region = np.arange(rows.shape[0], dtype=np.int64)
        self.regions: list[list[int]] = []
        vertices: list[np.ndarray] = []
        for point in rows:
            start = len(vertices)
            vertices.extend(point + _DELTA + _OFFSETS)
            self.regions.append(list(range(start, start + 4)))
        self.vertices = np.asarray(vertices, dtype=np.float64)


def _install_oracles(
    monkeypatch: pytest.MonkeyPatch,
    mask_factory: Callable[[int, int], np.ndarray],
) -> None:
    scipy_spatial = pytest.importorskip("scipy.spatial")
    monkeypatch.setattr(scipy_spatial, "Voronoi", _DeterministicVoronoi)
    calls = 0

    def inside(points: np.ndarray, _vertices: np.ndarray, _faces: np.ndarray) -> np.ndarray:
        nonlocal calls
        mask = np.asarray(mask_factory(calls, points.shape[0]), dtype=bool)
        calls += 1
        assert mask.shape == (points.shape[0],)
        return mask

    monkeypatch.setattr(poly_voronoi, "_inside_ray_cast", inside)


def _seeds() -> np.ndarray:
    return np.arange(24, dtype=np.float64).reshape(8, 3)


def _run(
    monkeypatch: pytest.MonkeyPatch,
    *,
    pin_mask: np.ndarray | None,
    mask_factory: Callable[[int, int], np.ndarray],
) -> np.ndarray:
    _install_oracles(monkeypatch, mask_factory)
    return poly_voronoi._lloyd_3d_iteration(
        _seeds(),
        _SURFACE_VERTICES,
        _SURFACE_FACES,
        n_lloyd=2,
        pinned_mask=pin_mask,
    )


def test_compaction_keeps_pins_row_aligned_three_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    pins = np.array([False, True, False, True, False, True, False, True])
    first_keep = np.array([False, True, True, False, True, True, True, True])

    outputs: list[np.ndarray] = []
    for _ in range(3):
        with monkeypatch.context() as context:
            output = _run(
                context,
                pin_mask=pins,
                mask_factory=lambda call, size: (
                    first_keep.copy() if call == 0 else np.ones(size, dtype=bool)
                ),
            )
        outputs.append(output)

    expected = _seeds()[first_keep].copy()
    surviving_pins = pins[first_keep]
    expected[~surviving_pins] += 2.0 * _DELTA

    assert outputs[0].shape == (6, 3)
    assert np.array_equal(outputs[0], expected)
    assert np.array_equal(outputs[1], outputs[0])
    assert np.array_equal(outputs[2], outputs[0])
    assert np.array_equal(outputs[0][surviving_pins], _seeds()[first_keep][surviving_pins])
    assert not any(np.array_equal(row, _seeds()[0]) for row in outputs[0])
    assert not any(np.array_equal(row, _seeds()[3]) for row in outputs[0])


def test_no_filter_path_retains_exact_legacy_result(monkeypatch: pytest.MonkeyPatch) -> None:
    pins = np.array([False, True, False, True, False, True, False, True])
    output = _run(
        monkeypatch,
        pin_mask=pins,
        mask_factory=lambda _call, size: np.ones(size, dtype=bool),
    )
    expected = _seeds().copy()
    expected[~pins] += 2.0 * _DELTA

    assert np.array_equal(output, expected)
    assert np.array_equal(output[pins], _seeds()[pins])


def test_malformed_pin_mask_keeps_unpinned_semantics(monkeypatch: pytest.MonkeyPatch) -> None:
    malformed = np.ones(_seeds().shape[0] - 1, dtype=bool)
    with monkeypatch.context() as malformed_context:
        malformed_output = _run(
            malformed_context,
            pin_mask=malformed,
            mask_factory=lambda _call, size: np.ones(size, dtype=bool),
        )
    with monkeypatch.context() as none_context:
        none_output = _run(
            none_context,
            pin_mask=None,
            mask_factory=lambda _call, size: np.ones(size, dtype=bool),
        )

    assert np.array_equal(malformed_output, none_output)
    assert np.array_equal(malformed_output, _seeds() + 2.0 * _DELTA)
