"""Default-off, exact-predicate bounded Tet 1-to-4 candidate generation."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Any

import numpy as np

from core.utils.native_extensions import import_native_extension


@dataclass(frozen=True, slots=True)
class BoundedSteinerCandidate:
    """One immutable candidate; callers must audit before applying/publishing."""

    points: np.ndarray
    tets: np.ndarray
    parent_tet: int
    barycentric_weights: tuple[int, int, int, int]


def _exact_orientation_signs(points: np.ndarray, tets: np.ndarray) -> np.ndarray:
    predicates: Any = import_native_extension("native_tet_predicates")
    rows = points[tets]
    signs = np.asarray(predicates.orient3d_signs(np.ascontiguousarray(rows)), dtype=np.int8)
    if signs.shape != (len(tets),):
        raise ValueError("native exact predicate returned an invalid sign vector")
    return signs


def enumerate_bounded_steiner_1to4(
    points: np.ndarray,
    tets: np.ndarray,
    target_tet_ids: list[int] | tuple[int, ...],
    *,
    denominator: int = 8,
    max_candidates: int = 4,
) -> tuple[BoundedSteinerCandidate, ...]:
    """Enumerate deterministic interior 1-to-4 splits with exact signs.

    The input arrays are never modified.  Candidates preserve every original
    parent face as one child face and add only the three interior faces joined
    to the new point.  No candidate is a release decision; the caller must run
    full topology/source/provenance/quality read-back in a private stage.
    """
    point_array = np.ascontiguousarray(np.asarray(points, dtype=np.float64))
    tet_array = np.ascontiguousarray(np.asarray(tets, dtype=np.int64))
    if point_array.ndim != 2 or point_array.shape[1:] != (3,):
        raise ValueError("points must have shape (N, 3)")
    if tet_array.ndim != 2 or tet_array.shape[1:] != (4,):
        raise ValueError("tets must have shape (M, 4)")
    if denominator < 4 or max_candidates < 0:
        raise ValueError("denominator must be >= 4 and max_candidates must be nonnegative")
    if not np.isfinite(point_array).all():
        raise ValueError("points must be finite")
    if len(tet_array) == 0:
        return ()

    target_ids = tuple(sorted(set(int(index) for index in target_tet_ids)))
    if any(index < 0 or index >= len(tet_array) for index in target_ids):
        raise IndexError("target tet id is outside the connectivity array")
    original_signs = _exact_orientation_signs(point_array, tet_array)
    candidates: list[BoundedSteinerCandidate] = []

    weights = tuple(
        weight
        for weight in product(range(1, denominator - 2), repeat=4)
        if sum(weight) == denominator
    )
    for parent_id in target_ids:
        parent = tet_array[parent_id]
        parent_sign = int(original_signs[parent_id])
        if parent_sign == 0:
            continue
        for barycentric in weights:
            if len(candidates) >= max_candidates:
                return tuple(candidates)
            new_point = np.asarray(
                sum(
                    (barycentric[local] * point_array[int(parent[local])] for local in range(4)),
                    np.zeros(3, dtype=np.float64),
                )
                / float(denominator),
                dtype=np.float64,
            )
            candidate_points = np.vstack((point_array, new_point))
            center_id = len(point_array)
            children = np.asarray(
                [
                    [center_id, int(parent[1]), int(parent[2]), int(parent[3])],
                    [int(parent[0]), center_id, int(parent[2]), int(parent[3])],
                    [int(parent[0]), int(parent[1]), center_id, int(parent[3])],
                    [int(parent[0]), int(parent[1]), int(parent[2]), center_id],
                ],
                dtype=np.int64,
            )
            child_signs = _exact_orientation_signs(candidate_points, children)
            if np.any(child_signs != parent_sign):
                continue
            candidate_tets = np.concatenate(
                (tet_array[:parent_id], children, tet_array[parent_id + 1 :]), axis=0
            )
            candidates.append(
                BoundedSteinerCandidate(
                    points=candidate_points,
                    tets=np.ascontiguousarray(candidate_tets),
                    parent_tet=parent_id,
                    barycentric_weights=tuple(int(value) for value in barycentric),
                )
            )
    return tuple(candidates)


__all__ = ["BoundedSteinerCandidate", "enumerate_bounded_steiner_1to4"]
