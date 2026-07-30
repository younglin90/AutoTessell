"""Exact optional-native contract for wall-fit boundary local scales."""

from __future__ import annotations

from hashlib import sha256
from typing import Any, cast

import numpy as np
import pytest

from core.generator.native_hex import quality
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
    low, high = -0.05, 1.05
    surface_points = np.asarray(
        [
            [low, low, low],
            [high, low, low],
            [high, high, low],
            [low, high, low],
            [low, low, high],
            [high, low, high],
            [high, high, high],
            [low, high, high],
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
    return cast(
        tuple[np.ndarray, dict[str, object]],
        _wall_fit_snap(
            fixture_points if points is None else points,
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
    def boundary_vertex_local_scales(
        cls,
        points: np.ndarray,
        cell_faces: list[list[list[int]]],
        boundary: np.ndarray,
    ) -> np.ndarray:
        cls.calls += 1
        result = np.zeros(boundary.shape[0], dtype=np.float64)
        for output_index, vertex in enumerate(boundary.tolist()):
            for cell in cell_faces:
                if vertex not in {value for face in cell for value in face}:
                    continue
                for face in cell:
                    for edge in range(len(face)):
                        result[output_index] = max(
                            result[output_index],
                            float(
                                np.linalg.norm(
                                    points[face[edge]]
                                    - points[face[(edge + 1) % len(face)]]
                                )
                            ),
                        )
        return cast(np.ndarray, result)


def test_native_local_scale_is_exact_and_single_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    points, _, _ = _fixture()
    before = sha256(points.tobytes()).hexdigest()
    monkeypatch.setattr(quality, "_NATIVE_HEX_QUALITY", None)
    monkeypatch.setattr(quality, "_NATIVE_HEX_QUALITY_IMPORT_ATTEMPTED", True)
    python_points, python_stats = _run(points)

    _ExactNative.calls = 0
    monkeypatch.setattr(quality, "_NATIVE_HEX_QUALITY", _ExactNative)
    native_points, native_stats = _run(points)

    assert _ExactNative.calls == 1
    assert np.array_equal(native_points, python_points)
    assert native_stats == python_stats
    assert sha256(points.tobytes()).hexdigest() == before


@pytest.mark.parametrize(  # type: ignore[untyped-decorator]
    "malformed",
    [
        object(),
        type(
            "WrongShape",
            (),
            {
                "boundary_vertex_local_scales": staticmethod(
                    lambda *_args: np.zeros((1, 1), dtype=np.float64)
                )
            },
        )(),
        type(
            "WrongDtype",
            (),
            {
                "boundary_vertex_local_scales": staticmethod(
                    lambda _points, _cells, boundary: np.zeros(
                        len(boundary), dtype=np.float32
                    )
                )
            },
        )(),
    ],
)
def test_loaded_malformed_local_scale_abi_fails_closed(
    monkeypatch: pytest.MonkeyPatch, malformed: Any
) -> None:
    monkeypatch.setattr(quality, "_NATIVE_HEX_QUALITY", malformed)
    monkeypatch.setattr(quality, "_NATIVE_HEX_QUALITY_IMPORT_ATTEMPTED", True)

    with pytest.raises(RuntimeError, match="native_hex_quality"):
        _run()


def test_loaded_local_scale_kernel_error_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingNative:
        @staticmethod
        def boundary_vertex_local_scales(*_args: Any) -> None:
            raise ValueError("broken local-scale ABI")

    monkeypatch.setattr(quality, "_NATIVE_HEX_QUALITY", FailingNative())
    monkeypatch.setattr(quality, "_NATIVE_HEX_QUALITY_IMPORT_ATTEMPTED", True)

    with pytest.raises(ValueError, match="broken local-scale ABI"):
        _run()
