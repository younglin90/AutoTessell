"""POLY-AGGLOM-FACEGEOM1 -- merged-interface face-geometry diagnostic.

Report-only, standalone module.  NOT imported by ``tier_native_poly.py``, the
CLI, ``dual.py``, or any production path.

Why this card exists
--------------------
``agglomeration_experiment.py`` (``POLY-AGGLOM-CFD1``) measured Pan & Persson
vertex-star agglomeration against ``polydual`` on an identical tet primal and
returned a KILL verdict: ~71% fewer cells, but max non-orthogonality 86-89 deg
(vs 50-55 deg for polydual) and mean Juretic ``psi`` ~4x higher.

That experiment deliberately exported every block-block interface as the
*raw, unmerged* set of tet triangles (its own docstring, "Face geometry
policy": "This module intentionally does *not* attempt to merge coplanar
facets into a single polygon per interface").  The measured consequence is
visible in its own output: the agglomerated mesh scores a near-perfect
``max_face_planar_deviation`` of 0.013 and ``max_face_normal_spread_deg`` of
1.4 -- not because its cells are well shaped, but because *every face is a
triangle*, and a triangle is planar by construction.

That makes the CFD1 comparison confounded on exactly the axis it decided:

* ``polydual`` emits ONE polygon per owner-neighbour pair, so its face normal
  is the area-weighted mean over the whole interface.
* the agglomerate emitted N separate triangles per owner-neighbour pair, so
  non-orthogonality was evaluated per tiny facet, each with its own scattered
  normal, against the same owner-neighbour centre line.

Non-orthogonality is an internal-face-only metric (``native_checker.py``,
"4. Non-orthogonality (internal faces only)").  A jagged tet-tet interface
therefore reports the worst facet in the patch rather than the flux-carrying
mean normal of the interface -- which is the quantity finite volume actually
discretises.

This module implements what the development plan's Phase 3 lists FIRST and
what CFD1 skipped (plan section 3, Phase 3): "every merged interface collapsed
to explicit polygonal faces and measured (facet-normal deviation, planarity,
non-ortho/skew); 'union of facets' geometry above threshold is rejected or
split, never exported".  Plan section 6: "Phase 3 opens with
``POLY-AGGLOM-FACEGEOM1`` in diagnostic mode: measure FV metrics on merged
interfaces before any generator competes."

Construction
------------
For each unordered block pair ``(lo, hi)`` the interface facets are split into
face-adjacency connected components (a block pair may touch in more than one
place).  Each component is merged *independently and transactionally*: its
boundary loop is extracted from the directed-edge residual of the
consistently-oriented triangle patch, and the whole component is either
replaced by that single polygon or left entirely as raw facets.  There is no
partial merge of a component.

What merging does and does not preserve
---------------------------------------
The vector area of a closed loop equals the sum of the vector areas of any
triangulation spanning it (interior edges telescope).  Merging a facet patch
into its boundary polygon therefore preserves that interface's ``sum(S_i n_i)``
*exactly*.  Two consequences:

* each cell still satisfies ``sum_f S_f = 0`` (it stays a closed polyhedron),
  and the discrete flux normal of the interface is exact rather than sampled;
* the scalar area shrinks -- ``|sum S_i n_i| <= sum S_i``, equality only for a
  planar patch -- which is the jaggedness the ``area_ratio`` diagnostic reports.

Merging does NOT preserve individual cell volumes.  The shared surface between
two blocks physically moves from the jagged patch to the spanning polygon, so
one block gains exactly the signed volume the other loses.  *Total* domain
volume is preserved exactly, because every moved surface is interior and shared
by exactly two cells with opposite orientation, while boundary faces are never
merged.  Per-cell volume can in principle be driven negative by a deep bulge,
so cell-volume positivity is enforced by reverting merges (see the revert
loop), never by dropping a cell.

The vector-area identity itself is verified numerically per component
(``_VECTOR_AREA_REL_TOL``) rather than assumed; a mismatch means the loop walk
and the patch disagree and the component is rejected.

Boundary faces (block vs domain exterior) are NEVER merged.  Merging them
would move flux through the surface off the true geometry and violate the
project's surface-preservation invariant; keeping them raw also makes
``surface_area_dev_pct`` a control that must stay bit-identical between the
facet-union and merged variants.
"""

