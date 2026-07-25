"""QUAD-ROSY1 -- Jakob 2015 4-RoSy orientation field, diagnostic-only.

This is the first native_quad card.  It measures whether a Jakob/Tarini/
Panozzo/Sorkine-Hornung 2015 ("Instant Field-Aligned Meshes",
``docs/references/literature/native_quad/jakob2015_instant.md``) four-fold
rotationally-symmetric orientation field can be built on AutoTessell's real
input surfaces at all, and what singularity structure comes out.  It makes
**zero mesh edits** -- it reads ``(V, F)``, builds a field in a scratch array,
and returns a report (same log-only precedent as
``core/generator/native_tet/boundary_invariant.py`` and
``core/generator/native_hex/match_diagnostic.py``).  Nothing here is wired
into ``native_remesh``'s production path; the existing triangle-pair merger
stays the production fallback untouched.

Why this shape of diagnostic and not another
--------------------------------------------
The whole point of the card is a falsifiable number, and a 4-RoSy field has
one: **Poincare-Hopf**.  On a closed oriented surface the fractional indices
of the field's singularities must sum to the Euler characteristic ``chi``.
So the report carries ``index_sum`` (in quarter-turn integer units, i.e.
``4 * chi`` when correct) next to the mesh's own ``chi = V - E + F``.  If the
transport/index code is wrong, that identity breaks loudly on every shape --
which is exactly what happened during this card's verification (see the
"convention" note on ``compute_orientation_singularities``).

The index is read out twice, once per discrete connection (extrinsic and
intrinsic), because on sharp-featured input the two readouts of the *same*
field disagree substantially, and which one you trust changes whether the
field looks usable.  See ``SingularityCensus``.  The readout also has a
sampling limit that shows up on very coarse input -- see the resolution
caveat on ``compute_orientation_singularities``.

What is ported faithfully
-------------------------
* **Eq. (2), extrinsic 4-RoSy smoothness energy.**  For an edge ``(i, j)``
  the energy is ``min_{k,l} ||R_{n_i}(k*pi/2) o_i - R_{n_j}(l*pi/2) o_j||^2``.
  Because both representatives are unit vectors this equals
  ``2 - 2*max_{k,l}(a . b)``, and because the 4-fold class ``{q, n x q, -q,
  -n x q}`` only has two directions up to sign, the inner minimization is a
  2x2 search with a sign fix -- the paper's own reduction, not an
  approximation of it.
* **Eq. (1), intrinsic energy**, is also measured (reported, not optimized):
  same comparison after parallel transport of ``o_i`` into ``n_j``'s tangent
  plane by the Rodrigues rotation about ``n_i x n_j``.
* **The nonlinear Gauss-Seidel update.**  Each visit rebuilds vertex ``i``'s
  representative as a running symmetry-aligned weighted average over its
  1-ring, re-projected to the tangent plane and re-normalized after every
  neighbor.  The vertex's own incoming value acts only as the symmetry-branch
  reference for the first neighbor (``weight_sum`` starts at zero), which is
  the paper's update, not a simplification of it.
* **Singularity indices** accumulate the integer symmetry jump
  ``l_ij - k_ij`` around each oriented face loop and reduce mod 4.

Documented scope reductions versus the full paper
-------------------------------------------------
1. **No multiresolution hierarchy.**  The paper runs ~6 Gauss-Seidel sweeps
   per level of a deterministic vertex-aggregation hierarchy, coarse to fine;
   this runs plain single-resolution sweeps on the input mesh.  Consequence:
   more local minima and (per the paper's own limitation section) more
   singularities than a hierarchical solve would give.  Measured here so the
   gap is a number rather than a guess -- ``QUAD-MULTIRES1`` is the card that
   closes it.
2. **No graph coloring / no parallelism.**  Sweeps are sequential in vertex
   index order.  That makes the result deterministic for a fixed seed (a
   property the parallel version does *not* have), which is what a diagnostic
   wants, but it is not the paper's solver.
3. **Uniform edge weights.**  The paper weights neighbor contributions by the
   hierarchy's area weights.  Weights are 1.0 here.
4. **Extrinsic energy drives the relaxation**, matching the reference
   implementation's default; the intrinsic energy is measured only.  The
   paper notes the extrinsic form is what snaps the field to sharp features
   without a separate feature detector.
5. **No 4-PoSy position field, no extraction.**  That is ``QUAD-POSY1`` and
   ``QUAD-EXTRACT1``.  This card stops at orientation.

The optional curvature-alignment measurement is Alliez et al. 2003's idea
(``docs/references/literature/native_quad/alliez2003_anisotropic.md``): a
good quad field should follow principal curvature lines where curvature is
anisotropic.  The codebase only had *scalar* curvature
(``core/analyzer/curvature.py``, ``core/analyzer/mean_curvature.py``), so the
normal-cycle *tensor* is estimated here, over the 1-ring only.  See
``estimate_curvature_tensors`` for that reduction.

Field lives on **vertices**, singularities on **faces**.  The card text in
``docs/plans/native_engine_autoresearch_queue_2026-07-23.md`` describes the
dual convention (field on faces, index around a vertex 1-ring); Jakob 2015
puts the orientation field on vertices, so its singularities necessarily live
on faces, and following the paper was judged more useful than following the
card's shorthand.
"""

