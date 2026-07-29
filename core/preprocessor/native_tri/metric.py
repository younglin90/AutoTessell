"""Validated metric primitives for the native-tri sizing lane.

This module provides the deterministic surface/BL metric representation and
conservative intersection operation consumed by the optional metric lane in
``operator_loop``.  The default scalar path remains unchanged, and normal-layer
point placement is still outside this module.

For an SPD metric ``M``, the unit ball is ``x.T @ M @ x <= 1``.  The
intersection below returns an SPD matrix that is greater than or equal to both
inputs in the Loewner order, so it never relaxes either requested resolution.
The generalized eigen construction is idempotent when the two inputs agree
and is invariant under rigid coordinate rotations.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


FloatArray = NDArray[np.float64]


@dataclass(frozen=True)
class MetricFieldReport:
    """Finite/SPD audit for a batch of metric tensors."""

    n_metrics: int
    min_eigenvalue: float
    max_eigenvalue: float
    max_condition: float
    n_invalid: int

    @property
    def valid(self) -> bool:
        return self.n_invalid == 0


@dataclass(frozen=True)
class BLHandoffReport:
    """Report-only separation of tangent and wall-normal metric scales."""

    n_vertices: int
    n_feature_rejected: int
    n_invalid: int
    normal_length_min: float
    normal_length_max: float
    tangent_length_min: float
    tangent_length_max: float

    @property
    def valid(self) -> bool:
        return self.n_invalid == 0


def _as_metric_batch(metrics: np.ndarray) -> FloatArray:
    values = np.asarray(metrics, dtype=np.float64)
    if values.ndim == 2 and values.shape == (3, 3):
        values = values[None, ...]
    if values.ndim != 3 or values.shape[1:] != (3, 3):
        raise ValueError("metrics must have shape (3, 3) or (n, 3, 3)")
    if not np.isfinite(values).all():
        raise ValueError("metrics must contain finite values")
    return 0.5 * (values + np.swapaxes(values, 1, 2))


def audit_spd_metrics(
    metrics: np.ndarray,
    *,
    min_eigenvalue: float = 1e-12,
    max_condition: float = 1e8,
) -> MetricFieldReport:
    """Audit, but do not repair, a scalar or batched SPD metric field."""
    values = _as_metric_batch(metrics)
    if min_eigenvalue <= 0.0 or not np.isfinite(min_eigenvalue):
        raise ValueError("min_eigenvalue must be finite and positive")
    if max_condition < 1.0 or not np.isfinite(max_condition):
        raise ValueError("max_condition must be finite and >= 1")
    eigenvalues = np.linalg.eigvalsh(values)
    smallest = eigenvalues[:, 0]
    largest = eigenvalues[:, -1]
    condition = np.divide(
        largest,
        smallest,
        out=np.full(len(values), np.inf),
        where=smallest > 0.0,
    )
    invalid = (
        ~np.isfinite(eigenvalues).all(axis=1)
        | (smallest < min_eigenvalue)
        | (condition > max_condition)
    )
    return MetricFieldReport(
        n_metrics=len(values),
        min_eigenvalue=float(np.min(smallest)) if len(values) else 0.0,
        max_eigenvalue=float(np.max(largest)) if len(values) else 0.0,
        max_condition=float(np.max(condition)) if len(values) else 0.0,
        n_invalid=int(invalid.sum()),
    )


def intersect_spd_metrics(
    first: np.ndarray,
    second: np.ndarray,
) -> FloatArray:
    """Return a conservative Loewner upper bound of two SPD metric fields.

    For each pair, diagonalize
    ``C = first^(-1/2) @ second @ first^(-1/2)`` and replace each generalized
    eigenvalue by ``max(1, lambda)``.  The result dominates both operands in
    the quadratic-form order.  Inputs may be one tensor or equally sized
    batches; a single tensor broadcasts across a batch.
    """
    left = _as_metric_batch(first)
    right = _as_metric_batch(second)
    if len(left) == 1 and len(right) > 1:
        left = np.broadcast_to(left, right.shape)
    elif len(right) == 1 and len(left) > 1:
        right = np.broadcast_to(right, left.shape)
    elif left.shape != right.shape:
        raise ValueError("metric batches must have equal length or be scalar")

    n = len(left)
    result = np.empty_like(left)
    for index in range(n):
        eigen_left, basis_left = np.linalg.eigh(left[index])
        if np.any(eigen_left <= 0.0) or not np.isfinite(eigen_left).all():
            raise ValueError("first metric is not SPD")
        sqrt_left = (basis_left * np.sqrt(eigen_left)) @ basis_left.T
        inv_sqrt_left = (basis_left * (1.0 / np.sqrt(eigen_left))) @ basis_left.T
        normalized = inv_sqrt_left @ right[index] @ inv_sqrt_left
        eigen_relative, basis_relative = np.linalg.eigh(
            0.5 * (normalized + normalized.T),
        )
        if np.any(eigen_relative <= 0.0) or not np.isfinite(eigen_relative).all():
            raise ValueError("second metric is not SPD")
        clipped = np.maximum(eigen_relative, 1.0)
        result[index] = sqrt_left @ (
            (basis_relative * clipped) @ basis_relative.T
        ) @ sqrt_left
    return 0.5 * (result + np.swapaxes(result, 1, 2))


def make_bl_metric(
    normals: np.ndarray,
    tangential_length: float | np.ndarray,
    *,
    normal_length: float | np.ndarray | None = None,
) -> FloatArray:
    """Build an SPD proxy for a wall-layer source metric.

    Surface edges only see the tangent block, while the normal eigenvalue
    records the requested layer-normal scale for the later BL handoff.
    ``normal_length`` defaults to the tangential scale and is never silently
    clipped or repaired.
    """
    unit_normals = np.asarray(normals, dtype=np.float64)
    if unit_normals.ndim != 2 or unit_normals.shape[1] != 3:
        raise ValueError("normals must have shape (n, 3)")
    lengths_t = np.broadcast_to(
        np.asarray(tangential_length, dtype=np.float64), (len(unit_normals),),
    )
    lengths_n = lengths_t if normal_length is None else np.broadcast_to(
        np.asarray(normal_length, dtype=np.float64), (len(unit_normals),),
    )
    norms = np.linalg.norm(unit_normals, axis=1)
    if (
        not np.isfinite(unit_normals).all()
        or np.any(norms <= 1e-14)
        or np.any(lengths_t <= 0.0)
        or np.any(lengths_n <= 0.0)
        or not np.isfinite(lengths_t).all()
        or not np.isfinite(lengths_n).all()
    ):
        raise ValueError("BL metric inputs must be finite and positive")
    unit_normals = unit_normals / norms[:, None]
    tangent_projector = (
        np.eye(3)[None, :, :] - unit_normals[:, :, None] * unit_normals[:, None, :]
    )
    normal_projector = unit_normals[:, :, None] * unit_normals[:, None, :]
    metrics = tangent_projector / lengths_t[:, None, None] ** 2
    metrics += normal_projector / lengths_n[:, None, None] ** 2
    return 0.5 * (metrics + np.swapaxes(metrics, 1, 2))


def audit_bl_handoff(
    metrics: np.ndarray,
    normals: np.ndarray,
    *,
    feature_vertices: np.ndarray | None = None,
) -> BLHandoffReport:
    """Audit tangent/normal scales without moving points or changing metrics.

    The returned lengths are the reciprocal square roots of the metric
    strengths. Feature vertices are explicitly excluded from the tangent
    census because a single tangent plane is not defined there.
    """
    field = _as_metric_batch(metrics)
    unit_normals = np.asarray(normals, dtype=np.float64)
    if unit_normals.ndim != 2 or unit_normals.shape != (len(field), 3):
        raise ValueError("normals must have shape (n, 3) matching metrics")
    normal_lengths = np.linalg.norm(unit_normals, axis=1)
    if np.any(normal_lengths <= 1e-14) or not np.isfinite(unit_normals).all():
        raise ValueError("normals must be finite and nonzero")
    unit_normals = unit_normals / normal_lengths[:, None]
    feature_mask = np.zeros(len(field), dtype=bool)
    if feature_vertices is not None:
        feature_mask = np.asarray(feature_vertices, dtype=bool)
        if feature_mask.shape != (len(field),):
            raise ValueError("feature_vertices must have shape (n,)")

    normal_strength = np.einsum("ni,nij,nj->n", unit_normals, field, unit_normals)
    projectors = (
        np.eye(3)[None, :, :]
        - unit_normals[:, :, None] * unit_normals[:, None, :]
    )
    tangent_strength = np.linalg.eigvalsh(projectors @ field @ projectors)[:, -2:]
    usable = ~feature_mask
    valid = (
        usable
        & np.isfinite(normal_strength)
        & (normal_strength > 0.0)
        & np.isfinite(tangent_strength).all(axis=1)
        & (tangent_strength > 0.0).all(axis=1)
    )
    normal_scale = np.zeros(len(field), dtype=np.float64)
    tangent_scale = np.zeros((len(field), 2), dtype=np.float64)
    normal_scale[valid] = 1.0 / np.sqrt(normal_strength[valid])
    tangent_scale[valid] = 1.0 / np.sqrt(tangent_strength[valid])
    return BLHandoffReport(
        n_vertices=len(field),
        n_feature_rejected=int(feature_mask.sum()),
        n_invalid=int((usable & ~valid).sum()),
        normal_length_min=float(np.min(normal_scale[valid])) if np.any(valid) else 0.0,
        normal_length_max=float(np.max(normal_scale[valid])) if np.any(valid) else 0.0,
        tangent_length_min=float(np.min(tangent_scale[valid])) if np.any(valid) else 0.0,
        tangent_length_max=float(np.max(tangent_scale[valid])) if np.any(valid) else 0.0,
    )


def metric_edge_lengths(
    vertices: np.ndarray,
    edges: np.ndarray,
    metrics: np.ndarray,
) -> FloatArray:
    """Evaluate edge lengths with the conservative endpoint intersection."""
    points = np.asarray(vertices, dtype=np.float64)
    edge_rows = np.asarray(edges, dtype=np.int64)
    field = _as_metric_batch(metrics)
    if points.ndim != 2 or points.shape[1] != 3:
        raise ValueError("vertices must have shape (n, 3)")
    if edge_rows.ndim != 2 or edge_rows.shape[1] != 2:
        raise ValueError("edges must have shape (m, 2)")
    if edge_rows.size and (
        edge_rows.min() < 0 or edge_rows.max() >= len(points)
        or edge_rows.max() >= len(field)
    ):
        raise ValueError("edge index is outside the metric field")
    if len(edge_rows) == 0:
        return np.zeros(0, dtype=np.float64)
    edge_metrics = intersect_spd_metrics(field[edge_rows[:, 0]], field[edge_rows[:, 1]])
    delta = points[edge_rows[:, 1]] - points[edge_rows[:, 0]]
    squared = np.einsum("ni,nij,nj->n", delta, edge_metrics, delta)
    return np.sqrt(np.maximum(squared, 0.0))


def vertex_normal_spread_deg(
    vertices: np.ndarray,
    faces: np.ndarray,
) -> FloatArray:
    """Return the maximum incident-face normal angle at every vertex.

    A large value means the vertex does not have one reliable tangent plane.
    The function reports that ambiguity; it never smooths or replaces the
    input normals.
    """
    points = np.asarray(vertices, dtype=np.float64)
    triangles = np.asarray(faces, dtype=np.int64)
    if points.ndim != 2 or points.shape[1] != 3:
        raise ValueError("vertices must have shape (n, 3)")
    if triangles.ndim != 2 or triangles.shape[1] != 3:
        raise ValueError("faces must have shape (m, 3)")
    face_normals = np.zeros((len(triangles), 3), dtype=np.float64)
    for index, face in enumerate(triangles):
        cross = np.cross(
            points[int(face[1])] - points[int(face[0])],
            points[int(face[2])] - points[int(face[0])],
        )
        length = float(np.linalg.norm(cross))
        if length > 1e-14 and np.isfinite(length):
            face_normals[index] = cross / length
    incident: list[list[np.ndarray]] = [[] for _ in range(len(points))]
    for face_index, face in enumerate(triangles):
        normal = face_normals[face_index]
        if np.linalg.norm(normal) <= 0.0:
            continue
        for vertex in face:
            incident[int(vertex)].append(normal)
    spread = np.zeros(len(points), dtype=np.float64)
    for vertex, normals in enumerate(incident):
        if len(normals) < 2:
            continue
        normal_array = np.asarray(normals)
        min_dot = float(np.min(normal_array @ normal_array.T))
        spread[vertex] = np.degrees(np.arccos(np.clip(min_dot, -1.0, 1.0)))
    return spread


def tangent_metric_edge_lengths(
    vertices: np.ndarray,
    edges: np.ndarray,
    metrics: np.ndarray,
    normals: np.ndarray,
    *,
    max_normal_angle_deg: float | None = None,
    feature_vertices: np.ndarray | None = None,
) -> FloatArray:
    """Evaluate only the tangent component of an endpoint metric field.

    The normal eigenvalue in a BL metric is deliberately removed by projecting
    onto the normalized average endpoint tangent plane.  If a caller supplies
    ``max_normal_angle_deg``, edges whose endpoint normals exceed that angle
    are rejected explicitly instead of silently inventing a tangent plane.
    """
    points = np.asarray(vertices, dtype=np.float64)
    edge_rows = np.asarray(edges, dtype=np.int64)
    unit_normals = np.asarray(normals, dtype=np.float64)
    field = _as_metric_batch(metrics)
    if points.ndim != 2 or points.shape[1] != 3:
        raise ValueError("vertices must have shape (n, 3)")
    if unit_normals.shape != points.shape:
        raise ValueError("normals must have the same shape as vertices")
    if edge_rows.ndim != 2 or edge_rows.shape[1] != 2:
        raise ValueError("edges must have shape (m, 2)")
    if edge_rows.size and (
        edge_rows.min() < 0
        or edge_rows.max() >= len(points)
        or edge_rows.max() >= len(field)
    ):
        raise ValueError("edge index is outside the metric field")
    if len(edge_rows) == 0:
        return np.zeros(0, dtype=np.float64)
    feature_mask = None
    if feature_vertices is not None:
        feature_mask = np.asarray(feature_vertices, dtype=bool)
        if feature_mask.shape != (len(points),):
            raise ValueError("feature_vertices must have shape (n,)")
        if np.any(feature_mask[edge_rows].any(axis=1)):
            raise ValueError("edge touches a feature vertex without a tangent plane")
    normal_lengths = np.linalg.norm(unit_normals, axis=1)
    if np.any(normal_lengths <= 1e-14) or not np.isfinite(unit_normals).all():
        raise ValueError("normals must be finite and nonzero")
    unit_normals = unit_normals / normal_lengths[:, None]
    left_normals = unit_normals[edge_rows[:, 0]]
    right_normals = unit_normals[edge_rows[:, 1]]
    normal_dot = np.clip(np.einsum("ni,ni->n", left_normals, right_normals), -1.0, 1.0)
    normal_angles = np.degrees(np.arccos(normal_dot))
    if max_normal_angle_deg is not None:
        if max_normal_angle_deg < 0.0 or not np.isfinite(max_normal_angle_deg):
            raise ValueError("max_normal_angle_deg must be finite and non-negative")
        if np.any(normal_angles > max_normal_angle_deg):
            raise ValueError("edge crosses a normal-discontinuous feature")
    common = left_normals + right_normals
    common_length = np.linalg.norm(common, axis=1)
    if np.any(common_length <= 1e-14):
        raise ValueError("endpoint normals do not define a common tangent plane")
    common = common / common_length[:, None]
    projector = (
        np.eye(3)[None, :, :]
        - common[:, :, None] * common[:, None, :]
    )
    edge_metrics = intersect_spd_metrics(
        field[edge_rows[:, 0]], field[edge_rows[:, 1]],
    )
    delta = points[edge_rows[:, 1]] - points[edge_rows[:, 0]]
    tangent_delta = np.einsum("nij,nj->ni", projector, delta)
    tangent_metrics = np.einsum(
        "nij,njk,nlk->nil", projector, edge_metrics, projector,
    )
    squared = np.einsum(
        "ni,nij,nj->n", tangent_delta, tangent_metrics, tangent_delta,
    )
    return np.sqrt(np.maximum(squared, 0.0))