from __future__ import annotations

import shutil
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

import numpy as np

from core.generator.native_poly.agglomeration_experiment import (
    AgglomerationResult,
    EngineMeasurement,
    _measure_case,
    _triangle_area_sum,
    vertex_star_agglomerate,
)
from core.generator.polymesh_writer import _TET_FACES, write_generic_polymesh
from core.utils.logging import get_logger

log = get_logger(__name__)

# A merged polygon's vector area must reproduce the summed facet vector area
# to this relative tolerance, else the component is rejected outright (it
# means the loop walk and the patch disagree -- an orientation or topology
# bug, never something to export).
_VECTOR_AREA_REL_TOL = 1.0e-9

# A closed polyhedron needs at least 4 faces; write_generic_polymesh drops
# cells below that.  Merging can only reduce a block's face count, so this is
# enforced by reverting merges rather than by dropping cells.
_MIN_FACES_PER_CELL = 4


# ---------------------------------------------------------------------------
# Tet facet topology (key -> the (tet, local face) slots that carry it)
# ---------------------------------------------------------------------------


def _tet_facet_slots(
    T: np.ndarray,
) -> tuple[dict[tuple[int, int, int], list[tuple[int, int]]], np.ndarray]:
    """Return (facet key -> [(tet, local face)], per-tet outward facet vertices)."""
    T = np.asarray(T, dtype=np.int64)
    n_tets = int(T.shape[0])
    tf = np.array(_TET_FACES, dtype=np.int64)
    face_verts = T[:, tf]  # (n_tets, 4, 3) outward from the owning tet
    keys = np.sort(face_verts, axis=2)

    slots: dict[tuple[int, int, int], list[tuple[int, int]]] = defaultdict(list)
    for ti in range(n_tets):
        for fi in range(4):
            key = (int(keys[ti, fi, 0]), int(keys[ti, fi, 1]), int(keys[ti, fi, 2]))
            slots[key].append((ti, fi))
    return slots, face_verts


# ---------------------------------------------------------------------------
# Facet patch -> single polygon
# ---------------------------------------------------------------------------


def _facet_components(tris: Sequence[tuple[int, int, int]]) -> list[list[int]]:
    """Split a facet patch into face-adjacency connected components.

    Two triangles are adjacent when they share an undirected edge.  Touching
    at a single vertex is NOT adjacency -- such a patch is two components and
    is merged into two separate polygons, which is the plan's "rejected or
    split" behaviour rather than fabricating one pinched face.
    """
    n = len(tris)
    edge_map: dict[tuple[int, int], list[int]] = defaultdict(list)
    for i, (a, b, c) in enumerate(tris):
        for u, v in ((a, b), (b, c), (c, a)):
            edge_map[(u, v) if u < v else (v, u)].append(i)

    adj: list[set[int]] = [set() for _ in range(n)]
    for members in edge_map.values():
        for i in members:
            for j in members:
                if i != j:
                    adj[i].add(j)

    seen = [False] * n
    components: list[list[int]] = []
    for start in range(n):
        if seen[start]:
            continue
        seen[start] = True
        stack = [start]
        comp = [start]
        while stack:
            cur = stack.pop()
            for nb in sorted(adj[cur]):
                if not seen[nb]:
                    seen[nb] = True
                    comp.append(nb)
                    stack.append(nb)
        components.append(sorted(comp))
    return components