from __future__ import annotations

import math
import time
from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

from core.utils.logging import get_logger

log = get_logger(__name__)

_EPS = 1e-12

# Alliez 2003 clamps sampling to isotropic where the curvature tensor's
# deviator vanishes (umbilics); below this normalized deviator a vertex has no
# stable principal direction and is excluded from the alignment statistic.
_ANISOTROPY_THRESHOLD_DEFAULT = 0.3


# --------------------------------------------------------------------------
# report types
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class OrientationSingularity:
    """One face whose accumulated 4-RoSy symmetry jump is nonzero.

    ``index`` is in quarter-turn integer units, reduced to the centered
    residue set ``{-1, 1, 2}`` (0 is not a singularity).  ``2`` is the
    ambiguous ``+-1/2`` case -- see ``RosyDiagnosticReport.n_half_index``.
    """

    face: int
    index: int
    centroid: tuple[float, float, float]

    @property
    def fractional_index(self) -> float:
        return self.index / 4.0


@dataclass(frozen=True)
class SingularityCensus:
    """Singularity set read out under one choice of discrete connection.

    The extrinsic and intrinsic readouts are two views of the *same* field and
    they do not always agree -- on sharp-featured input they disagree a lot
    (measured: 18 ambiguous ``+-1/2`` faces extrinsically versus 4
    intrinsically on ``03_hard_bracket.stl``).  Reporting only one would hide
    that, so the diagnostic carries both.
    """

    connection: str  # "extrinsic" | "intrinsic"
    euler_characteristic: int
    closed: bool
    singularities: tuple[OrientationSingularity, ...] = field(default_factory=tuple)

    @property
    def n_singularities(self) -> int:
        return len(self.singularities)

    @property
    def index_sum(self) -> int:
        return sum(s.index for s in self.singularities)

    @property
    def n_half_index(self) -> int:
        """Count of ambiguous ``+-1/2`` faces (raw jump == 2 mod 4).

        Each one costs the Poincare-Hopf sum up to 4 quarter-turns of
        ambiguity, so a strict mismatch is only meaningful when this is 0.
        """
        return sum(1 for s in self.singularities if s.index == 2)

    @property
    def index_histogram(self) -> dict[int, int]:
        hist: dict[int, int] = {}
        for s in self.singularities:
            hist[s.index] = hist.get(s.index, 0) + 1
        return dict(sorted(hist.items()))

    @property
    def poincare_hopf_ok(self) -> bool:
        """``sum(fractional index) == chi`` on a closed surface.

        The falsification gate for the whole card.  Undefined (reported
        ``False``) on meshes with boundary.
        """
        return self.closed and self.index_sum == 4 * self.euler_characteristic

    @property
    def poincare_hopf_reconcilable(self) -> bool:
        """``poincare_hopf_ok`` allowing for the ``+-1/2`` representative choice.

        A face whose raw jump is ``2 (mod 4)`` is genuinely ``+1/2`` *or*
        ``-1/2``; the residue reduction has to pick one arbitrarily, and each
        wrong pick shifts ``index_sum`` by exactly 4.  So the theorem is only
        actually violated if no assignment of those faces can reach
        ``4 * chi``.  Distinguishing the two cases is the difference between
        "the field is wrong" and "the readout is ambiguous", which matters a
        lot when deciding whether to build ``QUAD-POSY1`` on top of it.
        """
        if not self.closed:
            return False
        gap = self.index_sum - 4 * self.euler_characteristic
        if gap % 4 != 0:
            return False
        return 0 <= gap // 4 <= self.n_half_index


