"""Transactional native-tri local operators.

The operator loop follows the Botsch/Dunyach hysteresis bounds: split edges
longer than ``4L/3`` and collapse edges shorter than ``4L/5``.  Split,
collapse, and flip proposals all share the same transactional link, fold-over,
and exact-orientation guards.  Rejected proposals leave the state unchanged.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

import numpy as np


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


class OperatorTransaction:
    """Transactional boundary for the native-tri local operators.

    ``target_edge_length`` is the reference length ``L`` in the
    Botsch/Dunyach hysteresis rule.  The one-round driver applies split,
    collapse, flip, and guarded tangential relocation; no sizing or anisotropic
    metric is introduced here.
    """

    def __init__(
        self,
        vertices: np.ndarray,
        faces: np.ndarray,
        target_edge_length: float | None = None,
        *,
        surface_points: np.ndarray | None = None,
        surface_projection: SurfaceProjection | None = None,
        surface_vertices: Iterable[int] | None = None,
    ) -> None:
        self.state = MeshState(
            np.asarray(vertices, dtype=np.float64).copy(),
            np.asarray(faces, dtype=np.int64).copy(),
        )
        self.target_edge_length = target_edge_length
        self.surface_points = (
            None if surface_points is None else np.asarray(surface_points, dtype=np.float64).copy()
        )
        self.surface_projection = surface_projection
        self.surface_vertices = (
            None if surface_vertices is None else tuple(int(index) for index in surface_vertices)
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
            if not self._link_condition(after):
                return GuardReport(False, operator, "link_condition_failed")
            if not self._foldover_guard(before, after, face_correspondence):
                return GuardReport(False, operator, "foldover_guard_failed")
            if not self._exact_orientation_guard(after):
                return GuardReport(False, operator, "exact_orientation_failed")
            if operator is OperatorKind.FLIP and not self._flip_improves(
                before,
                after,
                face_correspondence,
            ):
                return GuardReport(False, operator, "flip_not_improved")
        except (TypeError, ValueError, IndexError, FloatingPointError, RuntimeError):
            self.state = before
            return GuardReport(False, operator, "exact_orientation_failed")

        self.state = MeshState(after.vertices.copy(), after.faces.copy())
        return GuardReport(True, operator, "committed")

    def should_split_edge(
        self,
        edge: tuple[int, int],
        target_edge_length: float | None = None,
    ) -> bool:
        """Return whether ``edge`` exceeds the upper split hysteresis bound."""
        target = self._target_length(target_edge_length)
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
            target = self._target_length(target_edge_length)
            a, b = self._edge_vertices(edge)
            edge_length = float(np.linalg.norm(before.vertices[a] - before.vertices[b]))
            if not np.isfinite(edge_length):
                return GuardReport(False, OperatorKind.SPLIT, "malformed_edge")
            if edge_length <= (4.0 / 3.0) * target:
                return GuardReport(False, OperatorKind.SPLIT, "split_threshold_not_exceeded")

            incident = self._edge_link_condition(before, a, b)
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

        report = self.attempt(
            OperatorKind.SPLIT,
            (vertices, faces),
            face_correspondence=correspondence,
        )
        if not report.accepted:
            self.state = before
        return report

    def should_collapse_edge(
        self,
        edge: tuple[int, int],
        target_edge_length: float | None = None,
    ) -> bool:
        """Return whether ``edge`` is below the strict collapse bound."""
        target = self._target_length(target_edge_length)
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
            target = self._target_length(target_edge_length)
            a, b = self._edge_vertices(edge)
            a, b = min(a, b), max(a, b)
            edge_length = float(np.linalg.norm(before.vertices[a] - before.vertices[b]))
            if not np.isfinite(edge_length):
                return GuardReport(False, OperatorKind.COLLAPSE, "malformed_edge")
            if edge_length >= (4.0 / 5.0) * target:
                return GuardReport(
                    False,
                    OperatorKind.COLLAPSE,
                    "collapse_threshold_not_exceeded",
                )

            incident = self._collapse_edge_link_condition(before, a, b)
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

        report = self.attempt(
            OperatorKind.COLLAPSE,
            (vertices, faces),
            face_correspondence=correspondence,
        )
        if not report.accepted:
            self.state = before
        return report

    def should_flip_edge(self, edge: tuple[int, int]) -> bool:
        """Return whether flipping ``edge`` is a guarded quality move."""
        a, b = self._edge_vertices(edge)
        incident = self._edge_link_condition(self.state, a, b)
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
        )

    def flip_edge(self, edge: tuple[int, int]) -> GuardReport:
        """Flip one internal edge when valence or local triangle quality improves."""
        before = self.state.copy()
        try:
            a, b = self._edge_vertices(edge)
            incident = self._edge_link_condition(before, a, b)
            if incident is None or len(incident) != 2:
                return GuardReport(False, OperatorKind.FLIP, "link_condition_failed")
            vertices, faces, correspondence = self._build_flip_candidate(
                before,
                a,
                b,
                incident,
            )
            after = MeshState(vertices, faces)
            if not self._flip_improves(before, after, correspondence):
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
        surface_points: np.ndarray | None = None,
        surface_projection: SurfaceProjection | None = None,
        surface_vertices: Iterable[int] | None = None,
    ) -> GuardReport:
        """Tangentially relocate one vertex with transactional rejection.

        The target is an area-weighted centroid of the vertex's one-ring
        neighbours.  Only the displacement tangent to the area-weighted
        vertex normal is applied.  Projection is then applied when the vertex
        is a declared surface vertex; the full mesh is checked before commit.
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
            factor = self._relocation_factor(relocation_lambda)
            centroid_and_normal = self._area_weighted_neighbor_centroid(before, index)
            if centroid_and_normal is None:
                return GuardReport(
                    False,
                    OperatorKind.SMOOTH,
                    "smooth_degenerate_vertex",
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
        correspondence = tuple((face_index, face_index) for face_index in range(len(before.faces)))
        report = self.attempt(
            OperatorKind.SMOOTH,
            (vertices, before.faces.copy()),
            face_correspondence=correspondence,
        )
        return GuardReport(report.accepted, report.operator, report.reason, index)

    def smooth_vertices(
        self,
        vertex_indices: Iterable[int] | None = None,
        *,
        relocation_lambda: float = 0.5,
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
        target = self._target_length(target_edge_length)
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
        surface_points: np.ndarray | None = None,
        surface_projection: SurfaceProjection | None = None,
        surface_vertices: Iterable[int] | None = None,
    ) -> tuple[GuardReport, ...]:
        """Compatibility name for the split/collapse/flip/smooth pass."""
        return self.run_one_round(
            target_edge_length,
            smooth=smooth,
            relocation_lambda=relocation_lambda,
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
        surface_points: np.ndarray | None = None,
        surface_projection: SurfaceProjection | None = None,
        surface_vertices: Iterable[int] | None = None,
    ) -> tuple[tuple[GuardReport, ...], ...]:
        """Run at most ``max_rounds`` and stop after a fully rejected round."""
        if isinstance(max_rounds, bool) or int(max_rounds) != max_rounds:
            raise ValueError("max_rounds must be an integer")
        if max_rounds < 0:
            raise ValueError("max_rounds must be non-negative")
        rounds: list[tuple[GuardReport, ...]] = []
        for _ in range(max_rounds):
            reports = self.run_one_round(
                target_edge_length,
                relocation_lambda=relocation_lambda,
                surface_points=surface_points,
                surface_projection=surface_projection,
                surface_vertices=surface_vertices,
            )
            rounds.append(reports)
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
    ) -> tuple[np.ndarray, np.ndarray] | None:
        """Return the area-weighted one-ring centroid and vertex normal."""
        weighted_centroid: np.ndarray = np.zeros(3, dtype=np.float64)
        weighted_normal: np.ndarray = np.zeros(3, dtype=np.float64)
        total_area = 0.0
        for face in mesh.faces.tolist():
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

    def _target_length(self, override: float | None) -> float:
        target = self.target_edge_length if override is None else override
        if target is None or not np.isfinite(target) or target <= 0.0:
            raise ValueError("target_edge_length must be finite and positive")
        return float(target)

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
        """Return the current mesh edges in deterministic lexical order."""
        edges: set[tuple[int, int]] = set()
        for face in self.state.faces.tolist():
            for u, v in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])):
                edges.add((min(int(u), int(v)), max(int(u), int(v))))
        return tuple(sorted(edges))

    @classmethod
    def _edge_link_condition(
        cls,
        mesh: MeshState,
        a: int,
        b: int,
    ) -> list[int] | None:
        """Return incident faces only for a manifold edge eligible to split."""
        if not cls._link_condition(mesh):
            return None
        incident = [
            index for index, face in enumerate(mesh.faces.tolist()) if a in face and b in face
        ]
        if not 1 <= len(incident) <= 2:
            return None
        opposite = []
        for index in incident:
            face = mesh.faces[index].tolist()
            opposite.append(next(vertex for vertex in face if vertex not in (a, b)))
        if len(set(opposite)) != len(opposite):
            return None
        return incident

    @classmethod
    def _collapse_edge_link_condition(
        cls,
        mesh: MeshState,
        a: int,
        b: int,
    ) -> list[int] | None:
        """Return incident faces only when the edge satisfies the collapse link."""
        incident = cls._edge_link_condition(mesh, a, b)
        if incident is None:
            return None

        neighbours_a = cls._vertex_neighbours(mesh.faces, a)
        neighbours_b = cls._vertex_neighbours(mesh.faces, b)
        common = neighbours_a.intersection(neighbours_b)
        opposite = {
            vertex
            for index in incident
            for vertex in mesh.faces[index].tolist()
            if vertex not in (a, b)
        }
        if common != opposite:
            return None
        return incident

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

    @staticmethod
    def _vertex_neighbours(faces: np.ndarray, vertex: int) -> set[int]:
        neighbours: set[int] = set()
        for face in faces.tolist():
            if vertex not in face:
                continue
            neighbours.update(int(other) for other in face if int(other) != vertex)
        return neighbours

    @classmethod
    def _vertex_valence_deviation(cls, mesh: MeshState) -> int:
        """Return deviation from valence six (interior) or four (boundary)."""
        edge_faces: dict[tuple[int, int], int] = {}
        for face in mesh.faces.tolist():
            for u, v in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])):
                key = (min(int(u), int(v)), max(int(u), int(v)))
                edge_faces[key] = edge_faces.get(key, 0) + 1

        boundary = [False] * len(mesh.vertices)
        for (u, v), count in edge_faces.items():
            if count == 1:
                boundary[u] = True
                boundary[v] = True

        deviation = 0
        for vertex in range(len(mesh.vertices)):
            valence = len(cls._vertex_neighbours(mesh.faces, vertex))
            if valence == 0:
                continue
            target = 4 if boundary[vertex] else 6
            deviation += abs(valence - target)
        return deviation

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
    ) -> bool:
        """Require a strict valence or local minimum-quality improvement."""
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

        quality_improved = new_quality > old_quality + 1e-12
        valence_improved = cls._vertex_valence_deviation(after) < cls._vertex_valence_deviation(
            before,
        )
        return bool(quality_improved or valence_improved)

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
        face_keys = {tuple(sorted(map(int, row))) for row in faces}
        if len(face_keys) != len(faces):
            return False

        edge_count: dict[tuple[int, int], int] = {}
        for a, b, c in faces.tolist():
            for u, v in ((a, b), (b, c), (c, a)):
                key = (u, v) if u < v else (v, u)
                edge_count[key] = edge_count.get(key, 0) + 1
        return all(count <= 2 for count in edge_count.values())

    @classmethod
    def _foldover_guard(
        cls,
        before: MeshState,
        after: MeshState,
        face_correspondence: FaceCorrespondence | None = None,
    ) -> bool:
        """Reject zero-area or orientation-reversed triangles with exact signs."""
        triangles = after.vertices[after.faces]
        if not np.isfinite(triangles).all():
            return False
        twice_area = np.linalg.norm(
            np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]),
            axis=1,
        )
        if not np.all(twice_area > np.finfo(float).tiny):
            return False

        pairs = face_correspondence or cls._common_face_correspondence(before, after)
        for old_index, new_index in pairs:
            if old_index < 0 or old_index >= len(before.faces):
                return False
            if new_index < 0 or new_index >= len(after.faces):
                return False
            old_tri = before.vertices[before.faces[old_index]]
            new_tri = after.vertices[after.faces[new_index]]
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
    def _exact_orientation_guard(cls, mesh: MeshState) -> bool:
        """Require every triangle to have a non-zero Shewchuk exact sign."""
        for face in mesh.faces.tolist():
            tri = mesh.vertices[np.asarray(face, dtype=np.int64)]
            normal = np.cross(tri[1] - tri[0], tri[2] - tri[0])
            normal_length = float(np.linalg.norm(normal))
            if not np.isfinite(normal_length) or normal_length <= np.finfo(float).tiny:
                return False
            scale = max(float(np.max(np.linalg.norm(tri - tri[0], axis=1))), 1.0)
            probe = tri.mean(axis=0) + normal / normal_length * scale
            if cls._exact_orient3d(tri[0], tri[1], tri[2], probe) == 0:
                return False
        return True

    @staticmethod
    def _exact_orient3d(a: np.ndarray, b: np.ndarray, c: np.ndarray, d: np.ndarray) -> int:
        """Call the bundled Shewchuk exact ``orient3d`` predicate."""
        from core.utils._shewchuk import orient3d

        if orient3d is None:
            raise RuntimeError("Shewchuk orient3d is unavailable")
        return int(orient3d(a, b, c, d))