def _patch_boundary_loop(
    tris: Sequence[tuple[int, int, int]],
) -> tuple[list[int] | None, str]:
    """Extract the single boundary loop of a consistently oriented triangle patch.

    Returns ``(loop, "ok")`` or ``(None, reason)``.  The loop is ordered so
    that its polygon vector area matches the patch's (the induced-boundary
    right-hand rule), which the caller verifies numerically.

    Rejection reasons are all structural: a repeated directed edge means the
    patch is non-manifold or has a duplicated triangle; a pinch vertex means
    the boundary visits one vertex twice; multiple loops mean the patch has a
    hole.  None of these can be expressed as one simple polygon, so the whole
    component is rejected rather than approximated.
    """
    directed: dict[tuple[int, int], int] = defaultdict(int)
    for a, b, c in tris:
        directed[(a, b)] += 1
        directed[(b, c)] += 1
        directed[(c, a)] += 1

    for count in directed.values():
        if count > 1:
            return None, "repeated_directed_edge"

    out_edge: dict[int, int] = {}
    in_degree: dict[int, int] = defaultdict(int)
    n_boundary = 0
    for (a, b) in directed:
        if directed.get((b, a), 0):
            continue  # interior edge of the patch
        if a in out_edge:
            return None, "pinch_vertex"
        out_edge[a] = b
        in_degree[b] += 1
        n_boundary += 1

    if n_boundary < 3:
        return None, "degenerate_boundary"
    if any(deg > 1 for deg in in_degree.values()):
        return None, "pinch_vertex"

    start = min(out_edge)
    loop = [start]
    cur = out_edge[start]
    while cur != start:
        if cur not in out_edge:
            return None, "open_boundary"
        if len(loop) >= n_boundary:
            return None, "walk_overrun"
        loop.append(cur)
        cur = out_edge[cur]

    if len(loop) != n_boundary:
        return None, "multiple_loops"
    if len(set(loop)) != len(loop):
        return None, "repeated_vertex"
    return loop, "ok"


def _closed_cell_volume(points: np.ndarray, faces: Sequence[Sequence[int]]) -> float:
    """Signed volume of a closed polyhedron whose faces are outward-oriented loops.

    Each face is decomposed into a cone from its own vertex-average centre,
    matching ``native_checker._compute_face_centres``.  That choice is not
    cosmetic: a *non-planar* polygon has no single surface, and a fan from
    ``face[0]`` describes a different surface than a fan from the reversed
    loop's ``face[0]``.  Owner and neighbour share one merged interface but
    store it in opposite order, so a vertex-0 fan makes the two cells disagree
    about where their common surface lies and total volume stops being
    conserved (measured at 1.0% on the cube primal before this was fixed).
    The centroid cone is invariant under loop reversal, so the two cells see
    the same surface and interior contributions cancel exactly.

    Used to guard merge acceptance: a merged interface moves the surface
    between two blocks, so a block's volume can in principle be driven
    non-positive even though the interface's vector area is exact.
    """
    total = 0.0
    for face in faces:
        k = len(face)
        if k < 3:
            continue
        p = points[np.asarray(face, dtype=np.int64)]
        c = p.mean(axis=0)
        for i in range(k):
            a = p[i]
            b = p[(i + 1) % k]
            total += float(np.dot(c, np.cross(a, b)))
    return total / 6.0


def _polygon_vector_area(points: np.ndarray, loop: Sequence[int]) -> np.ndarray:
    p = points[np.asarray(loop, dtype=np.int64)]
    return 0.5 * np.cross(p, np.roll(p, -1, axis=0)).sum(axis=0)


def _patch_vector_area(points: np.ndarray, tris: Sequence[tuple[int, int, int]]) -> np.ndarray:
    acc = np.zeros(3, dtype=np.float64)
    for a, b, c in tris:
        acc = acc + 0.5 * np.cross(points[b] - points[a], points[c] - points[a])
    return acc


@dataclass
class PatchGeometry:
    """Geometric description of one merged interface component."""

    n_facets: int
    scalar_facet_area: float  # sum |S_i|
    vector_area_norm: float  # |sum S_i n_i|
    area_ratio: float  # vector_area_norm / scalar_facet_area (1.0 == planar)
    max_facet_normal_deg: float  # worst facet normal vs merged polygon normal
    mean_facet_normal_deg: float
    planar_deviation: float  # max |offset from best-fit plane| / sqrt(area)