@dataclass(frozen=True)
class CurvatureAlignment:
    """Alliez-2003-style check: does the field follow principal directions?

    Deviations are 4-RoSy deviations, i.e. folded into ``[0, 45]`` degrees,
    because ``{+-e1, +-e2}`` is a single cross.  A uniformly random field
    averages 22.5 degrees, so ``mean_deviation_deg_initial`` (the same
    statistic on the un-relaxed seed field) is the honest null baseline to
    compare ``mean_deviation_deg`` against.
    """

    n_anisotropic_vertices: int
    anisotropy_threshold: float
    mean_deviation_deg: float
    median_deviation_deg: float
    p90_deviation_deg: float
    mean_deviation_deg_initial: float


@dataclass(frozen=True)
class RosyDiagnosticReport:
    """Per-shape QUAD-ROSY1 measurement.  Log-only; no mesh was touched."""

    shape_name: str
    n_vertices: int
    n_faces: int
    n_edges: int
    n_boundary_edges: int
    euler_characteristic: int
    n_sweeps: int
    seed: int
    energy_before: float
    energy_after: float
    energy_trace: tuple[float, ...] = field(default_factory=tuple)
    intrinsic_energy_before: float = 0.0
    intrinsic_energy_after: float = 0.0
    extrinsic: SingularityCensus | None = None
    intrinsic: SingularityCensus | None = None
    curvature: CurvatureAlignment | None = None
    elapsed_s: float = 0.0

    @property
    def closed(self) -> bool:
        return self.n_boundary_edges == 0

    # The extrinsic readout is the primary one: it is the connection the
    # relaxation actually minimizes against, so reading indices any other way
    # would describe a field we did not optimize.
    @property
    def singularities(self) -> tuple[OrientationSingularity, ...]:
        return self.extrinsic.singularities if self.extrinsic else ()

    @property
    def n_singularities(self) -> int:
        return self.extrinsic.n_singularities if self.extrinsic else 0

    @property
    def index_sum(self) -> int:
        return self.extrinsic.index_sum if self.extrinsic else 0

    @property
    def n_half_index(self) -> int:
        return self.extrinsic.n_half_index if self.extrinsic else 0

    @property
    def index_histogram(self) -> dict[int, int]:
        return self.extrinsic.index_histogram if self.extrinsic else {}

    @property
    def poincare_hopf_ok(self) -> bool:
        return bool(self.extrinsic and self.extrinsic.poincare_hopf_ok)

    @property
    def poincare_hopf_reconcilable(self) -> bool:
        return bool(self.extrinsic and self.extrinsic.poincare_hopf_reconcilable)

    @property
    def mean_edge_energy_after(self) -> float:
        return self.energy_after / self.n_edges if self.n_edges else 0.0


# --------------------------------------------------------------------------
# mesh connectivity helpers (read-only)
# --------------------------------------------------------------------------


def weld_vertices(
    vertices: NDArray[np.float64], faces: NDArray[np.int64], *, tol_digits: int = 9
) -> tuple[NDArray[np.float64], NDArray[np.int64]]:
    """Deduplicate coincident vertices into *new* arrays (inputs untouched).

    Raw STL is per-facet: every triangle carries its own copy of each corner,
    so the mesh has literally no vertex adjacency until it is welded, and a
    field diagnostic on an unwelded mesh measures nothing.  Rounding to
    ``tol_digits`` decimals keeps this deterministic (no floating-point
    tie-breaking on ``np.unique``) at the cost of being scale-dependent --
    acceptable because it only decides vertex identity, never geometry.
    """
    V = np.asarray(vertices, dtype=np.float64)
    F = np.asarray(faces, dtype=np.int64)
    if V.size == 0 or F.size == 0:
        return V.copy(), F.copy()
    keys = np.round(V, tol_digits)
    _, first_idx, inverse = np.unique(keys, axis=0, return_index=True, return_inverse=True)
    order = np.argsort(first_idx)
    remap = np.empty(order.shape[0], dtype=np.int64)
    remap[order] = np.arange(order.shape[0], dtype=np.int64)
    new_V = V[first_idx[order]]
    new_F = remap[inverse.reshape(-1)][F]
    # drop triangles that collapsed to a degenerate sliver by welding.
    keep = (
        (new_F[:, 0] != new_F[:, 1])
        & (new_F[:, 1] != new_F[:, 2])
        & (new_F[:, 0] != new_F[:, 2])
    )
    return new_V, new_F[keep]


