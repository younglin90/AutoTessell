"""Transactional native-tri local operators.

The operator loop follows the Botsch/Dunyach hysteresis bounds: split edges
longer than ``4L/3`` and collapse edges shorter than ``4L/5``.  Split,
collapse, and flip proposals all share the same transactional link, fold-over,
and exact-orientation guards.  Rejected proposals leave the state unchanged.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

import numpy as np

from .bijective_shell import (
    BijectiveShell,
    ShellCheckpointReport,
    ShellProvenanceReport,
)
from .metric import (
    audit_spd_metrics,
    intersect_spd_metrics,
    metric_edge_lengths,
    tangent_metric_edge_lengths,
)

_SHELL_PROVENANCE_ENV = "AUTO_TESSELL_TRI_SHELL_PROVENANCE1"
_LOCAL_GUARDS_ENV = "AUTO_TESSELL_TRI_LOCAL_GUARDS1"


def shell_provenance_reporting_enabled() -> bool:
    """Return whether the default-OFF provenance census is enabled."""
    return os.environ.get(_SHELL_PROVENANCE_ENV) == "1"


def local_guard_path_enabled() -> bool:
    """Return whether the opt-in local-equivalence guard path is enabled."""
    return os.environ.get(_LOCAL_GUARDS_ENV) == "1"

#: One triangle is three ``float64`` points, i.e. 9 * 8 bytes of coordinates.
_TRIANGLE_KEY_BYTES = 72

#: Memo of triangles already certified by ``_triangle_orientation_ok``.
#:
#: ``_triangle_orientation_ok`` is a *pure, deterministic* function of the
#: three ``float64`` corner coordinates alone (it derives its own probe point
#: from them), so memoizing it on the exact IEEE-754 bit pattern of those
#: coordinates cannot change any answer -- it only avoids re-running the
#: Shewchuk exact predicate on a triangle whose corners are bit-identical to
#: one already proven non-degenerate.  Only *passing* triangles are recorded,
#: so a rejected triangle is always re-evaluated.  This is what makes the
#: fold-over / exact-orientation guards cost O(edited faces) rather than
#: O(all faces) per local operation, without narrowing what either guard
#: checks: every face of every candidate is still consulted, it just answers
#: from the memo when the face is bit-identical to a previously certified one.
_ORIENTATION_MEMO: set[bytes] = set()

#: Bound on ``_ORIENTATION_MEMO`` so a long remeshing run cannot grow it
#: without limit; clearing it only costs recomputation, never correctness.
_ORIENTATION_MEMO_LIMIT = 1 << 20


def _triangle_keys(triangles: np.ndarray) -> list[bytes]:
    """Return one exact byte key per ``(n, 3, 3)`` triangle coordinate block."""
    count = len(triangles)
    if count == 0:
        return []
    flat = np.ascontiguousarray(triangles, dtype=np.float64).reshape(count, 9)
    buffer = flat.tobytes()
    return [
        buffer[index * _TRIANGLE_KEY_BYTES : (index + 1) * _TRIANGLE_KEY_BYTES]
        for index in range(count)
    ]


def _encode_rows(rows: np.ndarray) -> np.ndarray | None:
    """Pack small non-negative integer rows into one ``int64`` key per row.

    This is a positional numeral encoding over the observed index range, so
    ascending key order is exactly lexicographic row order -- which is what
    lets it stand in for ``np.unique(..., axis=0)`` (whose void-dtype sort is
    an order of magnitude slower) without changing either the unique set or
    its ordering.  Returns ``None`` when the range would overflow ``int64``,
    in which case callers fall back to ``np.unique(..., axis=0)``.
    """
    if rows.size == 0:
        return np.empty(0, dtype=np.int64)
    values = rows.astype(np.int64, copy=False)
    lowest = int(values.min())
    span = int(values.max()) - lowest + 1
    capacity = 1 << 62
    total = 1
    for _ in range(rows.shape[1]):
        total *= span
        if total > capacity:
            return None
    keys = np.zeros(len(values), dtype=np.int64)
    for column in range(rows.shape[1]):
        keys = keys * span + (values[:, column] - lowest)
    return keys


def _unique_rows_with_counts(rows: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return lexicographically sorted unique rows and their occurrence counts."""
    keys = _encode_rows(rows)
    if keys is None:
        unique, counts = np.unique(rows, axis=0, return_counts=True)
        return unique, counts
    _, first, counts = np.unique(keys, return_index=True, return_counts=True)
    return rows[first], counts