def _patch_geometry(
    points: np.ndarray,
    tris: Sequence[tuple[int, int, int]],
    loop: Sequence[int],
) -> PatchGeometry:
    """Measure a merged component with the existing Phase 0 metric definitions."""
    from core.evaluator.poly_quality_metrics import _face_planarity_and_normal_spread

    vec_area = _patch_vector_area(points, tris)
    vec_norm = float(np.linalg.norm(vec_area))

    scalar_area = 0.0
    facet_normals: list[np.ndarray] = []
    facet_areas: list[float] = []
    for a, b, c in tris:
        cross = np.cross(points[b] - points[a], points[c] - points[a])
        area = 0.5 * float(np.linalg.norm(cross))
        scalar_area += area
        if area > 1.0e-30:
            facet_normals.append(cross / (2.0 * area))
            facet_areas.append(area)

    if vec_norm > 1.0e-30 and facet_normals:
        unit = vec_area / vec_norm
        cosines = np.clip([float(np.dot(n, unit)) for n in facet_normals], -1.0, 1.0)
        angles = np.degrees(np.arccos(cosines))
        max_deg = float(angles.max())
        weights = np.asarray(facet_areas, dtype=np.float64)
        mean_deg = float(np.average(angles, weights=weights))
    else:
        max_deg = 0.0
        mean_deg = 0.0

    planar_dev, _ = _face_planarity_and_normal_spread(points, list(loop))

    return PatchGeometry(
        n_facets=len(tris),
        scalar_facet_area=scalar_area,
        vector_area_norm=vec_norm,
        area_ratio=(vec_norm / scalar_area) if scalar_area > 1.0e-30 else 0.0,
        max_facet_normal_deg=max_deg,
        mean_facet_normal_deg=mean_deg,
        planar_deviation=float(planar_dev),
    )


# ---------------------------------------------------------------------------
# Merged cell-face assembly
# ---------------------------------------------------------------------------


@dataclass
class MergeReport:
    """What the interface merge actually did, and what it refused to do."""

    n_block_pairs: int = 0
    n_components: int = 0
    n_merged: int = 0
    n_rejected: int = 0
    n_reverted_min_faces: int = 0
    n_reverted_negative_volume: int = 0
    unfixable_blocks: int = 0
    n_interface_facets: int = 0
    n_facets_after_merge: int = 0
    n_boundary_facets: int = 0
    rejection_reasons: Counter = field(default_factory=Counter)
    max_facet_normal_deg: float = 0.0
    mean_facet_normal_deg: float = 0.0
    p95_facet_normal_deg: float = 0.0
    min_area_ratio: float = 1.0
    mean_area_ratio: float = 1.0
    max_merged_planar_deviation: float = 0.0
    mean_merged_planar_deviation: float = 0.0
    max_loop_length: int = 0
    duplicate_face_keys: int = 0

    @property
    def interface_facet_reduction_pct(self) -> float:
        if not self.n_interface_facets:
            return 0.0
        return 100.0 * (1.0 - self.n_facets_after_merge / self.n_interface_facets)


