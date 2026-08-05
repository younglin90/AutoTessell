"""Native tet QOPT0 helpers.

This module is intentionally infrastructure-only: it extracts deterministic
local cavities and compares local quality vectors.  Later topology/smoothing
operations should use this shared accept/rollback gate.
"""
from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import NDArray

from core.utils.native_extensions import import_native_extension

_NATIVE_QOPT: Any | None = None
_NATIVE_QOPT_LOADED = False


def _load_native_tet_qopt() -> Any | None:
    """Load optional pybind11 QOPT kernels."""
    global _NATIVE_QOPT, _NATIVE_QOPT_LOADED
    if _NATIVE_QOPT_LOADED:
        return _NATIVE_QOPT
    _NATIVE_QOPT_LOADED = True
    try:
        _NATIVE_QOPT = import_native_extension("native_tet_qopt")
    except Exception:
        _NATIVE_QOPT = None
    return _NATIVE_QOPT


def _tet_shape_quality(points: NDArray[np.float64], tets: NDArray[np.int64]) -> NDArray[np.float64]:
    if tets.size == 0:
        return np.zeros(0, dtype=np.float64)
    v = points[tets]
    edges = np.stack(
        [
            v[:, 1] - v[:, 0],
            v[:, 2] - v[:, 0],
            v[:, 3] - v[:, 0],
            v[:, 2] - v[:, 1],
            v[:, 3] - v[:, 1],
            v[:, 3] - v[:, 2],
        ],
        axis=1,
    )
    longest = np.linalg.norm(edges, axis=2).max(axis=1)
    volume6 = np.abs(np.einsum("ij,ij->i", edges[:, 0], np.cross(edges[:, 1], edges[:, 2])))
    quality = np.zeros(tets.shape[0], dtype=np.float64)
    mask = longest > 1e-30
    quality[mask] = 8.48 * (volume6[mask] / 6.0) / (longest[mask] ** 3)
    return quality


def local_cavity_quality_vectors(
    points: NDArray[np.float64],
    tets: NDArray[np.int64],
    seed_tets: NDArray[np.int64],
    *,
    max_ring: int = 1,
) -> tuple[NDArray[np.int64], NDArray[np.int64], NDArray[np.float64], dict[str, int]]:
    """Return local cavity tet ids and sorted quality vectors for each seed tet."""
    points = np.asarray(points, dtype=np.float64)
    tets = np.asarray(tets, dtype=np.int64)
    seed_tets = np.asarray(seed_tets, dtype=np.int64)
    native = _load_native_tet_qopt()
    if native is not None:
        offsets, cavity_tets, quality, stats = native.local_cavity_quality_vectors(
            points, tets, seed_tets, int(max_ring),
        )
        return (
            np.asarray(offsets, dtype=np.int64),
            np.asarray(cavity_tets, dtype=np.int64),
            np.asarray(quality, dtype=np.float64),
            {str(k): int(v) for k, v in dict(stats).items()},
        )

    if points.ndim != 2 or points.shape[1] != 3:
        raise ValueError("local_cavity_quality_vectors expects points shaped (N, 3)")
    if tets.ndim != 2 or tets.shape[1] != 4:
        raise ValueError("local_cavity_quality_vectors expects tets shaped (M, 4)")
    if seed_tets.ndim != 1:
        raise ValueError("local_cavity_quality_vectors expects seed_tets shaped (K,)")
    if max_ring not in (0, 1):
        raise ValueError("max_ring must be 0 or 1")

    vertex_to_tets: dict[int, list[int]] = {}
    for ti, tet in enumerate(tets):
        for vertex in tet:
            vertex_to_tets.setdefault(int(vertex), []).append(ti)

    offsets = [0]
    flat_tets: list[int] = []
    flat_quality: list[float] = []
    max_cavity = 0
    for seed in seed_tets.tolist():
        if seed < 0 or seed >= len(tets):
            raise ValueError("seed_tets contains out-of-range index")
        if max_ring == 0:
            cavity = [int(seed)]
        else:
            seen: set[int] = set()
            for vertex in tets[int(seed)]:
                seen.update(vertex_to_tets.get(int(vertex), []))
            cavity = sorted(seen)
        qualities = np.sort(_tet_shape_quality(points, tets[np.asarray(cavity, dtype=np.int64)]))
        flat_tets.extend(cavity)
        flat_quality.extend(float(value) for value in qualities)
        offsets.append(len(flat_tets))
        max_cavity = max(max_cavity, len(cavity))

    return (
        np.asarray(offsets, dtype=np.int64),
        np.asarray(flat_tets, dtype=np.int64),
        np.asarray(flat_quality, dtype=np.float64),
        {"n_cavities": int(len(seed_tets)), "max_cavity_size": int(max_cavity), "max_ring": int(max_ring)},
    )


