"""Small report-only geometry fixtures for sparse diagnostics.

No generated triangles are routed into native-hex meshing.  They are only
canonical, deterministic input for closure and provenance tests.
"""

from __future__ import annotations

import numpy as np


def axis_aligned_box_triangles(lower: np.ndarray, upper: np.ndarray) -> np.ndarray:
    """Return twelve outward-oriented triangles for a non-degenerate box."""
    lo = np.asarray(lower, dtype=np.float64)
    hi = np.asarray(upper, dtype=np.float64)
    if lo.shape != (3,) or hi.shape != (3,) or not np.isfinite(lo).all() or not np.isfinite(hi).all():
        raise ValueError("box bounds must be finite three-vectors")
    if np.any(hi <= lo):
        raise ValueError("box upper bound must exceed lower bound on every axis")
    x0, y0, z0 = lo
    x1, y1, z1 = hi
    vertices = np.asarray(
        (
            (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
            (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1),
        ),
        dtype=np.float64,
    )
    # Each winding has an outward normal.  Face order is fixed for reproducibility.
    faces = np.asarray(
        (
            (0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7),
            (0, 1, 5), (0, 5, 4), (3, 7, 6), (3, 6, 2),
            (0, 4, 7), (0, 7, 3), (1, 2, 6), (1, 6, 5),
        ),
        dtype=np.int64,
    )
    return vertices[faces]