def build_merged_cell_faces(
    V: np.ndarray,
    T: np.ndarray,
    block_of: np.ndarray,
    *,
    max_planar_deviation: float | None = None,
    max_facet_normal_deg: float | None = None,
) -> tuple[list[list[list[int]]], MergeReport]:
    """Assemble ``cell_faces`` with each block-block interface merged to a polygon.

    ``max_planar_deviation`` / ``max_facet_normal_deg`` implement the card's
    "above threshold is rejected ... never exported" gate.  ``None`` disables
    a gate (merge whatever is structurally valid) -- that ungated run is the
    diagnostic upper bound.

    Every rejection falls back to the raw facets of that component, so the
    exported mesh is always a valid superset-of-facets partition: no partial
    merge, no dropped facet, no dropped cell.
    """
    points = np.asarray(V, dtype=np.float64)
    T = np.asarray(T, dtype=np.int64)
    block_of = np.asarray(block_of, dtype=np.int64)
    n_tets = int(T.shape[0])
    n_blocks = int(block_of.max()) + 1 if n_tets else 0

    slots, face_verts = _tet_facet_slots(T)
    report = MergeReport()

    # boundary facets: (block, tri) -- never merged
    boundary_facets: dict[int, list[list[int]]] = defaultdict(list)
    # interface facets keyed by (lo, hi), oriented outward from `lo`
    interface: dict[tuple[int, int], list[tuple[int, int, int]]] = defaultdict(list)

    for key in sorted(slots):
        carriers = slots[key]
        if len(carriers) == 1:
            ti, fi = carriers[0]
            b = int(block_of[ti])
            boundary_facets[b].append([int(x) for x in face_verts[ti, fi].tolist()])
            continue
        if len(carriers) != 2:
            # non-manifold primal facet: leave both sides raw, never merge
            for ti, fi in carriers:
                b = int(block_of[ti])
                boundary_facets[b].append([int(x) for x in face_verts[ti, fi].tolist()])
            report.rejection_reasons["non_manifold_primal_facet"] += 1
            continue

        (t0, f0), (t1, f1) = carriers
        b0, b1 = int(block_of[t0]), int(block_of[t1])
        if b0 == b1:
            continue  # interior to a block -- dropped, as in the facet-union build
        if b0 < b1:
            lo, hi, ti, fi = b0, b1, t0, f0
        else:
            lo, hi, ti, fi = b1, b0, t1, f1
        tri = face_verts[ti, fi].tolist()
        interface[(lo, hi)].append((int(tri[0]), int(tri[1]), int(tri[2])))

    report.n_block_pairs = len(interface)
    report.n_boundary_facets = sum(len(v) for v in boundary_facets.values())
    report.n_interface_facets = sum(len(v) for v in interface.values())

    # --- per-component transactional merge -------------------------------
    # candidate[(lo, hi, comp)] = (loop, tris)
    candidates: dict[tuple[int, int, int], tuple[list[int], list[tuple[int, int, int]]]] = {}
    raw_components: dict[tuple[int, int, int], list[tuple[int, int, int]]] = {}
    geometries: dict[tuple[int, int, int], PatchGeometry] = {}

    for (lo, hi) in sorted(interface):
        tris = interface[(lo, hi)]
        for comp_idx, comp in enumerate(_facet_components(tris)):
            comp_tris = [tris[i] for i in comp]
            cid = (lo, hi, comp_idx)
            raw_components[cid] = comp_tris
            report.n_components += 1

            loop, reason = _patch_boundary_loop(comp_tris)
            if loop is None:
                report.rejection_reasons[reason] += 1
                continue

            geom = _patch_geometry(points, comp_tris, loop)

            # Hard guard: the merged polygon must reproduce the patch's vector
            # area exactly (this is what keeps cell volumes unchanged).
            patch_vec = _patch_vector_area(points, comp_tris)
            loop_vec = _polygon_vector_area(points, loop)
            scale = max(float(np.linalg.norm(patch_vec)), 1.0e-30)
            if float(np.linalg.norm(loop_vec - patch_vec)) / scale > _VECTOR_AREA_REL_TOL:
                report.rejection_reasons["vector_area_mismatch"] += 1
                continue

            if max_planar_deviation is not None and geom.planar_deviation > max_planar_deviation:
                report.rejection_reasons["planarity_gate"] += 1
                continue
            if max_facet_normal_deg is not None and geom.max_facet_normal_deg > max_facet_normal_deg:
                report.rejection_reasons["normal_spread_gate"] += 1
                continue

            candidates[cid] = (loop, comp_tris)
            geometries[cid] = geom

    def _assemble(
        active: dict[tuple[int, int, int], tuple[list[int], list[tuple[int, int, int]]]],
    ) -> tuple[list[list[list[int]]], int]:
        cf: list[list[list[int]]] = [list(boundary_facets.get(b, ())) for b in range(n_blocks)]
        n_after = 0
        for cid, tris in sorted(raw_components.items()):
            lo, hi, _ = cid
            if cid in active:
                loop, _ = active[cid]
                cf[lo].append(list(loop))
                cf[hi].append(list(reversed(loop)))
                n_after += 1
            else:
                for a, b, c in tris:
                    cf[lo].append([a, b, c])
                    cf[hi].append([c, b, a])
                n_after += len(tris)
        return cf, n_after

    # --- transactional revert loop ---------------------------------------
    # Two invariants a merge can break: a block can fall below the four faces
    # a closed polyhedron needs, and a block's volume can go non-positive
    # because the merged polygon bulges past it.  Both are repaired by
    # reverting every merge incident to the offending block -- whole
    # components only, never a partial un-merge.  Reverting can only raise a
    # block's face count and restores its original volume, so the loop is
    # monotone and terminates.
    while True:
        cell_faces, n_after = _assemble(candidates)
        thin: set[int] = set()
        inverted: set[int] = set()
        for b in range(n_blocks):
            if len(cell_faces[b]) < _MIN_FACES_PER_CELL:
                thin.add(b)
            elif _closed_cell_volume(points, cell_faces[b]) <= 0.0:
                inverted.add(b)
        bad = thin | inverted
        if not bad:
            break
        doomed = [cid for cid in candidates if cid[0] in bad or cid[1] in bad]
        if not doomed:
            # Nothing left to revert -- the violation predates any merge and
            # belongs to the agglomeration, not to this card.  Recorded, not
            # papered over.
            report.unfixable_blocks = len(bad)
            break
        for cid in doomed:
            del candidates[cid]
            geometries.pop(cid, None)
            if cid[0] in thin or cid[1] in thin:
                report.rejection_reasons["min_face_count"] += 1
                report.n_reverted_min_faces += 1
            else:
                report.rejection_reasons["negative_cell_volume"] += 1
                report.n_reverted_negative_volume += 1

    report.n_merged = len(candidates)
    report.n_rejected = report.n_components - report.n_merged
    report.n_facets_after_merge = n_after

    # --- summaries --------------------------------------------------------
    if geometries:
        normals = np.array([g.max_facet_normal_deg for g in geometries.values()])
        means = np.array([g.mean_facet_normal_deg for g in geometries.values()])
        ratios = np.array([g.area_ratio for g in geometries.values()])
        devs = np.array([g.planar_deviation for g in geometries.values()])
        report.max_facet_normal_deg = float(normals.max())
        report.mean_facet_normal_deg = float(means.mean())
        report.p95_facet_normal_deg = float(np.percentile(normals, 95.0))
        report.min_area_ratio = float(ratios.min())
        report.mean_area_ratio = float(ratios.mean())
        report.max_merged_planar_deviation = float(devs.max())
        report.mean_merged_planar_deviation = float(devs.mean())
        report.max_loop_length = max(len(loop) for loop, _ in candidates.values())

    seen_keys: Counter = Counter()
    for faces in cell_faces:
        for f in faces:
            seen_keys[tuple(sorted(f))] += 1
    report.duplicate_face_keys = sum(1 for c in seen_keys.values() if c > 2)

    return cell_faces, report


