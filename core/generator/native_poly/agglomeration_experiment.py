"""POLY-AGGLOM-CFD1 measurement experiment — vertex-star tet agglomeration.

Report-only, standalone module.  NOT imported by ``tier_native_poly.py``, the
CLI, or any production path.  It exists to run the decisive keep/kill
measurement for the ``native_poly`` route-2 agglomeration leg described in
``docs/references/literature/native_poly/native_poly_literature_integrated_development_plan_2026-07-23.md``
(Phase 3) and
``docs/references/literature/native_poly/gap_search_3d_agglomeration.md``
("Verdict" section): does agglomerating the tet primal into polyhedral cells
(instead of the ``polydual`` node-dual construction) pass the same Phase 0 FV
metrics -- face planarity, non-orthogonality, skewness, ``h = 6V/A``,
Uniformity Factor -- at fewer cells, on the *same* primal tet mesh?

Algorithm
---------
Pan & Persson 2022 (J. Comput. Phys. 449, 110775) greedy vertex-star
agglomeration, screened in
``docs/references/literature/native_poly/pan2022_agglomeration_dg.md``:

    each tet carries weight = number of not-yet-processed face-neighbours;
    a priority queue is drained in ascending-weight order.  Popping a tet
    with weight >= 2 finds the vertex touching the most unprocessed tets and
    merges *all* unprocessed tets touching that vertex into one block.
    Popping a tet with weight < 2 appends it (an "orphan") to the smallest
    adjacent already-formed block.

The source paper's only validity bar is connectedness of the resulting
block union -- and vertex-star merging can produce a block that only
touches another part of itself at a single vertex ("bowtie"), which is
connected as a point-set but not admissible as one FV cell (no shared face
between the two lobes).  MAGNET's face-adjacency connected-component guard
(``POLY-AGG-CONNSPLIT1``, see ``magnet2025_gnn_agglomeration.md``) is applied
after the greedy pass: any block whose tets are not one connected component
under face adjacency is split into its components before export.

Face geometry policy
---------------------
Every interface between two different agglomerated blocks (or between a
block and the domain exterior) is exported as the *raw, unmerged* set of
tet-triangle facets that lie on that interface -- the "union of facets"
geometry ``POLY-AGGLOM-FACEGEOM1`` (development plan, Phase 3) flags as the
literal DG-vs-FV gap: DG/VEM absorb it via per-facet quadrature, FV cannot.
This module intentionally does *not* attempt to merge coplanar facets into a
single polygon per interface -- doing so is not generally well-defined for a
jagged tet-tet interface, and the whole point of this experiment is to
measure the naive construction the literature warns about, not to paper over
it before measuring.
"""

from __future__ import annotations

import heapq
import shutil
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from core.generator.polymesh_writer import _TET_FACES, write_generic_polymesh
from core.utils.logging import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Tet topology helpers
# ---------------------------------------------------------------------------


def _tet_face_topology(
    tets: np.ndarray,
) -> tuple[dict[tuple[int, int, int], list[int]], np.ndarray]:
    """Return (face_key -> [tet indices sharing it], per-tet outward face verts).

    ``face_verts[ti, fi]`` is the vertex triple for tet ``ti``'s face ``fi``,
    ordered outward from ``ti`` per the ``_TET_FACES`` right-hand convention
    (same convention ``PolyMeshWriter`` uses for a plain tet mesh).  Winding
    is assumed already normalised (positive volume) by the caller -- this
    experiment reuses the tet mesh straight from ``generate_native_tet``,
    which already emits right-handed tets.
    """
    tets = np.asarray(tets, dtype=np.int64)
    n_tets = tets.shape[0]
    tf = np.array(_TET_FACES, dtype=np.int64)  # (4, 3) local indices
    face_verts = tets[:, tf]  # (n_tets, 4, 3) global vertex ids, outward order
    face_key_arr = np.sort(face_verts, axis=2)

    face_tets: dict[tuple[int, int, int], list[int]] = defaultdict(list)
    for ti in range(n_tets):
        for fi in range(4):
            key = (
                int(face_key_arr[ti, fi, 0]),
                int(face_key_arr[ti, fi, 1]),
                int(face_key_arr[ti, fi, 2]),
            )
            face_tets[key].append(ti)
    return face_tets, face_verts


