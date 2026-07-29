"""Conforming tetra grid for closed, axis-aligned CSG surfaces."""
from __future__ import annotations

import numpy as np

from core.utils.geometry import inside_boolean_winding_number, inside_robust


_CUBE_TETS = np.asarray(
    [[0, 1, 2, 6], [0, 2, 3, 6], [0, 3, 7, 6],
     [0, 7, 4, 6], [0, 4, 5, 6], [0, 5, 1, 6]],
    dtype=np.int64,
)


def _is_axis_aligned(vertices: np.ndarray, faces: np.ndarray) -> bool:
    """Return whether every non-degenerate triangle lies on a coordinate plane."""
    triangles = vertices[faces]
    normals = np.cross(
        triangles[:, 1] - triangles[:, 0],
        triangles[:, 2] - triangles[:, 0],
    )
    lengths = np.linalg.norm(normals, axis=1)
    if np.any(lengths <= 1e-14):
        return False
    unit = np.abs(normals / lengths[:, None])
    return not bool(np.any(np.max(unit, axis=1) < 1.0 - 1e-10))


def _grid_axes(vertices: np.ndarray, target_edge: float) -> list[np.ndarray] | None:
    """Make a coordinate-plane-preserving Cartesian grid."""
    axes: list[np.ndarray] = []
    for axis in range(3):
        base = np.unique(vertices[:, axis])
        if base.size < 2:
            return None
        values = [float(base[0])]
        for lo, hi in zip(base[:-1], base[1:], strict=True):
            width = float(hi - lo)
            steps = max(1, int(np.ceil(width / max(float(target_edge), 1e-12))))
            values.extend(np.linspace(float(lo), float(hi), steps + 1)[1:])
        axes.append(np.asarray(values, dtype=np.float64))
    if np.prod([len(axis) - 1 for axis in axes], dtype=np.int64) > 150_000:
        return None
    return axes


def _tets_from_inside_mask(
    axes: list[np.ndarray],
    inside: np.ndarray,
) -> tuple[np.ndarray, np.ndarray] | None:
    """Convert selected Cartesian cells to consistently oriented Kuhn tets."""
    nx, ny, nz = (len(axis) for axis in axes)
    xx, yy, zz = np.meshgrid(*axes, indexing="ij")
    points = np.column_stack((xx.ravel(), yy.ravel(), zz.ravel()))

    def index(i: int, j: int, k: int) -> int:
        return (i * ny + j) * nz + k

    selected = np.argwhere(inside.reshape(nx - 1, ny - 1, nz - 1))
    if selected.size == 0:
        return None
    cells = np.empty((selected.shape[0], 8), dtype=np.int64)
    for row, (i, j, k) in enumerate(selected):
        cells[row] = (
            index(int(i), int(j), int(k)),
            index(int(i) + 1, int(j), int(k)),
            index(int(i) + 1, int(j) + 1, int(k)),
            index(int(i), int(j) + 1, int(k)),
            index(int(i), int(j), int(k) + 1),
            index(int(i) + 1, int(j), int(k) + 1),
            index(int(i) + 1, int(j) + 1, int(k) + 1),
            index(int(i), int(j) + 1, int(k) + 1),
        )
    tets = cells[:, _CUBE_TETS].reshape(-1, 4)
    tet_points = points[tets]
    signed = np.einsum(
        "ij,ij->i",
        np.cross(
            tet_points[:, 1] - tet_points[:, 0],
            tet_points[:, 2] - tet_points[:, 0],
        ),
        tet_points[:, 3] - tet_points[:, 0],
    )
    flip = signed < 0.0
    if bool(flip.any()):
        first = tets[flip, 0].copy()
        tets[flip, 0] = tets[flip, 1]
        tets[flip, 1] = first
    return points, tets