def write_merged_polymesh(
    V: np.ndarray,
    T: np.ndarray,
    agg: AgglomerationResult,
    case_dir: Path,
    *,
    max_planar_deviation: float | None = None,
    max_facet_normal_deg: float | None = None,
) -> tuple[dict[str, int], MergeReport]:
    cell_faces, report = build_merged_cell_faces(
        V,
        T,
        agg.block_of,
        max_planar_deviation=max_planar_deviation,
        max_facet_normal_deg=max_facet_normal_deg,
    )
    stats = write_generic_polymesh(np.asarray(V, dtype=np.float64), cell_faces, case_dir)
    return stats, report


# ---------------------------------------------------------------------------
# Comparison driver
# ---------------------------------------------------------------------------


@dataclass
class FaceGeomComparison:
    fixture: str
    n_tets: int
    n_blocks_final: int
    variants: list[tuple[str, EngineMeasurement]] = field(default_factory=list)
    merge_report_ungated: MergeReport | None = None
    merge_report_gated: MergeReport | None = None


def run_facegeom_comparison(
    stl_path: Path,
    *,
    target_edge_length: float | None = None,
    seed_density: int = 12,
    target_cells: int | None = None,
    gate_planar_deviation: float = 0.20,
    gate_facet_normal_deg: float = 60.0,
    workdir: Path | None = None,
) -> FaceGeomComparison:
    """Measure polydual vs facet-union vs merged-interface on ONE tet primal."""
    from core.analyzer.readers.stl import read_stl
    from core.generator.native_poly.agglomeration_experiment import (
        write_agglomerated_polymesh,
    )
    from core.generator.native_poly.dual import tet_to_poly_dual
    from core.generator.native_tet import generate_native_tet

    own_tmp = workdir is None
    tmp_root = Path(workdir) if workdir is not None else Path(tempfile.mkdtemp(prefix="poly_facegeom_"))
    try:
        mesh = read_stl(stl_path)
        true_area = _triangle_area_sum(mesh.vertices, mesh.faces)

        tet_res = generate_native_tet(
            mesh.vertices,
            mesh.faces,
            tmp_root / "tet",
            target_edge_length=target_edge_length,
            seed_density=seed_density,
            target_cells=target_cells,
        )
        if not tet_res.success or tet_res.tets is None:
            raise RuntimeError(f"generate_native_tet failed: {tet_res.message}")
        V = np.asarray(tet_res.tet_points, dtype=np.float64)
        T = np.asarray(tet_res.tets, dtype=np.int64)

        variants: list[tuple[str, EngineMeasurement]] = []

        dual_dir = tmp_root / "dual"
        dual_res = tet_to_poly_dual(V, T, dual_dir)
        if not dual_res.success:
            raise RuntimeError(f"tet_to_poly_dual failed: {dual_res.message}")
        variants.append(("polydual", _measure_case(dual_dir, "polydual", true_area)))

        agg = vertex_star_agglomerate(V, T)

        union_dir = tmp_root / "facet_union"
        write_agglomerated_polymesh(V, T, agg, union_dir)
        variants.append(("facet_union", _measure_case(union_dir, "facet_union", true_area)))

        merged_dir = tmp_root / "merged"
        _, rep_ungated = write_merged_polymesh(V, T, agg, merged_dir)
        variants.append(("merged_all", _measure_case(merged_dir, "merged_all", true_area)))

        gated_dir = tmp_root / "merged_gated"
        _, rep_gated = write_merged_polymesh(
            V,
            T,
            agg,
            gated_dir,
            max_planar_deviation=gate_planar_deviation,
            max_facet_normal_deg=gate_facet_normal_deg,
        )
        variants.append(("merged_gated", _measure_case(gated_dir, "merged_gated", true_area)))

        return FaceGeomComparison(
            fixture=Path(stl_path).name,
            n_tets=int(T.shape[0]),
            n_blocks_final=agg.n_blocks_final,
            variants=variants,
            merge_report_ungated=rep_ungated,
            merge_report_gated=rep_gated,
        )
    finally:
        if own_tmp:
            shutil.rmtree(tmp_root, ignore_errors=True)


