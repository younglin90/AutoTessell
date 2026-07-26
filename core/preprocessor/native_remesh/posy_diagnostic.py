"""QUAD-POSY1 -- diagnostic-only integer-offset ledger.

This module is a deliberately small, report-only bridge from the existing
deterministic multiresolution 4-RoSy field to the integer constraints used by
QuadriFlow (Huang et al. 2018).  It does not create, edit, pair, or extract
mesh faces.  In particular, importing this module has no effect on
``native_remesh`` or on any generator fallback.

The ledger uses one explicit local isotropic sizing value per triangle: the
mean length of its three edges.  Each directed edge is expressed in the
projected 4-RoSy representative at its tail, rounded to an integer 2-vector,
then rotated into the face frame by a deterministic quarter-turn.  For the
three resulting integer offsets ``o_0, o_1, o_2`` the report records:

* the unrotated and consistently rotated integer offsets;
* the three quarter-turn rotations;
* the regularity residual ``o_0 + o_1 + o_2``;
* the orientation determinant ``det(o_0, o_1)``;
* whether the candidate is a position-singularity/constraint violation.

The determinant is the signed 2-D determinant of the first two directed
offsets in the oriented triangle frame.  It is the integer diagnostic for the
non-negative orientation constraint in the card; a negative value is reported
as an inversion candidate, never repaired here.

The existing singularity ledger is consumed as an explicit branch contract.
Regular faces have the single admissible index ``(0,)``.  A centered 4-RoSy
residue ``2`` produces the explicit admissible pair ``(-2, 2)``.  Exclusive
or disagreeing extrinsic/intrinsic faces retain every value reported by the
two connections and remain unresolved.  No code in this module selects the
positive half-index or any other branch on behalf of a future solver.

This is a diagnostic reduction, not the full QuadriFlow integer solve: it has
no min-cost flow, SAT, continuous re-optimization, inversion cleanup, or
quad extraction.  Those stages are intentionally outside QUAD-POSY1.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

from core.preprocessor.native_remesh.rosy_diagnostic import (
    RosyDiagnosticReport,
    SingularityLedger,
    _edge_face_count,
    _vertex_adjacency,
    initial_orientation_field,
    optimize_orientations,
    optimize_orientations_multires,
    run_rosy_diagnostic,
    vertex_areas,
    vertex_normals,
    weld_vertices,
)
from core.utils.logging import get_logger

log = get_logger(__name__)

_EPS = 1e-12
POSY_ENV = "AUTO_TESSELL_QUAD_POSY1"


Int2 = tuple[int, int]
Int3 = tuple[Int2, Int2, Int2]


@dataclass(frozen=True)
class IntegerOffsetCandidate:
    """One explicit integer-offset branch for one triangle."""

    orientation_index: int
    raw_offsets: Int3
    rotations: tuple[int, int, int]
    rotated_offsets: Int3
    regularity_residual: Int2
    orientation_determinant: int

    @property
    def regular(self) -> bool:
        """Whether the integer offsets satisfy the zero-sum constraint."""

        return self.regularity_residual == (0, 0)

    @property
    def orientation_consistent(self) -> bool:
        """Whether the integer determinant meets the non-negative constraint."""

        return self.orientation_determinant >= 0

    @property
    def position_singularity(self) -> bool:
        """Whether this branch has a non-zero integer regularity residual."""

        return not self.regular

    @property
    def constraint_violation(self) -> bool:
        """Whether this branch violates regularity or orientation consistency."""

        return not self.regular or not self.orientation_consistent


@dataclass(frozen=True)
class PositionOffsetLedgerEntry:
    """One face's integer-offset candidates and explicit resolution state."""

    face: int
    face_vertex_ids: tuple[int, int, int]
    centroid: tuple[float, float, float]
    sizing: float
    extrinsic_index: int
    intrinsic_index: int
    admissible_orientation_indices: tuple[int, ...]
    unresolved: bool
    unresolved_reasons: tuple[str, ...]
    candidates: tuple[IntegerOffsetCandidate, ...]

    @property
    def regularity_residuals(self) -> tuple[Int2, ...]:
        return tuple(candidate.regularity_residual for candidate in self.candidates)

    @property
    def orientation_determinants(self) -> tuple[int, ...]:
        return tuple(candidate.orientation_determinant for candidate in self.candidates)

    @property
    def position_singularity(self) -> bool:
        """Conservative face census: any branch has a non-zero residual."""

        return any(candidate.position_singularity for candidate in self.candidates)

    @property
    def orientation_inversion(self) -> bool:
        return any(not candidate.orientation_consistent for candidate in self.candidates)

    @property
    def resolved_candidate(self) -> IntegerOffsetCandidate | None:
        """Return a candidate only when the source ledger permits one branch."""

        if self.unresolved or len(self.candidates) != 1:
            return None
        return self.candidates[0]