def compare_quality_vectors(
    old_quality: NDArray[np.float64],
    new_quality: NDArray[np.float64],
    *,
    eps: float = 0.0,
) -> int:
    """Lexicographic local quality-vector compare. Positive means new is better."""
    native = _load_native_tet_qopt()
    old_q = np.asarray(old_quality, dtype=np.float64)
    new_q = np.asarray(new_quality, dtype=np.float64)
    if native is not None:
        return int(native.compare_quality_vectors(old_q, new_q, float(eps)))
    if old_q.ndim != 1 or new_q.ndim != 1:
        raise ValueError("compare_quality_vectors expects 1D arrays")
    if eps < 0.0:
        raise ValueError("eps must be non-negative")
    old_sorted = np.sort(old_q)
    new_sorted = np.sort(new_q)
    for old_value, new_value in zip(old_sorted, new_sorted, strict=False):
        if new_value + eps < old_value:
            return -1
        if new_value > old_value + eps:
            return 1
    if len(new_sorted) < len(old_sorted):
        return 1
    if len(new_sorted) > len(old_sorted):
        return -1
    return 0


def quality_vector_accepts(
    old_quality: NDArray[np.float64],
    new_quality: NDArray[np.float64],
    *,
    eps: float = 0.0,
) -> bool:
    return compare_quality_vectors(old_quality, new_quality, eps=eps) > 0


def compare_quality_tuples(
    old_tuple: NDArray[np.float64],
    new_tuple: NDArray[np.float64],
    *,
    eps: float = 0.0,
) -> int:
    """Compare a fixed-schema, higher-is-better quality tuple.

    Each field must already use the same direction (for example, negate
    skewness/non-orthogonality/aspect when composing a higher-is-better
    tuple). The first field that changes decides the result. This is the
    native acceptance contract for topology/source/BL/quality gates; count
    remains a later field and cannot override an earlier failure.
    """
    native = _load_native_tet_qopt()
    old_q = np.asarray(old_tuple, dtype=np.float64)
    new_q = np.asarray(new_tuple, dtype=np.float64)
    if native is not None and hasattr(native, "compare_quality_tuples"):
        return int(native.compare_quality_tuples(old_q, new_q, float(eps)))
    if old_q.ndim != 1 or new_q.ndim != 1:
        raise ValueError("compare_quality_tuples expects 1D arrays")
    if old_q.shape != new_q.shape:
        raise ValueError("quality tuples must have the same schema length")
    if eps < 0.0:
        raise ValueError("eps must be non-negative")
    if not np.all(np.isfinite(old_q)) or not np.all(np.isfinite(new_q)):
        raise ValueError("quality tuple contains non-finite value")
    for old_value, new_value in zip(old_q.tolist(), new_q.tolist(), strict=True):
        if new_value + eps < old_value:
            return -1
        if new_value > old_value + eps:
            return 1
    return 0


