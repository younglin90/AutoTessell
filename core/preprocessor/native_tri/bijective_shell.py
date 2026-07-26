"""Static linear bijective shell (Jiang 2020) for the native-tri Phase 3
fine-tier error-gate / provenance contract.

This is the ``TRI-SHELL-DOMAIN1`` card: a generalized-prism shell layer
built **once** from the original input surface, before any remeshing
starts, and used afterward only as a read-only, static reference domain
(never rebuilt from the moving mesh -- see
``docs/references/literature/native_tri/jiang2020_bijective_shell.md``).

Per ``docs/references/literature/native_tri/shell_efficiency_check_2026-07-25.md``
(confirmed 2026-07-25: no published method makes a per-edit shell/bijective
check cheap for an iterative local-operator loop -- Jiang 2020 itself calls
a per-op shell check unsuitable for interactive use, and Zhu 2026
(BijectiveRemesh, arXiv:2605.30744) measures ~110x per-op overhead for the
chained-atlas alternative), this shell is deliberately **not** queried per
edit. It is queried once per completed ``operator_loop.py`` round (see
``run_rounds`` in ``operator_loop.py``), which amortizes the cost the
paper's own robustness numbers describe (mean ~6 min *build* time on
Thingi10k-scale meshes; per-op/per-round queries were not the expensive
part).

Contract (Jiang 2020 Section 3, Def 3.1-3.3, Theorem 3.2/3.5/3.6/3.7):
  * The shell is a set of prisms, one per input-surface triangle, each with
    a bottom/middle/top layer. Every prism decomposes into 6 tetrahedra
    (a "double slab": 3 from bottom-to-middle, 3 from middle-to-top).
  * **I1** (positivity): all 6 tets of every prism must have consistent,
    non-degenerate signed volume -- an inverted or self-intersecting prism
    fails I1.
  * **I2** (section validity): the input surface itself must lie strictly
    between the top and bottom caps with each face normal pointing into
    the positive half of the prism's extrusion field ("normal condition").
  * A mesh triangle is a "section" of the shell -- and hence bijectively
    mapped to the middle surface, and provably self-intersection-free -- if
    every point of it lies inside some prism with a positive dot product
    against that prism's local field (Theorem 3.7 licenses checking this
    per local operation or, here, once per batch of them).

Documented scope reductions versus the full paper (kept honest rather than
silently matching the paper's claims -- see the "Applicability to
AutoTessell cards" section of ``jiang2020_bijective_shell.md``, which
already flags exactly these two risks for a first implementation):

  1. **Extrusion direction** is the area-weighted vertex normal (the same
     pattern ``operator_loop.py``'s tangential smoothing already uses), not
     the paper's exact "most normal normal" QP (Appendix C). This is
     adequate for the closed, smooth verification corpus (cube/sphere) but
     is not certified to find a feasible direction on a badly conditioned
     1-ring the way the QP is -- a follow-up if a future corpus case fails
     construction because of it.
  2. **I1 is checked as self-consistency of one canonical 6-tet
     decomposition per prism** (all 6 tets share one nonzero orientation
     sign, keyed by rotating each face to start at its lowest global vertex
     index so shared side-quads pick the same diagonal from either
     neighbor), rather than the paper's full 24-tet / all-6-decomposition
     order-independence certificate. This still rejects every genuinely
     inverted or degenerate prism (I1's actual purpose) but is *not*
     certified against every numbering-order edge case the combinatorial
     6-decomposition check would catch. No topological beveling and no
     singularity pinching are implemented either -- both are unexercised by
     the closed, positive-dihedral verification corpus; both would be
     required before pointing this shell at general/CAD input.
  3. **Containment** is a brute-force, AABB-prefiltered point-in-tetrahedron
     test built only from Shewchuk exact ``orient3d`` (no Guigue-Devillers
     tri-tri overlap, no static AABB tree). This is adequate at the
     verification corpus scale; an accelerated spatial index is a scaling
     follow-up, not a correctness gap, if a future corpus case is too slow.

``TRI-SHELL-PROVENANCE1`` adds the floating-point map ``P(p) = (prism id,
alpha, beta, normalized h)`` and its inverse on exactly that linear-shell MVP.
It is wired to ``operator_loop.py`` only when
``AUTO_TESSELL_TRI_SHELL_PROVENANCE1=1`` and then records a deterministic
face-centroid census without changing acceptance. Shared-prism, pinched,
unmapped, and non-finite queries remain unassigned. This is a payload-transfer
diagnostic, not a claim that the reduced shell satisfies Jiang's complete
bijection contract.

Attene-style indirect predicates remain off-limits (LGPL vendoring decision
still pending user approval); every check here uses only the already
vendored, ``-ffp-contract=off``-compiled Shewchuk ``orient3d``
(``core/utils/_shewchuk/``).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

import numpy as np

# Each physical tet in ``_prism_tets`` is paired with the corresponding tet
# in the canonical triangular prism.  Coordinates are ``(alpha, beta, h)``:
# ``(1-alpha-beta, alpha, beta)`` are barycentric weights on the ordered
# middle triangle and ``h`` is normalized to -1/0/+1 on bottom/middle/top.
_REFERENCE_PRISM_TETS = np.asarray(
    (
        ((0.0, 0.0, -1.0), (1.0, 0.0, -1.0), (0.0, 1.0, -1.0), (0.0, 1.0, 0.0)),
        ((1.0, 0.0, -1.0), (0.0, 0.0, -1.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
        ((0.0, 0.0, -1.0), (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
        ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 1.0, 1.0)),
        ((1.0, 0.0, 0.0), (0.0, 0.0, 0.0), (1.0, 0.0, 1.0), (0.0, 1.0, 1.0)),
        ((0.0, 0.0, 0.0), (0.0, 0.0, 1.0), (1.0, 0.0, 1.0), (0.0, 1.0, 1.0)),
    ),
    dtype=np.float64,
)

_PROJECTION_TOLERANCE = 1e-10


def _orient3d(a: np.ndarray, b: np.ndarray, c: np.ndarray, d: np.ndarray) -> int:
    """Call the bundled Shewchuk exact ``orient3d`` predicate.

    Imported lazily (matching ``operator_loop.py``'s ``_exact_orient3d``) so
    the current value of the module-level binding is always used.
    """
    from core.utils._shewchuk import orient3d

    if orient3d is None:
        raise RuntimeError("Shewchuk orient3d is unavailable")
    return int(orient3d(a, b, c, d))


@dataclass(frozen=True)
class RoundContainmentReport:
    """Result of checking one round's resulting surface against the shell."""

    accepted: bool
    reason: str
    failed_face_index: int | None = None


@dataclass(frozen=True)
class ShellCheckpointReport:
    """Per-round shell-checkpoint outcome recorded by ``run_rounds``."""

    accepted: bool
    round_index: int
    reason: str
    failed_face_index: int | None = None


@dataclass(frozen=True)
class ShellBuildResult:
    """Outcome of :func:`build_linear_bijective_shell`.

    ``success=False`` always carries a ``reason`` -- construction failure is
    reported explicitly, never silently degraded (ROADMAP "explicit
    rejection" hard gate; see Phase 3's decision tree in the integrated
    development plan: a construction failure degrades the *tier*, and that
    degradation itself must be reported by the caller).
    """

    shell: BijectiveShell | None
    success: bool
    reason: str
    failed_face_indices: tuple[int, ...] = ()


class ShellProjectionStatus(StrEnum):
    """Exhaustive report-only outcomes for one shell projection query."""

    MAPPED = "mapped"
    UNMAPPED = "unmapped"
    AMBIGUOUS = "ambiguous"
    PINCHED = "pinched"
    NON_FINITE = "non_finite"


@dataclass(frozen=True)
class ShellCoordinate:
    """Jiang-2020 linear-shell coordinate ``P(p) = (pid, alpha, beta, h)``.

    ``alpha`` and ``beta`` address vertices 1 and 2 of the prism face sorted
    by global vertex id; vertex 0 has weight ``1 - alpha - beta``. ``h`` is
    normalized to ``[-1, 1]`` with the middle surface at zero.
    """

    prism_index: int
    alpha: float
    beta: float
    h: float


@dataclass(frozen=True)
class SourceFacePayload:
    """Immutable source-face identity and discrete CFD patch payload."""

    source_face_index: int
    source_vertex_indices: tuple[int, int, int]
    patch_id: int | str | None = None


@dataclass(frozen=True)
class PointProvenance:
    """Immutable result of one FP projection and inverse round trip."""

    status: ShellProjectionStatus
    coordinate: ShellCoordinate | None
    source_payload: SourceFacePayload | None
    middle_point: tuple[float, float, float] | None
    reconstructed_point: tuple[float, float, float] | None
    round_trip_error: float | None
    candidate_prism_indices: tuple[int, ...]
    reason: str


@dataclass(frozen=True)
class ShellProvenanceReport:
    """Deterministic census over an ordered sequence of query points."""

    total: int
    mapped: int
    unmapped: int
    ambiguous: int
    pinched: int
    non_finite: int
    max_round_trip_error: float | None
    p95_round_trip_error: float | None
    projections: tuple[PointProvenance, ...]

    @property
    def coverage(self) -> float:
        """Mapped fraction; zero for an empty census."""
        return 0.0 if self.total == 0 else self.mapped / self.total


@dataclass(frozen=True)
class BijectiveShell:
    """The static, once-built linear bijective shell.

    ``mid_vertices``/``faces`` are a frozen copy of the ORIGINAL input
    surface at construction time -- this is the provenance domain and must
    never be rebuilt from a moving mesh during remeshing.
    """

    mid_vertices: np.ndarray
    faces: np.ndarray
    top_vertices: np.ndarray
    bottom_vertices: np.ndarray
    thickness: np.ndarray
    normals: np.ndarray
    prism_tets: tuple[np.ndarray, ...]
    prism_aabb_min: np.ndarray
    prism_aabb_max: np.ndarray
    source_face_payloads: tuple[SourceFacePayload, ...] = ()

    def contains_point(self, point: np.ndarray, *, aabb_tolerance: float = 1e-9) -> bool:
        """Return whether ``point`` lies inside any prism of the shell."""
        p = np.asarray(point, dtype=np.float64)
        if not np.isfinite(p).all():
            return False
        candidate_mask = np.all(
            (p >= self.prism_aabb_min - aabb_tolerance)
            & (p <= self.prism_aabb_max + aabb_tolerance),
            axis=1,
        )
        for prism_index in np.nonzero(candidate_mask)[0]:
            tets = self.prism_tets[int(prism_index)]
            for tet in tets:
                if _point_in_tet(p, tet):
                    return True
        return False

    def contains_triangle(
        self,
        vertices: np.ndarray,
        face: np.ndarray,
    ) -> tuple[bool, np.ndarray | None]:
        """Return whether every sampled point of ``face`` is shell-contained."""
        tri = np.asarray(vertices, dtype=np.float64)[np.asarray(face, dtype=np.int64)]
        for sample in _triangle_samples(tri):
            if not self.contains_point(sample):
                return False, sample
        return True, None

    def check_round_containment(
        self,
        vertices: np.ndarray,
        faces: np.ndarray,
    ) -> RoundContainmentReport:
        """Per-round checkpoint: every current-surface triangle must stay
        inside the static shell built from the original surface."""
        verts = np.asarray(vertices, dtype=np.float64)
        tris = np.asarray(faces, dtype=np.int64)
        if verts.ndim != 2 or verts.shape[1] != 3 or not np.isfinite(verts).all():
            return RoundContainmentReport(False, "invalid_vertices")
        if tris.ndim != 2 or tris.shape[1] != 3:
            return RoundContainmentReport(False, "invalid_faces")
        for face_index, face in enumerate(tris.tolist()):
            contained, _ = self.contains_triangle(verts, face)
            if not contained:
                return RoundContainmentReport(
                    False,
                    "shell_containment_failed",
                    face_index,
                )
        return RoundContainmentReport(True, "shell_containment_ok", None)

    def project_point(
        self,
        point: np.ndarray,
        *,
        aabb_tolerance: float = 1e-9,
    ) -> PointProvenance:
        """Evaluate Jiang's linear-shell ``P`` in floating point.

        Candidate prisms are traversed in ascending source-face order.  A
        point lying in more than one prism is reported as ambiguous instead
        of selecting a payload by traversal order.  This MVP evaluates the
        existing canonical 6-tet decomposition only; it does not add the
        paper's 24-tet/I2/bevel/pinch certificate and therefore makes no
        complete-bijection claim.
        """
        p = np.asarray(point, dtype=np.float64).reshape(-1)
        if p.shape != (3,) or not np.isfinite(p).all():
            return _unmapped_projection(ShellProjectionStatus.NON_FINITE, "non_finite_point")

        candidate_mask = np.all(
            (p >= self.prism_aabb_min - aabb_tolerance)
            & (p <= self.prism_aabb_max + aabb_tolerance),
            axis=1,
        )
        candidate_indices = tuple(int(index) for index in np.nonzero(candidate_mask)[0])
        pinched = tuple(
            prism_index
            for prism_index in candidate_indices
            if self._point_is_at_pinched_pillar(p, prism_index, aabb_tolerance)
        )
        if pinched:
            return _unmapped_projection(
                ShellProjectionStatus.PINCHED,
                "pinched_pillar_excluded",
                pinched,
            )

        mapped: list[ShellCoordinate] = []
        inconsistent_prisms: list[int] = []
        for prism_index in candidate_indices:
            local_coordinates: list[np.ndarray] = []
            for tet_index, tet in enumerate(self.prism_tets[prism_index]):
                if not _point_in_tet(p, tet):
                    continue
                weights = _tet_barycentric_weights(p, tet)
                if weights is None:
                    continue
                reference = weights @ _REFERENCE_PRISM_TETS[tet_index]
                if np.isfinite(reference).all():
                    local_coordinates.append(_snap_reference_coordinate(reference))
            if not local_coordinates:
                continue
            first = local_coordinates[0]
            if any(
                not np.allclose(first, other, rtol=0.0, atol=_PROJECTION_TOLERANCE)
                for other in local_coordinates[1:]
            ):
                inconsistent_prisms.append(prism_index)
                continue
            mapped.append(
                ShellCoordinate(
                    prism_index,
                    float(first[0]),
                    float(first[1]),
                    float(first[2]),
                ),
            )

        mapped_prisms = tuple(coordinate.prism_index for coordinate in mapped)
        ambiguous_prisms = tuple(sorted((*mapped_prisms, *inconsistent_prisms)))
        if inconsistent_prisms or len(mapped) > 1:
            return _unmapped_projection(
                ShellProjectionStatus.AMBIGUOUS,
                "multiple_or_inconsistent_prism_coordinates",
                ambiguous_prisms,
            )
        if not mapped:
            return _unmapped_projection(
                ShellProjectionStatus.UNMAPPED,
                "point_outside_linear_shell",
                candidate_indices,
            )

        coordinate = mapped[0]
        reconstructed = self.inverse_project(coordinate)
        middle = self.inverse_project(
            ShellCoordinate(
                coordinate.prism_index,
                coordinate.alpha,
                coordinate.beta,
                0.0,
            ),
        )
        if reconstructed is None or middle is None:
            return _unmapped_projection(
                ShellProjectionStatus.AMBIGUOUS,
                "inverse_projection_ambiguous",
                (coordinate.prism_index,),
            )
        reconstructed_array = np.asarray(reconstructed, dtype=np.float64)
        error = float(np.linalg.norm(reconstructed_array - p))
        payload = self._payload_for_prism(coordinate.prism_index)
        return PointProvenance(
            ShellProjectionStatus.MAPPED,
            coordinate,
            payload,
            middle,
            reconstructed,
            error,
            (coordinate.prism_index,),
            "mapped",
        )

    def inverse_project(
        self,
        coordinate: ShellCoordinate,
    ) -> tuple[float, float, float] | None:
        """Evaluate ``P^-1`` in the same canonical 6-tet linear shell.

        ``None`` is returned for an invalid, pinched, unmapped, or ambiguous
        reference coordinate.  No tet or prism is selected by a tie-break.
        """
        prism_index = int(coordinate.prism_index)
        reference = np.asarray(
            (coordinate.alpha, coordinate.beta, coordinate.h),
            dtype=np.float64,
        )
        if (
            prism_index < 0
            or prism_index >= len(self.prism_tets)
            or not np.isfinite(reference).all()
            or reference[0] < -_PROJECTION_TOLERANCE
            or reference[1] < -_PROJECTION_TOLERANCE
            or reference[0] + reference[1] > 1.0 + _PROJECTION_TOLERANCE
            or abs(reference[2]) > 1.0 + _PROJECTION_TOLERANCE
        ):
            return None

        physical_points: list[np.ndarray] = []
        for tet_index, reference_tet in enumerate(_REFERENCE_PRISM_TETS):
            weights = _tet_barycentric_weights(reference, reference_tet)
            if weights is None or np.any(weights < -_PROJECTION_TOLERANCE):
                continue
            if np.any(weights > 1.0 + _PROJECTION_TOLERANCE):
                continue
            physical = weights @ self.prism_tets[prism_index][tet_index]
            if np.isfinite(physical).all():
                physical_points.append(physical)
        if not physical_points:
            return None
        first = physical_points[0]
        if any(
            not np.allclose(first, other, rtol=0.0, atol=_PROJECTION_TOLERANCE)
            for other in physical_points[1:]
        ):
            return None
        return float(first[0]), float(first[1]), float(first[2])

    def census_points(self, points: np.ndarray) -> ShellProvenanceReport:
        """Project ordered points and return an immutable deterministic census."""
        values = np.asarray(points, dtype=np.float64)
        if values.ndim != 2 or values.shape[1] != 3:
            raise ValueError("points must have shape (n, 3)")
        projections = tuple(self.project_point(point) for point in values)
        counts = {
            status: sum(projection.status is status for projection in projections)
            for status in ShellProjectionStatus
        }
        errors = np.asarray(
            [
                projection.round_trip_error
                for projection in projections
                if projection.round_trip_error is not None
            ],
            dtype=np.float64,
        )
        maximum = None if errors.size == 0 else float(errors.max())
        p95 = None if errors.size == 0 else float(np.percentile(errors, 95.0))
        return ShellProvenanceReport(
            len(projections),
            counts[ShellProjectionStatus.MAPPED],
            counts[ShellProjectionStatus.UNMAPPED],
            counts[ShellProjectionStatus.AMBIGUOUS],
            counts[ShellProjectionStatus.PINCHED],
            counts[ShellProjectionStatus.NON_FINITE],
            maximum,
            p95,
            projections,
        )

    def census_face_centroids(
        self,
        vertices: np.ndarray,
        faces: np.ndarray,
    ) -> ShellProvenanceReport:
        """Pull source-face/patch payloads back to target-face centroids."""
        verts = np.asarray(vertices, dtype=np.float64)
        tris = np.asarray(faces, dtype=np.int64)
        if verts.ndim != 2 or verts.shape[1] != 3:
            raise ValueError("vertices must have shape (n, 3)")
        if tris.ndim != 2 or tris.shape[1] != 3:
            raise ValueError("faces must have shape (m, 3)")
        if tris.size and (tris.min() < 0 or tris.max() >= len(verts)):
            raise ValueError("faces contain an invalid vertex index")
        return self.census_points(verts[tris].mean(axis=1))

    def _payload_for_prism(self, prism_index: int) -> SourceFacePayload:
        if self.source_face_payloads:
            return self.source_face_payloads[prism_index]
        face = self.faces[prism_index]
        return SourceFacePayload(
            prism_index,
            (int(face[0]), int(face[1]), int(face[2])),
            None,
        )

    def _point_is_at_pinched_pillar(
        self,
        point: np.ndarray,
        prism_index: int,
        tolerance: float,
    ) -> bool:
        face = self.faces[prism_index]
        for vertex in face.tolist():
            index = int(vertex)
            if self.thickness[index] > np.finfo(float).tiny:
                continue
            if float(np.linalg.norm(point - self.mid_vertices[index])) <= tolerance:
                return True
        return False


def build_linear_bijective_shell(
    vertices: np.ndarray,
    faces: np.ndarray,
    *,
    thickness_fraction: float = 0.1,
    local_scale_fraction: float = 0.5,
    max_shrink_iterations: int = 6,
    shrink_factor: float = 0.8,
    source_patch_ids: Sequence[int | str | None] | None = None,
) -> ShellBuildResult:
    """Build the static linear bijective shell once, from the original surface.

    ``thickness_fraction`` is the per-vertex symmetric offset as a fraction
    of the bounding-box diagonal (Jiang 2020's default: 10% of the bbox
    longest edge, generic-use setting; their tighter 2% setting is for
    bounding volumetric-PDE geometric error -- not needed here). It is then
    capped per vertex at ``local_scale_fraction`` times that vertex's
    shortest incident edge, so a highly refined mesh with a large bbox does
    not get a shell far thicker than its own local triangle size: Jiang 2020
    ran a full AABB tree for containment queries, this implementation does
    not (documented scope reduction above), so an oversized global thickness
    would make every ``contains_point`` query scan a large, mostly-irrelevant
    candidate-prism set. Capping to local scale keeps prisms geometrically
    tight to the surface (the paper's own "thinner = tighter fidelity bound"
    framing) and keeps containment queries local. Offending vertices are
    then iteratively shrunk (Jiang 2020's own "20% per offending triangle"
    rule) toward a self-intersection-free prism layer before I1/I2 are
    checked.
    """
    verts = np.asarray(vertices, dtype=np.float64)
    tris = np.asarray(faces, dtype=np.int64)

    if verts.ndim != 2 or verts.shape[1] != 3 or not np.isfinite(verts).all():
        return ShellBuildResult(None, False, "invalid_vertices")
    if tris.ndim != 2 or tris.shape[1] != 3 or tris.size == 0:
        return ShellBuildResult(None, False, "invalid_faces")
    if tris.min() < 0 or tris.max() >= len(verts):
        return ShellBuildResult(None, False, "face_index_out_of_range")
    try:
        payloads = _source_face_payloads(tris, source_patch_ids)
    except (TypeError, ValueError):
        return ShellBuildResult(None, False, "invalid_source_patch_payload")

    normals = _area_weighted_vertex_normals(verts, tris)
    norms = np.linalg.norm(normals, axis=1)
    if not np.isfinite(norms).all() or np.any(norms <= np.finfo(float).tiny):
        return ShellBuildResult(None, False, "degenerate_vertex_normal")
    unit_normals = normals / norms[:, None]

    bbox_diag = float(np.linalg.norm(verts.max(axis=0) - verts.min(axis=0)))
    if not np.isfinite(bbox_diag) or bbox_diag <= 0.0:
        return ShellBuildResult(None, False, "degenerate_bounding_box")

    local_scale = _local_edge_scale(verts, tris)
    if not np.isfinite(local_scale).all() or np.any(local_scale <= 0.0):
        return ShellBuildResult(None, False, "degenerate_incident_edge")

    thickness = np.minimum(
        thickness_fraction * bbox_diag,
        local_scale_fraction * local_scale,
    )
    vertex_faces = _vertex_face_incidence(tris, len(verts))

    top = bottom = None
    for _ in range(max_shrink_iterations):
        top = verts + thickness[:, None] * unit_normals
        bottom = verts - thickness[:, None] * unit_normals
        offending = _find_self_intersecting_faces(verts, tris, top, bottom, vertex_faces)
        if not offending:
            break
        for face_index in offending:
            for vertex in tris[face_index]:
                thickness[int(vertex)] *= shrink_factor

    top = verts + thickness[:, None] * unit_normals
    bottom = verts - thickness[:, None] * unit_normals
    offending = _find_self_intersecting_faces(verts, tris, top, bottom, vertex_faces)
    if offending:
        return ShellBuildResult(
            None,
            False,
            "self_intersection_unresolved",
            tuple(sorted(offending)),
        )
    if not np.isfinite(thickness).all() or np.any(thickness <= 0.0):
        return ShellBuildResult(None, False, "non_positive_thickness")

    prism_tets: list[np.ndarray] = []
    aabb_min = np.zeros((len(tris), 3), dtype=np.float64)
    aabb_max = np.zeros((len(tris), 3), dtype=np.float64)
    failed_faces: set[int] = set()

    for face_index, face in enumerate(tris.tolist()):
        ordered = _sort_by_global_id(face)
        tets = _prism_tets(ordered, bottom, verts, top)

        signs = [_orient3d(tet[0], tet[1], tet[2], tet[3]) for tet in tets]
        if 0 in signs or len(set(signs)) != 1:
            failed_faces.add(face_index)
        if not _normal_condition_ok(verts, tris, face_index, top, bottom):
            failed_faces.add(face_index)

        stacked = np.asarray(tets, dtype=np.float64)
        prism_tets.append(stacked)
        flat = stacked.reshape(-1, 3)
        aabb_min[face_index] = flat.min(axis=0)
        aabb_max[face_index] = flat.max(axis=0)

    if failed_faces:
        return ShellBuildResult(None, False, "I1_or_I2_failed", tuple(sorted(failed_faces)))

    shell = BijectiveShell(
        mid_vertices=verts.copy(),
        faces=tris.copy(),
        top_vertices=top,
        bottom_vertices=bottom,
        thickness=thickness,
        normals=unit_normals,
        prism_tets=tuple(prism_tets),
        prism_aabb_min=aabb_min,
        prism_aabb_max=aabb_max,
        source_face_payloads=payloads,
    )
    return ShellBuildResult(shell, True, "constructed")


def _source_face_payloads(
    faces: np.ndarray,
    patch_ids: Sequence[int | str | None] | None,
) -> tuple[SourceFacePayload, ...]:
    if patch_ids is None:
        values: tuple[int | str | None, ...] = (None,) * len(faces)
    else:
        if len(patch_ids) != len(faces):
            raise ValueError("source_patch_ids must match the source face count")
        normalized: list[int | str | None] = []
        for value in patch_ids:
            scalar = value.item() if isinstance(value, np.generic) else value
            if scalar is not None and not isinstance(scalar, (int, str)):
                raise TypeError("patch ids must be immutable int/str scalars")
            normalized.append(scalar)
        values = tuple(normalized)
    return tuple(
        SourceFacePayload(
            face_index,
            (int(face[0]), int(face[1]), int(face[2])),
            values[face_index],
        )
        for face_index, face in enumerate(faces.tolist())
    )


def _unmapped_projection(
    status: ShellProjectionStatus,
    reason: str,
    candidate_prism_indices: tuple[int, ...] = (),
) -> PointProvenance:
    return PointProvenance(
        status,
        None,
        None,
        None,
        None,
        None,
        candidate_prism_indices,
        reason,
    )


def _tet_barycentric_weights(point: np.ndarray, tet: np.ndarray) -> np.ndarray | None:
    matrix = np.column_stack((tet[1] - tet[0], tet[2] - tet[0], tet[3] - tet[0]))
    try:
        tail = np.linalg.solve(matrix, point - tet[0])
    except np.linalg.LinAlgError:
        return None
    weights = np.asarray((1.0 - float(tail.sum()), *tail.tolist()), dtype=np.float64)
    return weights if np.isfinite(weights).all() else None


def _snap_reference_coordinate(reference: np.ndarray) -> np.ndarray:
    result = np.asarray(reference, dtype=np.float64).copy()
    for index in range(3):
        for boundary in (-1.0, 0.0, 1.0):
            if abs(float(result[index] - boundary)) <= _PROJECTION_TOLERANCE:
                result[index] = boundary
    return result


def _point_in_tet(point: np.ndarray, tet: np.ndarray) -> bool:
    """Robust exact point-in-tetrahedron test using only ``orient3d``.

    For each of the 4 faces of the tet, ``point`` must lie on the same side
    as the tet's own opposite vertex (self-referential -- no canonical
    "positive volume" convention is required).
    """
    v0, v1, v2, v3 = tet
    faces = (
        (v1, v2, v3, v0),
        (v0, v2, v3, v1),
        (v0, v1, v3, v2),
        (v0, v1, v2, v3),
    )
    for a, b, c, opposite in faces:
        reference = _orient3d(a, b, c, opposite)
        if reference == 0:
            return False
        sign = _orient3d(a, b, c, point)
        if sign != 0 and sign != reference:
            return False
    return True


def _triangle_samples(tri: np.ndarray) -> np.ndarray:
    """Sample 3 corners + centroid + 3 edge midpoints of ``tri`` (7 points)."""
    v0, v1, v2 = tri
    centroid = (v0 + v1 + v2) / 3.0
    m01 = (v0 + v1) * 0.5
    m12 = (v1 + v2) * 0.5
    m20 = (v2 + v0) * 0.5
    return np.vstack([v0, v1, v2, centroid, m01, m12, m20])


def _sort_by_global_id(face: list[int]) -> tuple[int, int, int]:
    """Order ``face`` by ascending global vertex id (the Garimella-Shephard
    "total vertex order" trick Jiang 2020 cites).

    This must be a *true* sort, not a winding-preserving cyclic rotation: two
    prisms sharing a side quad (a surface edge) need to pick the identical
    diagonal for it regardless of which of the two faces they were built
    from, and each face's own winding direction along that shared edge is
    opposite between the two incident triangles (standard consistent-
    orientation convention). A cyclic rotation preserves winding and so
    disagrees between the two faces on that edge's relative order roughly
    half the time -- verified to actually produce a gap (a point exactly on
    a shared prism wall, e.g. an original triangle's own edge midpoint,
    landing in neither triangle's tet decomposition) on
    ``tests/benchmarks/sphere.stl``-like meshes during verification. A pure
    ascending-id sort has no such face-relative freedom: it depends only on
    the two shared vertices' ids, so both incident faces agree.

    Sorting instead of rotating can reverse the triangle's handedness (an
    odd permutation of the original winding) for roughly half of all faces.
    ``_prism_tets``'s pattern stays self-consistent regardless (see the
    numerical check in the development log): all 6 tets of a permuted
    prism still share one sign, just not necessarily the same sign as an
    even-permutation neighbor -- irrelevant here since I1 only requires
    self-consistency *within* one prism, never a uniform sign across faces.
    """
    ints = sorted(int(v) for v in face)
    return ints[0], ints[1], ints[2]


def _prism_tets(
    ordered_face: tuple[int, int, int],
    bottom: np.ndarray,
    mid: np.ndarray,
    top: np.ndarray,
) -> tuple[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray], ...]:
    """Return the 6-tet double-slab decomposition (Dompierre et al. 1999
    pattern) of the prism over one face, keyed by ``ordered_face``."""
    p0, p1, p2 = ordered_face
    b0, b1, b2 = bottom[p0], bottom[p1], bottom[p2]
    m0, m1, m2 = mid[p0], mid[p1], mid[p2]
    t0, t1, t2 = top[p0], top[p1], top[p2]
    # Middle tet of each slab has its first two corners swapped relative to
    # the naive (p0, p1, ...) pattern -- verified numerically against a
    # reference axis-aligned prism to give all 3 slab tets one consistent
    # orient3d sign (the naive un-swapped pattern alternates sign on the
    # middle tet, which would make I1's "6 tets share one sign" check
    # spuriously fail on every prism).
    return (
        (b0, b1, b2, m2),
        (b1, b0, m1, m2),
        (b0, m0, m1, m2),
        (m0, m1, m2, t2),
        (m1, m0, t1, t2),
        (m0, t0, t1, t2),
    )


