"""HEX-MATCH-2 — executable local hex repair behind a hard quality gate.

Continues :mod:`core.generator.native_hex.match_diagnostic` (HEX-MATCH-1, which
is targeting-only and makes zero mesh edits).  This module performs the actual
mesh edit that HEX-MATCH-1's decision selects, wrapped in the reject-and-rollback
transaction pattern already validated in ``native_tet``/``native_poly`` this
campaign: build the candidate operation on a *scratch* copy, measure the
project's own OpenFOAM boundary skewness / internal skewness / non-orthogonality
on the affected neighbourhood only, and splice the result into the live mesh
**only** if it strictly improves the flagged face without regressing anything
else locally.  A candidate that fails is discarded whole — the live mesh is
never left partially edited, because it is never touched until the scratch
construction has already passed the gate.

Targeting is NOT re-derived here.  ``run_match_repair`` calls
``match_diagnostic.compute_boundary_face_skew`` / ``flag_bad_skew_faces`` /
``classify_repair_candidates`` directly, so HEX-MATCH-2 executes exactly the
targets HEX-MATCH-1 reports by construction; the falsification check in
``scripts/diag_hex_match_repair.py`` re-runs the diagnostic on a pristine copy
of the input and asserts set-equality against what this module attempted, which
catches the one real divergence risk (accidental in-place mutation of the caller's
arrays before the diagnostic view is taken).

Operations
----------

**Pillow insertion** (``candidate_type == "pillow"``, footprint ``{owner}``) —
the Mitchell & Tautges 1995 pillow with shrink set = the single owner hex, as
scoped in ``ledoux2010_sheet_operations.md``: the cell's 8 nodes are *duplicated*
inward and the 6 original faces are inflated into 6 new hexes, so the cell
becomes 7 cells and 8 new **interior** nodes.  Every pre-existing node keeps its
exact position, and every original face of the cell is re-emitted with its
original vertex list and winding, so neighbouring cells are bit-identical
afterwards and no boundary vertex moves — the Section 7.3 invariant.

Why this moves the metric at all: Ledoux 2010 is explicit that pillowing is
topology-only and does not itself relieve skew — what it supplies is the degree
of freedom.  The flagged boundary face's *owner* becomes the newly inserted
slab, and this module places the 8 new interior nodes so that the slab's
centroid lands on the flagged face's own normal line (see
:func:`_pillow_interior_points`).  The project's boundary-skew formula is
``|tangential miss| / |normal distance|`` measured from the owner centroid, so
that placement drives the flagged face's skew to ~0.  A plain shrink-toward-the-
centroid placement provably does **not** work: it displaces the new centroid
along the very ray whose tangential/normal ratio the metric takes, leaving the
ratio — and therefore the skew — exactly unchanged.

**Column collapse** (``candidate_type == "collapse"``) — see
:func:`chord_collapse_boundary_conflict`.  A chord collapse merges the two
opposite node pairs of every quad the chord passes through (Ledoux 2010,
"Chord collapse"), and a column traced *from a boundary face inward* has that
boundary quad as its first chord quad, so every available pairing merges
boundary nodes.  More generally, in a hex mesh whose dual chords are not cycles
every chord terminates on a boundary quad at both ends, so no chord collapse
preserves a boundary at all — which is Ledoux 2010's own topological
restriction that atomic sheet operations may not modify a mesh boundary.  The
operation is therefore rejected by a hard guard before any construction
happens; the guard is the executable part and the topological rewiring is
deliberately not written, because it is unreachable.  Measured, not assumed:
the guard rejected 100% of the 649 collapse candidates HEX-MATCH-1 produced
across cylinder/sphere/gear, which is why ``match_diagnostic`` now carries a
boundary-admissibility precondition and those faces fall through to a pillow.

Measured outcome (2026-07-26, fine quality, pre-BL, ``max_cells=8000``): the
pillow is structurally correct everywhere and the quality gate still rejects it
on ~99% of targets, because the single-cell "onion" pillow inflates all six
faces and its rung faces land at ~70 deg non-orthogonality on snapped graded
octree cells.  See the plan document's "2026-07-26 HEX-MATCH-2 result" section;
the recommended follow-up is a *layer-wide* shrink set (HEX-SHEET-2), which
gives each wall cell exactly one inflated face and reuses everything here
except the choice of shrink set.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

import numpy as np

from core.generator.native_hex.match_diagnostic import (
    MatchCandidate,
    _cell_centroid,
    _is_clean_hex,
    classify_repair_candidates,
    compute_boundary_face_skew,
    face_centroid_normal_area,
    flag_bad_skew_faces,
)
from core.generator.native_hex.metrics import CellFaces, _face_key, _face_owners
from core.utils.logging import get_logger

log = get_logger(__name__)

Cells = list[list[list[int]]]

RepairStatus = Literal[
    "committed",
    "rejected_quality",
    "rejected_degenerate",
    "rejected_boundary_guard",
    "rejected_conflict",
    "no_candidate",
]

_DEFAULT_SKEW_THRESHOLD = 2.0
_DEFAULT_MAX_DEPTH = 2
_DEFAULT_MAX_ROUNDS = 4

# Bounded retry ladder for the pillow's interior node placement:
# (shrink, correction_blend).  ``shrink`` is how far the duplicated nodes move
# toward the cell centroid; ``correction_blend`` is how much of the tangential
# correction that zeroes the flagged face's skew is applied.  Tried in order,
# first one that passes the gate wins, and the list is a hard cap — there is no
# unbounded search.  This is HEX-MATCH-2's "retry at a capped increased depth"
# obligation realised on the parameter that actually controls this operation's
# outcome (a pillow's footprint is depth-1 by construction, so depth itself has
# nothing to escalate).
PillowMode = Literal["taper", "translate"]

_PILLOW_LADDER: tuple[tuple[float, float, PillowMode], ...] = (
    (0.55, 1.00, "taper"),
    (0.55, 1.00, "translate"),
    (0.70, 0.70, "taper"),
    (0.70, 0.70, "translate"),
    (0.55, 0.50, "taper"),
    (0.70, 0.30, "taper"),
    (0.70, 0.15, "taper"),
)

_EPS = 1e-12
# A pillow partitions the owner cell into 7 pieces, so the average piece is
# ~14% of it.  Anything under this fraction is a sliver: treated as degenerate
# regardless of what the skew/non-ortho numbers say, because neither of those
# two metrics sees aspect ratio and the project's grade gate does not either.
_VOLUME_FLOOR_FRACTION = 1e-3

# The project's own existing acceptance gate (grade "A" in
# ``native_hex.quality.hex_quality_grade``).  Reused verbatim rather than
# re-invented so HEX-MATCH-2 cannot accept anything the engine's own gate would
# have failed.
_GATE_MAX_SKEW = 1.0
_GATE_MAX_NON_ORTHO_DEG = 50.0


def _grade(max_non_ortho_deg: float, max_skew: float, n_cells: int) -> str:
    """``native_hex.quality.hex_quality_grade``'s rule, on loose numbers."""
    if n_cells == 0:
        return "D"
    if max_non_ortho_deg < 50.0 and max_skew < 1.0:
        return "A"
    if max_non_ortho_deg < 70.0 and max_skew < 4.0:
        return "B"
    if max_non_ortho_deg < 80.0 and max_skew < 8.0:
        return "C"
    return "D"