def _tet_adjacency(
    n_tets: int, face_tets: dict[tuple[int, int, int], list[int]]
) -> list[set[int]]:
    adj: list[set[int]] = [set() for _ in range(n_tets)]
    for tl in face_tets.values():
        if len(tl) == 2:
            a, b = tl
            adj[a].add(b)
            adj[b].add(a)
    return adj


# ---------------------------------------------------------------------------
# Pan-Persson greedy vertex-star agglomeration
# ---------------------------------------------------------------------------


@dataclass
class AgglomerationResult:
    """One coarsening level of vertex-star agglomeration, post connectivity guard."""

    block_of: np.ndarray  # (n_tets,) int64 -- final block id per tet
    n_blocks_pregap: int  # blocks emitted by the greedy pass, before the guard
    n_blocks_final: int  # blocks after POLY-AGG-CONNSPLIT1 splitting
    n_split_events: int  # number of pre-guard blocks that needed splitting
    n_isolated_orphans: int  # weight<2 tets with no processed neighbour to join
    tet_adjacency: list[set[int]] = field(default_factory=list)


def vertex_star_agglomerate(V: np.ndarray, T: np.ndarray, seed: int = 0) -> AgglomerationResult:
    """Pan-Persson greedy vertex-star agglomeration (one coarsening level).

    ``seed`` only affects the deterministic tie-break order used when a
    vertex-max-count tie must be broken (the paper breaks ties "at random";
    this module breaks them by lowest vertex id for full determinism and
    byte-identical repeat runs -- ``seed`` is accepted for interface
    stability but does not currently change behaviour).
    """
    del seed  # deterministic tie-break by vertex id; kept for interface parity
    T = np.asarray(T, dtype=np.int64)
    n_tets = int(T.shape[0])
    if n_tets == 0:
        return AgglomerationResult(np.zeros(0, dtype=np.int64), 0, 0, 0, 0, [])

    face_tets, _ = _tet_face_topology(T)
    tet_adj = _tet_adjacency(n_tets, face_tets)

    vert_tets: dict[int, list[int]] = defaultdict(list)
    for ti in range(n_tets):
        for v in T[ti].tolist():
            vert_tets[int(v)].append(ti)

    processed = np.zeros(n_tets, dtype=bool)
    block_of = -np.ones(n_tets, dtype=np.int64)
    n_blocks = 0
    n_isolated_orphans = 0

    def weight(ti: int) -> int:
        return sum(1 for nb in tet_adj[ti] if not processed[nb])

    # (weight, tet_id) heap; tet_id as secondary key gives a fixed,
    # reproducible pop order among equal-weight entries.  Stale entries
    # (weight changed since push) are detected on pop and re-pushed --
    # standard lazy-deletion priority queue.
    heap = [(weight(ti), ti) for ti in range(n_tets)]
    heapq.heapify(heap)

    while heap:
        w, ti = heapq.heappop(heap)
        if processed[ti]:
            continue
        cur_w = weight(ti)
        if cur_w != w:
            heapq.heappush(heap, (cur_w, ti))
            continue

        if cur_w >= 2:
            best_v = -1
            best_count = -1
            for v in sorted(int(x) for x in T[ti].tolist()):
                cnt = sum(1 for tj in vert_tets[v] if not processed[tj])
                if cnt > best_count:
                    best_count = cnt
                    best_v = v
            block_id = n_blocks
            n_blocks += 1
            for tj in vert_tets[best_v]:
                if not processed[tj]:
                    processed[tj] = True
                    block_of[tj] = block_id
        else:
            # Orphan (weight 0 or 1). Absorb into the smallest adjacent
            # already-formed block (Pan-Persson's stated rule).
            block_sizes: dict[int, int] = defaultdict(int)
            adjacent_blocks: set[int] = set()
            for nb in tet_adj[ti]:
                if processed[nb]:
                    adjacent_blocks.add(int(block_of[nb]))
            if adjacent_blocks:
                for tj in range(n_tets):
                    if processed[tj] and int(block_of[tj]) in adjacent_blocks:
                        block_sizes[int(block_of[tj])] += 1
                target = min(adjacent_blocks, key=lambda b: (block_sizes[b], b))
                processed[ti] = True
                block_of[ti] = target
            elif cur_w == 1:
                # Corner case the paper does not address: a weight-1 tet
                # whose single neighbour is also unprocessed (a "pendant"
                # in the current adjacency residual).  No existing block to
                # join yet -- merge it directly with that neighbour into a
                # fresh block so the queue keeps draining deterministically.
                (nb,) = (n for n in tet_adj[ti] if not processed[n])
                n_isolated_orphans += 1
                block_id = n_blocks
                n_blocks += 1
                processed[ti] = True
                block_of[ti] = block_id
                processed[nb] = True
                block_of[nb] = block_id
            else:
                # Fully isolated tet (no neighbours at all): singleton block.
                n_isolated_orphans += 1
                block_id = n_blocks
                n_blocks += 1
                processed[ti] = True
                block_of[ti] = block_id

    n_blocks_pregap = n_blocks

    # --- POLY-AGG-CONNSPLIT1: face-adjacency connected-component guard ---
    final_block_of = -np.ones(n_tets, dtype=np.int64)
    next_id = 0
    n_split_events = 0
    for b in range(n_blocks_pregap):
        members = [ti for ti in range(n_tets) if block_of[ti] == b]
        if not members:
            continue
        member_set = set(members)
        unvisited = set(members)
        components: list[list[int]] = []
        while unvisited:
            start = next(iter(unvisited))
            stack = [start]
            unvisited.discard(start)
            comp = [start]
            while stack:
                cur = stack.pop()
                for nb in tet_adj[cur]:
                    if nb in unvisited and nb in member_set:
                        unvisited.discard(nb)
                        comp.append(nb)
                        stack.append(nb)
            components.append(comp)
        if len(components) > 1:
            n_split_events += 1
        for comp in components:
            for ti in comp:
                final_block_of[ti] = next_id
            next_id += 1

    return AgglomerationResult(
        block_of=final_block_of,
        n_blocks_pregap=n_blocks_pregap,
        n_blocks_final=next_id,
        n_split_events=n_split_events,
        n_isolated_orphans=n_isolated_orphans,
        tet_adjacency=tet_adj,
    )


