"""Binary64 round-trip contract for native-tet OpenFOAM points."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, cast

import numpy as np
import pytest
import trimesh

from core.generator.native_tet.plane_coverage import _tet_boundary_faces
from core.generator.native_tet.rescue_gate import audit_tet_boundary
from core.generator.native_tet.source_facet_provenance import (
    audit_source_facet_provenance_python,
)
from core.generator.native_tet.star_core_l0 import build_star_tet_core
from core.generator.polymesh_writer import PolyMeshWriter, write_generic_polymesh
from core.layers.native_bl import _write_points
from core.utils.polymesh_reader import (
    parse_foam_faces,
    parse_foam_labels,
    parse_foam_points,
)

_POLYMESH_FILES = ("points", "faces", "owner", "neighbour", "boundary")
_GENERIC_DEFAULT_SHA256 = {
    "points": "da67a5f2c53047a8b7bb7da25daf0c285b738d8b1bf4a48f1f10ce74eec710c0",
    "faces": "ba913489996985ee998431479b6013a7da3abfaa2a45e1e15e50a4a17732b4a6",
    "owner": "5c0977e5c44bcbc5f53cdb2bb0080a388c169dfad9d8498519628c6bebc46440",
    "neighbour": "6f96684a25759c24c7b8cd4161ac6d9a2fe9b545404fa8fd1e691f4324180950",
    "boundary": "f42e4d01286952eea4540c2b8389afe68b59734b5af395eed39432242a528fa6",
}


def _generic_fixture() -> tuple[np.ndarray, list[list[list[int]]]]:
    points = np.asarray(
        (
            (np.pi, -0.0, np.nextafter(1.0, 2.0)),
            (1e-300, 2.0, 3.0),
            (4.0, 5.0, 6.0),
            (7.0, 8.0, 9.0),
        ),
        dtype=np.float64,
    )
    cell_faces = [
        [[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]],
    ]
    return points, cell_faces


def _file_hashes(case_dir: Path) -> dict[str, str]:
    poly_mesh = case_dir / "constant" / "polyMesh"
    return {
        name: hashlib.sha256((poly_mesh / name).read_bytes()).hexdigest()
        for name in _POLYMESH_FILES
    }


def _disk_boundary(case_dir: Path) -> tuple[np.ndarray, np.ndarray]:
    poly_mesh = case_dir / "constant" / "polyMesh"
    points = np.asarray(parse_foam_points(poly_mesh / "points"), dtype=np.float64)
    faces = np.asarray(parse_foam_faces(poly_mesh / "faces"), dtype=np.int64)
    n_internal = len(parse_foam_labels(poly_mesh / "neighbour"))
    return points, faces[n_internal:]


def test_write_points_17_round_trips_binary64_extremes(tmp_path: Path) -> None:
    smallest_subnormal = np.nextafter(np.float64(0.0), np.float64(1.0))
    points = np.asarray(
        (
            (-0.0, smallest_subnormal, np.finfo(np.float64).max),
            (np.nextafter(1.0, 2.0), -smallest_subnormal, np.pi),
        ),
        dtype=np.float64,
    )
    path = tmp_path / "points"

    _write_points(path, points, precision=17)
    restored = np.asarray(parse_foam_points(path), dtype=np.float64)

    assert np.array_equal(restored.view(np.uint64), points.view(np.uint64))
    assert np.signbit(restored[0, 0])


def test_write_points_rejects_invalid_precision(tmp_path: Path) -> None:
    for precision in (0, 18):
        with pytest.raises(ValueError, match="point precision"):
            _write_points(
                tmp_path / f"points_{precision}",
                np.zeros((1, 3), dtype=np.float64),
                precision=precision,
            )
    with pytest.raises(ValueError, match="point precision"):
        _write_points(
            tmp_path / "points_float",
            np.zeros((1, 3), dtype=np.float64),
            precision=cast(Any, 1.5),
        )


def test_generic_default_nine_digit_files_remain_byte_exact(tmp_path: Path) -> None:
    points, cell_faces = _generic_fixture()
    implicit = tmp_path / "implicit"
    explicit = tmp_path / "explicit"
    direct_implicit = tmp_path / "direct_implicit_points"
    direct_explicit = tmp_path / "direct_explicit_points"

    write_generic_polymesh(points, cell_faces, implicit)
    write_generic_polymesh(points, cell_faces, explicit, point_precision=9)
    _write_points(direct_implicit, points)
    _write_points(direct_explicit, points, precision=9)

    assert _file_hashes(implicit) == _GENERIC_DEFAULT_SHA256
    assert _file_hashes(explicit) == _GENERIC_DEFAULT_SHA256
    assert direct_implicit.read_bytes() == direct_explicit.read_bytes()
    assert hashlib.sha256(direct_implicit.read_bytes()).hexdigest() == (
        _GENERIC_DEFAULT_SHA256["points"]
    )


def test_poly_mesh_writer_17_changes_only_points_and_round_trips(
    tmp_path: Path,
) -> None:
    scale = np.nextafter(np.float64(np.pi), np.float64(4.0))
    translation = np.asarray((0.125, -0.25, 0.375), dtype=np.float64)
    points = translation + scale * np.eye(4, 3, dtype=np.float64)
    tets = np.asarray(((0, 1, 2, 3),), dtype=np.int64)
    default_case = tmp_path / "default9"
    roundtrip_case = tmp_path / "roundtrip17"

    PolyMeshWriter().write(points, tets.copy(), default_case)
    PolyMeshWriter().write(
        points,
        tets.copy(),
        roundtrip_case,
        point_precision=17,
    )

    restored, _ = _disk_boundary(roundtrip_case)
    assert np.array_equal(restored.view(np.uint64), points.view(np.uint64))
    default_hashes = _file_hashes(default_case)
    roundtrip_hashes = _file_hashes(roundtrip_case)
    assert default_hashes["points"] != roundtrip_hashes["points"]
    for name in ("faces", "owner", "neighbour", "boundary"):
        assert default_hashes[name] == roundtrip_hashes[name]


def test_poly_mesh_writer_rejects_nonfinite_before_artifacts(tmp_path: Path) -> None:
    points = np.asarray(
        ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, np.nan)),
        dtype=np.float64,
    )
    case_dir = tmp_path / "nonfinite"

    with pytest.raises(ValueError, match="must be finite"):
        PolyMeshWriter().write(
            points,
            np.asarray(((0, 1, 2, 3),), dtype=np.int64),
            case_dir,
            point_precision=17,
        )

    assert not case_dir.exists()


def test_transformed_cylinder_disk_preserves_source_facets(tmp_path: Path) -> None:
    transforms: tuple[tuple[float, tuple[float, float, float]], ...] = (
        (1.0, (0.0, 0.0, 0.0)),
        (1e-6, (3e-3, -2e-3, 1e-3)),
        (1e6, (3e9, -2e9, 1e9)),
        (0.125, (-11.0, 7.0, 3.0)),
    )
    for scale, translation in transforms:
        cylinder = trimesh.creation.cylinder(radius=0.5, height=1.0, sections=32)
        source_points = (
            np.asarray(cylinder.vertices, dtype=np.float64) * scale
            + np.asarray(translation, dtype=np.float64)
        )
        source_faces = np.asarray(cylinder.faces, dtype=np.int64)
        core = build_star_tet_core(source_points, source_faces)
        case_dir = tmp_path / f"cylinder_{scale:g}"

        PolyMeshWriter().write(
            core.points,
            core.tets.copy(),
            case_dir,
            point_precision=17,
        )
        disk_points, disk_boundary = _disk_boundary(case_dir)
        report = audit_source_facet_provenance_python(
            source_points,
            source_faces,
            disk_points,
            disk_boundary,
        )
        validity = audit_tet_boundary(disk_points, core.tets)

        assert report["source_faces_preserved"] is True
        assert report["n_owned_candidate_faces"] == len(source_faces)
        assert report["n_unowned_candidate_faces"] == 0
        assert validity.n_inverted_tets == 0
        assert validity.n_degenerate_tets == 0
        assert {
            tuple(int(vertex) for vertex in face)
            for face in np.sort(disk_boundary, axis=1)
        } == {
            tuple(int(vertex) for vertex in face)
            for face in np.sort(_tet_boundary_faces(core.tets), axis=1)
        }


def test_cylinder_roundtrip_point_file_stays_below_twice_default(
    tmp_path: Path,
) -> None:
    cylinder = trimesh.creation.cylinder(radius=0.5, height=1.0, sections=32)
    core = build_star_tet_core(cylinder.vertices, cylinder.faces)
    default_case = tmp_path / "default9"
    roundtrip_case = tmp_path / "roundtrip17"
    PolyMeshWriter().write(core.points, core.tets.copy(), default_case)
    PolyMeshWriter().write(
        core.points,
        core.tets.copy(),
        roundtrip_case,
        point_precision=17,
    )

    default_size = (default_case / "constant" / "polyMesh" / "points").stat().st_size
    roundtrip_size = (
        roundtrip_case / "constant" / "polyMesh" / "points"
    ).stat().st_size
    assert roundtrip_size <= 2 * default_size
