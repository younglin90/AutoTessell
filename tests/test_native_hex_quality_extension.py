"""Parity tests for native hexahedral quality primitives."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import astuple
from typing import Any

import numpy as np
import pytest

from core.generator.native_hex import quality


def _native_or_skip() -> Any:
    module = quality._load_native_hex_quality()
    if module is None or not hasattr(module, "hex_quality_primitives"):
        pytest.skip("native_hex_quality extension is not built")
    return module


def _structured_hexes(nx: int, ny: int, nz: int) -> tuple[np.ndarray, np.ndarray]:
    x, y, z = np.meshgrid(
        np.arange(nx + 1, dtype=np.float64),
        np.arange(ny + 1, dtype=np.float64),
        np.arange(nz + 1, dtype=np.float64),
        indexing="ij",
    )
    points = np.stack((x, y, z), axis=-1).reshape(-1, 3)
    ids = np.arange(points.shape[0], dtype=np.int64).reshape(nx + 1, ny + 1, nz + 1)
    cells: list[list[int]] = []
    for i in range(nx):
        for j in range(ny):
            for k in range(nz):
                cells.append(
                    [
                        ids[i, j, k],
                        ids[i + 1, j, k],
                        ids[i + 1, j + 1, k],
                        ids[i, j + 1, k],
                        ids[i, j, k + 1],
                        ids[i + 1, j, k + 1],
                        ids[i + 1, j + 1, k + 1],
                        ids[i, j + 1, k + 1],
                    ]
                )
    return points, np.asarray(cells, dtype=np.int64)


def _reports(
    monkeypatch: pytest.MonkeyPatch,
    points: np.ndarray,
    cells: np.ndarray,
) -> tuple[quality.HexQualityReport, quality.HexQualityReport]:
    native = _native_or_skip()
    monkeypatch.setattr(quality, "_NATIVE_HEX_QUALITY", native)
    monkeypatch.setattr(quality, "_NATIVE_HEX_QUALITY_IMPORT_ATTEMPTED", True)
    native_report = quality.hex_quality_report(points, cells)

    monkeypatch.setattr(quality, "_NATIVE_HEX_QUALITY", None)
    python_report = quality.hex_quality_report(points, cells)
    return native_report, python_report


def _assert_reports_equal(
    native_report: quality.HexQualityReport,
    python_report: quality.HexQualityReport,
) -> None:
    assert native_report.n_cells == python_report.n_cells
    assert native_report.n_faces == python_report.n_faces
    np.testing.assert_allclose(
        astuple(native_report)[2:],
        astuple(python_report)[2:],
        rtol=2e-13,
        atol=2e-13,
        equal_nan=True,
    )


@pytest.mark.parametrize("shape", [(1, 1, 1), (2, 1, 1), (4, 3, 2)])
def test_native_quality_matches_structured_grids(
    monkeypatch: pytest.MonkeyPatch,
    shape: tuple[int, int, int],
) -> None:
    points, cells = _structured_hexes(*shape)
    if len(cells) > 2:
        rng = np.random.default_rng(42)
        points = points + rng.normal(scale=0.025, size=points.shape)

    native_report, python_report = _reports(monkeypatch, points, cells)

    _assert_reports_equal(native_report, python_report)


def test_native_quality_duplicate_non_manifold_cells_match_python(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    points, cells = _structured_hexes(1, 1, 1)
    duplicate_cells = np.repeat(cells, 3, axis=0)

    native_report, python_report = _reports(monkeypatch, points, duplicate_cells)

    _assert_reports_equal(native_report, python_report)
    assert native_report.n_faces == 6
    assert native_report.min_face_area == 0.0


def test_native_quality_negative_indices_and_nan_match_python(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    points, cells = _structured_hexes(2, 1, 1)
    cells = cells.copy()
    cells[cells == points.shape[0] - 1] = -1
    points = points.copy()
    points[0, 2] = np.nan

    native_report, python_report = _reports(monkeypatch, points, cells)

    _assert_reports_equal(native_report, python_report)


def test_native_quality_failure_uses_python_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    points, cells = _structured_hexes(2, 2, 2)

    class FailingNative:
        @staticmethod
        def hex_quality_primitives(*_args: Any) -> None:
            raise RuntimeError("forced native hex quality failure")

    monkeypatch.setattr(quality, "_NATIVE_HEX_QUALITY", FailingNative())
    monkeypatch.setattr(quality, "_NATIVE_HEX_QUALITY_IMPORT_ATTEMPTED", True)
    failed_report = quality.hex_quality_report(points, cells)

    monkeypatch.setattr(quality, "_NATIVE_HEX_QUALITY", None)
    python_report = quality.hex_quality_report(points, cells)

    _assert_reports_equal(failed_report, python_report)


def test_native_generic_signed_volumes_match_python() -> None:
    native = _native_or_skip()
    assert hasattr(native, "generic_cell_signed_volumes")
    points, cells = _structured_hexes(4, 3, 2)
    rng = np.random.default_rng(13)
    points = points + rng.normal(scale=0.015, size=points.shape)
    cell_faces = [
        [[int(cell[local]) for local in face] for face in quality._HEX_FACES] for cell in cells
    ]

    native_volumes = native.generic_cell_signed_volumes(points, cell_faces)
    python_volumes: list[float] = []
    for cell in cell_faces:
        vertices = sorted({vertex for face in cell for vertex in face})
        centroid = points[np.asarray(vertices, dtype=np.int64)].mean(axis=0)
        volume = 0.0
        for face in cell:
            face_points = points[np.asarray(face, dtype=np.int64)]
            for slot in range(1, len(face) - 1):
                volume += (
                    float(
                        np.dot(
                            face_points[0] - centroid,
                            np.cross(
                                face_points[slot] - centroid,
                                face_points[slot + 1] - centroid,
                            ),
                        )
                    )
                    / 6.0
                )
        python_volumes.append(volume)

    np.testing.assert_allclose(
        native_volumes,
        python_volumes,
        rtol=2e-13,
        atol=2e-13,
    )


def test_native_boundary_vertex_local_scales_are_bitwise_exact() -> None:
    native = _native_or_skip()
    assert hasattr(native, "boundary_vertex_local_scales")
    points, cells = _structured_hexes(4, 3, 2)
    rng = np.random.default_rng(31)
    points = points + rng.normal(scale=0.015, size=points.shape)
    cell_faces = [
        [[int(cell[local]) for local in face] for face in quality._HEX_FACES]
        for cell in cells
    ]
    face_cells: dict[tuple[int, ...], list[int]] = defaultdict(list)
    for cell_index, cell in enumerate(cell_faces):
        for face in cell:
            face_cells[tuple(sorted(face))].append(cell_index)
    boundary_vertices = {
        vertex
        for face, owners in face_cells.items()
        if len(owners) == 1
        for vertex in face
    }
    incident = {vertex: set() for vertex in boundary_vertices}
    for cell_index, cell in enumerate(cell_faces):
        for vertex in {value for face in cell for value in face} & boundary_vertices:
            incident[vertex].add(cell_index)
    boundary = np.asarray(sorted(boundary_vertices), dtype=np.int64)
    expected = np.zeros(boundary.shape[0], dtype=np.float64)
    for output_index, vertex in enumerate(boundary.tolist()):
        for cell_index in incident[vertex]:
            for face in cell_faces[cell_index]:
                for edge in range(len(face)):
                    expected[output_index] = max(
                        expected[output_index],
                        float(
                            np.linalg.norm(
                                points[face[edge]] - points[face[(edge + 1) % len(face)]]
                            )
                        ),
                    )

    actual = native.boundary_vertex_local_scales(points, cell_faces, boundary)

    assert isinstance(actual, np.ndarray)
    assert actual.dtype == np.dtype(np.float64)
    assert actual.flags.c_contiguous
    assert np.array_equal(actual, expected)


def test_native_boundary_vertex_local_scales_reject_invalid_boundary() -> None:
    native = _native_or_skip()
    points, cells = _structured_hexes(1, 1, 1)
    cell_faces = [
        [[int(cells[0, local]) for local in face] for face in quality._HEX_FACES]
    ]

    with pytest.raises(ValueError, match="shape"):
        native.boundary_vertex_local_scales(
            points, cell_faces, np.asarray([[0]], dtype=np.int64)
        )
    with pytest.raises(ValueError, match="unique"):
        native.boundary_vertex_local_scales(
            points, cell_faces, np.asarray([0, 0], dtype=np.int64)
        )
    with pytest.raises(IndexError):
        native.boundary_vertex_local_scales(
            points, cell_faces, np.asarray([len(points)], dtype=np.int64)
        )


def test_native_oriented_box_certificate_assigns_every_role() -> None:
    native = _native_or_skip()
    assert hasattr(native, "certify_oriented_box")
    points, cells = _structured_hexes(1, 1, 1)
    faces = [[int(cells[0, local]) for local in face] for face in quality._HEX_FACES]
    random_matrix = np.array(
        [
            [-0.80193143, -1.324359, -0.24836162],
            [0.42044524, 1.13604653, 0.1097064],
            [-0.55264732, -0.78478036, 0.74874577],
        ],
        dtype=np.float64,
    )
    rotation, _ = np.linalg.qr(random_matrix)
    transformed = (points * np.array([2.0, 3.0, 4.0])) @ rotation.T

    report = native.certify_oriented_box(transformed, faces)

    np.testing.assert_allclose(
        np.sort(np.asarray(report["side_lengths"])),
        [2.0, 3.0, 4.0],
        rtol=2e-15,
        atol=2e-15,
    )
    assert sorted(report["vertex_roles"]) == list(range(8))
    assert sorted(tuple(role) for role in report["face_roles"]) == [
        (axis, side) for axis in range(3) for side in range(2)
    ]
    assert float(report["normalized_tolerance"]) == pytest.approx(
        8.0 * np.sqrt(np.finfo(np.float64).eps), rel=0.0, abs=0.0
    )


def test_native_oriented_box_certificate_has_frozen_serialization_envelope() -> None:
    native = _native_or_skip()
    points, cells = _structured_hexes(1, 1, 1)
    faces = [[int(cells[0, local]) for local in face] for face in quality._HEX_FACES]
    tolerance = 8.0 * np.sqrt(np.finfo(np.float64).eps)

    below = np.array([[1.0, 0.25 * tolerance, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    native.certify_oriented_box(points @ below.T, faces)

    above = np.array([[1.0, 2.0 * tolerance, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    with pytest.raises(ValueError, match="basis_edges_are_not_orthogonal"):
        native.certify_oriented_box(points @ above.T, faces)

    sheared = np.array([[1.0, 1.0e-3, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    with pytest.raises(ValueError, match="basis_edges_are_not_orthogonal"):
        native.certify_oriented_box(points @ sheared.T, faces)

    near_degenerate = points * np.array([1.0e-9, 1.0, 1.0])
    with pytest.raises(ValueError, match="box_side_length_not_positive"):
        native.certify_oriented_box(near_degenerate, faces)


def test_native_oriented_box_certificate_rejects_non_cube_face_edges() -> None:
    native = _native_or_skip()
    points, cells = _structured_hexes(1, 1, 1)
    faces = [[int(cells[0, local]) for local in face] for face in quality._HEX_FACES]
    malformed = [face.copy() for face in faces]
    malformed[0][1], malformed[0][2] = malformed[0][2], malformed[0][1]

    with pytest.raises(
        ValueError,
        match="requires_12_edges_with_incidence_2|edge_does_not_match_oriented_box_role",
    ):
        native.certify_oriented_box(points, malformed)


def test_native_generic_cell_face_signs_match_python() -> None:
    native = _native_or_skip()
    assert hasattr(native, "generic_cell_face_signs")
    points, cells = _structured_hexes(2, 1, 1)
    rng = np.random.default_rng(19)
    points = points + rng.normal(scale=0.02, size=points.shape)
    cell = [[int(cells[0, local]) for local in face] for face in quality._HEX_FACES]

    native_signs, native_magnitude = native.generic_cell_face_signs(points, cell)
    vertices = sorted({vertex for face in cell for vertex in face})
    centroid = points[np.asarray(vertices, dtype=np.int64)].mean(axis=0)
    python_signs: list[float] = []
    for face in cell:
        face_points = points[np.asarray(face, dtype=np.int64)] - centroid
        sign = 0.0
        for slot in range(1, len(face) - 1):
            sign += float(
                np.dot(
                    face_points[0],
                    np.cross(face_points[slot], face_points[slot + 1]),
                )
            )
        python_signs.append(sign)

    np.testing.assert_allclose(native_signs, python_signs, rtol=2e-13, atol=2e-13)
    assert native_magnitude == pytest.approx(
        sum(abs(value) for value in python_signs), rel=2e-13, abs=2e-13
    )


def test_native_generic_side_metrics_match_relax_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core.generator.native_hex.mesher import (  # noqa: PLC0415
        _relax_boundary_sliver_interior,
    )

    native = _native_or_skip()
    assert hasattr(native, "generic_side_metrics")
    points, cells = _structured_hexes(4, 3, 2)
    rng = np.random.default_rng(23)
    points = points + rng.normal(scale=0.02, size=points.shape)
    cell_faces = [
        [[int(cell[local]) for local in face] for face in quality._HEX_FACES] for cell in cells
    ]

    monkeypatch.setattr(quality, "_NATIVE_HEX_QUALITY", native)
    monkeypatch.setattr(quality, "_NATIVE_HEX_QUALITY_IMPORT_ATTEMPTED", True)
    native_points, native_stats = _relax_boundary_sliver_interior(points, cell_faces, iters=1)

    monkeypatch.setattr(quality, "_NATIVE_HEX_QUALITY", None)
    python_points, python_stats = _relax_boundary_sliver_interior(points, cell_faces, iters=1)

    np.testing.assert_allclose(native_points, python_points, atol=2e-13)
    assert native_stats.keys() == python_stats.keys()
    np.testing.assert_allclose(
        list(native_stats.values()),
        list(python_stats.values()),
        rtol=2e-13,
        atol=2e-13,
    )


def test_native_face_nonorthogonality_matches_postpass_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core.generator.native_hex.mesher import (  # noqa: PLC0415
        _reduce_nonortho_post,
    )

    native = _native_or_skip()
    assert hasattr(native, "hex_face_nonorthogonality")
    points, cells = _structured_hexes(4, 3, 2)
    rng = np.random.default_rng(29)
    points = points + rng.normal(scale=0.08, size=points.shape)

    monkeypatch.setattr(quality, "_NATIVE_HEX_QUALITY", native)
    monkeypatch.setattr(quality, "_NATIVE_HEX_QUALITY_IMPORT_ATTEMPTED", True)
    native_points = _reduce_nonortho_post(
        points, cells, threshold_deg=0.0, top_k=10, min_improve_deg=0.1
    )

    monkeypatch.setattr(quality, "_NATIVE_HEX_QUALITY", None)
    python_points = _reduce_nonortho_post(
        points, cells, threshold_deg=0.0, top_k=10, min_improve_deg=0.1
    )

    np.testing.assert_allclose(native_points, python_points, atol=2e-13)
