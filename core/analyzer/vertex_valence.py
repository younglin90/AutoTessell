"""CC2 / beta2759 — surface vertex valence (1-ring degree).

각 vertex 가 몇 face 에 incident, 몇 edge 에 incident.
- 정상 closed manifold: vertex degree = 4-8 in well-meshed surface.
- 매우 큰 valence (≥ 30) = singular vertex.

remesh / smoothing 후보 입력.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass
class VertexValenceResult:
    n_vertices: int = 0
    n_used: int = 0
    face_valence_min: int = 0
    face_valence_max: int = 0
    face_valence_mean: float = 0.0
    edge_valence_min: int = 0
    edge_valence_max: int = 0
    edge_valence_mean: float = 0.0
    n_high_face_valence: int = 0   # >= 12.
    n_isolated: int = 0
    elapsed_s: float = 0.0


def surface_vertex_valence(
    F: NDArray[np.int64],
    n_vertices: int | None = None,
) -> tuple[NDArray[np.int64], NDArray[np.int64], VertexValenceResult]:
    """vertex 별 face / edge incident count.

    Args:
        F: (M, 3) tri indices.
        n_vertices: optional. None → F.max()+1.

    Returns:
        (face_valence (n,), edge_valence (n,), VertexValenceResult).
    """
    import time
    t0 = time.perf_counter()

    F = np.asarray(F, dtype=np.int64)
    n_f = int(F.shape[0])

    if n_f == 0:
        n_v = int(n_vertices) if n_vertices is not None else 0
        return (
            np.zeros(n_v, dtype=np.int64),
            np.zeros(n_v, dtype=np.int64),
            VertexValenceResult(n_vertices=n_v,
                                elapsed_s=time.perf_counter() - t0),
        )

    n_v = int(n_vertices) if n_vertices is not None else int(F.max() + 1)

    # face valence: bincount of vertex appearance in F.
    face_val = np.bincount(F.reshape(-1), minlength=n_v).astype(np.int64)

    # edge valence: count of unique edges incident to each vertex.
    edges = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], axis=0)
    edges_s = np.sort(edges, axis=1)
    unique_e = np.unique(edges_s, axis=0)
    edge_val = np.zeros(n_v, dtype=np.int64)
    for ev in unique_e:
        edge_val[int(ev[0])] += 1
        edge_val[int(ev[1])] += 1

    used_mask = face_val > 0
    n_used = int(used_mask.sum())
    n_isolated = n_v - n_used

    if n_used == 0:
        return face_val, edge_val, VertexValenceResult(
            n_vertices=n_v, n_isolated=n_isolated,
            elapsed_s=time.perf_counter() - t0,
        )

    fv_used = face_val[used_mask]
    ev_used = edge_val[used_mask]

    return face_val, edge_val, VertexValenceResult(
        n_vertices=n_v,
        n_used=n_used,
        face_valence_min=int(fv_used.min()),
        face_valence_max=int(fv_used.max()),
        face_valence_mean=float(fv_used.mean()),
        edge_valence_min=int(ev_used.min()),
        edge_valence_max=int(ev_used.max()),
        edge_valence_mean=float(ev_used.mean()),
        n_high_face_valence=int((fv_used >= 12).sum()),
        n_isolated=n_isolated,
        elapsed_s=time.perf_counter() - t0,
    )
