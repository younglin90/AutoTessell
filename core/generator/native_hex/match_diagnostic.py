"""HEX-MATCH-1 — Staten-2010-adapted local repair-candidate targeting.

Diagnostic-only, log-only by default (mirrors ``boundary_invariant.py``'s
``log_only=True`` precedent from ``native_tet``).  This module makes ZERO mesh
edits: it reads an already-generated mesh's generic cell-face representation,
flags boundary ("side") faces whose OpenFOAM-style skewness clears a threshold,
and for each flagged face reports which local repair operation Staten,
Shepherd, Ledoux & Shimada 2010's (``staten2010_mesh_matching.md``) depth-bounded
mesh-matching operator catalog would select — pillow insertion, column
collapse, or "no clean candidate" — and the operation's bounded footprint.

Adaptation note (per the round-2 synthesis, section 7 of
``native_hex_literature_integrated_development_plan_2026-07-23.md``): Staten
2010's actual use case is two interfaces being matched into a conforming pair;
our use case is a single flagged bad face needing a local repair candidate, not
interface matching.  What is ported here is the underlying primitive — extract
an unpaired low-quality/self-intersecting/far-reaching dual sheet or column, or
insert a pillow sheet, decided by locality (the depth parameter) and topology
(self-intersection guard against doublets), never by the paper's own scaled
Jacobian or any other borrowed proxy metric.  Selection here is gated
conceptually by OUR skewness measurement (the flag itself), not by MSJ/ΔV.

No mesh mutation happens anywhere in this module.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

import numpy as np

from core.generator.native_hex.metrics import CellFaces, _face_owners
from core.utils.logging import get_logger

log = get_logger(__name__)

CandidateType = Literal["pillow", "collapse", "none"]

_SKEW_FLAG_THRESHOLD_DEFAULT = 2.0
_DEFAULT_MAX_DEPTH = 2


@dataclass(frozen=True)
class BoundaryFaceSkew:
    """One boundary ("side") quad face and its measured skewness."""

    face_key: tuple[int, ...]
    owner_cell: int
    skewness: float
    area: float


@dataclass(frozen=True)
class MatchCandidate:
    """The Staten-adapted local repair decision for one flagged bad face."""

    face_key: tuple[int, ...]
    owner_cell: int
    skewness: float
    candidate_type: CandidateType
    footprint_cells: tuple[int, ...]
    depth_used: int
    reason: str


@dataclass(frozen=True)
class MatchDiagnosticReport:
    """Aggregate per-shape targeting census, HEX-MATCH-1 pass/fail evidence."""

    shape_name: str
    n_boundary_faces: int
    n_flagged: int
    candidates: tuple[MatchCandidate, ...] = field(default_factory=tuple)

    @property
    def n_pillow(self) -> int:
        return sum(1 for c in self.candidates if c.candidate_type == "pillow")

    @property
    def n_collapse(self) -> int:
        return sum(1 for c in self.candidates if c.candidate_type == "collapse")

    @property
    def n_none(self) -> int:
        return sum(1 for c in self.candidates if c.candidate_type == "none")


def _quad_skewness(
    points: np.ndarray, owner_centroid: np.ndarray, face: Sequence[int]
) -> tuple[float, float]:
    """Boundary-face skewness, exact port of the project's own canonical
    formula (``NativeMeshChecker._compute_boundary_skewness`` in
    ``core/evaluator/native_checker.py``), not an independently-invented
    metric — the round-2 synthesis (section 7 of
    ``native_hex_literature_integrated_development_plan_2026-07-23.md``)
    explicitly requires gating by "our own OpenFOAM skew metric, never a
    borrowed proxy," so the flagging step here must use the same formula the
    project's checker uses, not a different boundary-skew approximation:

        normal_dist = dot(face_centroid - cell_centroid, face_normal)
        proj        = cell_centroid + normal_dist * face_normal
        skew        = ||face_centroid - proj|| / |normal_dist|

    i.e. how far the face centroid deviates, tangentially, from the straight
    line leaving the owner cell centroid along the face normal.
    """
    verts = points[np.asarray(face, dtype=np.int64)]
    if verts.shape[0] < 3:
        return 0.0, 0.0
    a, b, c = verts[0], verts[1], verts[2]
    cen = verts.mean(axis=0)
    normal = np.cross(b - a, c - a)
    norm = float(np.linalg.norm(normal))
    if norm < 1e-30:
        return 0.0, 0.0
    n_unit = normal / norm
    area = 0.0
    for i in range(1, len(face) - 1):
        area += 0.5 * float(np.linalg.norm(np.cross(verts[i] - verts[0], verts[i + 1] - verts[0])))
    to_face = cen - owner_centroid
    normal_dist = float(np.dot(to_face, n_unit))
    proj = owner_centroid + normal_dist * n_unit
    denom = max(abs(normal_dist), 1e-30)
    skew = float(np.linalg.norm(cen - proj)) / denom
    return skew, area


def _cell_centroid(points: np.ndarray, cell: Sequence[Sequence[int]]) -> np.ndarray:
    verts = sorted({int(v) for face in cell for v in face})
    centroid: np.ndarray = points[np.asarray(verts, dtype=np.int64)].mean(axis=0)
    return centroid


def compute_boundary_face_skew(points: np.ndarray, cell_faces: CellFaces) -> list[BoundaryFaceSkew]:
    """Compute the project's canonical boundary skewness for every quad face.

    Read-only: no mesh mutation. Non-quad boundary faces (triangulated caps —
    e.g. a boundary-layer prism's outer face, or a generic-writer transition
    face) are skipped: the Staten operator catalog is defined over hex dual
    sheets/columns, and this diagnostic's face-key format (4-tuple) matches
    that scope. Callers measuring the pre-BL octree/adaptive output (the
    scope this card targets — see ``scripts/diag_hex_match_candidates.py``)
    should disable the boundary-layer pass first, since BL re-triangulates
    the outer wall into prism caps that would otherwise hide every hex
    boundary quad this diagnostic is meant to flag.
    """
    pts = np.asarray(points, dtype=np.float64)
    cells = [[[int(v) for v in face] for face in cell] for cell in cell_faces]
    owners = _face_owners(cells)
    centroids = [_cell_centroid(pts, cell) for cell in cells]

    results: list[BoundaryFaceSkew] = []
    for face_key, owner_list in sorted(owners.items()):
        if len(owner_list) != 1 or len(face_key) != 4:
            continue
        owner = owner_list[0]
        skew, area = _quad_skewness(pts, centroids[owner], face_key)
        results.append(
            BoundaryFaceSkew(face_key=face_key, owner_cell=owner, skewness=skew, area=area)
        )
    return results


def flag_bad_skew_faces(
    faces: Sequence[BoundaryFaceSkew], threshold: float = _SKEW_FLAG_THRESHOLD_DEFAULT
) -> list[BoundaryFaceSkew]:
    """Faces at or above *threshold*, deterministic order (sorted face key)."""
    return sorted(
        (f for f in faces if f.skewness >= threshold),
        key=lambda f: f.face_key,
    )


def _is_clean_hex(cell: Sequence[Sequence[int]]) -> bool:
    if len(cell) != 6 or any(len(face) != 4 for face in cell):
        return False
    return len({int(v) for face in cell for v in face}) == 8


def _opposite_face_pairing(cell: Sequence[Sequence[int]]) -> list[tuple[int, int]] | None:
    """Pair the 6 faces of a clean hex into 3 (face_i, face_j) opposite pairs.

    Two faces of a hex are "opposite" (belong to the same dual sheet/column
    direction) iff they share no vertex. Purely combinatorial — independent of
    any canonical local-vertex ordering, so it works on generic
    reconstructed-from-polyMesh cells whose face order is not the writer's
    original local layout.
    """
    if not _is_clean_hex(cell):
        return None
    vsets = [frozenset(int(v) for v in face) for face in cell]
    used: set[int] = set()
    pairs: list[tuple[int, int]] = []
    for i in range(6):
        if i in used:
            continue
        candidates = [j for j in range(6) if j != i and j not in used and not (vsets[i] & vsets[j])]
        if len(candidates) != 1:
            return None
        j = candidates[0]
        pairs.append((i, j))
        used.add(i)
        used.add(j)
    return pairs if len(pairs) == 3 else None


_StopReason = Literal["max_depth", "boundary", "ambiguous", "self_intersecting"]


def _trace_column(
    cells: list[list[list[int]]],
    owners: dict[tuple[int, ...], list[int]],
    start_cell: int,
    start_face_key: tuple[int, ...],
    max_depth: int,
) -> tuple[list[int], bool, _StopReason]:
    """Walk the dual column through *start_face_key*'s opposite faces.

    Returns (visited_cell_chain, self_intersecting, stop_reason). The chain
    always begins with *start_cell*.

    - self_intersecting=True: the walk revisits a cell already in the chain
      (Staten's named doublet-risk condition — never collapse this column).
    - stop_reason="boundary": the column exits into ANOTHER boundary face
      (single-owner) within the depth bound — the column runs from one
      boundary patch straight through to another. Collapsing it risks
      merging two geometrically distinct boundary regions, the column-scale
      analog of Staten's node-associativity caveat (stated for sheet
      extraction; applied here as a secondary caution per section 7.1's
      Ledoux-2013 cross-reference).
    - stop_reason="ambiguous": the column exits into a non-hex cell or a
      face-pairing/topology could not be resolved — Staten's operator
      catalog is undefined past this point.
    - stop_reason="max_depth": the column stayed on regular, self-consistent
      hex-to-hex faces through the full depth bound without hitting a
      boundary — a clean, sufficiently-interior column.
    """
    chain = [start_cell]
    current_cell = start_cell
    current_face_key = start_face_key
    stop_reason: _StopReason = "max_depth"
    for _ in range(max_depth):
        cell = cells[current_cell]
        pairing = _opposite_face_pairing(cell)
        if pairing is None:
            stop_reason = "ambiguous"
            break
        face_keys = [tuple(sorted(int(v) for v in face)) for face in cell]
        try:
            local_idx = face_keys.index(current_face_key)
        except ValueError:
            stop_reason = "ambiguous"
            break
        opposite_idx = next(
            (j if i == local_idx else i for i, j in pairing if local_idx in (i, j)),
            None,
        )
        if opposite_idx is None:
            stop_reason = "ambiguous"
            break
        opposite_key = face_keys[opposite_idx]
        neighbors = owners.get(opposite_key, [])
        other = [c for c in neighbors if c != current_cell]
        if len(other) != 1:
            stop_reason = "boundary"
            break
        next_cell = other[0]
        if next_cell in chain:
            return chain, True, "self_intersecting"
        chain.append(next_cell)
        current_cell = next_cell
        current_face_key = opposite_key
    return chain, False, stop_reason


def classify_repair_candidates(
    points: np.ndarray,
    cell_faces: CellFaces,
    flagged_faces: Sequence[BoundaryFaceSkew],
    *,
    max_depth: int = _DEFAULT_MAX_DEPTH,
) -> list[MatchCandidate]:
    """Staten-adapted decision: pillow vs. column-collapse vs. no candidate.

    Pure targeting/feasibility logic — no mesh mutation. Processes flagged
    faces in the caller's (deterministic) order and claims cells into
    ``claimed`` so a later face cannot silently reuse an earlier face's
    footprint (the "too close to another flagged face" stop condition).

    Decision rule per flagged face, adapted from Staten 2010 Section 4.3 (the
    single-sided reading: one bad face, not two-sided interface matching):

    1. Owner cell is not a clean 6-quad/8-vertex hex (an octree transition
       polyhedron) -> "none": Staten's pillow/extraction/column-collapse
       catalog is defined over hex dual sheets/columns; no clean column or
       shrink-set primitive exists on a non-hex cell.
    2. Trace the dual column starting at the flagged face, depth-bounded.
       If the column is self-intersecting -> Staten's own named doublet-risk
       exception rules out column collapse; fall back to a depth-1 pillow
       (the shrink set = {owner_cell} alone, always valid/regular for a
       single face-connected hex per Ledoux 2010 / Staten 2010 Sec. 3).
    3. If the column reaches depth >= 2 without self-intersecting, without
       hitting another boundary face (which would risk merging two different
       geometric patches — Staten's other named exception), and its footprint
       does not overlap a cell already claimed by an earlier flagged face ->
       column collapse, footprint = the traced chain.
    4. Otherwise (short/degenerate column, or footprint conflict) -> fall back
       to the depth-1 pillow if that single-cell footprint is itself free;
       else "none" (footprint overlaps another flagged face's claimed cells).

    ``points`` is accepted for API symmetry with the rest of this module (and
    potential future geometric tie-breaking) but the decision itself is purely
    topological, matching Staten 2010's own description of Algorithm 1 as
    almost entirely topological/spatial-proximity driven.
    """
    del points
    cells = [[[int(v) for v in face] for face in cell] for cell in cell_faces]
    owners = _face_owners(cells)

    claimed: set[int] = set()
    results: list[MatchCandidate] = []

    for flagged in flagged_faces:
        owner = flagged.owner_cell
        cell = cells[owner]

        if not _is_clean_hex(cell):
            results.append(
                MatchCandidate(
                    face_key=flagged.face_key,
                    owner_cell=owner,
                    skewness=flagged.skewness,
                    candidate_type="none",
                    footprint_cells=(owner,),
                    depth_used=0,
                    reason=(
                        "owner cell is not a clean hex (octree transition polyhedron) — "
                        "Staten's pillow/collapse catalog is undefined here"
                    ),
                )
            )
            continue

        chain, self_intersecting, stop_reason = _trace_column(
            cells, owners, owner, flagged.face_key, max_depth
        )

        if self_intersecting:
            footprint = (owner,)
            if claimed.isdisjoint(footprint):
                claimed.update(footprint)
                results.append(
                    MatchCandidate(
                        face_key=flagged.face_key,
                        owner_cell=owner,
                        skewness=flagged.skewness,
                        candidate_type="pillow",
                        footprint_cells=footprint,
                        depth_used=1,
                        reason=(
                            "dual column is self-intersecting (doublet risk per Staten "
                            "2010's own caveat) — fell back to depth-1 pillow insertion"
                        ),
                    )
                )
            else:
                results.append(
                    MatchCandidate(
                        face_key=flagged.face_key,
                        owner_cell=owner,
                        skewness=flagged.skewness,
                        candidate_type="none",
                        footprint_cells=(),
                        depth_used=0,
                        reason=(
                            "self-intersecting column forces pillow fallback, but the "
                            "owner cell is already claimed by another flagged face"
                        ),
                    )
                )
            continue

        if len(chain) >= 2 and stop_reason == "max_depth" and claimed.isdisjoint(chain):
            claimed.update(chain)
            results.append(
                MatchCandidate(
                    face_key=flagged.face_key,
                    owner_cell=owner,
                    skewness=flagged.skewness,
                    candidate_type="collapse",
                    footprint_cells=tuple(chain),
                    depth_used=len(chain) - 1,
                    reason=(
                        f"clean depth-{len(chain) - 1} interior column, no self-intersection, "
                        "did not exit into another boundary patch within the depth bound — "
                        "column-collapse candidate"
                    ),
                )
            )
            continue

        # Fall back to depth-1 pillow.
        footprint = (owner,)
        if claimed.isdisjoint(footprint):
            claimed.update(footprint)
            if stop_reason == "boundary":
                reason = (
                    f"column reaches another boundary patch after {len(chain) - 1} "
                    "interior cell(s) — thru-column risks merging two distinct boundary "
                    "regions on collapse — fell back to depth-1 pillow insertion"
                )
            elif stop_reason == "ambiguous":
                reason = (
                    "column exits into a non-hex or topology-ambiguous cell before a safe "
                    "depth is reached — fell back to depth-1 pillow insertion"
                )
            else:
                reason = (
                    "column has no interior depth (isolated corner cell) — "
                    "depth-1 pillow insertion"
                )
            results.append(
                MatchCandidate(
                    face_key=flagged.face_key,
                    owner_cell=owner,
                    skewness=flagged.skewness,
                    candidate_type="pillow",
                    footprint_cells=footprint,
                    depth_used=1,
                    reason=reason,
                )
            )
        else:
            results.append(
                MatchCandidate(
                    face_key=flagged.face_key,
                    owner_cell=owner,
                    skewness=flagged.skewness,
                    candidate_type="none",
                    footprint_cells=(),
                    depth_used=0,
                    reason=(
                        "no clean collapse and owner cell already claimed by "
                        "another flagged face"
                    ),
                )
            )

    return results


def run_match_diagnostic(
    shape_name: str,
    points: np.ndarray,
    cell_faces: CellFaces,
    *,
    skew_threshold: float = _SKEW_FLAG_THRESHOLD_DEFAULT,
    max_depth: int = _DEFAULT_MAX_DEPTH,
    log_only: bool = True,
) -> MatchDiagnosticReport:
    """End-to-end HEX-MATCH-1 targeting census for one mesh. Zero mesh edits."""
    faces = compute_boundary_face_skew(points, cell_faces)
    flagged = flag_bad_skew_faces(faces, threshold=skew_threshold)
    candidates = classify_repair_candidates(points, cell_faces, flagged, max_depth=max_depth)
    report = MatchDiagnosticReport(
        shape_name=str(shape_name),
        n_boundary_faces=len(faces),
        n_flagged=len(flagged),
        candidates=tuple(candidates),
    )
    log.info(
        "native_hex_match_diagnostic",
        shape=report.shape_name,
        n_boundary_faces=report.n_boundary_faces,
        n_flagged=report.n_flagged,
        n_pillow=report.n_pillow,
        n_collapse=report.n_collapse,
        n_none=report.n_none,
        skew_threshold=float(skew_threshold),
        max_depth=int(max_depth),
        log_only=bool(log_only),
    )
    return report
