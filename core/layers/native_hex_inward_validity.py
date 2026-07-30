"""Direct validity predicates for the experimental native hex inward shell."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray


def signed_cell_volumes(
    points: NDArray[np.float64],
    cell_faces: Sequence[Sequence[Sequence[int]]],
) -> NDArray[np.float64]:
    """Signed volumes from outward-oriented polygon faces."""
    pts = np.asarray(points, dtype=np.float64)
    volumes = np.zeros(len(cell_faces), dtype=np.float64)
    for cell_index, faces in enumerate(cell_faces):
        accumulated = 0.0
        for face in faces:
            if len(face) < 3:
                continue
            anchor = pts[int(face[0])]
            for index in range(1, len(face) - 1):
                accumulated += float(
                    np.dot(
                        anchor,
                        np.cross(pts[int(face[index])], pts[int(face[index + 1])]),
                    )
                )
        volumes[cell_index] = accumulated / 6.0
    return volumes


def signed_hex_corner_determinants(
    points: NDArray[np.float64],
    hex_cells: NDArray[np.int64],
) -> NDArray[np.float64]:
    """Eight orientation-sensitive corner Jacobian proxies per canonical hex."""
    pts = np.asarray(points, dtype=np.float64)
    cells = np.asarray(hex_cells, dtype=np.int64)
    corner_neighbors = np.asarray(
        [
            [1, 3, 4],
            [2, 0, 5],
            [3, 1, 6],
            [0, 2, 7],
            [7, 5, 0],
            [4, 6, 1],
            [5, 7, 2],
            [6, 4, 3],
        ],
        dtype=np.int64,
    )
    determinants = np.empty((len(cells), 8), dtype=np.float64)
    for corner, neighbors in enumerate(corner_neighbors):
        origins = pts[cells[:, corner]]
        edges = pts[cells[:, neighbors]] - origins[:, None, :]
        determinants[:, corner] = np.einsum(
            "ij,ij->i",
            edges[:, 0],
            np.cross(edges[:, 1], edges[:, 2]),
        )
    return determinants