def _normal_condition_ok(
    verts: np.ndarray,
    tris: np.ndarray,
    face_index: int,
    top: np.ndarray,
    bottom: np.ndarray,
) -> bool:
    """I2 proxy: the face normal must point into the positive half of every
    one of its 3 vertex pillars (``top_i - bottom_i``) -- Jiang 2020's
    per-operation "normal condition" (checklist item 4), applied here to
    the static input surface at construction time."""
    face = tris[face_index]
    tri = verts[face]
    normal = np.cross(tri[1] - tri[0], tri[2] - tri[0])
    normal_length = float(np.linalg.norm(normal))
    if not np.isfinite(normal_length) or normal_length <= np.finfo(float).tiny:
        return False
    normal_unit = normal / normal_length
    for vertex in face.tolist():
        pillar = top[int(vertex)] - bottom[int(vertex)]
        if float(np.dot(normal_unit, pillar)) <= 0.0:
            return False
    return True


def _area_weighted_vertex_normals(verts: np.ndarray, tris: np.ndarray) -> np.ndarray:
    """Area-weighted vertex normal sum (unnormalized).

    Summing the raw ``cross`` vector (magnitude = 2*triangle area) over
    incident faces is exactly the area-weighted normal sum up to a factor
    of 2, which is irrelevant once the caller normalizes.
    """
    normals = np.zeros_like(verts)
    for face in tris.tolist():
        tri = verts[np.asarray(face, dtype=np.int64)]
        cross = np.cross(tri[1] - tri[0], tri[2] - tri[0])
        for vertex in face:
            normals[int(vertex)] += cross
    return normals