def _format_merge_report(name: str, r: MergeReport) -> str:
    reasons = ", ".join(f"{k}={v}" for k, v in sorted(r.rejection_reasons.items())) or "none"
    return "\n".join(
        [
            f"-- {name} --",
            (
                f"  block pairs={r.n_block_pairs} components={r.n_components} "
                f"merged={r.n_merged} rejected={r.n_rejected} "
                f"(reverted: min-face-count={r.n_reverted_min_faces}, "
                f"negative-volume={r.n_reverted_negative_volume}, "
                f"unfixable blocks={r.unfixable_blocks})"
            ),
            (
                f"  interface facets {r.n_interface_facets} -> {r.n_facets_after_merge} "
                f"({r.interface_facet_reduction_pct:.1f}% fewer internal faces); "
                f"boundary facets {r.n_boundary_facets} kept raw"
            ),
            (
                f"  facet-normal dev vs merged normal: max={r.max_facet_normal_deg:.2f} deg "
                f"p95={r.p95_facet_normal_deg:.2f} area-weighted mean={r.mean_facet_normal_deg:.2f}"
            ),
            (
                f"  area ratio |sum S n|/sum|S|: min={r.min_area_ratio:.4f} "
                f"mean={r.mean_area_ratio:.4f}   merged planar dev: "
                f"max={r.max_merged_planar_deviation:.4f} mean={r.mean_merged_planar_deviation:.4f}"
            ),
            f"  max loop length={r.max_loop_length}  duplicate face keys={r.duplicate_face_keys}",
            f"  rejections: {reasons}",
        ]
    )