def compose_quality_gate_tuple(
    *,
    inverted_count: int,
    duplicate_tet_count: int,
    nonmanifold_face_count: int,
    same_side_face_count: int,
    max_skewness: float,
    max_non_orthogonality: float,
    max_aspect: float,
    min_mean_ratio: float,
) -> NDArray[np.float64]:
    """Compose the fixed higher-is-better native quality-gate schema."""
    counts = (inverted_count, duplicate_tet_count, nonmanifold_face_count, same_side_face_count)
    if any(int(value) < 0 for value in counts):
        raise ValueError("quality gate counts must be non-negative")
    metrics = (max_skewness, max_non_orthogonality, max_aspect, min_mean_ratio)
    if not np.all(np.isfinite(np.asarray(metrics, dtype=np.float64))) or any(float(value) < 0.0 for value in metrics):
        raise ValueError("quality gate metrics must be finite and non-negative")
    native = _load_native_tet_qopt()
    kernel = getattr(native, "compose_quality_gate_tuple", None) if native is not None else None
    if kernel is not None:
        return np.asarray(kernel(*counts, *metrics), dtype=np.float64)
    return np.asarray(
        [-float(inverted_count), -float(duplicate_tet_count), -float(nonmanifold_face_count),
         -float(same_side_face_count), -float(max_skewness),
         -float(max_non_orthogonality), -float(max_aspect), float(min_mean_ratio)],
        dtype=np.float64,
    )
def tet_quality_oracle(
    points: NDArray[np.float64],
    tets: NDArray[np.int64],
    *,
    volume_tolerance_scale: float = 1e-12,
) -> dict[str, object]:
    """Return the native C++ Tet topology/geometry oracle evidence.

    The strict route fails closed when the C++ oracle is unavailable; this
    prevents a Python-only approximation from being mistaken for release
    evidence.
    """
    native = _load_native_tet_qopt()
    kernel = getattr(native, "tet_quality_oracle", None) if native is not None else None
    if kernel is None:
        raise RuntimeError("native_tet_qopt quality oracle unavailable")
    result = kernel(
        np.asarray(points, dtype=np.float64),
        np.asarray(tets, dtype=np.int64),
        float(volume_tolerance_scale),
    )
    return dict(result)
def quality_tuple_accepts(
    old_tuple: NDArray[np.float64],
    new_tuple: NDArray[np.float64],
    *,
    eps: float = 0.0,
) -> bool:
    """Return true only when the fixed-schema tuple strictly improves."""
    return compare_quality_tuples(old_tuple, new_tuple, eps=eps) > 0


def _signed_volume6(points: NDArray[np.float64], tets: NDArray[np.int64]) -> NDArray[np.float64]:
    if tets.size == 0:
        return np.zeros(0, dtype=np.float64)
    v = points[tets]
    return np.einsum(
        "ij,ij->i",
        v[:, 1] - v[:, 0],
        np.cross(v[:, 2] - v[:, 0], v[:, 3] - v[:, 0]),
    )


def build_vertex_to_tets_csr(
    tets: NDArray[np.int64],
    n_points: int,
) -> tuple[NDArray[np.int64], NDArray[np.int64]]:
    """Build vertex -> incident tet CSR once for repeated local QOPT gates."""
    tets = np.asarray(tets, dtype=np.int64)
    if tets.size == 0:
        return np.zeros(int(n_points) + 1, dtype=np.int64), np.zeros(0, dtype=np.int64)
    flat_vertices = tets.reshape(-1)
    flat_tets = np.repeat(np.arange(tets.shape[0], dtype=np.int64), 4)
    order = np.argsort(flat_vertices, kind="stable")
    sorted_vertices = flat_vertices[order]
    incident_tets = flat_tets[order]
    counts = np.bincount(sorted_vertices, minlength=int(n_points))
    offsets = np.concatenate(([0], np.cumsum(counts))).astype(np.int64)
    return offsets, incident_tets.astype(np.int64, copy=False)


