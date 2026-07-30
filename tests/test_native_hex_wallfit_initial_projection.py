"""Exact optional-native contract for wall-fit's initial projection batch."""

from __future__ import annotations

from hashlib import sha256
from typing import Any, cast

import numpy as np
import pytest

from core.generator.native_hex import snap
from core.generator.native_hex.mesher import _wall_fit_snap

_CELL_FACES = [
    [
        [0, 3, 2, 1],
        [4, 5, 6, 7],
        [0, 4, 7, 3],
        [1, 2, 6, 5],
        [0, 1, 5, 4],
        [3, 7, 6, 2],
    ]
]


def _fixture() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    points = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [1.0, 1.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [1.0, 0.0, 1.0],
            [1.0, 1.0, 1.0],
            [0.0, 1.0, 1.0],
        ],
        dtype=np.float64,
    )
    lo, hi = -0.05, 1.05
    surface_points = np.asarray(
        [
            [lo, lo, lo],
            [hi, lo, lo],
            [hi, hi, lo],
            [lo, hi, lo],
            [lo, lo, hi],
            [hi, lo, hi],
            [hi, hi, hi],
            [lo, hi, hi],
        ],
        dtype=np.float64,
    )
    surface_faces = np.asarray(
        [
            [0, 2, 1],
            [0, 3, 2],
            [4, 5, 6],
            [4, 6, 7],
            [0, 1, 5],
            [0, 5, 4],
            [3, 7, 6],
            [3, 6, 2],
            [0, 4, 7],
            [0, 7, 3],
            [1, 2, 6],
            [1, 6, 5],
        ],
        dtype=np.int64,
    )
    return points, surface_points, surface_faces


def _run(points: np.ndarray | None = None) -> tuple[np.ndarray, dict[str, object]]:
    fixture_points, surface_points, surface_faces = _fixture()
    if points is None:
        points = fixture_points
    return cast(
        tuple[np.ndarray, dict[str, object]],
        _wall_fit_snap(
            points,
            _CELL_FACES,
            surface_points,
            surface_faces,
            target_edge=1.0,
            tol=1.0e-12,
            ratio=0.2,
            iters=1,
        ),
    )


class _ExactNative:
    calls = 0

    @classmethod
    def closest_triangle_candidates(
        cls,
        points: np.ndarray,
        triangle_a: np.ndarray,
        triangle_b: np.ndarray,
        triangle_c: np.ndarray,
        candidates: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        cls.calls += 1
        best_points = np.empty_like(points)
        squared_distances = np.empty(points.shape[0], dtype=np.float64)
        valid = np.zeros(points.shape[0], dtype=np.bool_)
        for point_index, point in enumerate(points):
            best_point = point
            best_distance = float("inf")
            for triangle_index in candidates[point_index].tolist():
                if triangle_index >= triangle_a.shape[0]:
                    continue
                candidate_point = snap._closest_point_on_triangle(
                    point,
                    triangle_a[triangle_index],
                    triangle_b[triangle_index],
                    triangle_c[triangle_index],
                )
                squared_distance = float(((candidate_point - point) ** 2).sum())
                if squared_distance < best_distance:
                    best_distance = squared_distance
                    best_point = candidate_point
                    valid[point_index] = True
            best_points[point_index] = best_point
            squared_distances[point_index] = best_distance
        return best_points, squared_distances, valid


def test_initial_projection_native_batch_is_exact_and_single_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    points, _, _ = _fixture()
    input_digest = sha256(points.tobytes()).hexdigest()
    monkeypatch.setattr(snap, "_NATIVE_SNAP", None)
    monkeypatch.setattr(snap, "_NATIVE_SNAP_IMPORT_ATTEMPTED", True)
    python_points, python_stats = _run(points)

    _ExactNative.calls = 0
    monkeypatch.setattr(snap, "_NATIVE_SNAP", _ExactNative)
    native_points, native_stats = _run(points)

    assert _ExactNative.calls == 1
    assert np.array_equal(native_points, python_points)
    assert native_stats == python_stats
    assert sha256(points.tobytes()).hexdigest() == input_digest


@pytest.mark.parametrize(  # type: ignore[untyped-decorator]
    "malformed",
    [
        object(),
        type(
            "WrongTuple",
            (),
            {"closest_triangle_candidates": staticmethod(lambda *_args: (None, None))},
        )(),
        type(
            "WrongDtype",
            (),
            {
                "closest_triangle_candidates": staticmethod(
                    lambda points, *_args: (
                        np.zeros((len(points), 3), dtype=np.float32),
                        np.zeros(len(points), dtype=np.float64),
                        np.ones(len(points), dtype=np.bool_),
                    )
                )
            },
        )(),
    ],
)
def test_loaded_malformed_native_abi_fails_closed_without_input_mutation(
    monkeypatch: pytest.MonkeyPatch, malformed: Any
) -> None:
    points, _, _ = _fixture()
    before = points.copy()
    monkeypatch.setattr(snap, "_NATIVE_SNAP", malformed)
    monkeypatch.setattr(snap, "_NATIVE_SNAP_IMPORT_ATTEMPTED", True)

    with pytest.raises(RuntimeError, match="native_snap"):
        _run(points)

    assert np.array_equal(points, before)


def test_loaded_native_kernel_error_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingNative:
        @staticmethod
        def closest_triangle_candidates(*_args: Any) -> None:
            raise ValueError("broken native ABI")

    monkeypatch.setattr(snap, "_NATIVE_SNAP", FailingNative())
    monkeypatch.setattr(snap, "_NATIVE_SNAP_IMPORT_ATTEMPTED", True)

    with pytest.raises(ValueError, match="broken native ABI"):
        _run()
