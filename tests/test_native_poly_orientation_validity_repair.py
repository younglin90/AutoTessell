"""Cell-local outward winding repair for native-Poly Voronoi cells."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Iterable

import numpy as np

import core.generator.native_poly.voronoi as voronoi
from core.analyzer.readers import read_stl

_REPO = Path(__file__).resolve().parents[1]


def _canonical_topology(cells: list[list[list[int]]]) -> tuple[object, ...]:
    return tuple(tuple(tuple(sorted(face)) for face in cell) for cell in cells)


def _same_cycle(first: Iterable[int], second: Iterable[int]) -> bool:
    left = tuple(first)
    right = tuple(second)
    if len(left) != len(right):
        return False
    doubled = left + left
    return any(doubled[offset : offset + len(left)] == right for offset in range(len(left)))


def _opposite_cycles(first: list[int], second: list[int]) -> bool:
    return _same_cycle(first, reversed(second))


def test_mixed_tetra_winding_repairs_volume_without_geometry_drift() -> None:
    points = np.asarray(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )
    valid = [[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]]
    mixed = [
        [list(reversed(face)) if index % 2 else list(face) for index, face in enumerate(valid)]
    ]
    points_before = points.copy()
    topology_before = _canonical_topology(mixed)

    oriented, n_reversed, n_ambiguous = voronoi._orient_poly_cell_faces_outward(
        points,
        mixed,
    )

    assert n_reversed == 2
    assert n_ambiguous == 0
    assert voronoi.validate_poly_cell_volumes(oriented, points, mandatory=True) == (0, 0)
    assert np.array_equal(points, points_before)
    assert _canonical_topology(oriented) == topology_before
    assert [face[0] for face in oriented[0]] == [face[0] for face in mixed[0]]


def test_shared_face_has_opposite_winding_after_cell_local_orientation() -> None:
    points = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [0.0, 0.0, -1.0],
        ],
        dtype=np.float64,
    )
    cells = [
        [[0, 1, 2], [0, 1, 3], [1, 2, 3], [2, 0, 3]],
        [[0, 1, 2], [0, 1, 4], [1, 2, 4], [2, 0, 4]],
    ]
    topology_before = _canonical_topology(cells)

    oriented, _n_reversed, n_ambiguous = voronoi._orient_poly_cell_faces_outward(
        points,
        cells,
    )

    assert n_ambiguous == 0
    assert _opposite_cycles(oriented[0][0], oriented[1][0])
    assert _canonical_topology(oriented) == topology_before
    assert voronoi.validate_poly_cell_volumes(oriented, points, mandatory=True) == (0, 0)


def test_ambiguous_coplanar_cell_is_not_forced_and_remains_fail_closed(
    tmp_path: Path,
) -> None:
    points = np.asarray(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0]],
        dtype=np.float64,
    )
    cells = [[[0, 1, 2], [0, 1, 3], [1, 2, 3], [2, 0, 3]]]

    oriented, _n_reversed, n_ambiguous = voronoi._orient_poly_cell_faces_outward(
        points,
        cells,
    )
    outcome = voronoi._admit_and_write_polymesh_poly(
        points,
        oriented,
        tmp_path,
        strict=False,
        started_at=time.perf_counter(),
    )

    assert n_ambiguous == 4
    assert oriented == cells
    assert outcome.refusal is not None
    assert outcome.refusal.failure_kind == "validity_refused"
    assert outcome.refusal.n_degenerate_cells == 1
    assert not (tmp_path / "constant" / "polyMesh").exists()


def test_orientation_repair_is_deterministic_three_times() -> None:
    points = np.asarray(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )
    cells = [[[0, 1, 2], [0, 1, 3], [1, 2, 3], [2, 0, 3]]]

    outputs = [voronoi._orient_poly_cell_faces_outward(points, cells) for _ in range(3)]

    assert outputs[0] == outputs[1] == outputs[2]


def test_repaired_sphere_polymesh_is_deterministic_three_times(tmp_path: Path) -> None:
    mesh = read_stl(_REPO / "tests" / "benchmarks" / "sphere.stl")
    digests: list[tuple[tuple[str, bytes], ...]] = []

    for run in range(3):
        case_dir = tmp_path / str(run)
        result = voronoi.generate_native_poly_voronoi(
            mesh.vertices,
            mesh.faces,
            case_dir,
            seed_density=8,
            n_lloyd=2,
            auto_escalate=False,
            bl_layers=0,
        )
        assert result.success, result.message
        poly_dir = case_dir / "constant" / "polyMesh"
        digests.append(
            tuple(
                (path.name, path.read_bytes())
                for path in sorted(poly_dir.iterdir())
                if path.is_file()
            )
        )

    assert digests[0] == digests[1] == digests[2]