# ---------------------------------------------------------------------------
# Export agglomerated blocks as an OpenFOAM polyMesh
# ---------------------------------------------------------------------------


def build_agglomerated_cell_faces(
    T: np.ndarray,
    block_of: np.ndarray,
    face_tets: dict[tuple[int, int, int], list[int]] | None = None,
    face_verts: np.ndarray | None = None,
) -> list[list[list[int]]]:
    """Assemble ``cell_faces`` for ``write_generic_polymesh`` from a block partition.

    Every tet-triangle face that borders a *different* block (or the domain
    exterior) is kept, oriented outward from the tet that owns it -- which is
    outward from the block at that location, since the face is boundary of
    the block by construction.  Faces strictly interior to a block (shared by
    two tets in the same block) are dropped.  See the module docstring for
    why these interface facets are exported raw (not merged into per-interface
    polygons).
    """
    T = np.asarray(T, dtype=np.int64)
    n_tets = T.shape[0]
    if face_tets is None or face_verts is None:
        face_tets, face_verts = _tet_face_topology(T)

    n_blocks = int(block_of.max()) + 1 if n_tets else 0
    cell_faces: list[list[list[int]]] = [[] for _ in range(n_blocks)]

    tf = np.array(_TET_FACES, dtype=np.int64)
    face_key_arr = np.sort(T[:, tf], axis=2)

    for ti in range(n_tets):
        b = int(block_of[ti])
        for fi in range(4):
            key = (
                int(face_key_arr[ti, fi, 0]),
                int(face_key_arr[ti, fi, 1]),
                int(face_key_arr[ti, fi, 2]),
            )
            sharers = face_tets[key]
            if len(sharers) == 1:
                # domain boundary face
                cell_faces[b].append([int(x) for x in face_verts[ti, fi].tolist()])
            else:
                other = sharers[0] if sharers[1] == ti else sharers[1]
                if int(block_of[other]) != b:
                    cell_faces[b].append([int(x) for x in face_verts[ti, fi].tolist()])
                # else: interior to the block -- dropped
    return cell_faces