def build_rectilinear_boolean_tets(
    surfaces: list[tuple[np.ndarray, np.ndarray]],
    *,
    operation: str,
    target_edge: float,
) -> tuple[np.ndarray, np.ndarray] | None:
    """Native exact-grid route for axis-aligned multi-surface Boolean solids.

    Unlike a concatenated triangle soup, every grid cell is classified against
    the ordered original closed surfaces.  Input coordinate planes are grid
    planes, so boxes and orthogonal CAD CSG retain their Boolean volume exactly
    without requiring an external surface-Boolean backend.
    """
    if not surfaces:
        return None
    normalized = [
        (np.asarray(vertices, dtype=np.float64), np.asarray(faces, dtype=np.int64))
        for vertices, faces in surfaces
    ]
    if any(
        vertices.ndim != 2
        or vertices.shape[1] != 3
        or faces.ndim != 2
        or faces.shape[1] != 3
        or faces.size == 0
        or not _is_axis_aligned(vertices, faces)
        for vertices, faces in normalized
    ):
        return None
    axes = _grid_axes(
        np.concatenate([vertices for vertices, _ in normalized], axis=0),
        target_edge,
    )
    if axes is None:
        return None
    cx = (axes[0][:-1] + axes[0][1:]) * 0.5
    cy = (axes[1][:-1] + axes[1][1:]) * 0.5
    cz = (axes[2][:-1] + axes[2][1:]) * 0.5
    xx, yy, zz = np.meshgrid(cx, cy, cz, indexing="ij")
    centers = np.column_stack((xx.ravel(), yy.ravel(), zz.ravel()))
    inside = inside_boolean_winding_number(
        centers,
        normalized,
        operation=operation,
    )
    return _tets_from_inside_mask(axes, inside)


def build_rectilinear_csg_tets(
    vertices: np.ndarray,
    faces: np.ndarray,
    *,
    target_edge: float,
) -> tuple[np.ndarray, np.ndarray] | None:
    """Return conforming tets when every surface plane is axis-aligned.

    The grid preserves all input coordinate planes exactly.  It is therefore
    suitable for Boolean CAD boxes and other rectilinear CSG solids, but never
    selected for sloped or curved surfaces.
    """
    vertices = np.asarray(vertices, dtype=np.float64)
    faces = np.asarray(faces, dtype=np.int64)
    if vertices.ndim != 2 or vertices.shape[1] != 3 or faces.size == 0:
        return None
    triangles = vertices[faces]
    normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    lengths = np.linalg.norm(normals, axis=1)
    if np.any(lengths <= 1e-14):
        return None
    unit = np.abs(normals / lengths[:, None])
    if np.any(np.max(unit, axis=1) < 1.0 - 1e-10):
        return None

    axes: list[np.ndarray] = []
    for axis in range(3):
        base = np.unique(vertices[:, axis])
        if base.size < 2:
            return None
        values = [float(base[0])]
        for lo, hi in zip(base[:-1], base[1:], strict=True):
            width = float(hi - lo)
            steps = max(1, int(np.ceil(width / max(float(target_edge), 1e-12))))
            values.extend(np.linspace(float(lo), float(hi), steps + 1)[1:])
        axes.append(np.asarray(values, dtype=np.float64))

    nx, ny, nz = (len(axis) for axis in axes)
    if (nx - 1) * (ny - 1) * (nz - 1) > 150_000:
        return None
    xx, yy, zz = np.meshgrid(*axes, indexing="ij")
    points = np.column_stack((xx.ravel(), yy.ravel(), zz.ravel()))

    def index(i: int, j: int, k: int) -> int:
        return (i * ny + j) * nz + k

    cells: list[np.ndarray] = []
    for i in range(nx - 1):
        for j in range(ny - 1):
            for k in range(nz - 1):
                center = np.array([[
                    (axes[0][i] + axes[0][i + 1]) * 0.5,
                    (axes[1][j] + axes[1][j + 1]) * 0.5,
                    (axes[2][k] + axes[2][k + 1]) * 0.5,
                ]])
                if not bool(inside_robust(center, vertices, faces)[0]):
                    continue
                cube = np.asarray([
                    index(i, j, k), index(i + 1, j, k), index(i + 1, j + 1, k), index(i, j + 1, k),
                    index(i, j, k + 1), index(i + 1, j, k + 1), index(i + 1, j + 1, k + 1), index(i, j + 1, k + 1),
                ])
                cells.append(cube[_CUBE_TETS])
    if not cells:
        return None
    tets = np.concatenate(cells, axis=0)
    tet_points = points[tets]
    signed = np.einsum(
        "ij,ij->i",
        np.cross(tet_points[:, 1] - tet_points[:, 0], tet_points[:, 2] - tet_points[:, 0]),
        tet_points[:, 3] - tet_points[:, 0],
    )
    flip = signed < 0.0
    if bool(flip.any()):
        first = tets[flip, 0].copy()
        tets[flip, 0] = tets[flip, 1]
        tets[flip, 1] = first
    return points, tets