def _edge_face_count(faces: NDArray[np.int64]) -> dict[tuple[int, int], int]:
    counts: dict[tuple[int, int], int] = defaultdict(int)
    for tri in faces:
        a, b, c = int(tri[0]), int(tri[1]), int(tri[2])
        for u, v in ((a, b), (b, c), (c, a)):
            counts[(u, v) if u < v else (v, u)] += 1
    return dict(counts)


def _vertex_adjacency(faces: NDArray[np.int64], n_v: int) -> list[NDArray[np.int64]]:
    adj: list[set[int]] = [set() for _ in range(n_v)]
    for tri in faces:
        a, b, c = int(tri[0]), int(tri[1]), int(tri[2])
        adj[a].update((b, c))
        adj[b].update((a, c))
        adj[c].update((a, b))
    return [np.array(sorted(s), dtype=np.int64) for s in adj]


def vertex_normals(
    vertices: NDArray[np.float64], faces: NDArray[np.int64]
) -> NDArray[np.float64]:
    """Area-weighted vertex normals -- the tangent-plane definition the field
    lives in.  Matches the convention already used by ``native_tri``'s
    tangential smoothing so the two modules do not disagree about "the
    surface normal at v"."""
    V = np.asarray(vertices, dtype=np.float64)
    F = np.asarray(faces, dtype=np.int64)
    N = np.zeros_like(V)
    if F.size == 0:
        return N
    tri = V[F]
    # un-normalized cross product is already area-weighted (2 * area).
    fn = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    for k in range(3):
        np.add.at(N, F[:, k], fn)
    norms = np.linalg.norm(N, axis=1)
    bad = norms < _EPS
    if bad.any():
        # isolated / degenerate vertex: any unit vector keeps the frame valid.
        N[bad] = np.array([0.0, 0.0, 1.0])
        norms[bad] = 1.0
    return N / norms[:, None]


# --------------------------------------------------------------------------
# 4-RoSy primitives (Jakob 2015 Eq. 1 / Eq. 2 inner minimizations)
# --------------------------------------------------------------------------


def _rotate_into_plane(
    v: NDArray[np.float64], n_from: NDArray[np.float64], n_to: NDArray[np.float64]
) -> NDArray[np.float64]:
    """Parallel transport ``v`` from ``n_from``'s tangent plane to ``n_to``'s.

    Rodrigues rotation about ``n_from x n_to``.  Antipodal normals have no
    well-defined transport; the mesh would be locally degenerate there, so we
    return ``v`` unchanged rather than inventing an axis.
    """
    axis = np.cross(n_from, n_to)
    s = float(np.linalg.norm(axis))
    c = float(np.dot(n_from, n_to))
    if s < _EPS:
        return v
    axis = axis / s
    angle = math.atan2(s, c)
    ca, sa = math.cos(angle), math.sin(angle)
    return v * ca + np.cross(axis, v) * sa + axis * float(np.dot(axis, v)) * (1.0 - ca)