@dataclass(frozen=True)
class PositionOffsetLedger:
    """Deterministic, report-only integer-offset ledger over all input faces."""

    entries: tuple[PositionOffsetLedgerEntry, ...] = field(default_factory=tuple)
    source_singularity_ledger: SingularityLedger | None = None

    @property
    def n_faces(self) -> int:
        return len(self.entries)

    @property
    def position_singularity_count(self) -> int:
        return sum(entry.position_singularity for entry in self.entries)

    @property
    def regularity_failure_count(self) -> int:
        return sum(
            any(candidate.regularity_residual != (0, 0) for candidate in entry.candidates)
            for entry in self.entries
        )

    @property
    def orientation_inversion_count(self) -> int:
        return sum(entry.orientation_inversion for entry in self.entries)

    @property
    def unresolved_count(self) -> int:
        return sum(entry.unresolved for entry in self.entries)

    @property
    def resolved_count(self) -> int:
        return sum(entry.resolved_candidate is not None for entry in self.entries)

    @property
    def candidate_count(self) -> int:
        return sum(len(entry.candidates) for entry in self.entries)

    @property
    def regular_candidate_count(self) -> int:
        return sum(candidate.regular for entry in self.entries for candidate in entry.candidates)

    @property
    def orientation_consistent_candidate_count(self) -> int:
        return sum(
            candidate.orientation_consistent
            for entry in self.entries
            for candidate in entry.candidates
        )

    @property
    def max_regularity_residual_l1(self) -> int:
        residuals = (
            abs(x) + abs(y) for entry in self.entries for x, y in entry.regularity_residuals
        )
        return max(residuals, default=0)

    @property
    def total_offset_l1(self) -> int:
        return sum(
            abs(x) + abs(y)
            for entry in self.entries
            for candidate in entry.candidates
            for x, y in candidate.rotated_offsets
        )


@dataclass(frozen=True)
class PosyDiagnosticReport:
    """Per-shape QUAD-POSY1 report; no mesh data is changed."""

    shape_name: str
    n_vertices: int
    n_faces: int
    n_sweeps: int
    seed: int
    multires: bool
    rosy: RosyDiagnosticReport
    ledger: PositionOffsetLedger
    elapsed_s: float = 0.0

    @property
    def position_singularity_count(self) -> int:
        return self.ledger.position_singularity_count

    @property
    def unresolved_count(self) -> int:
        return self.ledger.unresolved_count

    @property
    def regularity_failure_count(self) -> int:
        return self.ledger.regularity_failure_count

    @property
    def orientation_inversion_count(self) -> int:
        return self.ledger.orientation_inversion_count


def posy_diagnostic_enabled() -> bool:
    """Return whether optional report-only POSY wiring was requested.

    No production caller currently wires this card.  The helper exists so a
    future report hook can use an explicit default-OFF switch without making
    an environment variable part of mesh generation.
    """

    return os.environ.get(POSY_ENV, "0").strip().lower() in {"1", "true", "yes", "on"}


def _normalize(vector: NDArray[np.float64], *, what: str) -> NDArray[np.float64]:
    length = float(np.linalg.norm(vector))
    if length <= _EPS:
        raise ValueError(f"cannot normalize degenerate {what}")
    return vector / length


