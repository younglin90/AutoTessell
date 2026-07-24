"""Phase 0 native_hex reporting metrics."""

from __future__ import annotations

import numpy as np

from core.generator.native_hex.metrics import compute_native_hex_metrics


def _cube_faces(offset: int) -> list[list[int]]:
    return [
        [offset + 0, offset + 3, offset + 2, offset + 1],
        [offset + 4, offset + 5, offset + 6, offset + 7],
        [offset + 0, offset + 1, offset + 5, offset + 4],
        [offset + 3, offset + 7, offset + 6, offset + 2],
        [offset + 0, offset + 4, offset + 7, offset + 3],
        [offset + 1, offset + 2, offset + 6, offset + 5],
    ]


def test_all_hex_cube_reports_phase0_baseline() -> None:
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
        ]
    )
    metrics = compute_native_hex_metrics(points, [_cube_faces(0)])

    assert metrics.cell_census == {"hex": 1, "prism": 0, "tet": 0, "other": 0}
    assert metrics.cell_count_fractions["hex"] == 1.0
    assert metrics.cell_volume_fractions["hex"] == 1.0
    assert metrics.score_che == 1.0
    assert metrics.n_hex_clusters == 1
    assert metrics.largest_cluster_frac == 1.0
    assert metrics.beta_pass
    assert metrics.local_mean_volume == 1.0


def test_census_distinguishes_generic_cell_families_and_clusters() -> None:
    # Two disjoint hexes make two deterministic hex-hex clusters.  The other
    # three shells exercise the generic writer's prism/tet/other labels.
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
            [3.0, 0.0, 0.0],
            [4.0, 0.0, 0.0],
            [4.0, 1.0, 0.0],
            [3.0, 1.0, 0.0],
            [3.0, 0.0, 1.0],
            [4.0, 0.0, 1.0],
            [4.0, 1.0, 1.0],
            [3.0, 1.0, 1.0],
            [0.0, 3.0, 0.0],
            [1.0, 3.0, 0.0],
            [0.0, 4.0, 0.0],
            [0.0, 3.0, 1.0],
            [1.0, 3.0, 1.0],
            [0.0, 4.0, 1.0],
            [3.0, 3.0, 0.0],
            [4.0, 3.0, 0.0],
            [3.0, 4.0, 0.0],
            [3.0, 3.0, 1.0],
            [4.0, 3.0, 1.0],
            [3.0, 4.0, 1.0],
            [5.0, 3.0, 0.0],
            [6.0, 3.0, 0.0],
            [6.0, 4.0, 0.0],
            [5.0, 4.0, 0.0],
            [5.0, 3.0, 1.0],
            [6.0, 3.0, 1.0],
        ]
    )
    prism = [
        [16, 17, 18],
        [19, 21, 20],
        [16, 19, 20, 17],
        [17, 20, 21, 18],
        [16, 18, 21, 19],
    ]
    tet = [[22, 23, 24], [22, 25, 23], [23, 25, 24], [24, 25, 22]]
    other = [
        [26, 27, 28, 29],
        [26, 30, 27],
        [27, 30, 28],
        [28, 30, 29],
        [29, 30, 26],
    ]
    cells = [_cube_faces(0), _cube_faces(8), prism, tet, other]
    metrics = compute_native_hex_metrics(points, cells)

    assert metrics.cell_census == {"hex": 2, "prism": 1, "tet": 1, "other": 1}
    assert sum(metrics.cell_census.values()) == 5
    assert sum(metrics.cell_count_fractions.values()) == 1.0
    assert sum(metrics.cell_volume_fractions.values()) == 1.0
    assert metrics.n_hex_clusters == 2
    assert metrics.largest_cluster_frac == 0.5
