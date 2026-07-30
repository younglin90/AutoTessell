"""Cycle39: default-off fixed-outer native hex inward shell."""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest

_AUTHORITATIVE = ("points", "faces", "owner", "neighbour", "boundary")
_SOURCE_POINTS = np.array(
    [
        [0, 0, 0],
        [1, 0, 0],
        [1, 1, 0],
        [0, 1, 0],
        [0, 0, 1],
        [1, 0, 1],
        [1, 1, 1],
        [0, 1, 1],
    ],
    dtype=np.float64,
)
_SOURCE_FACES = [
    [0, 3, 2, 1],
    [4, 5, 6, 7],
    [0, 1, 5, 4],
    [1, 2, 6, 5],
    [2, 3, 7, 6],
    [3, 0, 4, 7],
]


def _write_cube(
    case_dir: Path,
    *,
    partial: bool = False,
    points: np.ndarray = _SOURCE_POINTS,
) -> None:
    from core.generator.polymesh_writer import write_generic_polymesh

    floor_key = tuple(sorted(_SOURCE_FACES[0]))

    def classify(face: list[int], _points: np.ndarray) -> tuple[str, str]:
        if tuple(sorted(face)) == floor_key:
            return ("inlet", "patch") if partial else ("wallFloor", "wall")
        return "wallOther", "wall"

    write_generic_polymesh(
        points,
        [[list(face) for face in _SOURCE_FACES]],
        case_dir,
        boundary_patch_classifier=classify,
        strict=True,
    )


def _transaction_artifacts(case_dir: Path) -> list[Path]:
    return list((case_dir / "constant").glob(".autotessell_hexbl_*"))


def _bytes(case_dir: Path) -> dict[str, bytes]:
    poly_dir = case_dir / "constant" / "polyMesh"
    return {name: (poly_dir / name).read_bytes() for name in _AUTHORITATIVE}


def _digest(case_dir: Path) -> str:
    digest = hashlib.sha256()
    for name in _AUTHORITATIVE:
        digest.update(name.encode("ascii"))
        digest.update(_bytes(case_dir)[name])
    return digest.hexdigest()


def _normals() -> np.ndarray:
    normals = np.zeros_like(_SOURCE_POINTS)
    for quad in np.asarray(_SOURCE_FACES, dtype=np.int64):
        p0, p1, p2, p3 = _SOURCE_POINTS[quad]
        normal = np.cross(p1 - p0, p2 - p0) + np.cross(p2 - p0, p3 - p0)
        for vertex in quad:
            normals[int(vertex)] += normal
    normals /= np.linalg.norm(normals, axis=1)[:, None]
    return normals


def test_inward_primitive_preserves_inputs_and_records_bijective_provenance() -> None:
    from core.layers.native_hex_bl import extrude_hex_bl_inward_shell

    points = _SOURCE_POINTS.copy()
    quads = np.asarray(_SOURCE_FACES, dtype=np.int64)
    normals = _normals()
    points_before = points.copy()
    quads_before = quads.copy()
    normals_before = normals.copy()

    new_points, hexes, result, provenance = extrude_hex_bl_inward_shell(
        points,
        quads,
        normals,
        num_layers=3,
        first_thickness=0.05,
        growth_ratio=1.2,
    )

    assert np.array_equal(points, points_before)
    assert np.array_equal(quads, quads_before)
    assert np.array_equal(normals, normals_before)
    assert result.n_layers == 3
    assert result.n_hex_cells == 18
    assert len(np.unique(provenance.source_point_ids)) == 8
    assert len(np.unique(provenance.outer_point_ids)) == 8
    assert not np.intersect1d(
        provenance.source_point_ids,
        provenance.outer_point_ids,
    ).size
    assert np.array_equal(
        new_points[provenance.outer_point_ids],
        points[provenance.source_point_ids],
    )
    assert np.array_equal(
        new_points[provenance.outer_face_point_ids],
        points[quads],
    )
    assert np.array_equal(provenance.outer_face_point_ids, hexes[2::3, 4:8])