GatePolicy = Literal["neighbourhood", "mesh"]


@dataclass(frozen=True)
class GateCeiling:
    """The pass-wide ceiling a single repair may not push its neighbourhood past.

    Two readings of the card's "commit only if it does not regress below the
    existing gate" are defensible and they give very different accept rates, so
    the policy is an explicit parameter rather than a silent choice:

    * ``"neighbourhood"`` (default) — the ceiling is only the project's grade-A
      thresholds, raised per repair to whatever that neighbourhood already had.
      A repair may not make its own neighbourhood worse than it was, nor push a
      currently-passing neighbourhood out of grade A. Conservative, and the
      right default for a card that ships default-OFF.
    * ``"mesh"`` — the ceiling is additionally raised to the whole mesh's
      pre-existing maxima, so a repair may spend headroom that exists *somewhere
      else* in the mesh. The engine's reported max never moves, but an
      individual neighbourhood can degrade a long way (measured on the gear:
      local non-orthogonality 29 -> 70 deg on the 4 faces this admits, because
      the mesh already contained a 75 deg face elsewhere).
    """

    max_internal_skew: float
    max_non_ortho_deg: float

    @staticmethod
    def from_mesh(pre: MeshQuality, policy: GatePolicy = "neighbourhood") -> GateCeiling:
        if policy == "mesh":
            return GateCeiling(
                max_internal_skew=max(pre.max_internal_skew, _GATE_MAX_SKEW),
                max_non_ortho_deg=max(pre.max_non_ortho_deg, _GATE_MAX_NON_ORTHO_DEG),
            )
        return GateCeiling(
            max_internal_skew=_GATE_MAX_SKEW,
            max_non_ortho_deg=_GATE_MAX_NON_ORTHO_DEG,
        )


@dataclass(frozen=True)
class LocalQuality:
    """Quality of one neighbourhood, measured with the project's own formulas."""

    max_boundary_skew: float
    max_internal_skew: float
    max_non_ortho_deg: float
    min_signed_volume: float
    n_faces: int

    def gate_failure(
        self,
        pre: LocalQuality,
        ceiling: GateCeiling,
        *,
        tol: float = 1e-9,
    ) -> str | None:
        """Return a description of the first gate violation, or ``None``.

        Boundary skewness is the objective, so it is held to strict
        non-regression on the neighbourhood.  Internal skewness and
        non-orthogonality are held to a ceiling that is deliberately *not*
        "no number may ever rise" — no genuine subdivision could satisfy that,
        because inserting cells necessarily inserts faces — and equally not a
        free-floating tolerance.  The ceiling is the larger of

        * what this neighbourhood already had, and
        * what the **whole mesh** already had before the pass started,
          floored at the project's own grade-A thresholds
          (``native_hex.quality.hex_quality_grade``: ``max_skew < 1.0``,
          ``max_non_ortho < 50 deg``) so a clean mesh still has working room.

        Anchoring on the mesh's own headline maxima is what makes "does not
        regress below the existing gate" checkable rather than a matter of
        taste: a repair can use headroom the mesh already contains, but it can
        never make the number the engine actually reports and grades on worse.
        """
        if self.max_boundary_skew > pre.max_boundary_skew + tol:
            return (
                f"local max boundary skewness regressed "
                f"({pre.max_boundary_skew:.4f} -> {self.max_boundary_skew:.4f})"
            )
        ceiling_skew = max(pre.max_internal_skew, ceiling.max_internal_skew)
        if self.max_internal_skew > ceiling_skew + tol:
            return (
                f"local max internal skewness {self.max_internal_skew:.4f} exceeds gate ceiling "
                f"{ceiling_skew:.4f}"
            )
        ceiling_no = max(pre.max_non_ortho_deg, ceiling.max_non_ortho_deg)
        if self.max_non_ortho_deg > ceiling_no + tol:
            return (
                f"local max non-orthogonality {self.max_non_ortho_deg:.3f} deg exceeds gate "
                f"ceiling {ceiling_no:.3f} deg"
            )
        return None


@dataclass(frozen=True)
class RepairOutcome:
    """What HEX-MATCH-2 actually did to one HEX-MATCH-1 target."""

    face_key: tuple[int, ...]
    owner_cell: int
    candidate_type: str
    status: RepairStatus
    round_index: int
    pre_face_skew: float
    post_face_skew: float
    attempts: int
    pre_local: LocalQuality | None = None
    post_local: LocalQuality | None = None
    reason: str = ""