def format_facegeom(cmp: FaceGeomComparison) -> str:
    names = [n for n, _ in cmp.variants]
    lines = [
        f"=== {cmp.fixture} (primal tets={cmp.n_tets}, agglomerated blocks={cmp.n_blocks_final}) ===",
        f"{'metric':32s}" + "".join(f"{n:>15s}" for n in names),
    ]

    rows: list[tuple[str, str, str]] = [
        ("n_cells", "n_cells", "d"),
        ("negative_volumes", "negative_volumes", "d"),
        ("max_non_orthogonality (deg)", "max_non_orthogonality", "f"),
        ("max_skewness", "max_skewness", "f"),
        ("surface_area_dev (%)", "surface_area_dev_pct", "f"),
        ("max_face_planar_deviation", "max_face_planar_deviation", "f"),
        ("mean_face_planar_deviation", "mean_face_planar_deviation", "f"),
        ("max_face_normal_spread_deg", "max_face_normal_spread_deg", "f"),
        ("mean_juretic_psi", "mean_juretic_psi", "f"),
        ("min_cell_h", "min_cell_h", "f"),
        ("mean_cell_h", "mean_cell_h", "f"),
        ("min_uniformity_factor", "min_uniformity_factor", "f"),
        ("mean_uniformity_factor", "mean_uniformity_factor", "f"),
    ]
    for label, attr, kind in rows:
        cells = []
        for _, m in cmp.variants:
            val = getattr(m, attr)
            cells.append(f"{val:>15d}" if kind == "d" else f"{val:>15.4f}")
        lines.append(f"{label:32s}" + "".join(cells))

    for name, m in cmp.variants:
        if m.error:
            lines.append(f"{name} ERROR: {m.error}")

    if cmp.merge_report_ungated is not None:
        lines.append(_format_merge_report("merged_all (no geometric gate)", cmp.merge_report_ungated))
    if cmp.merge_report_gated is not None:
        lines.append(_format_merge_report("merged_gated", cmp.merge_report_gated))
    return "\n".join(lines)


def main() -> int:  # pragma: no cover -- manual experiment entry point
    from core.utils.logging import configure_logging

    configure_logging(verbose=False, json=False)

    repo = Path(__file__).resolve().parents[3]
    fixtures = [
        (repo / "tests" / "benchmarks" / "cube.stl", {"seed_density": 10, "target_cells": 200}),
        (repo / "tests" / "benchmarks" / "cylinder.stl", {"seed_density": 20, "target_cells": 2000}),
    ]
    for stl_path, kwargs in fixtures:
        cmp = run_facegeom_comparison(stl_path, **kwargs)
        print(format_facegeom(cmp))
        print()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