def _local_edge_scale(verts: np.ndarray, tris: np.ndarray) -> np.ndarray:
    """Return each vertex's shortest incident-edge length."""
    scale = np.full(len(verts), np.inf, dtype=np.float64)
    for face in tris.tolist():
        for u, v in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])):
            length = float(np.linalg.norm(verts[int(u)] - verts[int(v)]))
            if length < scale[int(u)]:
                scale[int(u)] = length
            if length < scale[int(v)]:
                scale[int(v)] = length
    return scale


def _vertex_face_incidence(tris: np.ndarray, vertex_count: int) -> list[set[int]]:
    incidence: list[set[int]] = [set() for _ in range(vertex_count)]
    for face_index, face in enumerate(tris.tolist()):
        for vertex in face:
            incidence[int(vertex)].add(face_index)
    return incidence


def _find_self_intersecting_faces(
    verts: np.ndarray,
    tris: np.ndarray,
    top: np.ndarray,
    bottom: np.ndarray,
    vertex_faces: list[set[int]],
) -> set[int]:
    """Return indices of faces whose top or bottom cap intersects some
    non-adjacent original-surface triangle (Jiang 2020's initial-thickness
    self-collision screen, brute-force + AABB prefilter instead of the
    paper's static AABB tree over ``T``)."""
    original_tris = verts[tris]
    original_min = original_tris.min(axis=1)
    original_max = original_tris.max(axis=1)

    offending: set[int] = set()
    for face_index, face in enumerate(tris.tolist()):
        neighbours: set[int] = set()
        for vertex in face:
            neighbours |= vertex_faces[int(vertex)]

        face_idx = np.asarray(face, dtype=np.int64)
        for cap_tri in (top[face_idx], bottom[face_idx]):
            cap_min = cap_tri.min(axis=0)
            cap_max = cap_tri.max(axis=0)
            candidate_mask = np.all(
                (original_min <= cap_max) & (original_max >= cap_min),
                axis=1,
            )
            hit = False
            for other_index in np.nonzero(candidate_mask)[0]:
                other_index = int(other_index)
                if other_index in neighbours:
                    continue
                if _triangles_intersect(cap_tri, original_tris[other_index]):
                    hit = True
                    break
            if hit:
                offending.add(face_index)
                break
    return offending