def _project_to_plane(
    vector: NDArray[np.float64], normal: NDArray[np.float64]
) -> NDArray[np.float64]:
    return vector - float(np.dot(vector, normal)) * normal


def _quarter_turn(offset: Int2, turns: int) -> Int2:
    """Rotate an integer 2-vector by ``turns * 90`` degrees."""

    x, y = offset
    for _ in range(turns % 4):
        x, y = -y, x
    return x, y


def _round_integer(value: float) -> int:
    """Round a finite coordinate deterministically to the nearest integer."""

    if not np.isfinite(value):
        raise ValueError("non-finite position-field coordinate")
    return int(np.floor(value + 0.5) if value >= 0.0 else np.ceil(value - 0.5))


def _face_frame(
    V: NDArray[np.float64],
    face: NDArray[np.int64],
    Q: NDArray[np.float64],
) -> tuple[NDArray[np.float64], NDArray[np.float64], float]:
    points = V[face]
    edge0 = points[1] - points[0]
    edge1 = points[2] - points[0]
    normal = _normalize(np.cross(edge0, edge1), what="face normal")
    edge_vectors = (points[1] - points[0], points[2] - points[1], points[0] - points[2])
    sizing = float(np.mean([np.linalg.norm(edge) for edge in edge_vectors]))
    if sizing <= _EPS:
        raise ValueError("cannot size degenerate face")

    projected = [_project_to_plane(Q[int(vertex)], normal) for vertex in face]
    try:
        face_x = _normalize(sum(projected, start=np.zeros(3, dtype=np.float64)), what="face field")
    except ValueError:
        longest = max(edge_vectors, key=lambda edge: float(np.linalg.norm(edge)))
        face_x = _normalize(longest, what="face fallback field")
    return normal, face_x, sizing


def _face_candidate(
    V: NDArray[np.float64],
    face: NDArray[np.int64],
    Q: NDArray[np.float64],
    normal: NDArray[np.float64],
    face_x: NDArray[np.float64],
    sizing: float,
    orientation_index: int,
) -> IntegerOffsetCandidate:
    points = V[face]
    raw: list[Int2] = []
    rotations: list[int] = []
    for corner in range(3):
        local_x = _normalize(
            _project_to_plane(Q[int(face[corner])], normal),
            what="vertex field in face plane",
        )
        local_y = _normalize(np.cross(normal, local_x), what="vertex field transverse")
        edge = points[(corner + 1) % 3] - points[corner]
        local_offset = (
            _round_integer(float(np.dot(edge, local_x) / sizing)),
            _round_integer(float(np.dot(edge, local_y) / sizing)),
        )
        scores = []
        for turns in range(4):
            if turns == 0:
                candidate_x = local_x
            elif turns == 1:
                candidate_x = np.cross(normal, local_x)
            elif turns == 2:
                candidate_x = -local_x
            else:
                candidate_x = -np.cross(normal, local_x)
            scores.append(float(np.dot(candidate_x, face_x)))
        turn = max(range(4), key=lambda value: (scores[value], -value))
        raw.append(local_offset)
        rotations.append(turn)

    rotated = tuple(_quarter_turn(raw[index], rotations[index]) for index in range(3))
    residual = (
        sum(offset[0] for offset in rotated),
        sum(offset[1] for offset in rotated),
    )
    determinant = rotated[0][0] * rotated[1][1] - rotated[0][1] * rotated[1][0]
    return IntegerOffsetCandidate(
        orientation_index=orientation_index,
        raw_offsets=(raw[0], raw[1], raw[2]),
        rotations=(rotations[0], rotations[1], rotations[2]),
        rotated_offsets=(rotated[0], rotated[1], rotated[2]),
        regularity_residual=residual,
        orientation_determinant=int(determinant),
    )


