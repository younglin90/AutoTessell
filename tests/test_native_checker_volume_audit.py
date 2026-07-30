"""Signed raw-winding audit and checker observability regressions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from core.evaluator import native_checker as checker_module
from core.evaluator.native_checker import NativeMeshChecker
from core.generator.polymesh_writer import _TET_FACES, write_generic_polymesh
from core.utils.native_extensions import load_native_metrics


def _cube_face_geometry() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    centres = np.asarray(
        (
            (0.0, 0.5, 0.5),
            (1.0, 0.5, 0.5),
            (0.5, 0.0, 0.5),
            (0.5, 1.0, 0.5),
            (0.5, 0.5, 0.0),
            (0.5, 0.5, 1.0),
        ),
        dtype=np.float64,
    )
    normals = np.asarray(
        (
            (-1.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, -1.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, -1.0),
            (0.0, 0.0, 1.0),
        ),
        dtype=np.float64,
    )
    return centres, normals, np.ones(6, dtype=np.float64)


def test_native_oriented_volume_audit_reports_cube_winding() -> None:
    module = load_native_metrics()
    if module is None or not hasattr(module, "compute_oriented_cell_volume_audit"):
        pytest.skip("native oriented volume audit is not built")
    centres, normals, areas = _cube_face_geometry()
    cell_centres = np.asarray(((0.5, 0.5, 0.5),), dtype=np.float64)
    owner = np.zeros(6, dtype=np.int64)
    neighbour = np.empty((0,), dtype=np.int64)

    signed, absolute = module.compute_oriented_cell_volume_audit(
        centres, normals, areas, cell_centres, owner, neighbour, 1, 0
    )
    np.testing.assert_allclose(np.asarray(signed), np.asarray((1.0,)))
    np.testing.assert_allclose(np.asarray(absolute), np.asarray((1.0,)))
    reversed_signed, reversed_absolute = module.compute_oriented_cell_volume_audit(
        centres, -normals, areas, cell_centres, owner, neighbour, 1, 0
    )
    np.testing.assert_allclose(np.asarray(reversed_signed), np.asarray((-1.0,)))
    np.testing.assert_allclose(np.asarray(reversed_absolute), np.asarray((1.0,)))


def test_native_oriented_volume_audit_uses_neighbour_opposite_sign() -> None:
    module = load_native_metrics()
    if module is None or not hasattr(module, "compute_oriented_cell_volume_audit"):
        pytest.skip("native oriented volume audit is not built")
    signed, absolute = module.compute_oriented_cell_volume_audit(
        np.asarray(((0.0, 0.0, 0.0),)),
        np.asarray(((1.0, 0.0, 0.0),)),
        np.asarray((1.0,)),
        np.asarray(((-0.5, 0.0, 0.0), (0.5, 0.0, 0.0))),
        np.asarray((0,), dtype=np.int64),
        np.asarray((1,), dtype=np.int64),
        2,
        1,
    )
    expected = np.asarray((1.0 / 6.0, 1.0 / 6.0))
    np.testing.assert_allclose(np.asarray(signed), expected)
    np.testing.assert_allclose(np.asarray(absolute), expected)

    with pytest.raises(ValueError, match="owner cell id"):
        module.compute_oriented_cell_volume_audit(
            np.asarray(((0.0, 0.0, 0.0),)),
            np.asarray(((1.0, 0.0, 0.0),)),
            np.asarray((1.0,)),
            np.asarray(((0.0, 0.0, 0.0),)),
            np.asarray((2,), dtype=np.int64),
            np.empty((0,), dtype=np.int64),
            1,
            0,
        )


def test_oriented_volume_native_matches_python_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_native_metrics()
    if module is None or not hasattr(module, "compute_oriented_cell_volume_audit"):
        pytest.skip("native oriented volume audit is not built")
    centres, normals, areas = _cube_face_geometry()
    cell_centres = np.asarray(((0.5, 0.5, 0.5),), dtype=np.float64)
    owner = np.zeros(6, dtype=np.int64)
    neighbour = np.empty((0,), dtype=np.int64)
    native = tuple(
        np.asarray(values)
        for values in module.compute_oriented_cell_volume_audit(
            centres, normals, areas, cell_centres, owner, neighbour, 1, 0
        )
    )

    monkeypatch.setattr(checker_module, "_load_native_metrics", lambda: None)
    fallback = NativeMeshChecker._compute_oriented_cell_volume_audit(
        centres, normals, areas, cell_centres, owner, neighbour, 1, 0
    )
    np.testing.assert_array_equal(native[0], fallback[0])
    np.testing.assert_array_equal(native[1], fallback[1])


def _write_three_disconnected_tets(case_dir: Path, *, reverse_last: bool) -> None:
    base = np.asarray(
        ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0),
         (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
        dtype=np.float64,
    )
    points = np.vstack(
        (base, base + np.asarray((3.0, 0.0, 0.0)),
         base + np.asarray((6.0, 0.0, 0.0)))
    )
    cells: list[list[list[int]]] = []
    for cell in range(3):
        offset = cell * 4
        faces = [[offset + local for local in face] for face in _TET_FACES]
        if reverse_last and cell == 2:
            faces = [list(reversed(face)) for face in faces]
        cells.append(faces)
    write_generic_polymesh(points, cells, case_dir)


@pytest.mark.parametrize(
    ("reverse_last", "expected_negative"), ((False, 0), (True, 1))
)
def test_checker_done_log_matches_effective_negative_count(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    reverse_last: bool,
    expected_negative: int,
) -> None:
    _write_three_disconnected_tets(tmp_path, reverse_last=reverse_last)
    done_events: list[dict[str, Any]] = []
    original_info = checker_module.log.info

    def _capture_info(event: str, *args: Any, **values: Any) -> Any:
        if event == "NativeMeshChecker done":
            done_events.append(values.copy())
        return original_info(event, *args, **values)

    monkeypatch.setattr(checker_module.log, "info", _capture_info)
    result = NativeMeshChecker().run(tmp_path)

    assert result.negative_volumes == expected_negative
    assert result.mesh_ok is (expected_negative == 0)
    assert len(done_events) == 1
    event = done_events[0]
    assert event["negative_volumes"] == result.negative_volumes
    assert event["raw_pyramid_negative_volumes"] == 0
    assert event["inverted_owner_cells"] == expected_negative
    assert event["oriented_negative_cells"] == expected_negative