def write_agglomerated_polymesh(
    V: np.ndarray,
    T: np.ndarray,
    agg: AgglomerationResult,
    case_dir: Path,
) -> dict[str, int]:
    cell_faces = build_agglomerated_cell_faces(T, agg.block_of)
    return write_generic_polymesh(np.asarray(V, dtype=np.float64), cell_faces, case_dir)


# ---------------------------------------------------------------------------
# Comparison driver
# ---------------------------------------------------------------------------


def _triangle_area_sum(points: np.ndarray, tris: np.ndarray) -> float:
    p = np.asarray(points, dtype=np.float64)
    t = np.asarray(tris, dtype=np.int64)
    a = p[t[:, 0]]
    b = p[t[:, 1]]
    c = p[t[:, 2]]
    return float(np.sum(0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)))


def _boundary_area_from_polymesh(case_dir: Path) -> float:
    from core.utils.polymesh_reader import (
        parse_foam_faces,
        parse_foam_labels,
        parse_foam_points,
    )

    poly = case_dir / "constant" / "polyMesh"
    pts = np.asarray(parse_foam_points(poly / "points"), dtype=np.float64)
    faces = [list(f) for f in parse_foam_faces(poly / "faces")]
    nb = np.asarray(parse_foam_labels(poly / "neighbour"), dtype=np.int64)
    n_int = len(nb)
    total = 0.0
    for f in faces[n_int:]:
        p = pts[np.asarray(f, dtype=np.int64)]
        acc = np.zeros(3)
        for i in range(1, len(f) - 1):
            acc = acc + np.cross(p[i] - p[0], p[i + 1] - p[0]) / 2.0
        total += float(np.linalg.norm(acc))
    return total


@dataclass
class EngineMeasurement:
    label: str
    n_cells: int = 0
    n_points: int = 0
    negative_volumes: int = 0
    max_non_orthogonality: float = 0.0
    max_skewness: float = 0.0
    boundary_area: float = 0.0
    surface_area_dev_pct: float = 0.0
    max_face_planar_deviation: float = 0.0
    mean_face_planar_deviation: float = 0.0
    max_face_normal_spread_deg: float = 0.0
    mean_juretic_psi: float = 0.0
    min_cell_h: float = 0.0
    mean_cell_h: float = 0.0
    min_uniformity_factor: float = 0.0
    mean_uniformity_factor: float = 0.0
    error: str = ""