def _source_options(
    source_entry: object | None,
) -> tuple[tuple[int, ...], bool, tuple[str, ...], int, int]:
    if source_entry is None:
        return (0,), False, (), 0, 0
    # Avoid importing the concrete ledger entry solely for this small readout;
    # these attributes are part of the QUAD-SINGULARITY1 frozen contract.
    extrinsic_index = int(getattr(source_entry, "extrinsic_index"))
    intrinsic_index = int(getattr(source_entry, "intrinsic_index"))
    extrinsic_options = tuple(
        int(value) for value in getattr(source_entry, "extrinsic_admissible_indices")
    )
    intrinsic_options = tuple(
        int(value) for value in getattr(source_entry, "intrinsic_admissible_indices")
    )
    options = tuple(sorted(set(extrinsic_options + intrinsic_options)))
    reasons: list[str] = []
    if bool(getattr(source_entry, "ambiguous")):
        reasons.append("half-index-ambiguous")
    if bool(getattr(source_entry, "connection_disagreement")):
        reasons.append("connection-disagreement")
    if getattr(source_entry, "category") != "shared":
        reasons.append("connection-exclusive")
    return (
        options,
        bool(getattr(source_entry, "unresolved")),
        tuple(reasons),
        extrinsic_index,
        intrinsic_index,
    )


def build_position_offset_ledger(
    vertices: NDArray[np.float64],
    faces: NDArray[np.int64],
    orientation_field: NDArray[np.float64],
    singularity_ledger: SingularityLedger | None = None,
    *,
    target_edge_length: float | None = None,
) -> PositionOffsetLedger:
    """Build an immutable integer-offset ledger without changing its inputs.

    ``orientation_field`` must be the deterministic vertex field returned by
    the QUAD-ROSY1 solver.  If no source singularity ledger is supplied, every
    face is treated as regular with the sole explicit index ``0``; production
    POSY runs always supply the existing extrinsic/intrinsic ledger.
    """

    V = np.asarray(vertices, dtype=np.float64)
    F = np.asarray(faces, dtype=np.int64)
    Q = np.asarray(orientation_field, dtype=np.float64)
    if V.ndim != 2 or V.shape[1] != 3:
        raise ValueError("vertices must have shape (n, 3)")
    if F.ndim != 2 or F.shape[1] != 3:
        raise ValueError("faces must have shape (m, 3)")
    if Q.shape != V.shape:
        raise ValueError("orientation_field must have the same shape as vertices")
    if target_edge_length is not None and target_edge_length <= _EPS:
        raise ValueError("target_edge_length must be positive")

    source_by_face = {
        entry.face: entry
        for entry in (singularity_ledger.entries if singularity_ledger is not None else ())
    }
    entries: list[PositionOffsetLedgerEntry] = []
    for face_id, face in enumerate(F):
        normal, face_x, local_sizing = _face_frame(V, face, Q)
        sizing = float(target_edge_length if target_edge_length is not None else local_sizing)
        source_entry = source_by_face.get(face_id)
        options, unresolved, reasons, extrinsic_index, intrinsic_index = _source_options(
            source_entry
        )
        candidates = tuple(
            _face_candidate(V, face, Q, normal, face_x, sizing, orientation_index)
            for orientation_index in options
        )
        centroid_array = V[face].mean(axis=0)
        entries.append(
            PositionOffsetLedgerEntry(
                face=face_id,
                face_vertex_ids=(int(face[0]), int(face[1]), int(face[2])),
                centroid=(
                    float(centroid_array[0]),
                    float(centroid_array[1]),
                    float(centroid_array[2]),
                ),
                sizing=sizing,
                extrinsic_index=extrinsic_index,
                intrinsic_index=intrinsic_index,
                admissible_orientation_indices=options,
                unresolved=unresolved,
                unresolved_reasons=reasons,
                candidates=candidates,
            )
        )
    return PositionOffsetLedger(
        entries=tuple(entries), source_singularity_ledger=singularity_ledger
    )