def _best_match_extrinsic_4(
    q0: NDArray[np.float64],
    n0: NDArray[np.float64],
    q1: NDArray[np.float64],
    n1: NDArray[np.float64],
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Representatives of the two 4-RoSy classes that minimize Eq. (2).

    The class of ``q`` in the tangent plane of ``n`` is ``{q, n x q, -q,
    -n x q}``.  Up to sign that is two directions, so the 4x4 minimization
    collapses to a 2x2 search on ``|a . b|`` plus one sign fix -- the same
    reduction the reference implementation makes.
    """
    A = (q0, np.cross(n0, q0))
    B = (q1, np.cross(n1, q1))
    best = -np.inf
    ba = bb = 0
    for i in range(2):
        for j in range(2):
            score = abs(float(np.dot(A[i], B[j])))
            if score > best:
                best, ba, bb = score, i, j
    sign = 1.0 if float(np.dot(A[ba], B[bb])) >= 0.0 else -1.0
    return A[ba], B[bb] * sign


def _best_match_extrinsic_index_4(
    q0: NDArray[np.float64],
    n0: NDArray[np.float64],
    q1: NDArray[np.float64],
    n1: NDArray[np.float64],
) -> tuple[int, int]:
    """Same minimization as ``_best_match_extrinsic_4`` but returning the
    integer symmetry indices ``k, l in {0..3}`` -- the quantity whose loop sum
    is the singularity index."""
    A = (q0, np.cross(n0, q0))
    B = (q1, np.cross(n1, q1))
    best = -np.inf
    ba = bb = 0
    for i in range(2):
        for j in range(2):
            score = abs(float(np.dot(A[i], B[j])))
            if score > best:
                best, ba, bb = score, i, j
    if float(np.dot(A[ba], B[bb])) < 0.0:
        bb += 2
    return ba, bb


def _best_match_intrinsic_index_4(
    q0: NDArray[np.float64],
    n0: NDArray[np.float64],
    q1: NDArray[np.float64],
    n1: NDArray[np.float64],
) -> tuple[int, int]:
    """Eq. (1)'s integer symmetry indices: transport ``q0`` into ``n1``'s
    tangent plane first, then match.  This is the Levi-Civita-flavoured
    connection; ``_best_match_extrinsic_index_4`` is the embedded one."""
    q0t = _rotate_into_plane(q0, n0, n1)
    A = (q0t, np.cross(n1, q0t))
    B = (q1, np.cross(n1, q1))
    best = -np.inf
    ba = bb = 0
    for i in range(2):
        for j in range(2):
            score = abs(float(np.dot(A[i], B[j])))
            if score > best:
                best, ba, bb = score, i, j
    if float(np.dot(A[ba], B[bb])) < 0.0:
        bb += 2
    return ba, bb


def _pair_energy_extrinsic(
    q0: NDArray[np.float64],
    n0: NDArray[np.float64],
    q1: NDArray[np.float64],
    n1: NDArray[np.float64],
) -> float:
    a, b = _best_match_extrinsic_4(q0, n0, q1, n1)
    d = a - b
    return float(np.dot(d, d))


def _pair_energy_intrinsic(
    q0: NDArray[np.float64],
    n0: NDArray[np.float64],
    q1: NDArray[np.float64],
    n1: NDArray[np.float64],
) -> float:
    """Eq. (1): the same disagreement measured after parallel transport."""
    q0t = _rotate_into_plane(q0, n0, n1)
    a, b = _best_match_extrinsic_4(q0t, n1, q1, n1)
    d = a - b
    return float(np.dot(d, d))


# --------------------------------------------------------------------------
# field construction
# --------------------------------------------------------------------------


def initial_orientation_field(
    normals: NDArray[np.float64], *, seed: int = 0
) -> NDArray[np.float64]:
    """Deterministic pseudo-random unit tangent per vertex.

    The paper seeds randomly; a fixed ``default_rng`` seed keeps the whole
    diagnostic reproducible, which the sequential (uncolored) sweep order
    then preserves end to end.
    """
    N = np.asarray(normals, dtype=np.float64)
    rng = np.random.default_rng(seed)
    raw = rng.standard_normal(N.shape)
    tangent = raw - N * np.sum(raw * N, axis=1)[:, None]
    norms = np.linalg.norm(tangent, axis=1)
    bad = norms < 1e-6
    if bad.any():
        # random draw landed on the normal; any perpendicular axis will do.
        alt = np.tile(np.array([1.0, 0.0, 0.0]), (int(bad.sum()), 1))
        flip = np.abs(N[bad][:, 0]) > 0.9
        alt[flip] = np.array([0.0, 1.0, 0.0])
        t = alt - N[bad] * np.sum(alt * N[bad], axis=1)[:, None]
        tangent[bad] = t
        norms[bad] = np.linalg.norm(t, axis=1)
    return tangent / np.maximum(norms, _EPS)[:, None]


def optimize_orientations(
    normals: NDArray[np.float64],
    adjacency: list[NDArray[np.int64]],
    orientations: NDArray[np.float64],
    edges: NDArray[np.int64],
    *,
    n_sweeps: int = 20,
) -> tuple[NDArray[np.float64], list[float]]:
    """Sequential nonlinear Gauss-Seidel on the extrinsic 4-RoSy energy.

    Returns the relaxed field (a new array) plus the per-sweep energy trace
    including the pre-relaxation value, so convergence -- or stalling in a
    local minimum, which the paper explicitly warns about -- is visible in
    the report instead of implied.
    """
    Q = np.array(orientations, dtype=np.float64, copy=True)
    N = np.asarray(normals, dtype=np.float64)
    trace = [orientation_energy(Q, N, edges)]
    for _ in range(n_sweeps):
        for i in range(Q.shape[0]):
            nbrs = adjacency[i]
            if nbrs.size == 0:
                continue
            n_i = N[i]
            acc = Q[i].copy()
            weight_sum = 0.0
            for j in nbrs:
                weight = 1.0
                a, b = _best_match_extrinsic_4(acc, n_i, Q[j], N[j])
                acc = a * weight_sum + b * weight
                acc = acc - n_i * float(np.dot(n_i, acc))
                weight_sum += weight
                nrm = float(np.linalg.norm(acc))
                if nrm > _EPS:
                    acc = acc / nrm
            if weight_sum > 0.0:
                Q[i] = acc
        trace.append(orientation_energy(Q, N, edges))
    return Q, trace


def orientation_energy(
    orientations: NDArray[np.float64],
    normals: NDArray[np.float64],
    edges: NDArray[np.int64],
    *,
    intrinsic: bool = False,
) -> float:
    """Total Jakob 2015 4-RoSy smoothness energy over the edge set."""
    if edges.size == 0:
        return 0.0
    pair = _pair_energy_intrinsic if intrinsic else _pair_energy_extrinsic
    total = 0.0
    for e in edges:
        i, j = int(e[0]), int(e[1])
        total += pair(orientations[i], normals[i], orientations[j], normals[j])
    return total


def compute_orientation_singularities(
    vertices: NDArray[np.float64],
    faces: NDArray[np.int64],
    orientations: NDArray[np.float64],
    normals: NDArray[np.float64],
    *,
    intrinsic: bool = False,
) -> list[OrientationSingularity]:
    """Faces whose accumulated symmetry jump around the oriented loop is
    nonzero mod 4.

    Convention note: the raw loop sum ``sum(l_ij - k_ij)`` taken in the
    face's own winding order, reduced to the centered residue set, already
    satisfies Poincare-Hopf against outward-oriented faces -- no negation.
    That was verified rather than assumed: an experimental negation made the
    cube report ``index_sum = -8`` against ``4 * chi = +8`` and was removed.
    The sign is pinned by the theorem's *total*, which does not constrain the
    individual indices, so nothing about the singularity pattern is forced.

    Resolution caveat (measured, not theoretical): the jump chosen per edge is
    the *smallest* rotation aligning the two 4-fold classes, so the readout
    only recovers the true index while adjacent frames differ by less than a
    quarter turn.  A mesh coarse enough to violate that aliases -- a bare
    tetrahedron (adjacent vertex normals ~109 degrees apart) reports
    ``index_sum = 4`` where ``4 * chi = 8``, under *both* connections.  That
    is a sampling limit of the discrete index, not a solver failure; it is
    pinned by ``test_tetrahedron_is_too_coarse_for_a_faithful_index``.
    """
    V = np.asarray(vertices, dtype=np.float64)
    F = np.asarray(faces, dtype=np.int64)
    match = _best_match_intrinsic_index_4 if intrinsic else _best_match_extrinsic_index_4
    out: list[OrientationSingularity] = []
    for fi in range(F.shape[0]):
        loop = 0
        for k in range(3):
            i = int(F[fi, k])
            j = int(F[fi, (k + 1) % 3])
            a, b = match(orientations[i], normals[i], orientations[j], normals[j])
            loop += b - a
        # centered residue in {-1, 0, 1, 2}: 3 quarter-turns == -1 quarter-turn.
        idx = ((loop + 1) % 4) - 1
        if idx != 0:
            cen = V[F[fi]].mean(axis=0)
            out.append(
                OrientationSingularity(
                    face=fi,
                    index=idx,
                    centroid=(float(cen[0]), float(cen[1]), float(cen[2])),
                )
            )
    return out


# --------------------------------------------------------------------------
# Alliez 2003 curvature alignment (secondary measurement)
# --------------------------------------------------------------------------


def estimate_curvature_tensors(
    vertices: NDArray[np.float64], faces: NDArray[np.int64]
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Cohen-Steiner/Morvan normal-cycle curvature tensor per vertex.

    ``T(v) = (1/|B|) * sum_e beta(e) * |e| * e_hat e_hat^T`` over the edges of
    the 1-ring, with ``beta(e)`` the signed dihedral angle across ``e``.

    Scope reduction versus Alliez 2003: the paper clips each edge to a ball
    ``B`` (``|e ^ B|``) and smooths the tensor field afterwards.  Here ``B``
    is exactly the 1-ring, edges enter at full length, and there is no tensor
    smoothing.  That makes the estimate noisier than the paper's, which only
    matters for the *secondary* alignment statistic -- the RoSy diagnostic
    itself does not consume this.

    Returns ``(tensors (n,3,3), vertex_areas (n,))``.
    """
    V = np.asarray(vertices, dtype=np.float64)
    F = np.asarray(faces, dtype=np.int64)
    n_v = V.shape[0]
    T = np.zeros((n_v, 3, 3), dtype=np.float64)
    areas = np.zeros(n_v, dtype=np.float64)
    if F.size == 0:
        return T, areas

    tri = V[F]
    fn = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    fa = 0.5 * np.linalg.norm(fn, axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        fn_unit = fn / np.maximum(np.linalg.norm(fn, axis=1), _EPS)[:, None]
    for k in range(3):
        np.add.at(areas, F[:, k], fa / 3.0)

    edge_faces: dict[tuple[int, int], list[int]] = defaultdict(list)
    for fi in range(F.shape[0]):
        a, b, c = int(F[fi, 0]), int(F[fi, 1]), int(F[fi, 2])
        for u, v in ((a, b), (b, c), (c, a)):
            edge_faces[(u, v) if u < v else (v, u)].append(fi)

    for (u, v), fl in edge_faces.items():
        if len(fl) != 2:
            continue  # boundary or non-manifold: no dihedral angle defined.
        e = V[v] - V[u]
        length = float(np.linalg.norm(e))
        if length < _EPS:
            continue
        e_hat = e / length
        n1, n2 = fn_unit[fl[0]], fn_unit[fl[1]]
        beta = math.atan2(float(np.dot(np.cross(n1, n2), e_hat)), float(np.dot(n1, n2)))
        contrib = beta * length * np.outer(e_hat, e_hat)
        T[u] += contrib
        T[v] += contrib

    nz = areas > _EPS
    T[nz] /= areas[nz][:, None, None]
    return T, areas


def measure_curvature_alignment(
    vertices: NDArray[np.float64],
    faces: NDArray[np.int64],
    orientations: NDArray[np.float64],
    normals: NDArray[np.float64],
    initial_orientations: NDArray[np.float64],
    *,
    anisotropy_threshold: float = _ANISOTROPY_THRESHOLD_DEFAULT,
) -> CurvatureAlignment:
    """4-RoSy deviation of the field from the principal-curvature cross.

    Only vertices whose normalized tensor deviator clears
    ``anisotropy_threshold`` count -- at an umbilic there is no stable
    principal direction, so including it would just add noise at the random
    baseline (Alliez 2003's umbilic fallback, applied here as a filter rather
    than as a sampling mode).

    Which tangent eigenvector is ``k_max`` versus ``k_min`` does not matter:
    the 4-RoSy cross ``{+-e1, +-e2}`` is the same set either way, so the
    deviation statistic is invariant to that (frequently mis-stated)
    correspondence.
    """
    T, _ = estimate_curvature_tensors(vertices, faces)
    devs: list[float] = []
    devs_initial: list[float] = []
    for i in range(T.shape[0]):
        w, U = np.linalg.eigh(T[i])
        # the eigenvector closest to the surface normal carries the ~0
        # eigenvalue; the other two span the tangent plane.
        align = np.abs(U.T @ normals[i])
        n_axis = int(np.argmax(align))
        tangent_axes = [k for k in range(3) if k != n_axis]
        l0, l1 = abs(float(w[tangent_axes[0]])), abs(float(w[tangent_axes[1]]))
        denom = l0 + l1
        if denom < _EPS:
            continue
        if abs(l0 - l1) / denom < anisotropy_threshold:
            continue
        e1 = U[:, tangent_axes[0] if l0 >= l1 else tangent_axes[1]]
        e1 = e1 - normals[i] * float(np.dot(normals[i], e1))
        nrm = float(np.linalg.norm(e1))
        if nrm < _EPS:
            continue
        e1 = e1 / nrm
        for src, sink in ((orientations, devs), (initial_orientations, devs_initial)):
            c = min(1.0, abs(float(np.dot(src[i], e1))))
            theta = math.degrees(math.acos(c))
            sink.append(min(theta, 90.0 - theta))

    if not devs:
        return CurvatureAlignment(0, anisotropy_threshold, 0.0, 0.0, 0.0, 0.0)
    arr = np.array(devs)
    return CurvatureAlignment(
        n_anisotropic_vertices=len(devs),
        anisotropy_threshold=anisotropy_threshold,
        mean_deviation_deg=float(arr.mean()),
        median_deviation_deg=float(np.median(arr)),
        p90_deviation_deg=float(np.percentile(arr, 90)),
        mean_deviation_deg_initial=float(np.array(devs_initial).mean()),
    )


# --------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------


def run_rosy_diagnostic(
    vertices: NDArray[np.float64],
    faces: NDArray[np.int64],
    shape_name: str,
    *,
    n_sweeps: int = 20,
    seed: int = 0,
    weld: bool = True,
    with_curvature: bool = True,
    anisotropy_threshold: float = _ANISOTROPY_THRESHOLD_DEFAULT,
) -> RosyDiagnosticReport:
    """Build and measure a 4-RoSy field on ``(V, F)``.  Nothing is mutated.

    ``weld`` deduplicates coincident vertices into a local copy first, because
    raw STL has no vertex adjacency at all (see ``weld_vertices``).  The
    caller's arrays are never written to.
    """
    t0 = time.perf_counter()
    V = np.asarray(vertices, dtype=np.float64)
    F = np.asarray(faces, dtype=np.int64)
    if weld:
        V, F = weld_vertices(V, F)

    n_v, n_f = int(V.shape[0]), int(F.shape[0])
    edge_counts = _edge_face_count(F)
    edges = np.array(sorted(edge_counts.keys()), dtype=np.int64).reshape(-1, 2)
    n_boundary = sum(1 for c in edge_counts.values() if c != 2)
    chi = n_v - edges.shape[0] + n_f

    normals = vertex_normals(V, F)
    Q0 = initial_orientation_field(normals, seed=seed)
    adjacency = _vertex_adjacency(F, n_v)
    Q, trace = optimize_orientations(normals, adjacency, Q0, edges, n_sweeps=n_sweeps)

    closed = n_boundary == 0
    censuses = {
        name: SingularityCensus(
            connection=name,
            euler_characteristic=int(chi),
            closed=closed,
            singularities=tuple(
                compute_orientation_singularities(
                    V, F, Q, normals, intrinsic=(name == "intrinsic")
                )
            ),
        )
        for name in ("extrinsic", "intrinsic")
    }
    curvature = (
        measure_curvature_alignment(
            V, F, Q, normals, Q0, anisotropy_threshold=anisotropy_threshold
        )
        if with_curvature
        else None
    )

    report = RosyDiagnosticReport(
        shape_name=shape_name,
        n_vertices=n_v,
        n_faces=n_f,
        n_edges=int(edges.shape[0]),
        n_boundary_edges=n_boundary,
        euler_characteristic=int(chi),
        n_sweeps=n_sweeps,
        seed=seed,
        energy_before=trace[0],
        energy_after=trace[-1],
        energy_trace=tuple(trace),
        intrinsic_energy_before=orientation_energy(Q0, normals, edges, intrinsic=True),
        intrinsic_energy_after=orientation_energy(Q, normals, edges, intrinsic=True),
        extrinsic=censuses["extrinsic"],
        intrinsic=censuses["intrinsic"],
        curvature=curvature,
        elapsed_s=time.perf_counter() - t0,
    )
    log.info(
        "quad_rosy_diagnostic",
        shape=report.shape_name,
        n_vertices=report.n_vertices,
        n_faces=report.n_faces,
        n_edges=report.n_edges,
        closed=report.closed,
        euler=report.euler_characteristic,
        energy_before=round(report.energy_before, 6),
        energy_after=round(report.energy_after, 6),
        mean_edge_energy_after=round(report.mean_edge_energy_after, 6),
        intrinsic_energy_after=round(report.intrinsic_energy_after, 6),
        n_singularities=report.n_singularities,
        index_histogram=report.index_histogram,
        index_sum=report.index_sum,
        n_half_index=report.n_half_index,
        poincare_hopf_ok=report.poincare_hopf_ok,
        poincare_hopf_reconcilable=report.poincare_hopf_reconcilable,
        intrinsic_n_singularities=censuses["intrinsic"].n_singularities,
        intrinsic_index_histogram=censuses["intrinsic"].index_histogram,
        intrinsic_index_sum=censuses["intrinsic"].index_sum,
        intrinsic_n_half_index=censuses["intrinsic"].n_half_index,
        intrinsic_poincare_hopf_ok=censuses["intrinsic"].poincare_hopf_ok,
        curvature_mean_dev_deg=(
            round(curvature.mean_deviation_deg, 3) if curvature else None
        ),
        curvature_mean_dev_deg_initial=(
            round(curvature.mean_deviation_deg_initial, 3) if curvature else None
        ),
        elapsed_s=round(report.elapsed_s, 3),
    )
    return report