def _measure_case(case_dir: Path, label: str, true_area: float) -> EngineMeasurement:
    from core.evaluator.native_checker import NativeMeshChecker

    m = EngineMeasurement(label=label)
    try:
        r = NativeMeshChecker().run(case_dir)
    except Exception as exc:  # noqa: BLE001
        m.error = f"{type(exc).__name__}: {exc}"
        return m
    m.n_cells = int(r.cells)
    m.n_points = int(r.points)
    m.negative_volumes = int(r.negative_volumes)
    m.max_non_orthogonality = float(r.max_non_orthogonality)
    m.max_skewness = float(r.max_skewness)
    m.max_face_planar_deviation = float(r.max_face_planar_deviation or 0.0)
    m.mean_face_planar_deviation = float(r.mean_face_planar_deviation or 0.0)
    m.max_face_normal_spread_deg = float(r.max_face_normal_spread_deg or 0.0)
    m.mean_juretic_psi = float(r.mean_juretic_psi or 0.0)
    m.min_cell_h = float(r.min_cell_h or 0.0)
    m.mean_cell_h = float(r.mean_cell_h or 0.0)
    m.min_uniformity_factor = float(r.min_uniformity_factor or 0.0)
    m.mean_uniformity_factor = float(r.mean_uniformity_factor or 0.0)
    try:
        m.boundary_area = _boundary_area_from_polymesh(case_dir)
        if true_area > 0:
            m.surface_area_dev_pct = abs(m.boundary_area / true_area - 1.0) * 100.0
    except Exception as exc:  # noqa: BLE001
        m.error = f"boundary_area failed: {exc}"
    return m


@dataclass
class FixtureComparison:
    fixture: str
    n_tets: int
    n_blocks_pregap: int
    n_blocks_final: int
    n_split_events: int
    n_isolated_orphans: int
    dual: EngineMeasurement
    agglom: EngineMeasurement


def run_comparison(
    stl_path: Path,
    *,
    target_edge_length: float | None = None,
    seed_density: int = 12,
    target_cells: int | None = None,
    workdir: Path | None = None,
) -> FixtureComparison:
    """Run polydual and vertex-star agglomeration on the SAME tet primal.

    Both engines consume the identical ``(V, T)`` output of
    ``generate_native_tet`` so the cell-count-reduction and FV-metric
    comparison is apples-to-apples.
    """
    from core.analyzer.readers.stl import read_stl
    from core.generator.native_poly.dual import tet_to_poly_dual
    from core.generator.native_tet import generate_native_tet

    own_tmp = workdir is None
    tmp_root = Path(workdir) if workdir is not None else Path(tempfile.mkdtemp(prefix="poly_agglom_"))
    try:
        mesh = read_stl(stl_path)
        true_area = _triangle_area_sum(mesh.vertices, mesh.faces)

        tet_dir = tmp_root / "tet"
        tet_res = generate_native_tet(
            mesh.vertices,
            mesh.faces,
            tet_dir,
            target_edge_length=target_edge_length,
            seed_density=seed_density,
            target_cells=target_cells,
        )
        if not tet_res.success or tet_res.tets is None:
            raise RuntimeError(f"generate_native_tet failed: {tet_res.message}")
        V = np.asarray(tet_res.tet_points, dtype=np.float64)
        T = np.asarray(tet_res.tets, dtype=np.int64)
        n_tets = int(T.shape[0])

        dual_dir = tmp_root / "dual"
        dual_res = tet_to_poly_dual(V, T, dual_dir)
        if not dual_res.success:
            raise RuntimeError(f"tet_to_poly_dual failed: {dual_res.message}")
        dual_metrics = _measure_case(dual_dir, "polydual", true_area)

        agg = vertex_star_agglomerate(V, T)
        agg_dir = tmp_root / "agglom"
        write_agglomerated_polymesh(V, T, agg, agg_dir)
        agg_metrics = _measure_case(agg_dir, "vstar_agglom", true_area)

        return FixtureComparison(
            fixture=Path(stl_path).name,
            n_tets=n_tets,
            n_blocks_pregap=agg.n_blocks_pregap,
            n_blocks_final=agg.n_blocks_final,
            n_split_events=agg.n_split_events,
            n_isolated_orphans=agg.n_isolated_orphans,
            dual=dual_metrics,
            agglom=agg_metrics,
        )
    finally:
        if own_tmp:
            shutil.rmtree(tmp_root, ignore_errors=True)