@dataclass(frozen=True)
class MeshQuality:
    """Whole-mesh quality snapshot (same formulas as :class:`LocalQuality`)."""

    n_cells: int
    n_points: int
    n_boundary_faces: int
    max_boundary_skew: float
    mean_boundary_skew: float
    max_internal_skew: float
    max_non_ortho_deg: float
    mean_non_ortho_deg: float
    min_signed_volume: float
    n_flagged: int


@dataclass(frozen=True)
class RepairReport:
    """Aggregate HEX-MATCH-2 result for one shape."""

    shape_name: str
    rounds_run: int
    pre: MeshQuality
    post: MeshQuality
    outcomes: tuple[RepairOutcome, ...] = field(default_factory=tuple)
    round0_candidates: tuple[MatchCandidate, ...] = field(default_factory=tuple)
    pass_rolled_back: bool = False
    rollback_reason: str = ""

    def count(self, status: RepairStatus) -> int:
        return sum(1 for o in self.outcomes if o.status == status)

    @property
    def n_committed(self) -> int:
        return self.count("committed")


# ---------------------------------------------------------------------------
# geometry helpers — all deliberately mirror match_diagnostic / native_checker
# ---------------------------------------------------------------------------


def _face_centroid_normal(pts: np.ndarray, face: Sequence[int]) -> tuple[np.ndarray, np.ndarray]:
    """Face centroid and unit normal — delegated, never re-derived.

    Calls ``match_diagnostic.face_centroid_normal_area`` rather than writing the
    formula out a second time, so the executor's notion of "the normal the gate
    will measure against" cannot drift from the flagging formula.  Drift between
    those two is exactly the bug this card's falsification check exists to
    detect, and it did occur once (see that function's docstring).  *face* must
    be in cyclic order.
    """
    cen, n_unit, _area = face_centroid_normal_area(pts, face)
    return cen, n_unit


def _boundary_skew(pts: np.ndarray, owner_centroid: np.ndarray, face: Sequence[int]) -> float:
    cen, n_unit = _face_centroid_normal(pts, face)
    if not np.any(n_unit):
        return 0.0
    normal_dist = float(np.dot(cen - owner_centroid, n_unit))
    proj = owner_centroid + normal_dist * n_unit
    return float(np.linalg.norm(cen - proj)) / max(abs(normal_dist), 1e-30)


def _internal_skew_and_nonortho(
    pts: np.ndarray,
    face: Sequence[int],
    c_own: np.ndarray,
    c_nbr: np.ndarray,
) -> tuple[float, float]:
    """OpenFOAM-style internal-face skewness and non-orthogonality (degrees)."""
    cen, n_unit = _face_centroid_normal(pts, face)
    d = c_nbr - c_own
    d_mag = float(np.linalg.norm(d))
    if d_mag < 1e-30:
        return 0.0, 0.0
    t = float(np.dot(cen - c_own, d)) / (d_mag * d_mag)
    skew = float(np.linalg.norm(cen - (c_own + t * d))) / d_mag
    non_ortho = 0.0
    if np.any(n_unit):
        cos_a = min(1.0, max(0.0, abs(float(np.dot(n_unit, d))) / d_mag))
        non_ortho = float(np.degrees(np.arccos(cos_a)))
    return skew, non_ortho


def _signed_volume(pts: np.ndarray, cell: Sequence[Sequence[int]]) -> float:
    """Signed volume from the cell's own face windings (outward => positive).

    Unlike ``metrics._cell_volume`` (which takes ``abs`` per tetrahedron and so
    cannot see an inverted cell) this keeps the sign, which is what the
    no-inversion half of the gate needs.
    """
    ids = sorted({int(v) for face in cell for v in face})
    if len(ids) < 4:
        return 0.0
    center = pts[np.asarray(ids, dtype=np.int64)].mean(axis=0)
    total = 0.0
    for face in cell:
        if len(face) < 3:
            continue
        p = pts[np.asarray(face, dtype=np.int64)] - center
        for i in range(1, len(face) - 1):
            total += float(np.dot(p[0], np.cross(p[i], p[i + 1]))) / 6.0
    return total


def orient_cells_outward(pts: np.ndarray, cell_faces: CellFaces) -> Cells:
    """Re-wind every face CCW as seen from outside the cell that stores it.

    ``metrics.read_written_polymesh_cells`` rebuilds a cell list from a written
    polyMesh, where a face's stored winding is outward for its **owner** only —
    the neighbour is handed the same vertex list, wound inward.  Roughly a third
    of a reconstructed hex mesh's faces are therefore inward (measured: 880 of
    the 2400 faces on the first 400 cells of the fine cylinder).  Left alone
    that makes signed cell volumes meaningless (3269 of the cylinder's 6320
    cells "invert" on paper, and HEX-MATCH-2's degeneracy guard rejected 216
    perfectly good repairs because of it) and hands the pillow's inserted slabs
    the wrong orientation.

    This normalises to the representation
    ``polymesh_writer.write_generic_polymesh`` documents and this module
    assumes.  It is a no-op on cell lists that are already consistent, which
    includes the octree path's own in-memory output, and it never moves a point.

    Caveat inherited from the checker: reversing a face changes which vertex the
    area-weighted fan starts from, and on a *warped* quad two fans from
    different start vertices are not bit-identical.  The skew of a re-wound face
    can therefore differ in the last digits from the skew of the same face as
    stored.  This is a property of
    ``NativeMeshChecker._compute_face_normals_areas``' own fan-from-v0 formula,
    not something introduced here, and it is below the level that changes any
    decision: the falsification check compared targets derived from the raw and
    the re-wound cell lists on all three measured shapes (344 / 960 / 68
    targets) and found them identical.
    """
    out: Cells = []
    for cell in cell_faces:
        ids = sorted({int(v) for face in cell for v in face})
        if len(ids) < 4:
            out.append([[int(v) for v in face] for face in cell])
            continue
        centre = pts[np.asarray(ids, dtype=np.int64)].mean(axis=0)
        oriented: list[list[int]] = []
        for face in cell:
            verts = [int(v) for v in face]
            if len(verts) < 3:
                oriented.append(verts)
                continue
            p = pts[np.asarray(verts, dtype=np.int64)]
            area_vec = np.cross(p[1:-1] - p[0], p[2:] - p[0]).sum(axis=0)
            if float(np.dot(p.mean(axis=0) - centre, area_vec)) < 0.0:
                verts.reverse()
            oriented.append(verts)
        out.append(oriented)
    return out