def test_signed_corner_gate_detects_local_inversion_with_positive_volume() -> None:
    """Global signed volume alone cannot certify every hex corner."""
    from core.generator.tier_layers_post import _HEX_FACES
    from core.layers.native_hex_inward_validity import (
        signed_cell_volumes,
        signed_hex_corner_determinants,
    )

    points = _SOURCE_POINTS.copy()
    points[6] = [-0.2, 1.0, 1.0]
    cell = np.arange(8, dtype=np.int64)
    cell_faces = [[[int(cell[index]) for index in face] for face in _HEX_FACES]]
    assert signed_cell_volumes(points, cell_faces)[0] > 0.0
    determinants = signed_hex_corner_determinants(points, cell[None, :])
    assert float(np.min(determinants)) < 0.0


@pytest.mark.parametrize(("layers", "expected_cells"), [(1, 7), (3, 19)])
def test_inward_cube_is_exact_valid_and_deterministic(
    tmp_path: Path,
    layers: int,
    expected_cells: int,
) -> None:
    from core.evaluator.native_checker import NativeMeshChecker
    from core.generator.tier_layers_post import (
        _boundary_entries_with_types,
        _run_native_hex_bl,
    )
    from core.utils.polymesh_reader import (
        parse_foam_faces,
        parse_foam_points_array,
    )

    hashes: list[str] = []
    messages: list[str] = []
    for repeat in range(3):
        case_dir = tmp_path / f"case-{repeat}"
        _write_cube(case_dir)
        extra_file = case_dir / "constant" / "polyMesh" / "cellZones"
        extra_file.write_bytes(b"cycle39-extra-zone-evidence")
        ok, message, actual_faces = _run_native_hex_bl(
            case_dir,
            num_layers=layers,
            growth_ratio=1.2,
            first_thickness=0.05,
            params={"post_layers_hex_inward_shell": True},
        )
        assert ok, message
        assert actual_faces == 6
        assert f"requested_layers={layers}" in message
        assert f"actual_layers={layers}" in message
        assert "provenance_points=8" in message
        assert "provenance_faces=6" in message

        checker = NativeMeshChecker().run(case_dir)
        assert checker.mesh_ok
        assert checker.cells == expected_cells
        assert checker.negative_volumes == 0
        assert checker.min_determinant > 0.0
        assert extra_file.read_bytes() == b"cycle39-extra-zone-evidence"

        poly_dir = case_dir / "constant" / "polyMesh"
        output_points = parse_foam_points_array(poly_dir / "points")
        output_faces = parse_foam_faces(poly_dir / "faces")
        boundary = _boundary_entries_with_types(poly_dir / "boundary")
        observed: dict[tuple[tuple[float, float, float], ...], tuple[str, str]] = {}
        for patch in boundary:
            patch_name = str(patch["name"])
            patch_type = str(patch["type"])
            start = int(patch["startFace"])
            for face_index in range(start, start + int(patch["nFaces"])):
                coordinates = tuple(
                    sorted(tuple(output_points[vertex]) for vertex in output_faces[face_index])
                )
                observed[coordinates] = patch_name, patch_type
        for face_index, source_face in enumerate(_SOURCE_FACES):
            coordinates = tuple(sorted(tuple(_SOURCE_POINTS[vertex]) for vertex in source_face))
            expected_patch = (
                ("wallFloor", "wall")
                if face_index == 0
                else (
                    "wallOther",
                    "wall",
                )
            )
            assert observed[coordinates] == expected_patch

        hashes.append(_digest(case_dir))
        messages.append(message)
        assert not _transaction_artifacts(case_dir)

    assert len(set(hashes)) == 1
    assert len(set(messages)) == 1


def test_inward_oversized_shell_rolls_back_without_artifacts(tmp_path: Path) -> None:
    from core.generator.tier_layers_post import _run_native_hex_bl

    case_dir = tmp_path / "oversized"
    _write_cube(case_dir)
    before = _bytes(case_dir)
    ok, message, actual = _run_native_hex_bl(
        case_dir,
        num_layers=1,
        growth_ratio=1.2,
        first_thickness=1.0,
        params={"post_layers_hex_inward_shell": True},
    )
    assert not ok
    assert actual == 0
    assert message.startswith("native_hex_bl_inward_l0_thickness_limit:")
    assert _bytes(case_dir) == before
    assert not _transaction_artifacts(case_dir)