def _triangles_intersect(tri_a: np.ndarray, tri_b: np.ndarray) -> bool:
    """Exact (orientation-predicate) triangle-triangle overlap test.

    Checks whether any edge of one triangle crosses the interior of the
    other (Guigue-Devillers-family approach: orientation predicates only).
    Exactly coplanar overlapping triangles are not detected -- a documented
    limitation, acceptable for a self-collision *screen* that only needs to
    trigger a conservative thickness shrink, not certify full CSG.
    """
    a0, a1, a2 = tri_a
    b0, b1, b2 = tri_b
    for p, q in ((a0, a1), (a1, a2), (a2, a0)):
        if _segment_crosses_triangle(p, q, tri_b):
            return True
    for p, q in ((b0, b1), (b1, b2), (b2, b0)):
        if _segment_crosses_triangle(p, q, tri_a):
            return True
    return False


def _segment_crosses_triangle(p: np.ndarray, q: np.ndarray, tri: np.ndarray) -> bool:
    """Exact segment-vs-triangle-interior crossing test (Ericson-style
    signed-volume construction; predicate-exact via ``orient3d``)."""
    a, b, c = tri
    side_p = _orient3d(a, b, c, p)
    side_q = _orient3d(a, b, c, q)
    if side_p == 0 and side_q == 0:
        return False
    if side_p != 0 and side_q != 0 and side_p == side_q:
        return False
    s1 = _orient3d(p, q, a, b)
    s2 = _orient3d(p, q, b, c)
    s3 = _orient3d(p, q, c, a)
    return (s1 > 0 and s2 > 0 and s3 > 0) or (s1 < 0 and s2 < 0 and s3 < 0)