def _cyclic_face(cell: Sequence[Sequence[int]], face_key: tuple[int, ...]) -> list[int] | None:
    """Recover a face's stored cyclic vertex order from its sorted key."""
    for face in cell:
        if _face_key(face) == face_key:
            return [int(v) for v in face]
    return None


def boundary_vertices(owners: dict[tuple[int, ...], list[int]]) -> set[int]:
    """Every vertex lying on a single-owner (boundary) face."""
    out: set[int] = set()
    for key, owner_list in owners.items():
        if len(owner_list) == 1:
            out.update(int(v) for v in key)
    return out


# ---------------------------------------------------------------------------
# column / chord collapse — guard only (see module docstring)
# ---------------------------------------------------------------------------


def _hex_opposite_face(
    cell: Sequence[Sequence[int]], face_key: tuple[int, ...]
) -> tuple[int, ...] | None:
    """The face of a clean hex sharing no vertex with *face_key*."""
    if not _is_clean_hex(cell):
        return None
    target = set(face_key)
    matches = [_face_key(f) for f in cell if not (set(_face_key(f)) & target)]
    return matches[0] if len(matches) == 1 else None


def chord_quads(
    cells: Cells,
    owners: dict[tuple[int, ...], list[int]],
    start_cell: int,
    start_face_key: tuple[int, ...],
    *,
    cap: int = 256,
) -> tuple[list[tuple[int, ...]], list[int], str]:
    """Walk the FULL chord through *start_face_key*, unbounded up to *cap*.

    Unlike ``match_diagnostic._trace_column`` (which stops at the card's depth
    bound because it is only sizing a footprint) this follows the chord to its
    actual termination, because the collapse guard has to know what the *whole*
    operation would touch — a chord collapse is not depth-limited, it removes
    every hex on the chord.

    Returns ``(quads, cells_on_chord, termination)`` where ``termination`` is
    ``"boundary"`` (the chord ran into a single-owner quad, i.e. the mesh
    surface), ``"cycle"`` (closed on itself), ``"ambiguous"`` (ran into a
    non-hex) or ``"cap"``.
    """
    quads: list[tuple[int, ...]] = [start_face_key]
    chain: list[int] = []
    current_cell = start_cell
    current_key = start_face_key
    seen_cells: set[int] = set()
    termination = "cap"
    for _ in range(cap):
        if current_cell in seen_cells:
            termination = "cycle"
            break
        seen_cells.add(current_cell)
        chain.append(current_cell)
        cell = cells[current_cell]
        opposite = _hex_opposite_face(cell, current_key)
        if opposite is None:
            termination = "ambiguous"
            break
        quads.append(opposite)
        nxt = [c for c in owners.get(opposite, []) if c != current_cell]
        if len(nxt) != 1:
            termination = "boundary"
            break
        current_cell = nxt[0]
        current_key = opposite
    return quads, chain, termination


def face_collapse_pairings(face: Sequence[int]) -> tuple[tuple[tuple[int, int], ...], ...]:
    """The two node-merge sets a face collapse of a quad may choose.

    Ledoux 2010 ("Chord collapse"): a face collapse merges the two opposite node
    pairs of a quad, collapsing it to an edge, and there are exactly two ways to
    do it — which is the source of the operation's documented non-determinism.
    """
    if len(face) != 4:
        return ()
    a, b, c, d = (int(v) for v in face)
    return (((a, b), (c, d)), ((b, c), (d, a)))


def chord_collapse_boundary_conflict(
    cells: Cells,
    owners: dict[tuple[int, ...], list[int]],
    start_cell: int,
    start_face_key: tuple[int, ...],
    bnd_verts: set[int],
) -> tuple[bool, str]:
    """Hard guard: would a chord collapse here merge any boundary vertex?

    Merging a boundary vertex with anything deletes it from the mesh surface (or
    drags it onto its partner), so it modifies preserved geometry either way —
    which HEX-MATCH-2's own invariant (plan doc Section 7.3: "boundary vertices
    are never repositioned") and the project's surface-preservation invariant
    both forbid.  Ledoux 2010 states the same restriction from the topological
    side: atomic sheet operations are not allowed to modify a mesh boundary.

    Returns ``(conflicted, reason)``.  ``conflicted=True`` means *every*
    available pairing on at least one chord quad touches the boundary, so no
    choice of the operation's non-deterministic reconnection avoids it.
    """
    quads, _chain, termination = chord_quads(cells, owners, start_cell, start_face_key)
    for key in quads:
        owner_list = owners.get(key, [])
        cell_index = owner_list[0] if owner_list else None
        cyclic = _cyclic_face(cells[cell_index], key) if cell_index is not None else None
        pairings = face_collapse_pairings(cyclic) if cyclic else ()
        if not pairings:
            # Cannot even enumerate the operation here — refuse.
            return True, f"chord quad {key} has no enumerable face-collapse pairing"
        if all(
            any(u in bnd_verts or v in bnd_verts for (u, v) in pairing) for pairing in pairings
        ):
            n_b = sum(1 for v in key if v in bnd_verts)
            return True, (
                f"every face-collapse pairing on chord quad {key} merges a boundary vertex "
                f"({n_b}/4 of its nodes are on the surface); chord termination={termination}"
            )
    return False, f"no boundary vertex on the chord (termination={termination})"