def test_inward_partial_boundary_selection_fails_closed(tmp_path: Path) -> None:
    from core.generator.tier_layers_post import _run_native_hex_bl

    case_dir = tmp_path / "partial"
    _write_cube(case_dir, partial=True)
    before = _bytes(case_dir)
    ok, message, actual = _run_native_hex_bl(
        case_dir,
        num_layers=1,
        growth_ratio=1.2,
        first_thickness=0.05,
        params={"post_layers_hex_inward_shell": True},
    )
    assert not ok
    assert actual == 0
    assert message == ("native_hex_bl_inward_l0_contract:requires_all_6_boundary_quads_selected")
    assert _bytes(case_dir) == before
    assert not _transaction_artifacts(case_dir)


def test_inward_non_unit_rectangular_box_is_evidenced_l0(tmp_path: Path) -> None:
    from core.evaluator.native_checker import NativeMeshChecker
    from core.generator.tier_layers_post import _run_native_hex_bl

    points = _SOURCE_POINTS * np.array([2.0, 3.0, 4.0])
    case_dir = tmp_path / "rectangular"
    _write_cube(case_dir, points=points)
    ok, message, actual = _run_native_hex_bl(
        case_dir,
        num_layers=3,
        growth_ratio=1.2,
        first_thickness=0.05,
        params={"post_layers_hex_inward_shell": True},
    )
    assert ok, message
    assert actual == 6
    checker = NativeMeshChecker().run(case_dir)
    assert checker.cells == 19
    assert checker.negative_volumes == 0
    assert checker.min_determinant > 0.0
    assert not _transaction_artifacts(case_dir)


@pytest.mark.parametrize("thickness", [0.45, 0.49])
def test_inward_box_rejects_margin_equality_and_near_collapse(
    tmp_path: Path,
    thickness: float,
) -> None:
    from core.generator.tier_layers_post import _run_native_hex_bl

    case_dir = tmp_path / f"margin-{thickness}"
    _write_cube(case_dir)
    before = _bytes(case_dir)
    ok, message, actual = _run_native_hex_bl(
        case_dir,
        num_layers=1,
        growth_ratio=1.2,
        first_thickness=thickness,
        params={"post_layers_hex_inward_shell": True},
    )
    assert not ok
    assert actual == 0
    assert message.startswith("native_hex_bl_inward_l0_thickness_limit:")
    assert _bytes(case_dir) == before
    assert not _transaction_artifacts(case_dir)


def test_inward_rejects_rotated_box_before_candidate(tmp_path: Path) -> None:
    from core.generator.tier_layers_post import _run_native_hex_bl

    angle = np.deg2rad(30.0)
    rotation = np.array(
        [
            [np.cos(angle), -np.sin(angle), 0.0],
            [np.sin(angle), np.cos(angle), 0.0],
            [0.0, 0.0, 1.0],
        ]
    )
    case_dir = tmp_path / "rotated"
    _write_cube(case_dir, points=_SOURCE_POINTS @ rotation.T)
    before = _bytes(case_dir)
    ok, message, actual = _run_native_hex_bl(
        case_dir,
        num_layers=1,
        growth_ratio=1.2,
        first_thickness=0.05,
        params={"post_layers_hex_inward_shell": True},
    )
    assert not ok
    assert actual == 0
    assert message.startswith("native_hex_bl_inward_l0_contract:axis_")
    assert _bytes(case_dir) == before
    assert not _transaction_artifacts(case_dir)


def test_inward_rejects_two_base_hex_cells_before_candidate(tmp_path: Path) -> None:
    from core.generator.polymesh_writer import write_generic_polymesh
    from core.generator.tier_layers_post import _run_native_hex_bl

    second_points = _SOURCE_POINTS + np.array([2.0, 0.0, 0.0])
    points = np.vstack((_SOURCE_POINTS, second_points))
    second_faces = [[vertex + 8 for vertex in face] for face in _SOURCE_FACES]
    case_dir = tmp_path / "two-cells"
    write_generic_polymesh(
        points,
        [[list(face) for face in _SOURCE_FACES], second_faces],
        case_dir,
        strict=True,
    )
    before = _bytes(case_dir)
    ok, message, actual = _run_native_hex_bl(
        case_dir,
        num_layers=1,
        growth_ratio=1.2,
        first_thickness=0.05,
        params={"post_layers_hex_inward_shell": True},
    )
    assert not ok
    assert actual == 0
    assert message == "native_hex_bl_inward_l0_contract:requires_exactly_8_finite_points"
    assert _bytes(case_dir) == before
    assert not _transaction_artifacts(case_dir)