def _build_rosy_field(
    V: NDArray[np.float64],
    F: NDArray[np.int64],
    *,
    n_sweeps: int,
    seed: int,
    multires: bool,
) -> NDArray[np.float64]:
    edge_counts = _edge_face_count(F)
    edges = np.asarray(sorted(edge_counts), dtype=np.int64).reshape(-1, 2)
    normals = vertex_normals(V, F)
    initial = initial_orientation_field(normals, seed=seed)
    adjacency = _vertex_adjacency(F, int(V.shape[0]))
    if not multires:
        field, _trace = optimize_orientations(normals, adjacency, initial, edges, n_sweeps=n_sweeps)
        return field
    field, _trace, _stats = optimize_orientations_multires(
        normals,
        adjacency,
        initial,
        edges,
        positions=V,
        areas=vertex_areas(V, F),
        n_sweeps=n_sweeps,
        seed=seed,
    )
    return field


def run_posy_diagnostic(
    vertices: NDArray[np.float64],
    faces: NDArray[np.int64],
    shape_name: str,
    *,
    n_sweeps: int = 20,
    seed: int = 0,
    weld: bool = True,
    multires: bool = True,
    target_edge_length: float | None = None,
) -> PosyDiagnosticReport:
    """Run QUAD-POSY1 on a scratch copy and return its report-only ledger.

    Multiresolution is the default because QUAD-MULTIRES1 showed materially
    lower seed variance and is the required upstream mode for this card.  The
    ``multires=False`` A/B remains available for falsification and does not
    alter the existing QUAD-ROSY1 default.
    """

    t0 = time.perf_counter()
    V = np.asarray(vertices, dtype=np.float64)
    F = np.asarray(faces, dtype=np.int64)
    if weld:
        V, F = weld_vertices(V, F)
    rosy = run_rosy_diagnostic(
        V,
        F,
        shape_name,
        n_sweeps=n_sweeps,
        seed=seed,
        weld=False,
        with_curvature=False,
        multires=multires,
    )
    if rosy.extrinsic is None or rosy.intrinsic is None or rosy.ledger is None:
        raise RuntimeError("QUAD-ROSY1 did not return both connection ledgers")
    Q = _build_rosy_field(V, F, n_sweeps=n_sweeps, seed=seed, multires=multires)
    ledger = build_position_offset_ledger(
        V,
        F,
        Q,
        rosy.ledger,
        target_edge_length=target_edge_length,
    )
    report = PosyDiagnosticReport(
        shape_name=shape_name,
        n_vertices=int(V.shape[0]),
        n_faces=int(F.shape[0]),
        n_sweeps=n_sweeps,
        seed=seed,
        multires=multires,
        rosy=rosy,
        ledger=ledger,
        elapsed_s=time.perf_counter() - t0,
    )
    log.info(
        "quad_posy_diagnostic",
        shape=shape_name,
        multires=multires,
        n_vertices=report.n_vertices,
        n_faces=report.n_faces,
        candidate_count=ledger.candidate_count,
        position_singularity_count=ledger.position_singularity_count,
        regularity_failure_count=ledger.regularity_failure_count,
        orientation_inversion_count=ledger.orientation_inversion_count,
        unresolved_count=ledger.unresolved_count,
        max_regularity_residual_l1=ledger.max_regularity_residual_l1,
        elapsed_s=round(report.elapsed_s, 3),
    )
    return report


def run_posy_diagnostic_if_enabled(
    vertices: NDArray[np.float64],
    faces: NDArray[np.int64],
    shape_name: str,
    **kwargs: object,
) -> PosyDiagnosticReport | None:
    """Optional future report hook; default OFF and never a mesh path."""

    if not posy_diagnostic_enabled():
        return None
    return run_posy_diagnostic(vertices, faces, shape_name, **kwargs)  # type: ignore[arg-type]


__all__ = [
    "IntegerOffsetCandidate",
    "POSY_ENV",
    "PositionOffsetLedger",
    "PositionOffsetLedgerEntry",
    "PosyDiagnosticReport",
    "build_position_offset_ledger",
    "posy_diagnostic_enabled",
    "run_posy_diagnostic",
    "run_posy_diagnostic_if_enabled",
]
