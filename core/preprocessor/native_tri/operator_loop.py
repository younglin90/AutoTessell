"""Transactional native-tri edge-split operator.

The MVP deliberately implements only edge split.  Long edges are selected with
the Botsch/Dunyach upper hysteresis bound ``|e| > 4L/3``.  A proposed split is
committed only after the edge link, mesh link, and exact orientation guards
pass; every rejected proposal leaves the transaction state unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy as np


class OperatorKind(StrEnum):
    """Local operators reserved for the native-tri MVP."""

    SPLIT = "split"
    COLLAPSE = "collapse"
    FLIP = "flip"


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


FaceCorrespondence = tuple[tuple[int, int], ...]


class OperatorTransaction:
    """Transactional boundary for the native-tri split operator.

    ``target_edge_length`` is the reference length ``L`` in the
    Botsch/Dunyach hysteresis rule.  Collapse and flip remain reserved enum
    values, but are intentionally rejected because this MVP implements split
    only.
    """

    def __init__(
        self,
        vertices: np.ndarray,
        faces: np.ndarray,
        target_edge_length: float | None = None,
    ) -> None:
        self.state = MeshState(
            np.asarray(vertices, dtype=np.float64).copy(),
            np.asarray(faces, dtype=np.int64).copy(),
        )
        self.target_edge_length = target_edge_length

    def attempt(
        self,
        operator: OperatorKind,
        candidate: tuple[np.ndarray, np.ndarray] | None = None,
        *,
        face_correspondence: FaceCorrespondence | None = None,
    ) -> GuardReport:
        """Validate and conditionally commit a proposed split candidate.

        ``face_correspondence`` contains ``(old_face, new_face)`` pairs for
        faces whose orientation must be preserved.  The split builder supplies
        this for every child face; direct callers may omit it, in which case
        unchanged face keys are matched automatically.
        """
        before = self.state.copy()
        if operator is not OperatorKind.SPLIT:
            return GuardReport(False, operator, "operator_not_implemented")
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
        except (TypeError, ValueError, IndexError, FloatingPointError, RuntimeError):
            self.state = before
            reason = (
                "exact_orientation_failed"
                if operator is OperatorKind.SPLIT
                else "malformed_candidate"
            )
            return GuardReport(False, operator, reason)

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
