"""Parity checks for the optional native polyMesh topology kernel."""

from __future__ import annotations

import hashlib
import types
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from core.generator import polymesh_writer as writer
from core.utils.polymesh_reader import parse_foam_labels


def _native_or_skip() -> Any:
    module = writer._load_native_polymesh()
    if module is None or not hasattr(module, "build_topology"):
        pytest.skip("native_polymesh extension is not built")
    return module


def test_native_face_geometry_matches_python_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core.generator.native_poly import dual
    from core.utils import native_extensions

    native = _native_or_skip()
    if not hasattr(native, "face_flip_mask") or not hasattr(
        native, "face_plane_geometry"
    ):
        pytest.skip("native face-geometry batch kernel is not built")

    points = np.asarray(
        (
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (1.0, 1.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
            (1.0, 0.0, 1.0),
            (0.0, 1.0, 1.0),
        ),
        dtype=np.float64,
    )
    faces = [[0, 1, 2, 3], [4, 5, 6]]
    owners = np.asarray((0, 1), dtype=np.int64)
    centroids = np.asarray(((0.5, 0.5, -1.0), (0.25, 0.25, 2.0)))
    normals = np.asarray(((0.0, 0.0, 1.0),), dtype=np.float64)
    offsets = np.asarray((0.0,), dtype=np.float64)

    flip_mask = np.asarray(
        native.face_flip_mask(points, faces, owners, centroids), dtype=bool
    )
    assert flip_mask.tolist() == [False, True]

    native_on, native_off, on_plane = native.face_plane_geometry(
        points, faces, normals, offsets, 1e-6
    )
    assert np.asarray(on_plane, dtype=bool).tolist() == [True, False]

    monkeypatch.setattr(native_extensions, "load_native_polymesh", lambda: None)
    python_on, python_off = dual._area_split(
        points, faces, [(normals[0], float(offsets[0]))]
    )
    assert float(native_on) == pytest.approx(python_on, abs=1e-15)
    assert float(native_off) == pytest.approx(python_off, abs=1e-15)


def test_native_face_geometry_rejects_invalid_connectivity() -> None:
    native = _native_or_skip()
    if not hasattr(native, "face_flip_mask"):
        pytest.skip("native face-geometry batch kernel is not built")

    points = np.eye(3, dtype=np.float64)
    centroids = np.zeros((1, 3), dtype=np.float64)
    with pytest.raises(IndexError, match="face vertex index is out of bounds"):
        native.face_flip_mask(points, [[0, 1, 3]], np.asarray([0]), centroids)


def test_native_face_geometry_preserves_dual_output_bytes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from core.generator.native_poly.dual import tet_to_poly_dual
    from core.utils import native_extensions

    native = _native_or_skip()
    if not hasattr(native, "face_flip_mask"):
        pytest.skip("native face-geometry batch kernel is not built")
    incidence_only = types.SimpleNamespace(
        build_tet_incidence_maps=native.build_tet_incidence_maps
    )
    vertices = np.asarray(
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

    monkeypatch.setattr(native_extensions, "load_native_polymesh", lambda: native)
    native_case = tmp_path / "native_face_geometry"
    native_result = tet_to_poly_dual(vertices, tets, native_case)

    monkeypatch.setattr(
        native_extensions, "load_native_polymesh", lambda: incidence_only
    )
    python_case = tmp_path / "python_face_geometry"
    python_result = tet_to_poly_dual(vertices, tets, python_case)

    assert native_result.success and python_result.success
    assert (
        native_result.n_cells,
        native_result.n_points,
        native_result.invalid_star_cells,
        native_result.invalid_star_subtets,
    ) == (
        python_result.n_cells,
        python_result.n_points,
        python_result.invalid_star_cells,
        python_result.invalid_star_subtets,
    )
    assert _case_snapshot(native_case) == _case_snapshot(python_case)


def _case_snapshot(case_dir: Path) -> dict[str, tuple[str, bytes]]:
    snapshot: dict[str, tuple[str, bytes]] = {}
    for path in sorted(item for item in case_dir.rglob("*") if item.is_file()):
        payload = path.read_bytes()
        snapshot[str(path.relative_to(case_dir))] = (
            hashlib.sha256(payload).hexdigest(),
            payload,
        )
    return snapshot


def _assert_native_python_parity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    vertices: np.ndarray,
    cell_faces: list[list[list[int]]],
) -> dict[str, int]:
    native_module = _native_or_skip()
    native_dir = tmp_path / "native"
    python_dir = tmp_path / "python"

    monkeypatch.setattr(writer, "_NATIVE_POLYMESH", native_module)
    monkeypatch.setattr(writer, "_NATIVE_POLYMESH_IMPORT_ATTEMPTED", True)
    native_stats = writer.write_generic_polymesh(vertices, cell_faces, native_dir)

    monkeypatch.setattr(writer, "_NATIVE_POLYMESH", None)
    monkeypatch.setattr(writer, "_NATIVE_POLYMESH_IMPORT_ATTEMPTED", True)
    python_stats = writer.write_generic_polymesh(vertices, cell_faces, python_dir)

    assert native_stats == python_stats
    assert _case_snapshot(native_dir) == _case_snapshot(python_dir)
    return native_stats


def _two_shared_cubes() -> tuple[np.ndarray, list[list[list[int]]]]:
    vertices = np.array(
        [
            [0, 0, 0],
            [1, 0, 0],
            [1, 1, 0],
            [0, 1, 0],
            [0, 0, 1],
            [1, 0, 1],
            [1, 1, 1],
            [0, 1, 1],
            [2, 0, 0],
            [2, 1, 0],
            [2, 0, 1],
            [2, 1, 1],
        ],
        dtype=np.float64,
    )
    left = [
        [0, 3, 2, 1],
        [4, 5, 6, 7],
        [0, 4, 7, 3],
        [1, 2, 6, 5],
        [0, 1, 5, 4],
        [3, 7, 6, 2],
    ]
    right = [
        [1, 2, 9, 8],
        [5, 10, 11, 6],
        [1, 5, 6, 2],
        [8, 9, 11, 10],
        [1, 8, 10, 5],
        [2, 6, 11, 9],
    ]
    return vertices, [left, right]


def test_native_two_shared_cubes_matches_python(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    vertices, cell_faces = _two_shared_cubes()

    stats = _assert_native_python_parity(
        monkeypatch,
        tmp_path,
        vertices,
        cell_faces,
    )

    assert stats == {
        "num_cells": 2,
        "num_points": 12,
        "num_faces": 11,
        "num_internal_faces": 1,
    }


def test_native_boundary_only_cube_matches_python(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    vertices, cell_faces = _two_shared_cubes()

    stats = _assert_native_python_parity(
        monkeypatch,
        tmp_path,
        vertices[:8],
        cell_faces[:1],
    )

    assert stats["num_cells"] == 1
    assert stats["num_faces"] == 6
    assert stats["num_internal_faces"] == 0


def test_native_repeated_and_degenerate_faces_match_python(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    native = _native_or_skip()
    vertices = np.array(
        [
            [0, 0, 0],
            [1, 0, 0],
            [2, 0, 0],
            [0, 1, 0],
            [0, 0, 1],
        ],
        dtype=np.float64,
    )
    degenerate = [
        [0, 1, 2],
        [0, 1, 4],
        [1, 2, 4],
        [2, 0, 4],
    ]
    repeated = [
        [0, 3, 3, 1, 0],
        [0, 1, 1, 4, 0],
        [0, 4, 4, 3, 0],
        [1, 3, 3, 4, 1],
    ]

    stats = _assert_native_python_parity(
        monkeypatch,
        tmp_path,
        vertices,
        [degenerate, repeated],
    )

    assert stats["num_cells"] == 1
    owners = parse_foam_labels(tmp_path / "native" / "constant/polyMesh/owner")
    assert owners == [0, 0, 0, 0]

    result = native.build_topology(vertices, [degenerate, repeated], 1e-30)
    assert result[5:8] == (1, 1, 1)
    assert result[1].dtype == np.dtype(np.int64)
    assert result[2].dtype == np.dtype(np.int64)
    assert result[4].dtype == np.dtype(np.int64)


def test_native_strict_rejection_matches_python_before_write(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    native = _native_or_skip()
    vertices = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [0.5, 0.0, 0.0],
        ],
        dtype=np.float64,
    )
    good = [[0, 2, 1], [0, 1, 3], [1, 2, 3], [2, 0, 3]]
    bad = [[0, 1, 2], [0, 4, 1], [1, 4, 2], [2, 4, 0]]
    messages: list[str] = []

    for module, case_name in ((native, "native"), (None, "python")):
        monkeypatch.setattr(writer, "_NATIVE_POLYMESH", module)
        monkeypatch.setattr(writer, "_NATIVE_POLYMESH_IMPORT_ATTEMPTED", True)
        case_dir = tmp_path / case_name
        with pytest.raises(ValueError, match="strict polyMesh contract") as exc_info:
            writer.write_generic_polymesh(
                vertices,
                [good, bad],
                case_dir,
                strict=True,
            )
        messages.append(str(exc_info.value))
        assert not case_dir.exists()

    assert messages[0] == messages[1]


def test_native_non_manifold_first_two_matches_python(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    native = _native_or_skip()
    vertices = np.array(
        [
            [0, 0, 0],
            [1, 0, 0],
            [0, 1, 0],
            [0, 0, 1],
            [0, 0, -1],
            [0.2, 0.2, 2],
        ],
        dtype=np.float64,
    )
    cells = [
        [[0, 2, 1], [0, 1, 3], [1, 2, 3], [2, 0, 3]],
        [[0, 1, 2], [0, 4, 1], [1, 4, 2], [2, 4, 0]],
        [[2, 0, 1], [0, 5, 1], [1, 5, 2], [2, 5, 0]],
    ]

    stats = _assert_native_python_parity(monkeypatch, tmp_path, vertices, cells)

    assert stats["num_cells"] == 3
    assert stats["num_faces"] == 10
    assert stats["num_internal_faces"] == 1
    result = native.build_topology(vertices, cells, 1e-30)
    assert result[1].tolist() == [0]
    assert result[2].tolist() == [1]
    assert result[8] == [(3, 3)]

    strict_messages: list[str] = []
    for module, case_name in ((native, "strict_native"), (None, "strict_python")):
        monkeypatch.setattr(writer, "_NATIVE_POLYMESH", module)
        monkeypatch.setattr(writer, "_NATIVE_POLYMESH_IMPORT_ATTEMPTED", True)
        case_dir = tmp_path / case_name
        with pytest.raises(ValueError, match="non-manifold face references") as exc_info:
            writer.write_generic_polymesh(
                vertices,
                cells,
                case_dir,
                strict=True,
            )
        strict_messages.append(str(exc_info.value))
        assert not case_dir.exists()
    assert strict_messages[0] == strict_messages[1]


def test_native_nan_face_area_matches_python(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    vertices = np.array(
        [
            [0, 0, 0],
            [1, 0, 0],
            [0, 1, 0],
            [0, 0, np.nan],
        ],
        dtype=np.float64,
    )
    cell_faces = [
        [[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]],
    ]

    stats = _assert_native_python_parity(monkeypatch, tmp_path, vertices, cell_faces)

    assert stats["num_cells"] == 1
    assert stats["num_faces"] == 4


def test_native_call_failure_uses_python_fallback_exactly(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    vertices, cell_faces = _two_shared_cubes()
    expected_dir = tmp_path / "expected"
    failed_dir = tmp_path / "failed"

    monkeypatch.setattr(writer, "_NATIVE_POLYMESH", None)
    monkeypatch.setattr(writer, "_NATIVE_POLYMESH_IMPORT_ATTEMPTED", True)
    expected_stats = writer.write_generic_polymesh(
        vertices,
        cell_faces,
        expected_dir,
    )

    class FailingNative:
        @staticmethod
        def build_topology(*_args: Any) -> None:
            raise RuntimeError("forced native polymesh failure")

    monkeypatch.setattr(writer, "_NATIVE_POLYMESH", FailingNative())
    failed_stats = writer.write_generic_polymesh(vertices, cell_faces, failed_dir)

    assert failed_stats == expected_stats
    assert _case_snapshot(failed_dir) == _case_snapshot(expected_dir)


def test_native_tet_incidence_maps_match_python_order_exactly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    native = _native_or_skip()
    assert hasattr(native, "build_tet_incidence_maps")
    from core.generator.native_poly import dual
    from core.utils import native_extensions

    tets = np.array(
        [
            [4, 2, 1, 0],
            [4, 1, 2, 3],
            [4, 5, 2, 0],
            [4, 3, 2, 6],
        ],
        dtype=np.int64,
    )
    native_maps = native.build_tet_incidence_maps(tets, 7)
    monkeypatch.setattr(native_extensions, "load_native_polymesh", lambda: None)
    python_maps = dual._build_tet_topology(tets, 7)

    for native_map, python_map in zip(native_maps, python_maps, strict=True):
        assert list(native_map.items()) == list(python_map.items())


def test_native_tet_incidence_maps_reject_invalid_input() -> None:
    native = _native_or_skip()
    with pytest.raises(ValueError, match="shape"):
        native.build_tet_incidence_maps(np.array([0, 1, 2, 3]), 4)
    with pytest.raises(ValueError, match="index out of range"):
        native.build_tet_incidence_maps(
            np.array([[0, 1, 2, 4]], dtype=np.int64),
            4,
        )