def apply_guarded_vertex_moves(
    points: NDArray[np.float64],
    tets: NDArray[np.int64],
    vertices: NDArray[np.int64],
    targets: NDArray[np.float64],
    *,
    incident_offsets: NDArray[np.int64] | None = None,
    incident_tets: NDArray[np.int64] | None = None,
    eps: float = 1e-15,
) -> tuple[NDArray[np.float64], dict[str, float | int]]:
    """Sequentially apply vertex moves if local-star volume and quality guards pass."""
    points = np.asarray(points, dtype=np.float64)
    tets = np.asarray(tets, dtype=np.int64)
    vertices = np.asarray(vertices, dtype=np.int64)
    targets = np.asarray(targets, dtype=np.float64)
    native = _load_native_tet_qopt()
    if native is not None:
        if incident_offsets is not None and incident_tets is not None:
            kernel = getattr(native, "apply_guarded_vertex_moves_csr", None)
            if kernel is not None:
                out, stats = kernel(
                    points, tets,
                    np.asarray(incident_offsets, dtype=np.int64),
                    np.asarray(incident_tets, dtype=np.int64),
                    vertices, targets, float(eps),
                )
                return np.asarray(out, dtype=np.float64), dict(stats)
        out, stats = native.apply_guarded_vertex_moves(points, tets, vertices, targets, float(eps))
        return np.asarray(out, dtype=np.float64), dict(stats)

    if points.ndim != 2 or points.shape[1] != 3:
        raise ValueError("apply_guarded_vertex_moves expects points shaped (N, 3)")
    if tets.ndim != 2 or tets.shape[1] != 4:
        raise ValueError("apply_guarded_vertex_moves expects tets shaped (M, 4)")
    if vertices.ndim != 1:
        raise ValueError("apply_guarded_vertex_moves expects vertices shaped (K,)")
    if targets.shape != (vertices.shape[0], 3):
        raise ValueError("apply_guarded_vertex_moves expects targets shaped (K, 3)")

    if incident_offsets is None or incident_tets is None:
        incident_offsets, incident_tets = build_vertex_to_tets_csr(tets, points.shape[0])
    incident_offsets = np.asarray(incident_offsets, dtype=np.int64)
    incident_tets = np.asarray(incident_tets, dtype=np.int64)

    out = points.copy()
    attempted = accepted = rejected_volume = rejected_quality = 0
    max_disp = 0.0
    for vertex, target in zip(vertices.tolist(), targets, strict=True):
        start = int(incident_offsets[int(vertex)])
        end = int(incident_offsets[int(vertex) + 1])
        if start == end:
            continue
        attempted += 1
        incident_arr = incident_tets[start:end]
        local_tets = tets[incident_arr]
        old_vol = _signed_volume6(out, local_tets)
        old_quality = _tet_shape_quality(out, local_tets)
        old_point = out[int(vertex)].copy()
        out[int(vertex)] = target
        new_vol = _signed_volume6(out, local_tets)
        if np.any(np.abs(new_vol) <= 1e-20) or np.any(np.signbit(old_vol) != np.signbit(new_vol)):
            out[int(vertex)] = old_point
            rejected_volume += 1
            continue
        new_quality = _tet_shape_quality(out, local_tets)
        if compare_quality_vectors(old_quality, new_quality, eps=eps) < 0:
            out[int(vertex)] = old_point
            rejected_quality += 1
            continue
        max_disp = max(max_disp, float(np.linalg.norm(target - old_point)))
        accepted += 1

    return out, {
        "attempted": int(attempted),
        "accepted": int(accepted),
        "rejected_volume": int(rejected_volume),
        "rejected_quality": int(rejected_quality),
        "max_displacement": float(max_disp),
    }


def smooth_interior_guarded_native(
    points: NDArray[np.float64],
    tets: NDArray[np.int64],
    locked_vertex_ids: NDArray[np.int64],
    *,
    n_iter: int = 2,
    relax: float = 0.5,
    eps: float = 1e-15,
    use_worst_cell_queue: bool = False,
) -> tuple[NDArray[np.float64], dict[str, float | int]] | None:
    """Use fused native guarded Laplacian smoothing when available."""
    native = _load_native_tet_qopt()
    queue_kernel = getattr(native, "smooth_interior_worst_cell_guarded", None) if native is not None else None
    if use_worst_cell_queue and queue_kernel is not None:
        kernel = queue_kernel
    else:
        kernel = getattr(native, "smooth_interior_guarded", None) if native is not None else None
    if kernel is None:
        return None
    out, stats = kernel(
        np.asarray(points, dtype=np.float64),
        np.asarray(tets, dtype=np.int64),
        np.asarray(locked_vertex_ids, dtype=np.int64),
        int(n_iter),
        float(relax),
        float(eps),
    )
    return np.asarray(out, dtype=np.float64), dict(stats)