def _unique_edges_with_counts(faces: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return sorted unique undirected edges and their face-corner counts."""
    if faces.size == 0:
        return np.empty((0, 2), dtype=np.int64), np.empty(0, dtype=np.int64)
    corners = np.concatenate((faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]))
    undirected = np.stack(
        (
            np.minimum(corners[:, 0], corners[:, 1]),
            np.maximum(corners[:, 0], corners[:, 1]),
        ),
        axis=1,
    )
    return _unique_rows_with_counts(undirected)


def _sorted_unique_edges(faces: np.ndarray) -> np.ndarray:
    """Return the lexicographically sorted unique undirected edges of ``faces``."""
    return _unique_edges_with_counts(faces)[0]


class OperatorKind(StrEnum):
    """Local operators used by the native-tri operator loop."""

    SPLIT = "split"
    COLLAPSE = "collapse"
    FLIP = "flip"
    SMOOTH = "smooth"


@dataclass(frozen=True)
class MeshState:
    """Immutable-shaped mesh container used by the transaction boundary."""

    vertices: np.ndarray
    faces: np.ndarray

    def copy(self) -> MeshState:
        return MeshState(self.vertices.copy(), self.faces.copy())


@dataclass(frozen=True)
class GuardReport:
    """Result of one candidate transaction."""

    accepted: bool
    operator: OperatorKind
    reason: str
    vertex_index: int | None = None


FaceCorrespondence = tuple[tuple[int, int], ...]
SurfaceProjection = Callable[[np.ndarray], np.ndarray]


def estimate_curvature_sizing(
    vertices: np.ndarray,
    faces: np.ndarray,
    epsilon: float,
    *,
    min_length: float | None = None,
    max_length: float | None = None,
) -> np.ndarray:
    """Estimate scalar Dunyach target lengths from discrete edge curvature.

    The edge turning angle is accumulated at each vertex and normalized by
    its incident triangle area.  This is deliberately a scalar curvature
    lane: the anisotropic metric tensor is a later phase.  Flat vertices use
    the mesh median edge length as a stable upper-scale fallback.
    """
    points = np.asarray(vertices, dtype=np.float64)
    triangles = np.asarray(faces, dtype=np.int64)
    eps = float(epsilon)
    if points.ndim != 2 or points.shape[1] != 3 or not np.isfinite(points).all():
        raise ValueError("vertices must be a finite (n, 3) array")
    if triangles.ndim != 2 or triangles.shape[1] != 3:
        raise ValueError("faces must have shape (m, 3)")
    if triangles.size and (
        triangles.min() < 0 or triangles.max() >= len(points)
    ):
        raise ValueError("faces contain an invalid vertex index")
    if not np.isfinite(eps) or eps <= 0.0:
        raise ValueError("epsilon must be finite and positive")

    edge_faces: dict[tuple[int, int], list[int]] = {}
    face_normals = np.zeros((len(triangles), 3), dtype=np.float64)
    face_areas = np.zeros(len(triangles), dtype=np.float64)
    for face_index, face in enumerate(triangles.tolist()):
        a, b, c = (int(vertex) for vertex in face)
        cross = np.cross(points[b] - points[a], points[c] - points[a])
        twice_area = float(np.linalg.norm(cross))
        if twice_area > np.finfo(float).tiny and np.isfinite(twice_area):
            face_normals[face_index] = cross / twice_area
            face_areas[face_index] = 0.5 * twice_area
        for u, v in ((a, b), (b, c), (c, a)):
            edge = (min(u, v), max(u, v))
            edge_faces.setdefault(edge, []).append(face_index)

    edge_lengths = np.asarray(
        [np.linalg.norm(points[b] - points[a]) for a, b in edge_faces],
        dtype=np.float64,
    )
    positive_edges = edge_lengths[np.isfinite(edge_lengths) & (edge_lengths > 0.0)]
    if positive_edges.size == 0:
        raise ValueError("mesh has no positive-length edge")
    reference = float(np.median(positive_edges))
    upper = reference * 2.0 if max_length is None else float(max_length)
    lower = reference * 0.25 if min_length is None else float(min_length)
    if not np.isfinite(lower) or not np.isfinite(upper) or 0.0 < lower > upper:
        raise ValueError("min_length/max_length must be finite and ordered")
    if lower <= 0.0 or upper <= 0.0:
        raise ValueError("min_length/max_length must be positive")
    upper = max(lower, upper)

    curvature = np.zeros(len(points), dtype=np.float64)
    vertex_area = np.zeros(len(points), dtype=np.float64)
    for edge, incident_faces in edge_faces.items():
        a, b = edge
        length = float(np.linalg.norm(points[b] - points[a]))
        if not np.isfinite(length) or length <= 0.0:
            continue
        turning = 0.0
        if len(incident_faces) >= 2:
            for left in range(len(incident_faces)):
                for right in range(left + 1, len(incident_faces)):
                    dot = float(
                        np.dot(
                            face_normals[incident_faces[left]],
                            face_normals[incident_faces[right]],
                        )
                    )
                    turning = max(turning, float(np.arccos(np.clip(dot, -1.0, 1.0))))
        contribution = length * turning
        curvature[a] += contribution
        curvature[b] += contribution
    for face_index, face in enumerate(triangles.tolist()):
        share = face_areas[face_index] / 3.0
        for vertex in face:
            vertex_area[int(vertex)] += share
    valid_area = vertex_area > np.finfo(float).tiny
    # ``sum(edge_length * exterior_dihedral) / (2 A_i)`` is the
    # edge-integrated *twice* mean-curvature convention at a barycentric
    # vertex area.  Dunyach's sizing formula instead takes a principal
    # curvature.  Until the separate cotangent/Gaussian-curvature card
    # supplies ``H + sqrt(H**2 - K)``, use the corresponding mean-curvature
    # surrogate: halve that integrated convention.  This is exact for the
    # umbilic calibration case (a sphere), preserves the existing scalar
    # ordering, and never changes the finite/clamped fallback path.
    curvature[valid_area] /= 4.0 * vertex_area[valid_area]

    lengths = np.full(len(points), upper, dtype=np.float64)
    positive_curvature = valid_area & np.isfinite(curvature) & (curvature > 1e-14)
    radicand = np.zeros(len(points), dtype=np.float64)
    radicand[positive_curvature] = (
        6.0 * eps / curvature[positive_curvature] - 3.0 * eps * eps
    )
    valid_formula = positive_curvature & (radicand > 0.0) & np.isfinite(radicand)
    lengths[valid_formula] = np.sqrt(radicand[valid_formula])
    return np.clip(lengths, lower, upper)


class OperatorTransaction:
    """Transactional boundary for the native-tri local operators.

    ``target_edge_length`` is the reference length ``L`` in the
    Botsch/Dunyach hysteresis rule.  ``curvature_epsilon`` enables the scalar
    Frey/Dunyach sizing lane; anisotropic metric tensors remain out of scope.
    """

    _state: MeshState
    _cache_unique_edges: tuple[tuple[int, int], ...] | None
    _cache_vertex_faces: list[list[int]] | None
    _cache_link_condition: bool | None
    _cache_valence_deviation: int | None
    _cache_identity_correspondence: FaceCorrespondence | None

    def __init__(
        self,
        vertices: np.ndarray,
        faces: np.ndarray,
        target_edge_length: float | None = None,
        *,
        surface_points: np.ndarray | None = None,
        surface_projection: SurfaceProjection | None = None,
        surface_vertices: Iterable[int] | None = None,
        curvature_epsilon: float | None = None,
        metric_field: np.ndarray | None = None,
        metric_normals: np.ndarray | None = None,
        metric_feature_vertices: np.ndarray | None = None,
        metric_max_normal_angle_deg: float | None = None,
    ) -> None:
        self._state = MeshState(
            np.asarray(vertices, dtype=np.float64).copy(),
            np.asarray(faces, dtype=np.int64).copy(),
        )
        self._invalidate_state_cache()
        self.target_edge_length = target_edge_length
        self.surface_points = (
            None if surface_points is None else np.asarray(surface_points, dtype=np.float64).copy()
        )
        self.surface_projection = surface_projection
        self.surface_vertices = (
            None if surface_vertices is None else tuple(int(index) for index in surface_vertices)
        )
        self.curvature_epsilon = curvature_epsilon
        self.vertex_target_lengths: np.ndarray | None = None
        if curvature_epsilon is not None:
            self._refresh_curvature_sizing()
        if metric_field is not None and len(metric_field) != len(self.state.vertices):
            raise ValueError("metric_field length must match vertices")
        self.metric_field = self._validate_metric_field(metric_field)
        self.metric_normals = self._validate_metric_normals(metric_normals)
        if self.metric_normals is not None and self.metric_field is None:
            raise ValueError("metric_normals require metric_field")
        if metric_feature_vertices is not None and self.metric_normals is None:
            raise ValueError("metric_feature_vertices require metric_normals")
        self.metric_feature_vertices = self._validate_metric_feature_vertices(
            metric_feature_vertices,
        )
        if metric_max_normal_angle_deg is not None and (
            metric_max_normal_angle_deg < 0.0
            or not np.isfinite(metric_max_normal_angle_deg)
        ):
            raise ValueError("metric_max_normal_angle_deg must be finite and non-negative")
        self.metric_max_normal_angle_deg = metric_max_normal_angle_deg
        self._pending_metric_field: np.ndarray | None = None
        self._pending_metric_normals: np.ndarray | None = None
        self._pending_metric_feature_vertices: np.ndarray | None = None
        self.shell_checkpoint_reports: list[ShellCheckpointReport] = []
        self.shell_provenance_reports: list[ShellProvenanceReport] = []
        self.shell_provenance_report_failures: list[str] = []

    # ------------------------------------------------------------------
    # Per-state derived caches.
    #
    # Every entry below is a *pure function of ``self.state``* and is
    # discarded the moment ``self.state`` is rebound.  Nothing here changes
    # what any guard checks; it only stops the hot loop from recomputing the
    # same whole-mesh derived structure once per candidate edge/vertex.  The
    # transaction only ever rebinds ``self.state`` to a whole new frozen
    # ``MeshState`` (commit or roll-back), never mutates one in place, so
    # rebinding is the complete invalidation trigger.
    # ------------------------------------------------------------------

    @property
    def state(self) -> MeshState:
        """Current committed mesh state."""
        return self._state

    @state.setter
    def state(self, value: MeshState) -> None:
        # The vertex -> incident-face map is a pure function of ``faces``
        # alone, so a state change that only moves vertices (every accepted
        # smoothing move, and every roll-back to a bit-equal copy) may carry
        # it over instead of rebuilding it in ``O(faces)`` per edit.
        previous = getattr(self, "_state", None)
        carried = (
            self._cache_vertex_faces
            if previous is not None
            and previous.faces.shape == value.faces.shape
            and len(previous.vertices) == len(value.vertices)
            and np.array_equal(previous.faces, value.faces)
            else None
        )
        self._state = value
        self._invalidate_state_cache()
        self._cache_vertex_faces = carried

    def _invalidate_state_cache(self) -> None:
        self._cache_unique_edges = None
        self._cache_vertex_faces = None
        self._cache_link_condition = None
        self._cache_valence_deviation = None
        self._cache_identity_correspondence = None

    def _state_link_condition(self) -> bool:
        """``_link_condition(self.state)``, evaluated at most once per state."""
        if self._cache_link_condition is None:
            self._cache_link_condition = self._link_condition(self._state)
        return self._cache_link_condition

    def _state_vertex_faces(self) -> list[list[int]]:
        """Vertex -> ascending incident-face indices for the current state."""
        cached = self._cache_vertex_faces
        if cached is not None:
            return cached
        incidence: list[list[int]] = [[] for _ in range(len(self._state.vertices))]
        limit = len(incidence)
        for face_index, face in enumerate(self._state.faces.tolist()):
            for vertex in face:
                index = int(vertex)
                if 0 <= index < limit:
                    bucket = incidence[index]
                    if not bucket or bucket[-1] != face_index:
                        bucket.append(face_index)
        self._cache_vertex_faces = incidence
        return incidence

    def _state_incident_faces(self, a: int, b: int) -> list[int]:
        """Ascending face indices containing both ``a`` and ``b``.

        Identical to ``[i for i, f in enumerate(faces) if a in f and b in f]``
        (the incidence list is built in face order, so the intersection stays
        ascending), but scoped to the two vertices instead of the face array.
        """
        incidence = self._state_vertex_faces()
        if not 0 <= a < len(incidence) or not 0 <= b < len(incidence):
            return []
        other = set(incidence[b])
        return [index for index in incidence[a] if index in other]

    def _state_vertex_neighbours(self, vertex: int) -> set[int]:
        """One-ring neighbours of ``vertex``, read off the cached incidence."""
        neighbours: set[int] = set()
        faces = self._state.faces
        for face_index in self._state_vertex_faces()[vertex]:
            neighbours.update(
                int(other) for other in faces[face_index].tolist() if int(other) != vertex
            )
        return neighbours

    def _state_valence_deviation(self) -> int:
        """``_vertex_valence_deviation(self.state)``, cached per state.

        Every ``_flip_improves`` call in a flip scan compares against the
        *same* pre-edit state, so this is computed once per state instead of
        once per candidate edge.
        """
        if self._cache_valence_deviation is None:
            self._cache_valence_deviation = self._vertex_valence_deviation(self._state)
        return self._cache_valence_deviation

    def _state_identity_correspondence(self) -> FaceCorrespondence:
        """Identity ``(i, i)`` face correspondence for the current state."""
        cached = self._cache_identity_correspondence
        if cached is None:
            cached = tuple(
                (face_index, face_index) for face_index in range(len(self._state.faces))
            )
            self._cache_identity_correspondence = cached
        return cached

    def _state_edge_link_condition(self, a: int, b: int) -> list[int] | None:
        """Return incident faces only for a manifold edge eligible to edit.

        The whole-mesh ``_link_condition`` term is a property of the state,
        not of the edge, so it is evaluated once per state rather than once
        per candidate edge; the edge-local terms (one or two incident faces,
        distinct opposite vertices) are unchanged.
        """
        if not self._state_link_condition():
            return None
        incident = self._state_incident_faces(a, b)
        if not 1 <= len(incident) <= 2:
            return None
        opposite = []
        for index in incident:
            face = self._state.faces[index].tolist()
            opposite.append(next(vertex for vertex in face if vertex not in (a, b)))
        if len(set(opposite)) != len(opposite):
            return None
        return incident

    def _state_collapse_edge_link_condition(self, a: int, b: int) -> list[int] | None:
        """Return incident faces only when the edge satisfies the collapse link."""
        incident = self._state_edge_link_condition(a, b)
        if incident is None:
            return None
        common = self._state_vertex_neighbours(a).intersection(
            self._state_vertex_neighbours(b),
        )
        opposite = {
            vertex
            for index in incident
            for vertex in self._state.faces[index].tolist()
            if vertex not in (a, b)
        }
        if common != opposite:
            return None
        return incident

    @classmethod
    def _local_guard_inputs(
        cls,
        before: MeshState,
        after: MeshState,
        face_correspondence: FaceCorrespondence | None,
    ) -> tuple[MeshState, np.ndarray, FaceCorrespondence] | None:
        """Return a conservative local guard view when unchanged faces are known.

        The caller has already constructed a candidate from a valid committed
        state.  A correspondence pair whose corner coordinates differ marks a
        geometrically changed face; all faces incident to those corners are
        included for the local topology census.  If the candidate contract is
        ambiguous, return ``None`` so the legacy full-mesh guards remain in
        force.  This helper never changes the candidate or the acceptance rule;
        it only identifies the smallest safe proof domain for the opt-in path.
        """
        if face_correspondence is None or not face_correspondence:
            return None
        if not np.isfinite(after.vertices).all():
            return None
        pairs = np.asarray(face_correspondence, dtype=np.int64)
        if pairs.ndim != 2 or pairs.shape[1] != 2:
            return None
        old_indices, new_indices = pairs[:, 0], pairs[:, 1]
        if (
            old_indices.min() < 0
            or old_indices.max() >= len(before.faces)
            or new_indices.min() < 0
            or new_indices.max() >= len(after.faces)
        ):
            return None
        old_triangles = before.vertices[before.faces[old_indices]]
        new_triangles = after.vertices[after.faces[new_indices]]
        changed = np.any(old_triangles != new_triangles, axis=(1, 2))
        selected_pairs = pairs[changed] if changed.any() else pairs
        selected_new = np.unique(selected_pairs[:, 1])
        if selected_new.size == 0:
            return None
        affected_vertices = np.unique(after.faces[selected_new].reshape(-1))
        local_mask = np.any(np.isin(after.faces, affected_vertices), axis=1)
        local_indices = np.flatnonzero(local_mask)
        if local_indices.size == 0:
            return None
        local_faces = after.faces[local_indices]
        new_position = {int(index): position for position, index in enumerate(local_indices.tolist())}
        local_pairs = tuple(
            (int(old_index), new_position[int(new_index)])
            for old_index, new_index in selected_pairs.tolist()
            if int(new_index) in new_position
        )
        if not local_pairs:
            return None
        return MeshState(after.vertices, local_faces), selected_new, local_pairs

    @classmethod
    def _local_exact_orientation_guard(
        cls,
        after: MeshState,
        selected_new: np.ndarray,
    ) -> bool:
        """Check only changed faces; unchanged faces inherit the valid state."""
        triangles = after.vertices[after.faces[selected_new]]
        if not np.isfinite(triangles).all():
            return False
        keys = _triangle_keys(triangles)
        return all(
            cls._triangle_orientation_certified(triangle, key)
            for triangle, key in zip(triangles, keys)
        )

    def attempt(
        self,
        operator: OperatorKind,
        candidate: tuple[np.ndarray, np.ndarray] | None = None,
        *,
        face_correspondence: FaceCorrespondence | None = None,
    ) -> GuardReport:
        """Validate and conditionally commit a proposed local-operator candidate.

        ``face_correspondence`` contains ``(old_face, new_face)`` pairs for
        faces whose orientation must be preserved.  The split builder supplies
        this for every child face; direct callers may omit it, in which case
        unchanged face keys are matched automatically.
        """
        before = self.state.copy()
        if candidate is None:
            return GuardReport(False, operator, "mvp_noop_operator")

        try:
            after = MeshState(
                np.asarray(candidate[0], dtype=np.float64),
                np.asarray(candidate[1], dtype=np.int64),
            )
            pending_metric = self._pending_metric_field
            if self.metric_field is not None and len(after.vertices) != len(before.vertices):
                if pending_metric is None or len(pending_metric) != len(after.vertices):
                    return GuardReport(False, operator, "metric_field_shape_mismatch")
                if (
                    self.metric_normals is not None
                    and (
                        self._pending_metric_normals is None
                        or len(self._pending_metric_normals) != len(after.vertices)
                    )
                ):
                    return GuardReport(False, operator, "metric_normals_shape_mismatch")
                if (
                    self.metric_feature_vertices is not None
                    and (
                        self._pending_metric_feature_vertices is None
                        or len(self._pending_metric_feature_vertices) != len(after.vertices)
                    )
                ):
                    return GuardReport(False, operator, "metric_feature_shape_mismatch")
            local_inputs = (
                self._local_guard_inputs(before, after, face_correspondence)
                if local_guard_path_enabled() and self._state_link_condition()
                else None
            )
            if local_inputs is None:
                if not self._link_condition(after):
                    return GuardReport(False, operator, "link_condition_failed")
                after_triangles = after.vertices[after.faces]
                after_keys = _triangle_keys(after_triangles)
                if not self._foldover_guard(
                    before,
                    after,
                    face_correspondence,
                    after_triangles=after_triangles,
                    after_keys=after_keys,
                ):
                    return GuardReport(False, operator, "foldover_guard_failed")
                if not self._exact_orientation_guard(
                    after,
                    triangles=after_triangles,
                    triangle_keys=after_keys,
                ):
                    return GuardReport(False, operator, "exact_orientation_failed")
            else:
                local_after, selected_new, local_pairs = local_inputs
                if not self._link_condition(local_after):
                    return GuardReport(False, operator, "link_condition_failed")
                local_triangles = local_after.vertices[local_after.faces]
                local_keys = _triangle_keys(local_triangles)
                local_correspondence = tuple(
                    (old_index, int(new_index))
                    for old_index, new_index in local_pairs
                )
                if not self._foldover_guard(
                    before,
                    local_after,
                    local_correspondence,
                    after_triangles=local_triangles,
                    after_keys=local_keys,
                ):
                    return GuardReport(False, operator, "foldover_guard_failed")
                if not self._local_exact_orientation_guard(after, selected_new):
                    return GuardReport(False, operator, "exact_orientation_failed")
            if operator is OperatorKind.FLIP and not self._flip_improves(
                before,
                after,
                face_correspondence,
                # ``before`` is a bit-exact copy of ``self.state``, so the
                # cached pre-edit valence deviation is the same number.
                before_deviation=self._state_valence_deviation(),
            ):
                return GuardReport(False, operator, "flip_not_improved")
        except (TypeError, ValueError, IndexError, FloatingPointError, RuntimeError):
            self.state = before
            return GuardReport(False, operator, "exact_orientation_failed")

        self.state = MeshState(after.vertices.copy(), after.faces.copy())
        if pending_metric is not None:
            self.metric_field = pending_metric.copy()
        if self._pending_metric_normals is not None:
            self.metric_normals = self._pending_metric_normals.copy()
        if self._pending_metric_feature_vertices is not None:
            self.metric_feature_vertices = self._pending_metric_feature_vertices.copy()
        return GuardReport(True, operator, "committed")

    def should_split_edge(
        self,
        edge: tuple[int, int],
        target_edge_length: float | None = None,
    ) -> bool:
        """Return whether ``edge`` exceeds the upper split hysteresis bound."""
        metric_length = self._metric_edge_length(edge, target_edge_length)
        if metric_length is not None:
            return bool(np.isfinite(metric_length) and metric_length > 4.0 / 3.0)
        target = self._edge_target_length(edge, target_edge_length)
        a, b = self._edge_vertices(edge)
        length = float(np.linalg.norm(self.state.vertices[a] - self.state.vertices[b]))
        return bool(length > (4.0 / 3.0) * target)

    def split_edge(
        self,
        edge: tuple[int, int],
        target_edge_length: float | None = None,
    ) -> GuardReport:
        """Split one eligible edge at its midpoint and commit transactionally."""
        before = self.state.copy()
        try:
            a, b = self._edge_vertices(edge)
            metric_length = self._metric_edge_length(edge, target_edge_length)
            if metric_length is None:
                target = self._edge_target_length(edge, target_edge_length)
                edge_length = float(np.linalg.norm(before.vertices[a] - before.vertices[b]))
                if not np.isfinite(edge_length):
                    return GuardReport(False, OperatorKind.SPLIT, "malformed_edge")
                if edge_length <= (4.0 / 3.0) * target:
                    return GuardReport(False, OperatorKind.SPLIT, "split_threshold_not_exceeded")
            elif not np.isfinite(metric_length) or metric_length <= 4.0 / 3.0:
                return GuardReport(False, OperatorKind.SPLIT, "split_threshold_not_exceeded")

            incident = self._state_edge_link_condition(a, b)
            if incident is None:
                return GuardReport(False, OperatorKind.SPLIT, "link_condition_failed")

            vertices, faces, correspondence = self._build_split_candidate(
                before,
                a,
                b,
                incident,
            )
        except (TypeError, ValueError, IndexError, FloatingPointError):
            self.state = before
            return GuardReport(False, OperatorKind.SPLIT, "malformed_edge")

        self._pending_metric_field = self._metric_after_split(a, b)
        self._pending_metric_normals = self._metric_normals_after_split(a, b)
        self._pending_metric_feature_vertices = self._metric_features_after_split(a, b)
        try:
            report = self.attempt(
                OperatorKind.SPLIT,
                (vertices, faces),
                face_correspondence=correspondence,
            )
        finally:
            self._pending_metric_field = None
            self._pending_metric_normals = None
            self._pending_metric_feature_vertices = None
        if not report.accepted:
            self.state = before
        elif self.curvature_epsilon is not None:
            self._refresh_curvature_sizing()
        return report

    def should_collapse_edge(
        self,
        edge: tuple[int, int],
        target_edge_length: float | None = None,
    ) -> bool:
        """Return whether ``edge`` is below the strict collapse bound."""
        metric_length = self._metric_edge_length(edge, target_edge_length)
        if metric_length is not None:
            return bool(np.isfinite(metric_length) and metric_length < 4.0 / 5.0)
        target = self._edge_target_length(edge, target_edge_length)
        a, b = self._edge_vertices(edge)
        length = float(np.linalg.norm(self.state.vertices[a] - self.state.vertices[b]))
        return bool(np.isfinite(length) and length < (4.0 / 5.0) * target)

    def collapse_edge(
        self,
        edge: tuple[int, int],
        target_edge_length: float | None = None,
    ) -> GuardReport:
        """Collapse one eligible edge to its midpoint transactionally."""
        before = self.state.copy()
        try:
            a, b = self._edge_vertices(edge)
            a, b = min(a, b), max(a, b)
            metric_length = self._metric_edge_length((a, b), target_edge_length)
            if metric_length is None:
                target = self._edge_target_length((a, b), target_edge_length)
                edge_length = float(np.linalg.norm(before.vertices[a] - before.vertices[b]))
                if not np.isfinite(edge_length):
                    return GuardReport(False, OperatorKind.COLLAPSE, "malformed_edge")
                if edge_length >= (4.0 / 5.0) * target:
                    return GuardReport(
                        False,
                        OperatorKind.COLLAPSE,
                        "collapse_threshold_not_exceeded",
                    )
            elif not np.isfinite(metric_length) or metric_length >= 4.0 / 5.0:
                return GuardReport(
                    False,
                    OperatorKind.COLLAPSE,
                    "collapse_threshold_not_exceeded",
                )

            incident = self._state_collapse_edge_link_condition(a, b)
            if incident is None:
                return GuardReport(False, OperatorKind.COLLAPSE, "link_condition_failed")
            vertices, faces, correspondence = self._build_collapse_candidate(
                before,
                a,
                b,
                incident,
            )
        except (TypeError, ValueError, IndexError, FloatingPointError):
            self.state = before
            return GuardReport(False, OperatorKind.COLLAPSE, "malformed_edge")

        self._pending_metric_field = self._metric_after_collapse(a, b)
        self._pending_metric_normals = self._metric_normals_after_collapse(a, b)
        self._pending_metric_feature_vertices = self._metric_features_after_collapse(a, b)
        try:
            report = self.attempt(
                OperatorKind.COLLAPSE,
                (vertices, faces),
                face_correspondence=correspondence,
            )
        finally:
            self._pending_metric_field = None
            self._pending_metric_normals = None
            self._pending_metric_feature_vertices = None
        if not report.accepted:
            self.state = before
        elif self.curvature_epsilon is not None:
            self._refresh_curvature_sizing()
        return report

    def should_flip_edge(self, edge: tuple[int, int]) -> bool:
        """Return whether flipping ``edge`` is a guarded quality move."""
        a, b = self._edge_vertices(edge)
        incident = self._state_edge_link_condition(a, b)
        if incident is None or len(incident) != 2:
            return False
        try:
            vertices, faces, correspondence = self._build_flip_candidate(
                self.state,
                a,
                b,
                incident,
            )
        except (TypeError, ValueError, IndexError, FloatingPointError):
            return False
        return self._flip_improves(
            self.state,
            MeshState(vertices, faces),
            correspondence,
            before_deviation=self._state_valence_deviation(),
        )

    def flip_edge(self, edge: tuple[int, int]) -> GuardReport:
        """Flip one internal edge when valence or local triangle quality improves."""
        before = self.state.copy()
        try:
            a, b = self._edge_vertices(edge)
            incident = self._state_edge_link_condition(a, b)
            if incident is None or len(incident) != 2:
                return GuardReport(False, OperatorKind.FLIP, "link_condition_failed")
            vertices, faces, correspondence = self._build_flip_candidate(
                before,
                a,
                b,
                incident,
            )
            after = MeshState(vertices, faces)
            if not self._flip_improves(
                before,
                after,
                correspondence,
                before_deviation=self._state_valence_deviation(),
            ):
                return GuardReport(False, OperatorKind.FLIP, "flip_not_improved")
        except (TypeError, ValueError, IndexError, FloatingPointError):
            self.state = before
            return GuardReport(False, OperatorKind.FLIP, "malformed_edge")

        report = self.attempt(
            OperatorKind.FLIP,
            (vertices, faces),
            face_correspondence=correspondence,
        )
        if not report.accepted:
            self.state = before
        return report

    def smooth_vertex(
        self,
        vertex_index: int,
        *,
        relocation_lambda: float = 0.5,
        sizing_aware_relocation: bool = False,
        surface_points: np.ndarray | None = None,
        surface_projection: SurfaceProjection | None = None,
        surface_vertices: Iterable[int] | None = None,
    ) -> GuardReport:
        """Tangentially relocate one vertex with transactional rejection.

        The default target is an area-weighted centroid of the vertex's
        one-ring neighbours.  When ``sizing_aware_relocation`` is enabled and
        a curvature sizing field is available, the target instead uses the
        Dunyach equation-(6) triangle-barycenter weights
        ``area * mean(L(vertex))``.  Only the displacement tangent to the
        area-weighted vertex normal is applied.  Projection is then applied
        when the vertex is a declared surface vertex; the full mesh is checked
        before commit.
        """
        before = self.state.copy()
        try:
            index = int(vertex_index)
            if index < 0 or index >= len(before.vertices):
                return GuardReport(
                    False,
                    OperatorKind.SMOOTH,
                    "malformed_vertex",
                    index,
                )
            if (
                self.metric_feature_vertices is not None
                and bool(self.metric_feature_vertices[index])
            ):
                return GuardReport(
                    False,
                    OperatorKind.SMOOTH,
                    "metric_feature_vertex_locked",
                    index,
                )
            factor = self._relocation_factor(relocation_lambda)
            centroid_and_normal = self._area_weighted_neighbor_centroid(
                before,
                index,
                incident_faces=self._state_vertex_faces()[index],
            )
            if centroid_and_normal is None:
                return GuardReport(
                    False,
                    OperatorKind.SMOOTH,
                    "smooth_degenerate_vertex",
                    index,
                )
            if sizing_aware_relocation:
                centroid_and_normal = self._sizing_weighted_barycenter(
                    before,
                    index,
                    incident_faces=self._state_vertex_faces()[index],
                )
                if centroid_and_normal is None:
                    return GuardReport(
                        False,
                        OperatorKind.SMOOTH,
                        "sizing_field_unavailable",
                        index,
                    )
            centroid, normal = centroid_and_normal
            normal_length = float(np.linalg.norm(normal))
            if not np.isfinite(normal_length) or normal_length <= np.finfo(float).tiny:
                return GuardReport(
                    False,
                    OperatorKind.SMOOTH,
                    "smooth_degenerate_vertex",
                    index,
                )

            point = before.vertices[index]
            normal_unit = normal / normal_length
            displacement = centroid - point
            tangent = displacement - np.dot(displacement, normal_unit) * normal_unit
            proposed = point + factor * tangent
            if not np.isfinite(proposed).all():
                return GuardReport(
                    False,
                    OperatorKind.SMOOTH,
                    "malformed_vertex",
                    index,
                )
            if float(np.linalg.norm(proposed - point)) <= np.finfo(float).eps:
                return GuardReport(False, OperatorKind.SMOOTH, "smooth_no_change", index)

            points = self.surface_points if surface_points is None else surface_points
            projection = (
                self.surface_projection if surface_projection is None else surface_projection
            )
            surface_set = self._surface_vertex_set(surface_vertices)
            if surface_set is None or index in surface_set:
                proposed = self._project_surface_point(proposed, points, projection)
            if not np.isfinite(proposed).all():
                return GuardReport(
                    False,
                    OperatorKind.SMOOTH,
                    "surface_projection_failed",
                    index,
                )
            if float(np.linalg.norm(proposed - point)) <= np.finfo(float).eps:
                return GuardReport(False, OperatorKind.SMOOTH, "smooth_no_change", index)
        except (TypeError, ValueError, IndexError, FloatingPointError):
            self.state = before
            return GuardReport(False, OperatorKind.SMOOTH, "malformed_vertex", vertex_index)

        vertices = before.vertices.copy()
        vertices[index] = proposed
        correspondence = self._state_identity_correspondence()
        report = self.attempt(
            OperatorKind.SMOOTH,
            (vertices, before.faces.copy()),
            face_correspondence=correspondence,
        )
        if report.accepted and sizing_aware_relocation and self.curvature_epsilon is not None:
            self._refresh_curvature_sizing()
        return GuardReport(report.accepted, report.operator, report.reason, index)

    def smooth_vertices(
        self,
        vertex_indices: Iterable[int] | None = None,
        *,
        relocation_lambda: float = 0.5,
        sizing_aware_relocation: bool = False,
        surface_points: np.ndarray | None = None,
        surface_projection: SurfaceProjection | None = None,
        surface_vertices: Iterable[int] | None = None,
    ) -> tuple[GuardReport, ...]:
        """Relocate selected vertices one at a time and return per-vertex reports."""
        indices = (
            tuple(range(len(self.state.vertices)))
            if vertex_indices is None
            else tuple(int(index) for index in vertex_indices)
        )
        projected_vertices = (
            None if surface_vertices is None else tuple(int(index) for index in surface_vertices)
        )
        return tuple(
            self.smooth_vertex(
                index,
                relocation_lambda=relocation_lambda,
                sizing_aware_relocation=sizing_aware_relocation,
                surface_points=surface_points,
                surface_projection=surface_projection,
                surface_vertices=projected_vertices,
            )
            for index in indices
        )

    def run_one_round(
        self,
        target_edge_length: float | None = None,
        *,
        smooth: bool = True,
        relocation_lambda: float = 0.5,
        sizing_aware_relocation: bool = False,
        surface_points: np.ndarray | None = None,
        surface_projection: SurfaceProjection | None = None,
        surface_vertices: Iterable[int] | None = None,
    ) -> tuple[GuardReport, ...]:
        """Run one split → collapse → flip → smooth pass.

        Split candidates are taken from the pass entry state.  Collapse and
        flip candidates are refreshed after each accepted edit because collapse
        compacts vertex indices and every local edit changes its neighbourhood.
        Each edge is processed at most once per phase, while later candidates
        may still be attempted after a rejection.
        """
        target = (
            None
            if target_edge_length is None
            and (self.vertex_target_lengths is not None or self.metric_field is not None)
            else self._target_length(target_edge_length)
        )
        reports: list[GuardReport] = []

        for edge in self._unique_edges():
            if self.should_split_edge(edge, target):
                reports.append(self.split_edge(edge, target))

        processed: set[tuple[int, int]] = set()
        while True:
            candidates = [
                edge
                for edge in self._unique_edges()
                if edge not in processed and self.should_collapse_edge(edge, target)
            ]
            if not candidates:
                break
            edge = min(candidates, key=self._edge_length)
            report = self.collapse_edge(edge, target)
            reports.append(report)
            processed.add(edge)

        processed.clear()
        while True:
            candidates = [
                edge
                for edge in self._unique_edges()
                if edge not in processed and self.should_flip_edge(edge)
            ]
            if not candidates:
                break
            edge = min(candidates, key=self._edge_length)
            report = self.flip_edge(edge)
            reports.append(report)
            processed.add(edge)

        if smooth:
            reports.extend(
                self.smooth_vertices(
                    relocation_lambda=relocation_lambda,
                    sizing_aware_relocation=sizing_aware_relocation,
                    surface_points=surface_points,
                    surface_projection=surface_projection,
                    surface_vertices=surface_vertices,
                ),
            )

        return tuple(reports)

    def remesh_one_round(
        self,
        target_edge_length: float | None = None,
        *,
        smooth: bool = True,
        relocation_lambda: float = 0.5,
        sizing_aware_relocation: bool = False,
        surface_points: np.ndarray | None = None,
        surface_projection: SurfaceProjection | None = None,
        surface_vertices: Iterable[int] | None = None,
    ) -> tuple[GuardReport, ...]:
        """Compatibility name for the split/collapse/flip/smooth pass."""
        return self.run_one_round(
            target_edge_length,
            smooth=smooth,
            relocation_lambda=relocation_lambda,
            sizing_aware_relocation=sizing_aware_relocation,
            surface_points=surface_points,
            surface_projection=surface_projection,
            surface_vertices=surface_vertices,
        )

    def run_rounds(
        self,
        max_rounds: int,
        target_edge_length: float | None = None,
        *,
        relocation_lambda: float = 0.5,
        sizing_aware_relocation: bool = False,
        surface_points: np.ndarray | None = None,
        surface_projection: SurfaceProjection | None = None,
        surface_vertices: Iterable[int] | None = None,
        shell: BijectiveShell | None = None,
    ) -> tuple[tuple[GuardReport, ...], ...]:
        """Run at most ``max_rounds`` and stop after a fully rejected round.

        ``shell`` wires in the Phase-3 per-round bijective-shell checkpoint
        (Jiang 2020, ``bijective_shell.py``): a coarser, batched safety net
        layered *on top of* the existing per-op link-condition/fold-over/
        exact-orientation guards inside ``run_one_round`` -- it never
        replaces them. Per
        ``docs/references/literature/native_tri/shell_efficiency_check_2026-07-25.md``,
        a per-edit shell query is too expensive for the hot loop, so this is
        checked once per completed round instead. When the round's
        resulting surface is not fully contained in the static shell, the
        whole round is rolled back to its pre-round state and the loop
        stops; that round's per-op ``GuardReport`` history is still
        returned unchanged (for diagnostics -- it records what was
        attempted, even though it was ultimately reverted). Every
        checkpoint outcome is also appended to
        ``self.shell_checkpoint_reports``.
        """
        if isinstance(max_rounds, bool) or int(max_rounds) != max_rounds:
            raise ValueError("max_rounds must be an integer")
        if max_rounds < 0:
            raise ValueError("max_rounds must be non-negative")
        rounds: list[tuple[GuardReport, ...]] = []
        for round_index in range(max_rounds):
            pre_round_state = self.state.copy()
            reports = self.run_one_round(
                target_edge_length,
                relocation_lambda=relocation_lambda,
                sizing_aware_relocation=sizing_aware_relocation,
                surface_points=surface_points,
                surface_projection=surface_projection,
                surface_vertices=surface_vertices,
            )
            rounds.append(reports)

            # TRI-SHELL-PROVENANCE1 is diagnostic-only.  It reads the
            # completed round state and appends an immutable census; neither
            # its status nor its round-trip error participates in acceptance,
            # rollback, stopping, or any GuardReport.
            if shell is not None and shell_provenance_reporting_enabled():
                try:
                    provenance_report = shell.census_face_centroids(
                        self.state.vertices,
                        self.state.faces,
                    )
                except Exception as error:  # noqa: BLE001
                    # Diagnostics must remain fail-open with respect to the
                    # operator loop.  The exception class is retained as a
                    # deterministic, report-only failure reason.
                    self.shell_provenance_report_failures.append(type(error).__name__)
                else:
                    self.shell_provenance_reports.append(provenance_report)

            if shell is not None:
                containment = shell.check_round_containment(
                    self.state.vertices,
                    self.state.faces,
                )
                self.shell_checkpoint_reports.append(
                    ShellCheckpointReport(
                        containment.accepted,
                        round_index,
                        containment.reason,
                        containment.failed_face_index,
                    ),
                )
                if not containment.accepted:
                    self.state = pre_round_state
                    break

            if not any(report.accepted for report in reports):
                break
        return tuple(rounds)

    @staticmethod
    def _relocation_factor(value: float) -> float:
        factor = float(value)
        if not np.isfinite(factor) or factor < 0.0:
            raise ValueError("relocation_lambda must be finite and non-negative")
        return factor

    def _surface_vertex_set(
        self,
        override: Iterable[int] | None,
    ) -> set[int] | None:
        indices = self.surface_vertices if override is None else tuple(override)
        if indices is None:
            return None
        return {int(index) for index in indices}

    @staticmethod
    def _project_surface_point(
        point: np.ndarray,
        surface_points: np.ndarray | None,
        surface_projection: SurfaceProjection | None,
    ) -> np.ndarray:
        if surface_projection is not None:
            projected = cast(
                np.ndarray,
                np.asarray(surface_projection(point.copy()), dtype=np.float64).reshape(-1),
            )
            if projected.shape != (3,):
                raise ValueError("surface_projection must return a 3-vector")
            return cast(np.ndarray, np.array(projected, dtype=np.float64, copy=True))
        if surface_points is None:
            return point.copy()

        points = np.asarray(surface_points, dtype=np.float64)
        if points.ndim != 2 or points.shape[1] != 3 or points.shape[0] == 0:
            raise ValueError("surface_points must have shape (n, 3)")
        if not np.isfinite(points).all():
            raise ValueError("surface_points must be finite")
        distances = np.linalg.norm(points - point, axis=1)
        return cast(
            np.ndarray,
            np.array(points[int(np.argmin(distances))], dtype=np.float64, copy=True),
        )

    @classmethod
    def _area_weighted_neighbor_centroid(
        cls,
        mesh: MeshState,
        vertex_index: int,
        *,
        incident_faces: Sequence[int] | None = None,
    ) -> tuple[np.ndarray, np.ndarray] | None:
        """Return the area-weighted one-ring centroid and vertex normal.

        ``incident_faces`` optionally restricts the scan to the faces already
        known to contain ``vertex_index``.  This is a pure iteration-scope
        reduction: the full-mesh loop below skips every face that does not
        contain the vertex anyway (``if vertex_index not in face: continue``),
        so supplying the exact incidence yields a bit-identical accumulation.
        """
        weighted_centroid: np.ndarray = np.zeros(3, dtype=np.float64)
        weighted_normal: np.ndarray = np.zeros(3, dtype=np.float64)
        total_area = 0.0
        candidate_faces = (
            mesh.faces.tolist()
            if incident_faces is None
            else [mesh.faces[face_index].tolist() for face_index in incident_faces]
        )
        for face in candidate_faces:
            if vertex_index not in face:
                continue
            neighbours = [int(vertex) for vertex in face if int(vertex) != vertex_index]
            if len(neighbours) != 2:
                continue
            tri = mesh.vertices[np.asarray(face, dtype=np.int64)]
            cross = np.cross(tri[1] - tri[0], tri[2] - tri[0])
            twice_area = float(np.linalg.norm(cross))
            if not np.isfinite(twice_area) or twice_area <= np.finfo(float).tiny:
                continue
            area = 0.5 * twice_area
            neighbour_centroid = (mesh.vertices[neighbours[0]] + mesh.vertices[neighbours[1]]) * 0.5
            weighted_centroid += area * neighbour_centroid
            weighted_normal += area * cross / twice_area
            total_area += area

        if total_area <= 0.0 or not np.isfinite(total_area):
            return None
        centroid = weighted_centroid / total_area
        if not np.isfinite(centroid).all() or not np.isfinite(weighted_normal).all():
            return None
        return centroid, weighted_normal

    def _sizing_weighted_barycenter(
        self,
        mesh: MeshState,
        vertex_index: int,
        *,
        incident_faces: Sequence[int] | None = None,
    ) -> tuple[np.ndarray, np.ndarray] | None:
        """Return Dunyach's sizing-weighted triangle-barycenter target.

        Equation (6) weights each incident triangle barycenter by its area and
        by the average target length at that triangle's vertices.  This is an
        opt-in relocation target; the caller still applies the tangent
        projection and the full transactional guard before committing it.
        """
        lengths = self.vertex_target_lengths
        if lengths is None or len(lengths) != len(mesh.vertices):
            return None
        weighted_centroid = np.zeros(3, dtype=np.float64)
        weighted_normal = np.zeros(3, dtype=np.float64)
        total_weight = 0.0
        candidate_faces = (
            mesh.faces.tolist()
            if incident_faces is None
            else [mesh.faces[face_index].tolist() for face_index in incident_faces]
        )
        for face in candidate_faces:
            if vertex_index not in face:
                continue
            indices = np.asarray(face, dtype=np.int64)
            tri = mesh.vertices[indices]
            cross = np.cross(tri[1] - tri[0], tri[2] - tri[0])
            twice_area = float(np.linalg.norm(cross))
            if not np.isfinite(twice_area) or twice_area <= np.finfo(float).tiny:
                continue
            face_lengths = lengths[indices]
            length_at_barycenter = float(np.mean(face_lengths))
            if not np.isfinite(length_at_barycenter) or length_at_barycenter <= 0.0:
                continue
            area = 0.5 * twice_area
            weight = area * length_at_barycenter
            weighted_centroid += weight * np.mean(tri, axis=0)
            weighted_normal += area * cross / twice_area
            total_weight += weight

        if total_weight <= 0.0 or not np.isfinite(total_weight):
            return None
        centroid = weighted_centroid / total_weight
        if not np.isfinite(centroid).all() or not np.isfinite(weighted_normal).all():
            return None
        return centroid, weighted_normal

    def _target_length(self, override: float | None) -> float:
        target = self.target_edge_length if override is None else override
        if target is None or not np.isfinite(target) or target <= 0.0:
            raise ValueError("target_edge_length must be finite and positive")
        return float(target)

    @staticmethod
    def _validate_metric_field(metric_field: np.ndarray | None) -> np.ndarray | None:
        if metric_field is None:
            return None
        values = np.asarray(metric_field, dtype=np.float64)
        if values.ndim != 3 or values.shape[1:] != (3, 3):
            raise ValueError("metric_field must have shape (n, 3, 3)")
        report = audit_spd_metrics(values)
        if not report.valid:
            raise ValueError("metric_field must contain finite SPD tensors")
        return 0.5 * (values + np.swapaxes(values, 1, 2))

    def _validate_metric_normals(self, normals: np.ndarray | None) -> np.ndarray | None:
        if normals is None:
            return None
        values = np.asarray(normals, dtype=np.float64)
        if values.shape != self.state.vertices.shape:
            raise ValueError("metric_normals must have the same shape as vertices")
        lengths = np.linalg.norm(values, axis=1)
        if np.any(lengths <= 1e-14) or not np.isfinite(values).all():
            raise ValueError("metric_normals must be finite and nonzero")
        return values.copy()

    def _validate_metric_feature_vertices(
        self,
        feature_vertices: np.ndarray | None,
    ) -> np.ndarray | None:
        if feature_vertices is None:
            return None
        values = np.asarray(feature_vertices, dtype=bool)
        if values.shape != (len(self.state.vertices),):
            raise ValueError("metric_feature_vertices must have shape (n,)")
        return values.copy()

    def _metric_edge_length(
        self,
        edge: tuple[int, int],
        override: float | None,
    ) -> float | None:
        if self.metric_field is None or override is not None:
            return None
        a, b = self._edge_vertices(edge)
        edge_rows = np.asarray([[a, b]], dtype=np.int64)
        try:
            if self.metric_normals is not None:
                return float(
                    tangent_metric_edge_lengths(
                        self.state.vertices,
                        edge_rows,
                        self.metric_field,
                        self.metric_normals,
                        max_normal_angle_deg=self.metric_max_normal_angle_deg,
                        feature_vertices=self.metric_feature_vertices,
                    )[0],
                )
            return float(metric_edge_lengths(self.state.vertices, edge_rows, self.metric_field)[0])
        except ValueError:
            # A feature edge or discontinuous normal has no admissible tangent
            # plane.  NaN makes both hysteresis predicates reject it without
            # falling back to an unrelated world-space metric.
            return float("nan")

    def _metric_after_split(self, a: int, b: int) -> np.ndarray | None:
        if self.metric_field is None:
            return None
        inserted = intersect_spd_metrics(
            self.metric_field[[a]],
            self.metric_field[[b]],
        )[0]
        return np.vstack((self.metric_field, inserted[None, ...]))

    def _metric_after_collapse(self, a: int, b: int) -> np.ndarray | None:
        if self.metric_field is None:
            return None
        merged = intersect_spd_metrics(
            self.metric_field[[a]],
            self.metric_field[[b]],
        )[0]
        values = np.delete(self.metric_field, b, axis=0)
        values[a] = merged
        return values

    def _metric_normals_after_split(self, a: int, b: int) -> np.ndarray | None:
        if self.metric_normals is None:
            return None
        inserted = self.metric_normals[a] + self.metric_normals[b]
        length = float(np.linalg.norm(inserted))
        if length <= 1e-14 or not np.isfinite(length):
            return None
        return np.vstack((self.metric_normals, inserted[None, :] / length))

    def _metric_normals_after_collapse(self, a: int, b: int) -> np.ndarray | None:
        if self.metric_normals is None:
            return None
        merged = self.metric_normals[a] + self.metric_normals[b]
        length = float(np.linalg.norm(merged))
        if length <= 1e-14 or not np.isfinite(length):
            return None
        values = np.delete(self.metric_normals, b, axis=0)
        values[a] = merged / length
        return values

    def _metric_features_after_split(self, a: int, b: int) -> np.ndarray | None:
        if self.metric_feature_vertices is None:
            return None
        inserted = bool(self.metric_feature_vertices[a] or self.metric_feature_vertices[b])
        return np.concatenate((self.metric_feature_vertices, np.asarray([inserted])))

    def _metric_features_after_collapse(self, a: int, b: int) -> np.ndarray | None:
        if self.metric_feature_vertices is None:
            return None
        values = np.delete(self.metric_feature_vertices, b, axis=0)
        values[a] = bool(self.metric_feature_vertices[a] or self.metric_feature_vertices[b])
        return values

    def _edge_target_length(
        self,
        edge: tuple[int, int],
        override: float | None,
    ) -> float:
        if override is not None:
            return self._target_length(override)
        if self.vertex_target_lengths is not None:
            a, b = self._edge_vertices(edge)
            # Dunyach et al. use the conservative endpoint minimum: a
            # high-curvature endpoint controls the whole edge. Averaging
            # would silently relax the fine endpoint and can suppress a
            # required split near a feature.
            return float(min(self.vertex_target_lengths[a], self.vertex_target_lengths[b]))
        return self._target_length(None)

    def _refresh_curvature_sizing(self) -> None:
        if self.curvature_epsilon is None:
            return
        self.vertex_target_lengths = estimate_curvature_sizing(
            self.state.vertices,
            self.state.faces,
            self.curvature_epsilon,
        )

    def _edge_vertices(self, edge: tuple[int, int]) -> tuple[int, int]:
        if len(edge) != 2:
            raise ValueError("edge must contain two vertex indices")
        a, b = int(edge[0]), int(edge[1])
        if (
            a == b
            or a < 0
            or b < 0
            or a >= len(self.state.vertices)
            or b >= len(self.state.vertices)
        ):
            raise ValueError("edge vertex index is invalid")
        return a, b

    def _edge_length(self, edge: tuple[int, int]) -> float:
        a, b = edge
        return float(np.linalg.norm(self.state.vertices[a] - self.state.vertices[b]))

    def _unique_edges(self) -> tuple[tuple[int, int], ...]:
        """Return the current mesh edges in deterministic lexical order.

        Cached per state: the collapse and flip phases ask for this once per
        loop iteration, and it only changes when ``self.state`` is rebound.
        """
        cached = self._cache_unique_edges
        if cached is not None:
            return cached
        edges = _sorted_unique_edges(self.state.faces)
        result = tuple((int(a), int(b)) for a, b in edges.tolist())
        self._cache_unique_edges = result
        return result

    @staticmethod
    def _build_split_candidate(
        mesh: MeshState,
        a: int,
        b: int,
        incident: list[int],
    ) -> tuple[np.ndarray, np.ndarray, FaceCorrespondence]:
        midpoint = (mesh.vertices[a] + mesh.vertices[b]) * 0.5
        new_vertex = len(mesh.vertices)
        vertices = np.vstack((mesh.vertices, midpoint))
        faces_out: list[list[int]] = []
        correspondence: list[tuple[int, int]] = []
        incident_set = set(incident)

        for old_index, face_array in enumerate(mesh.faces.tolist()):
            if old_index not in incident_set:
                faces_out.append(face_array)
                continue

            face = tuple(int(vertex) for vertex in face_array)
            for offset in range(3):
                x, y, z = face[offset], face[(offset + 1) % 3], face[(offset + 2) % 3]
                if {x, y} != {a, b}:
                    continue
                child_start = len(faces_out)
                faces_out.extend(([x, new_vertex, z], [new_vertex, y, z]))
                correspondence.extend(
                    ((old_index, child_start), (old_index, child_start + 1)),
                )
                break
            else:
                raise ValueError("incident face does not contain the split edge")

        return vertices, np.asarray(faces_out, dtype=np.int64), tuple(correspondence)

    @staticmethod
    def _build_collapse_candidate(
        mesh: MeshState,
        a: int,
        b: int,
        incident: list[int],
    ) -> tuple[np.ndarray, np.ndarray, FaceCorrespondence]:
        """Build a midpoint collapse and retain old/new face correspondence."""
        vertices = mesh.vertices.copy()
        vertices[a] = (vertices[a] + vertices[b]) * 0.5

        remap: np.ndarray = np.arange(len(vertices), dtype=np.int64)
        remap[b] = a
        remap[b + 1 :] -= 1
        vertices = np.delete(vertices, b, axis=0)

        faces_out: list[list[int]] = []
        correspondence: list[tuple[int, int]] = []
        for old_index, face_array in enumerate(mesh.faces.tolist()):
            mapped = [int(remap[int(vertex)]) for vertex in face_array]
            if len(set(mapped)) != 3:
                continue
            new_index = len(faces_out)
            faces_out.append(mapped)
            correspondence.append((old_index, new_index))

        return vertices, np.asarray(faces_out, dtype=np.int64), tuple(correspondence)

    @staticmethod
    def _build_flip_candidate(
        mesh: MeshState,
        a: int,
        b: int,
        incident: list[int],
    ) -> tuple[np.ndarray, np.ndarray, FaceCorrespondence]:
        """Build the alternate diagonal while preserving each face orientation."""
        if len(incident) != 2:
            raise ValueError("flip requires two incident faces")
        first_index, second_index = incident
        first = tuple(int(vertex) for vertex in mesh.faces[first_index])
        second = tuple(int(vertex) for vertex in mesh.faces[second_index])

        first_direction: tuple[int, int, int] | None = None
        for offset in range(3):
            x, y, z = first[offset], first[(offset + 1) % 3], first[(offset + 2) % 3]
            if {x, y} == {a, b}:
                first_direction = (x, y, z)
                break
        if first_direction is None:
            raise ValueError("first incident face does not contain the edge")
        x, y, c = first_direction

        second_direction: tuple[int, int, int] | None = None
        for offset in range(3):
            p, q, r = second[offset], second[(offset + 1) % 3], second[(offset + 2) % 3]
            if p == y and q == x:
                second_direction = (p, q, r)
                break
        if second_direction is None:
            raise ValueError("incident faces do not have opposite edge orientation")
        _, _, d = second_direction
        if c == d or c in (x, y) or d in (x, y):
            raise ValueError("flip would repeat a vertex")

        faces_out = mesh.faces.copy()
        faces_out[first_index] = np.asarray([c, x, d], dtype=np.int64)
        faces_out[second_index] = np.asarray([c, d, y], dtype=np.int64)
        correspondence = ((first_index, first_index), (second_index, second_index))
        return mesh.vertices.copy(), faces_out, correspondence

    @classmethod
    def _vertex_valence_deviation(cls, mesh: MeshState) -> int:
        """Return deviation from valence six (interior) or four (boundary).

        Vectorized restatement of the original per-vertex one-ring rescan,
        which was ``O(vertices * faces)``.  It computes the identical number:
        a vertex's valence is the count of *distinct* edges incident to it
        (self-edges of a degenerate face excluded, exactly as the neighbour
        set excluded the vertex itself), boundary vertices are the endpoints
        of any edge with a single face corner, and isolated vertices (valence
        zero) contribute nothing.
        """
        count = len(mesh.vertices)
        if count == 0 or mesh.faces.size == 0:
            return 0
        unique, counts = _unique_edges_with_counts(mesh.faces)

        boundary = np.zeros(count, dtype=bool)
        boundary_edges = unique[counts == 1]
        if boundary_edges.size:
            endpoints = boundary_edges.ravel()
            boundary[endpoints[(endpoints >= 0) & (endpoints < count)]] = True

        proper = unique[unique[:, 0] != unique[:, 1]].ravel()
        valence = np.bincount(
            proper[(proper >= 0) & (proper < count)],
            minlength=count,
        )[:count]

        target = np.where(boundary, 4, 6)
        deviation = np.abs(valence.astype(np.int64) - target)
        deviation[valence == 0] = 0
        return int(deviation.sum())

    @staticmethod
    def _triangle_quality(vertices: np.ndarray, face: np.ndarray) -> float:
        tri = vertices[np.asarray(face, dtype=np.int64)]
        edge01 = tri[1] - tri[0]
        edge12 = tri[2] - tri[1]
        edge20 = tri[0] - tri[2]
        denominator = float(
            np.dot(edge01, edge01) + np.dot(edge12, edge12) + np.dot(edge20, edge20),
        )
        area_twice = float(np.linalg.norm(np.cross(edge01, -edge20)))
        if denominator <= 0.0 or not np.isfinite(denominator) or not np.isfinite(area_twice):
            return 0.0
        return float((2.0 * np.sqrt(3.0) * area_twice) / denominator)

    @classmethod
    def _flip_improves(
        cls,
        before: MeshState,
        after: MeshState,
        face_correspondence: FaceCorrespondence | None,
        *,
        before_deviation: int | None = None,
    ) -> bool:
        """Require a strict valence or local minimum-quality improvement.

        ``before_deviation`` optionally supplies an already-computed
        ``_vertex_valence_deviation(before)``; every caller inside a flip scan
        compares against the same unchanged pre-edit state, so recomputing it
        per candidate edge was pure waste.  The disjunction is unchanged --
        the valence term is simply not evaluated when the quality term has
        already decided the answer.
        """
        if face_correspondence:
            old_quality = min(
                cls._triangle_quality(before.vertices, before.faces[old_index])
                for old_index, _ in face_correspondence
            )
            new_quality = min(
                cls._triangle_quality(after.vertices, after.faces[new_index])
                for _, new_index in face_correspondence
            )
        else:
            old_quality = min(cls._triangle_quality(before.vertices, face) for face in before.faces)
            new_quality = min(cls._triangle_quality(after.vertices, face) for face in after.faces)

        if new_quality > old_quality + 1e-12:
            return True
        reference = (
            cls._vertex_valence_deviation(before)
            if before_deviation is None
            else int(before_deviation)
        )
        return bool(cls._vertex_valence_deviation(after) < reference)

    @staticmethod
    def _link_condition(mesh: MeshState) -> bool:
        """Reject duplicate faces, repeated vertices, and non-manifold edges."""
        vertices, faces = mesh.vertices, mesh.faces
        if vertices.ndim != 2 or vertices.shape[1] != 3:
            return False
        if faces.ndim != 2 or faces.shape[1] != 3 or faces.size == 0:
            return False
        if not np.isfinite(vertices).all():
            return False
        if np.any(faces < 0) or np.any(faces >= len(vertices)):
            return False
        if np.any(faces[:, 0] == faces[:, 1]):
            return False
        if np.any(faces[:, 1] == faces[:, 2]):
            return False
        if np.any(faces[:, 2] == faces[:, 0]):
            return False
        # Vectorized restatement of the original Python scans: duplicate faces
        # are detected as repeated sorted index triples, and a non-manifold
        # edge as an undirected edge used by more than two face corners.
        sorted_faces = np.sort(faces, axis=1)
        face_keys = _encode_rows(sorted_faces)
        distinct = (
            len(np.unique(sorted_faces, axis=0))
            if face_keys is None
            else len(np.unique(face_keys))
        )
        if distinct != len(faces):
            return False
        _, edge_counts = _unique_edges_with_counts(faces)
        return bool(edge_counts.size == 0 or edge_counts.max() <= 2)

    @classmethod
    def _foldover_guard(
        cls,
        before: MeshState,
        after: MeshState,
        face_correspondence: FaceCorrespondence | None = None,
        *,
        after_triangles: np.ndarray | None = None,
        after_keys: list[bytes] | None = None,
    ) -> bool:
        """Reject zero-area or orientation-reversed triangles with exact signs."""
        triangles = after.vertices[after.faces] if after_triangles is None else after_triangles
        if not np.isfinite(triangles).all():
            return False
        twice_area = np.linalg.norm(
            np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]),
            axis=1,
        )
        if not np.all(twice_area > np.finfo(float).tiny):
            return False

        pairs = face_correspondence or cls._common_face_correspondence(before, after)
        pairs = cls._foldover_pairs_needing_exact_test(before, triangles, pairs, after_keys)
        for old_index, new_index in pairs:
            if old_index < 0 or old_index >= len(before.faces):
                return False
            if new_index < 0 or new_index >= len(after.faces):
                return False
            old_tri = before.vertices[before.faces[old_index]]
            new_tri = triangles[new_index]
            new_key = new_tri.tobytes() if after_keys is None else after_keys[new_index]
            if old_tri.tobytes() == new_key:
                # The pair's two triangles are bit-identical, so the probe
                # built from ``old_tri`` is the same point and ``old_sign``
                # and ``new_sign`` are the same call: the pair test collapses
                # exactly to "this triangle is non-degenerate", which is the
                # memoized single-triangle predicate below.  Nothing is
                # skipped -- the same question is answered from a memo.
                if not cls._triangle_orientation_certified(new_tri, new_key):
                    return False
                continue
            normal = np.cross(old_tri[1] - old_tri[0], old_tri[2] - old_tri[0])
            normal_length = float(np.linalg.norm(normal))
            if not np.isfinite(normal_length) or normal_length <= np.finfo(float).tiny:
                return False
            scale = max(float(np.max(np.linalg.norm(old_tri - old_tri[0], axis=1))), 1.0)
            probe = old_tri.mean(axis=0) + normal / normal_length * scale
            old_sign = cls._exact_orient3d(old_tri[0], old_tri[1], old_tri[2], probe)
            new_sign = cls._exact_orient3d(new_tri[0], new_tri[1], new_tri[2], probe)
            if old_sign == 0 or new_sign == 0 or old_sign != new_sign:
                return False
        return True

    @staticmethod
    def _foldover_pairs_needing_exact_test(
        before: MeshState,
        after_triangles: np.ndarray,
        pairs: FaceCorrespondence,
        after_keys: list[bytes] | None,
    ) -> FaceCorrespondence:
        """Drop the correspondence pairs that are provably already satisfied.

        A pair whose old and new triangles are bit-identical reduces exactly
        to "this triangle is non-degenerate" (see the identical-triangle
        branch in ``_foldover_guard``), and a triangle in
        ``_ORIENTATION_MEMO`` has already answered that question.  When *all*
        such pairs are certified in one batched ``set.issuperset`` call they
        can be dropped from the ordered loop without changing its verdict.
        If any of them is not certified the full original pair list is
        returned instead, so the loop's short-circuit order -- and therefore
        which guard reports the failure -- is preserved exactly.

        This is what keeps a single-vertex smoothing move ``O(one-ring)``
        instead of ``O(faces)``: its correspondence is the identity over
        every face, but only the moved vertex's ring actually changed.
        """
        count = len(pairs)
        if after_keys is None or count == 0:
            return pairs
        old_faces = before.faces
        new_count = len(after_triangles)
        indices = np.asarray(pairs, dtype=np.int64)
        old_index, new_index = indices[:, 0], indices[:, 1]
        if old_index.min() < 0 or old_index.max() >= len(old_faces):
            return pairs
        if new_index.min() < 0 or new_index.max() >= new_count:
            return pairs
        try:
            old_triangles = before.vertices[old_faces[old_index]]
        except IndexError:
            return pairs
        new_triangles = after_triangles[new_index]
        if old_triangles.shape != new_triangles.shape:
            return pairs

        identical = ~np.any(old_triangles != new_triangles, axis=(1, 2))
        if not identical.any():
            return pairs
        certified_rows = new_index[identical].tolist()
        if not _ORIENTATION_MEMO.issuperset(map(after_keys.__getitem__, certified_rows)):
            return pairs
        remaining = np.flatnonzero(~identical)
        return tuple(pairs[position] for position in remaining.tolist())

    @staticmethod
    def _common_face_correspondence(
        before: MeshState,
        after: MeshState,
    ) -> FaceCorrespondence:
        old_by_key = {
            tuple(sorted(map(int, face))): index for index, face in enumerate(before.faces.tolist())
        }
        pairs = []
        for new_index, face in enumerate(after.faces.tolist()):
            old_index = old_by_key.get(tuple(sorted(map(int, face))))
            if old_index is not None:
                pairs.append((old_index, new_index))
        return tuple(pairs)

    @classmethod
    def _exact_orientation_guard(
        cls,
        mesh: MeshState,
        *,
        triangles: np.ndarray | None = None,
        triangle_keys: list[bytes] | None = None,
    ) -> bool:
        """Require every triangle to have a non-zero Shewchuk exact sign.

        Every face is still consulted.  Faces whose three corner coordinates
        are bit-identical to a triangle already certified answer from
        ``_ORIENTATION_MEMO`` instead of re-running the exact predicate --
        which is what turns a one-vertex smoothing move from ``O(faces)``
        exact predicate calls into ``O(one-ring)``.
        """
        blocks = mesh.vertices[mesh.faces] if triangles is None else triangles
        keys = _triangle_keys(blocks) if triangle_keys is None else triangle_keys
        for index, key in enumerate(keys):
            if key in _ORIENTATION_MEMO:
                continue
            if not cls._triangle_orientation_ok(blocks[index]):
                return False
            cls._memoize_orientation(key)
        return True

    @staticmethod
    def _memoize_orientation(key: bytes) -> None:
        if len(_ORIENTATION_MEMO) >= _ORIENTATION_MEMO_LIMIT:
            _ORIENTATION_MEMO.clear()
        _ORIENTATION_MEMO.add(key)

    @classmethod
    def _triangle_orientation_certified(cls, tri: np.ndarray, key: bytes) -> bool:
        """Memoized ``_triangle_orientation_ok`` keyed on exact coordinates."""
        if key in _ORIENTATION_MEMO:
            return True
        if not cls._triangle_orientation_ok(tri):
            return False
        cls._memoize_orientation(key)
        return True

    @classmethod
    def _triangle_orientation_ok(cls, tri: np.ndarray) -> bool:
        """Return whether one triangle has a non-zero Shewchuk exact sign."""
        normal = np.cross(tri[1] - tri[0], tri[2] - tri[0])
        normal_length = float(np.linalg.norm(normal))
        if not np.isfinite(normal_length) or normal_length <= np.finfo(float).tiny:
            return False
        scale = max(float(np.max(np.linalg.norm(tri - tri[0], axis=1))), 1.0)
        probe = tri.mean(axis=0) + normal / normal_length * scale
        return cls._exact_orient3d(tri[0], tri[1], tri[2], probe) != 0

    @staticmethod
    def _exact_orient3d(a: np.ndarray, b: np.ndarray, c: np.ndarray, d: np.ndarray) -> int:
        """Call the bundled Shewchuk exact ``orient3d`` predicate."""
        from core.utils._shewchuk import orient3d

        if orient3d is None:
            raise RuntimeError("Shewchuk orient3d is unavailable")
        return int(orient3d(a, b, c, d))
