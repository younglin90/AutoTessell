"""Transactional skeleton for the future native-tri local-operator loop.

This Phase-0 module deliberately performs no quality move.  A caller may pass
an externally proposed ``(vertices, faces)`` candidate to ``attempt``; the
candidate is committed only after topology, fold-over, and exact-orientation
guards pass.  A rejected candidate leaves the state byte-for-byte unchanged.
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


class OperatorTransaction:
    """Guarded commit/rollback boundary for split, collapse, and flip.

    ``attempt(kind)`` is a safe no-op rejection until a real operator proposal
    is supplied.  This makes the skeleton usable in Phase 0 without silently
    changing the existing L2 remesher.
    """

    def __init__(self, vertices: np.ndarray, faces: np.ndarray) -> None:
        self.state = MeshState(
            np.asarray(vertices, dtype=np.float64).copy(),
            np.asarray(faces, dtype=np.int64).copy(),
        )

    def attempt(
        self,
        operator: OperatorKind,
        candidate: tuple[np.ndarray, np.ndarray] | None = None,
    ) -> GuardReport:
        """Validate and conditionally commit a proposed local operation."""
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
            if not self._foldover_guard(before, after):
                return GuardReport(False, operator, "foldover_guard_failed")
            if not self._exact_orientation_guard(after):
                return GuardReport(False, operator, "exact_orientation_failed")
        except (TypeError, ValueError, IndexError, FloatingPointError):
            self.state = before
            return GuardReport(False, operator, "malformed_candidate")

        self.state = MeshState(after.vertices.copy(), after.faces.copy())
        return GuardReport(True, operator, "committed")

    @staticmethod
    def _link_condition(mesh: MeshState) -> bool:
        """Reject duplicate faces, repeated vertices, and non-manifold edges."""
        V, F = mesh.vertices, mesh.faces
        if V.ndim != 2 or V.shape[1] != 3 or F.ndim != 2 or F.shape[1] != 3:
            return False
        if not np.isfinite(V).all() or F.size == 0:
            return False
        if np.any(F < 0) or np.any(F >= len(V)):
            return False
        if np.any(F[:, 0] == F[:, 1]) or np.any(F[:, 1] == F[:, 2]) or np.any(F[:, 2] == F[:, 0]):
            return False
        face_keys = {tuple(sorted(map(int, row))) for row in F}
        if len(face_keys) != len(F):
            return False
        edge_count: dict[tuple[int, int], int] = {}
        for a, b, c in F.tolist():
            for u, v in ((a, b), (b, c), (c, a)):
                key = (u, v) if u < v else (v, u)
                edge_count[key] = edge_count.get(key, 0) + 1
        return all(count <= 2 for count in edge_count.values())

    @staticmethod
    def _foldover_guard(before: MeshState, after: MeshState) -> bool:
        """Require every resulting triangle to have positive finite area."""
        del before  # The full correspondence map arrives with real operators.
        tri = after.vertices[after.faces]
        twice_area = np.linalg.norm(
            np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1,
        )
        return bool(
            twice_area.size
            and np.isfinite(twice_area).all()
            and np.all(twice_area > 1e-14)
        )

    @staticmethod
    def _exact_orientation_guard(mesh: MeshState) -> bool:
        """Use the bundled Shewchuk orient3d sign on each triangle."""
        try:
            from core.utils._shewchuk import orient3d
        except Exception:
            return False
        for a, b, c in mesh.faces.tolist():
            pa, pb, pc = mesh.vertices[[a, b, c]]
            normal = np.cross(pb - pa, pc - pa)
            norm = float(np.linalg.norm(normal))
            if not np.isfinite(norm) or norm <= 1e-14:
                return False
            d = (pa + pb + pc) / 3.0 + normal / norm
            if int(orient3d(pa, pb, pc, d)) == 0:
                return False
        return True