# ---------------------------------------------------------------------------
# pillow insertion — the executable operation
# ---------------------------------------------------------------------------


def _pillow_interior_points(
    pts: np.ndarray,
    cell: Sequence[Sequence[int]],
    flagged_face: Sequence[int],
    shrink: float,
    correction: float,
    mode: PillowMode,
) -> tuple[list[int], np.ndarray] | None:
    """Positions for the 8 duplicated (interior) nodes of a single-cell pillow.

    Base placement is the textbook shrink ``v' = c + s*(v - c)``.  On its own
    that is useless for our metric: the inserted slab's centroid then sits on the
    segment from the cell centroid to the face centroid, so the tangential/normal
    ratio the skew formula takes is identical to the un-pillowed cell's and the
    skew does not move at all.

    So the shrunken copy is additionally *translated* by
    ``correction * (1 - s) * t``, where ``t`` is the component of
    ``face_centroid - cell_centroid`` perpendicular to the face normal.  The
    inserted slab's centroid is then offset from the flagged face's centroid by
    ``(1-s)/2 * (alpha*n + (1-correction)*t)``, so the measured skew becomes
    ``(1 - correction)`` times the original: ``correction = 1`` drives it to ~0
    and smaller values give a proportionally smaller but still strict
    improvement, which is what the retry ladder walks.

    Two placements achieve the identical centroid offset and both are on the
    ladder, because they fail in opposite directions and neither dominates:

    ``"taper"`` shifts only the flagged face's four nodes (a linear taper to
    zero at the opposite face).  It keeps the copy small but shears it, and it
    has an exact degeneracy: when the cell's own shear runs along ``t``, the
    tangential push cancels the shrink's inward pull on the two side slabs
    straddling the flagged face and their volume goes to zero *for every shrink
    value* (reproducible on a plain sheared unit hex).

    ``"translate"`` shifts all eight nodes, keeping the copy a rigid, similar
    image of the original — better-shaped inner cell, but the whole displacement
    lands on one side, so it inverts sooner.

    Neither can reach ``correction = 1`` at high skew, and that is a property of
    the geometry rather than a defect: ``|t| = skew * |alpha|``, so at
    ``skew >= 2`` the full correction is at least twice the cell's own
    normal-direction half-thickness and necessarily pushes the copy out of the
    cell.  The reachable repair is therefore a partial one, and the ladder
    descends until the gate accepts.
    """
    ids = sorted({int(v) for face in cell for v in face})
    if len(ids) != 8:
        return None
    c = pts[np.asarray(ids, dtype=np.int64)].mean(axis=0)

    f_cen, n_unit = _face_centroid_normal(pts, flagged_face)
    if not np.any(n_unit):
        return None
    delta = f_cen - c
    tangential = delta - float(np.dot(delta, n_unit)) * n_unit
    shift = correction * (1.0 - shrink) * tangential
    on_face = {int(v) for v in flagged_face}

    out = []
    for v in ids:
        pos = c + shrink * (pts[v] - c)
        if mode == "translate" or v in on_face:
            pos = pos + shift
        out.append(pos)
    return ids, np.asarray(out, dtype=np.float64)


def build_pillow(
    pts: np.ndarray,
    cell: Sequence[Sequence[int]],
    flagged_face: Sequence[int],
    n_existing_points: int,
    shrink: float,
    correction: float,
    mode: PillowMode = "taper",
) -> tuple[np.ndarray, Cells] | None:
    """Construct the 7 cells and 8 new points of a single-cell pillow.

    Pure construction on a scratch: nothing here reads or writes live state.
    Returns ``(new_points, new_cells)`` where ``new_cells[0]`` is the shrunken
    inner hex and ``new_cells[1:]`` are the 6 inflated slabs, one per original
    face, each re-emitting that original face with its original vertex list and
    winding so neighbouring cells stay bit-identical.
    """
    if not _is_clean_hex(cell):
        return None
    built = _pillow_interior_points(pts, cell, flagged_face, shrink, correction, mode)
    if built is None:
        return None
    ids, new_pts = built
    dup = {v: n_existing_points + i for i, v in enumerate(ids)}

    inner: list[list[int]] = []
    slabs: Cells = []
    for face in cell:
        outer = [int(v) for v in face]
        primed = [dup[v] for v in outer]
        # Inner hex keeps the same winding (its outward direction at this face
        # is the original cell's outward direction).
        inner.append(list(primed))
        # Slab: original face outward as-is, primed face reversed (it faces the
        # opposite way), plus one rung quad per edge of the original face.
        slab: list[list[int]] = [list(outer), list(reversed(primed))]
        n = len(outer)
        for i in range(n):
            j = (i + 1) % n
            slab.append([outer[i], primed[i], primed[j], outer[j]])
        slabs.append(slab)
    return new_pts, [inner, *slabs]


# ---------------------------------------------------------------------------
# quality measurement
# ---------------------------------------------------------------------------


def _quality_over_faces(
    pts: np.ndarray,
    cells: Cells,
    faces_with_owners: dict[tuple[int, ...], tuple[list[int], list[int]]],
    centroids: dict[int, np.ndarray],
    cell_ids: Sequence[int],
) -> LocalQuality:
    """Measure a face set. ``faces_with_owners`` maps key -> (cyclic, owners)."""
    max_b = 0.0
    max_i = 0.0
    max_no = 0.0
    for cyclic, owner_list in faces_with_owners.values():
        if len(owner_list) == 1:
            max_b = max(max_b, _boundary_skew(pts, centroids[owner_list[0]], cyclic))
        elif len(owner_list) >= 2:
            skew, non_ortho = _internal_skew_and_nonortho(
                pts, cyclic, centroids[owner_list[0]], centroids[owner_list[1]]
            )
            max_i = max(max_i, skew)
            max_no = max(max_no, non_ortho)
    min_vol = min((_signed_volume(pts, cells[c]) for c in cell_ids), default=0.0)
    return LocalQuality(
        max_boundary_skew=max_b,
        max_internal_skew=max_i,
        max_non_ortho_deg=max_no,
        min_signed_volume=min_vol,
        n_faces=len(faces_with_owners),
    )


