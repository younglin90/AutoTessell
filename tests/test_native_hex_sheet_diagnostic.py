"""HEX-SHEET-2 layer-wide shrink-set diagnostic tests."""

from __future__ import annotations

import numpy as np

from core.generator.native_hex.match_repair import build_pillow
from core.generator.native_hex.sheet_diagnostic import analyze_layer_wide_shrink_set

_HEX_FACES = (
    (0, 3, 2, 1),
    (4, 5, 6, 7),
    (0, 1, 5, 4),
    (3, 7, 6, 2),
    (0, 4, 7, 3),
    (1, 2, 6, 5),
)
_UNIT_HEX = np.array(
    [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]],
    dtype=np.float64,
)


def _single_cell() -> list[list[list[int]]]:
    return [[[int(vertex) for vertex in face] for face in _HEX_FACES]]


def _valid_pillow_shell() -> tuple[np.ndarray, list[list[list[int]]]]:
    cells = _single_cell()
    built = build_pillow(_UNIT_HEX, cells[0], cells[0][1], 8, 0.55, 0.0, "taper")
    assert built is not None
    new_points, new_cells = built
    return np.vstack([_UNIT_HEX, new_points]), new_cells


def _grid(n: int) -> tuple[np.ndarray, list[list[list[int]]]]:
    values: np.ndarray = np.arange(n + 1, dtype=np.float64)
    points = np.stack(np.meshgrid(values, values, values, indexing="ij"), axis=-1).reshape(-1, 3)
    n1 = n + 1

    def vertex(i: int, j: int, k: int) -> int:
        return i * n1 * n1 + j * n1 + k

    hexes = [
        [
            vertex(i, j, k),
            vertex(i + 1, j, k),
            vertex(i + 1, j + 1, k),
            vertex(i, j + 1, k),
            vertex(i, j, k + 1),
            vertex(i + 1, j, k + 1),
            vertex(i + 1, j + 1, k + 1),
            vertex(i, j + 1, k + 1),
        ]
        for i in range(n)
        for j in range(n)
        for k in range(n)
    ]
    cells = [[[int(cell[index]) for index in face] for face in _HEX_FACES] for cell in hexes]
    return points, cells


def test_valid_pillow_shell_satisfies_every_precondition() -> None:
    points, cells = _valid_pillow_shell()
    report = analyze_layer_wide_shrink_set("shell", points, cells, log_only=False)

    assert report.n_shrink == 6
    assert report.n_shrink_nonhex == 0
    assert report.n_interface_quads == 6
    assert report.n_interface_nonquads == 0
    assert report.edge_incidence_histogram == ((2, 12),)
    assert report.n_components == 1
    assert report.n_open_edges == 0
    assert report.n_nonmanifold_edges == 0
    assert report.shrink_boundary_interface_histogram == ((1, 1, 6),)
    assert report.expected_point_growth == 8
    assert report.expected_cell_growth == 6
    assert report.q_closed_manifold_quad_set
    assert report.wall_cell_incidence_contract
    assert report.topology_ready


def test_cartesian_shell_measures_edge_and_corner_incidence_instead_of_assuming_it() -> None:
    points, cells = _grid(4)
    report = analyze_layer_wide_shrink_set("grid", points, cells, log_only=False)

    assert report.n_shrink == 56
    assert report.n_core == 8
    assert report.n_interface_quads == 24
    assert report.edge_incidence_histogram == ((2, 48),)
    assert report.n_components == 1
    assert report.q_closed_manifold_quad_set
    assert report.shrink_boundary_face_histogram == ((1, 24), (2, 24), (3, 8))
    assert report.shrink_interface_face_histogram == ((0, 32), (1, 24))
    assert not report.wall_cell_incidence_contract
    assert not report.topology_ready


def test_diagnostic_is_report_only_and_deterministic() -> None:
    points, cells = _valid_pillow_shell()
    points_before = points.copy()
    cells_before = [[list(face) for face in cell] for cell in cells]

    first = analyze_layer_wide_shrink_set("shell", points, cells, log_only=False)
    second = analyze_layer_wide_shrink_set("shell", points, cells, log_only=False)

    assert first == second
    assert np.array_equal(points, points_before)
    assert cells == cells_before