def format_comparison(cmp: FixtureComparison) -> str:
    lines = [
        f"=== {cmp.fixture} (primal tets={cmp.n_tets}) ===",
        (
            f"agglomeration: {cmp.n_blocks_pregap} blocks pre-guard -> "
            f"{cmp.n_blocks_final} final "
            f"({cmp.n_split_events} blocks split by POLY-AGG-CONNSPLIT1, "
            f"{cmp.n_isolated_orphans} isolated-orphan singletons)"
        ),
        f"{'metric':32s} {'polydual':>14s} {'vstar_agglom':>14s}",
    ]

    def row(name: str, a: Any, b: Any, fmt: str = "{:.4f}") -> str:
        fa = fmt.format(a) if isinstance(a, float) else str(a)
        fb = fmt.format(b) if isinstance(b, float) else str(b)
        return f"{name:32s} {fa:>14s} {fb:>14s}"

    d, a = cmp.dual, cmp.agglom
    if d.error:
        lines.append(f"polydual ERROR: {d.error}")
    if a.error:
        lines.append(f"vstar_agglom ERROR: {a.error}")
    lines.append(row("n_cells", d.n_cells, a.n_cells))
    lines.append(row("negative_volumes", d.negative_volumes, a.negative_volumes))
    lines.append(row("max_non_orthogonality (deg)", d.max_non_orthogonality, a.max_non_orthogonality))
    lines.append(row("max_skewness", d.max_skewness, a.max_skewness))
    lines.append(row("surface_area_dev (%)", d.surface_area_dev_pct, a.surface_area_dev_pct))
    lines.append(row("max_face_planar_deviation", d.max_face_planar_deviation, a.max_face_planar_deviation))
    lines.append(row("mean_face_planar_deviation", d.mean_face_planar_deviation, a.mean_face_planar_deviation))
    lines.append(row("max_face_normal_spread_deg", d.max_face_normal_spread_deg, a.max_face_normal_spread_deg))
    lines.append(row("mean_juretic_psi", d.mean_juretic_psi, a.mean_juretic_psi))
    lines.append(row("min_cell_h", d.min_cell_h, a.min_cell_h))
    lines.append(row("mean_cell_h", d.mean_cell_h, a.mean_cell_h))
    lines.append(row("min_uniformity_factor", d.min_uniformity_factor, a.min_uniformity_factor))
    lines.append(row("mean_uniformity_factor", d.mean_uniformity_factor, a.mean_uniformity_factor))
    if d.n_cells and a.n_cells:
        reduction = 1.0 - (a.n_cells / d.n_cells)
        lines.append(f"cell-count reduction vs polydual: {reduction * 100.0:.1f}%")
    return "\n".join(lines)


def main() -> int:  # pragma: no cover -- manual experiment entry point
    from core.utils.logging import configure_logging

    configure_logging(verbose=False, json=False)

    repo = Path(__file__).resolve().parents[3]
    # target_cells=2000 collapses cube.stl's tet primal to a 40-tet coarse
    # candidate (a pre-existing generate_native_tet quirk unrelated to this
    # experiment -- its internal best-of selection prefers a coarser grade-A
    # candidate over a finer one at this target for this specific bbox/seed
    # combination). target_cells=200 with the default seed_density instead
    # yields a 1662-tet primal for cube -- the same order of magnitude as
    # cylinder's 2394-tet primal at target_cells=2000 -- so that is used here
    # to keep both fixtures' primal density comparable.
    fixtures = [
        (repo / "tests" / "benchmarks" / "cube.stl", {"seed_density": 10, "target_cells": 200}),
        (repo / "tests" / "benchmarks" / "cylinder.stl", {"seed_density": 20, "target_cells": 2000}),
    ]
    for stl_path, kwargs in fixtures:
        cmp = run_comparison(stl_path, **kwargs)
        print(format_comparison(cmp))
        print()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