def mesh_quality(
    pts: np.ndarray,
    cells: Cells,
    *,
    skew_threshold: float = _DEFAULT_SKEW_THRESHOLD,
) -> MeshQuality:
    """Whole-mesh snapshot for the global (pass-level) rollback check."""
    owners = _face_owners(cells)
    centroids = [_cell_centroid(pts, cell) for cell in cells]
    b_skews: list[float] = []
    max_i = 0.0
    non_orthos: list[float] = []
    for cell_index, cell in enumerate(cells):
        for face in cell:
            key = _face_key(face)
            owner_list = owners.get(key, [])
            if len(owner_list) == 1:
                if owner_list[0] == cell_index:
                    b_skews.append(_boundary_skew(pts, centroids[cell_index], face))
            elif len(owner_list) >= 2 and owner_list[0] == cell_index:
                skew, non_ortho = _internal_skew_and_nonortho(
                    pts, face, centroids[owner_list[0]], centroids[owner_list[1]]
                )
                max_i = max(max_i, skew)
                non_orthos.append(non_ortho)
    min_vol = min((_signed_volume(pts, cell) for cell in cells), default=0.0)
    return MeshQuality(
        n_cells=len(cells),
        n_points=int(pts.shape[0]),
        n_boundary_faces=len(b_skews),
        max_boundary_skew=max(b_skews, default=0.0),
        mean_boundary_skew=float(np.mean(b_skews)) if b_skews else 0.0,
        max_internal_skew=max_i,
        max_non_ortho_deg=max(non_orthos, default=0.0),
        mean_non_ortho_deg=float(np.mean(non_orthos)) if non_orthos else 0.0,
        min_signed_volume=min_vol,
        n_flagged=sum(1 for s in b_skews if s >= skew_threshold),
    )


# ---------------------------------------------------------------------------
# the transaction
# ---------------------------------------------------------------------------


def _try_pillow(
    pts: np.ndarray,
    cells: Cells,
    owners: dict[tuple[int, ...], list[int]],
    owner_cell: int,
    flagged_face_key: tuple[int, ...],
    ceiling: GateCeiling,
) -> tuple[tuple[np.ndarray, Cells, LocalQuality, LocalQuality, float, int, str] | None, str]:
    """Trial every ladder rung on a scratch; return the first that passes.

    Returns ``(payload, reason)`` where ``payload`` is ``(new_points, new_cells,
    pre_local, post_local, post_face_skew, attempts, reason)`` or ``None``.  On
    ``None`` nothing whatsoever has been written anywhere, which is what makes
    the operation transactional; ``reason`` then carries the last rung's
    rejection so the census can attribute it.
    """
    cell = cells[owner_cell]
    # Everything downstream needs the face cyclic order, not its sorted key: the
    # checker area-weighted normal is order-dependent on a warped quad.
    flagged_face = _cyclic_face(cell, flagged_face_key)
    if flagged_face is None:
        return None, "flagged face is not on the owner cell"
    pre_centroid = _cell_centroid(pts, cell)
    orig_volume = _signed_volume(pts, cell)
    if orig_volume <= 0.0:
        return None, f"owner cell has non-positive signed volume ({orig_volume:.3e})"
    # A pillow partitions the owner cell exactly, so the 7 pieces must sum back
    # to ``orig_volume``; anything at or below this floor is a flattened slab.
    volume_floor = _VOLUME_FLOOR_FRACTION * orig_volume

    # Pre state: the faces of the owner cell are exactly the faces this
    # operation replaces the owner side of, so they are the affected set.
    pre_faces: dict[tuple[int, ...], tuple[list[int], list[int]]] = {}
    nbr_ids: list[int] = []
    for face in cell:
        key = _face_key(face)
        owner_list = list(owners.get(key, []))
        ordered = [owner_cell] + [c for c in owner_list if c != owner_cell]
        pre_faces[key] = ([int(v) for v in face], ordered)
        nbr_ids.extend(c for c in owner_list if c != owner_cell)
    pre_centroids = {owner_cell: pre_centroid}
    for c in nbr_ids:
        pre_centroids[c] = _cell_centroid(pts, cells[c])
    pre_local = _quality_over_faces(pts, cells, pre_faces, pre_centroids, [owner_cell])
    pre_face_skew = _boundary_skew(pts, pre_centroid, flagged_face)

    attempts = 0
    last_reason = "no ladder rung attempted"
    for shrink, correction, mode in _PILLOW_LADDER:
        attempts += 1
        rung = f"shrink={shrink} correction={correction} mode={mode}"
        built = build_pillow(
            pts, cell, flagged_face, int(pts.shape[0]), shrink, correction, mode
        )
        if built is None:
            last_reason = "pillow construction failed (cell not a clean hex)"
            continue
        new_pts, new_cells = built
        scratch_pts = np.vstack([pts, new_pts])

        # Post state, assembled locally: the 7 new cells get provisional indices
        # starting at len(cells) (index owner_cell is reused for the inner hex
        # at commit time, but for measurement any consistent labelling works).
        base = len(cells)
        local_cells: Cells = list(cells) + new_cells
        local_ids = [base + i for i in range(len(new_cells))]
        post_faces: dict[tuple[int, ...], tuple[list[int], list[int]]] = {}
        for local_index, new_cell in zip(local_ids, new_cells, strict=True):
            for face in new_cell:
                key = _face_key(face)
                cyclic, existing = post_faces.get(key, ([int(v) for v in face], []))
                post_faces[key] = (cyclic, [*existing, local_index])
        # Faces inherited from the original cell still have their outside
        # neighbour; splice it back in so their skew/non-ortho stays honest.
        for key, (_cyclic, owner_list) in pre_faces.items():
            outside = [c for c in owner_list if c != owner_cell]
            if key in post_faces and outside:
                cyclic, inside = post_faces[key]
                post_faces[key] = (cyclic, [*inside, *outside])
        post_centroids = {i: _cell_centroid(scratch_pts, local_cells[i]) for i in local_ids}
        for c in nbr_ids:
            post_centroids[c] = _cell_centroid(scratch_pts, local_cells[c])
        post_local = _quality_over_faces(
            scratch_pts, local_cells, post_faces, post_centroids, local_ids
        )

        post_owner = next(
            (i for i in local_ids if _face_key(local_cells[i][0]) == flagged_face_key),
            None,
        )
        if post_owner is None:
            post_owner = next(
                (
                    i
                    for i in local_ids
                    if any(_face_key(f) == flagged_face_key for f in local_cells[i])
                ),
                None,
            )
        if post_owner is None:
            last_reason = "flagged face vanished from the pillowed cell group"
            continue
        post_face_skew = _boundary_skew(
            scratch_pts, post_centroids[post_owner], flagged_face
        )

        if post_local.min_signed_volume <= volume_floor:
            last_reason = (
                f"{rung}: inserted cells are degenerate or inverted "
                f"(min signed volume {post_local.min_signed_volume:.3e} <= floor "
                f"{volume_floor:.3e})"
            )
            continue
        if post_face_skew >= pre_face_skew:
            last_reason = (
                f"{rung}: flagged face skew did not strictly improve "
                f"({pre_face_skew:.3f} -> {post_face_skew:.3f})"
            )
            continue
        failure = post_local.gate_failure(pre_local, ceiling)
        if failure is not None:
            last_reason = f"{rung}: {failure}"
            continue
        return (
            new_pts,
            new_cells,
            pre_local,
            post_local,
            post_face_skew,
            attempts,
            f"pillow accepted at {rung}",
        ), ""
    return None, last_reason


def _commit_pillow(
    pts: np.ndarray,
    cells: Cells,
    owner_cell: int,
    new_pts: np.ndarray,
    new_cells: Cells,
) -> tuple[np.ndarray, list[int]]:
    """Splice an already-gated pillow into the live mesh.

    The owner index is reused by the inner hex and the 6 slabs are appended, so
    every other cell keeps its index and any pending candidate's ``owner_cell``
    stays valid.  This runs only after the gate has passed, so there is no
    failure path that could leave the mesh half-edited.
    """
    cells[owner_cell] = new_cells[0]
    appended = list(range(len(cells), len(cells) + len(new_cells) - 1))
    cells.extend(new_cells[1:])
    return np.vstack([pts, new_pts]), [owner_cell, *appended]


def run_match_repair(
    shape_name: str,
    points: np.ndarray,
    cell_faces: CellFaces,
    *,
    skew_threshold: float = _DEFAULT_SKEW_THRESHOLD,
    max_depth: int = _DEFAULT_MAX_DEPTH,
    max_rounds: int = _DEFAULT_MAX_ROUNDS,
    global_rollback: bool = True,
    gate_policy: GatePolicy = "neighbourhood",
) -> tuple[np.ndarray, Cells, RepairReport]:
    """Sequential, transactional HEX-MATCH-2 repair pass.

    Rounds exist so that targeting is re-derived against the *current* mesh: a
    candidate whose depth-bounded footprint collides with a repair already
    committed in this round is deferred rather than dropped, and the next round
    re-flags and re-classifies everything against the edited mesh, which is
    where HEX-MATCH-1's static all-at-once "footprint conflict" verdicts get a
    second chance.  Every individual repair is still gated and committed (or
    discarded) on its own.

    If ``global_rollback`` and the whole-mesh snapshot regressed, the entire
    pass is discarded and the untouched input is returned — the outer half of
    the never-partially-applied contract.
    """
    pts = np.array(points, dtype=np.float64, copy=True)
    cells: Cells = orient_cells_outward(pts, cell_faces)
    # Kept verbatim (not the re-wound copy) so a whole-pass rollback returns the
    # caller exactly what it handed in — the strongest form of the
    # never-partially-applied contract.
    original_cells: Cells = [[[int(v) for v in face] for face in cell] for cell in cell_faces]
    pre_mesh = mesh_quality(pts, cells, skew_threshold=skew_threshold)
    ceiling = GateCeiling.from_mesh(pre_mesh, gate_policy)

    outcomes: list[RepairOutcome] = []
    round0: tuple[MatchCandidate, ...] = ()
    rounds_run = 0

    for round_index in range(max_rounds):
        faces = compute_boundary_face_skew(pts, cells)
        flagged = flag_bad_skew_faces(faces, threshold=skew_threshold)
        if not flagged:
            break
        candidates = classify_repair_candidates(pts, cells, flagged, max_depth=max_depth)
        if round_index == 0:
            round0 = tuple(candidates)
        rounds_run = round_index + 1

        owners = _face_owners(cells)
        bnd_verts = boundary_vertices(owners)
        # Static, round-start adjacency. A candidate is only admissible if its
        # own cell, its footprint AND its immediate neighbours are all still
        # pristine, because ``_try_pillow`` measures against those neighbours'
        # centroids. Anything else is deferred to the next round, where the
        # census is rebuilt from scratch against the edited mesh — that deferral
        # is what makes this pass sequential rather than the diagnostic's
        # all-at-once claim order.
        neighbours: list[set[int]] = [set() for _ in cells]
        for owner_list in owners.values():
            for a in owner_list:
                neighbours[a].update(c for c in owner_list if c != a)
        touched: set[int] = set()
        committed_this_round = 0
        round_outcomes: list[RepairOutcome] = []

        for cand in candidates:
            owner = cand.owner_cell
            footprint = set(cand.footprint_cells) | {owner} | neighbours[owner]
            if touched & footprint:
                round_outcomes.append(
                    RepairOutcome(
                        face_key=cand.face_key,
                        owner_cell=owner,
                        candidate_type=cand.candidate_type,
                        status="rejected_conflict",
                        round_index=round_index,
                        pre_face_skew=cand.skewness,
                        post_face_skew=cand.skewness,
                        attempts=0,
                        reason="footprint overlaps a repair already committed this round",
                    )
                )
                continue

            if cand.candidate_type == "none":
                round_outcomes.append(
                    RepairOutcome(
                        face_key=cand.face_key,
                        owner_cell=owner,
                        candidate_type="none",
                        status="no_candidate",
                        round_index=round_index,
                        pre_face_skew=cand.skewness,
                        post_face_skew=cand.skewness,
                        attempts=0,
                        reason=cand.reason,
                    )
                )
                continue

            if cand.candidate_type == "collapse":
                conflicted, why = chord_collapse_boundary_conflict(
                    cells, owners, owner, cand.face_key, bnd_verts
                )
                if conflicted:
                    round_outcomes.append(
                        RepairOutcome(
                            face_key=cand.face_key,
                            owner_cell=owner,
                            candidate_type="collapse",
                            status="rejected_boundary_guard",
                            round_index=round_index,
                            pre_face_skew=cand.skewness,
                            post_face_skew=cand.skewness,
                            attempts=0,
                            reason=why,
                        )
                    )
                    continue
                # A boundary-safe chord would be executable, but no such chord
                # can be reached from a boundary face (see module docstring);
                # refuse rather than silently doing something else.
                round_outcomes.append(
                    RepairOutcome(
                        face_key=cand.face_key,
                        owner_cell=owner,
                        candidate_type="collapse",
                        status="rejected_boundary_guard",
                        round_index=round_index,
                        pre_face_skew=cand.skewness,
                        post_face_skew=cand.skewness,
                        attempts=0,
                        reason=(
                            "chord reported boundary-safe, which HEX-MATCH-2 does not implement "
                            f"(unreachable from a boundary-seeded column): {why}"
                        ),
                    )
                )
                continue

            trial, why_failed = _try_pillow(
                pts, cells, owners, owner, cand.face_key, ceiling
            )
            if trial is None:
                round_outcomes.append(
                    RepairOutcome(
                        face_key=cand.face_key,
                        owner_cell=owner,
                        candidate_type="pillow",
                        status="rejected_quality",
                        round_index=round_index,
                        pre_face_skew=cand.skewness,
                        post_face_skew=cand.skewness,
                        attempts=len(_PILLOW_LADDER),
                        reason=f"every ladder rung failed the gate; last: {why_failed}",
                    )
                )
                continue

            (new_pts, new_cells, pre_local, post_local, post_skew, attempts, why) = trial
            pts, new_ids = _commit_pillow(pts, cells, owner, new_pts, new_cells)
            touched.update(new_ids)
            touched.update(footprint)
            committed_this_round += 1
            round_outcomes.append(
                RepairOutcome(
                    face_key=cand.face_key,
                    owner_cell=owner,
                    candidate_type="pillow",
                    status="committed",
                    round_index=round_index,
                    pre_face_skew=cand.skewness,
                    post_face_skew=post_skew,
                    attempts=attempts,
                    pre_local=pre_local,
                    post_local=post_local,
                    reason=why,
                )
            )

        outcomes.extend(round_outcomes)
        if committed_this_round == 0:
            break

    post_mesh = mesh_quality(pts, cells, skew_threshold=skew_threshold)
    rolled_back = False
    rollback_reason = ""
    if global_rollback:
        pre_grade = _grade(
            pre_mesh.max_non_ortho_deg,
            max(pre_mesh.max_internal_skew, pre_mesh.max_boundary_skew),
            pre_mesh.n_cells,
        )
        post_grade = _grade(
            post_mesh.max_non_ortho_deg,
            max(post_mesh.max_internal_skew, post_mesh.max_boundary_skew),
            post_mesh.n_cells,
        )
        if post_mesh.min_signed_volume <= 0.0 < pre_mesh.min_signed_volume:
            rolled_back, rollback_reason = True, "global min signed volume went non-positive"
        elif post_grade > pre_grade:  # "A" < "B" < "C" < "D"
            rolled_back, rollback_reason = (
                True,
                f"whole-mesh quality grade dropped {pre_grade} -> {post_grade}",
            )
        elif post_mesh.max_boundary_skew > pre_mesh.max_boundary_skew + 1e-9:
            rolled_back, rollback_reason = True, "global max boundary skewness regressed"
    if rolled_back:
        pts = np.array(points, dtype=np.float64, copy=True)
        cells = original_cells
        post_mesh = pre_mesh

    report = RepairReport(
        shape_name=str(shape_name),
        rounds_run=rounds_run,
        pre=pre_mesh,
        post=post_mesh,
        outcomes=tuple(outcomes),
        round0_candidates=round0,
        pass_rolled_back=rolled_back,
        rollback_reason=rollback_reason,
    )
    log.info(
        "native_hex_match_repair",
        shape=report.shape_name,
        rounds=report.rounds_run,
        n_committed=report.n_committed,
        n_rejected_quality=report.count("rejected_quality"),
        n_rejected_boundary_guard=report.count("rejected_boundary_guard"),
        n_rejected_conflict=report.count("rejected_conflict"),
        n_no_candidate=report.count("no_candidate"),
        cells_before=pre_mesh.n_cells,
        cells_after=post_mesh.n_cells,
        gate_policy=str(gate_policy),
        max_bskew_before=round(pre_mesh.max_boundary_skew, 4),
        max_bskew_after=round(post_mesh.max_boundary_skew, 4),
        max_nonortho_before=round(pre_mesh.max_non_ortho_deg, 3),
        max_nonortho_after=round(post_mesh.max_non_ortho_deg, 3),
        rolled_back=report.pass_rolled_back,
    )
    return pts, cells, report
