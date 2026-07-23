# Native Poly Quality: Literature-Integrated Development Plan

Date: 2026-07-23
Status: implementation plan, not a solved-quality claim
Primary target: take native_poly past its ~55% state (ROADMAP.md A-2: 4 solid
invariants permanent-gated on cube; S5 sphere/cylinder E2E green) toward broader
topology/patch coverage and FV-grade quality, using the 34 ledger cards owned by
`evidence_matrix.md` (17 pre-existing + 17 from the 2026-07-23 nine-paper
full-read batch). Evidence base: 13 FULL_READ papers; per-paper notes cited
inline. This plan owns the union of both card generations.

## 1. Executive decision

1. **Polydual (route-2 primal-dual) is the main generator, and for the first
   time that choice is FV-accuracy-backed, not just pragmatic.** Juretić &
   Gosman's face-pair cancellation analysis shows cells built of opposing
   equal-area face pairs cancel leading truncation terms: hexagon-like polyhedral
   duals sit at ~1.155x square/hex truncation error and need only ~2x cells for
   equal mean error, while *perfect-quality* tetrahedra are the worst FV cells
   (~10x cells, no face pairs) (`juretic2010_fv_error_cell_shape.md`). The
   industrial FV lineage (Oaks-Paoletti, Fluent §6.7.1) independently converges
   on node-dual construction (`gap_search_3d_agglomeration.md`, Theme 3).
2. **Gate calibration runs FIRST, before any new mechanism.** The 2026-07-23
   audit of `core/evaluator/native_checker.py` against primary FV error theory
   found one *missing* gate and two mis-calibrated ones (evidence_matrix.md,
   quality-gate audit): (a) face planarity/warpage is absent, yet Katz Table 5
   proves single-point flux on a non-planar face is first order — and our dual
   cells' curved interior faces are exactly the at-risk population
   (`katz2011_mesh_quality_cfd_accuracy.md`); (b) our skewness and the paper's
   `psi = |m|/|d|` are different quantities — thresholds cannot be cited until
   the definitions are reconciled (`juretic2010_fv_error_cell_shape.md`); (c)
   the aspect-ratio gate must NOT reject aligned boundary-layer stretching —
   Katz shows AR up to 1e6 is fine for aligned cell-centered BL cells, and
   Juretić explicitly declines to analyze AR. Phase 0 is therefore a
   measurement phase: new metrics land report-only, gates change only on data.
3. **Quality effort is routed to what FV theory actually rewards** (the
   FSL-style honesty rule from the tet plan): face pairing, face planarity, and
   uniformity `fx` are the measured error drivers
   (`juretic2010_fv_error_cell_shape.md`, `katz2011_mesh_quality_cfd_accuracy.md`);
   generic shape beauty (sphericity, ball ratio, CR) is *reported* for
   diagnosis (`magnet2025_gnn_agglomeration.md`,
   `antonietti2022_ml_agglomeration.md`) but never optimized for its own sake.
   A card is accepted on the FV-relevant axis it owns.
4. **The agglomeration leg of route 2 is demoted to a quality-gated secondary,
   confirmed by five independent full reads** (Bassi 2012, Pan-Persson 2022,
   R3MG 2025, MAGNET 2025, PVEM 2025). Every strong agglomeration result lives
   in DG/VEM land where per-facet quadrature and stabilization absorb arbitrary
   cell shape; none of the five computes a single FV metric on its agglomerates
   (`bassi2012_agglomeration_dg.md`, `pan2022_agglomeration_dg.md`,
   `r3mg2025_rtree_agglomeration.md`, `magnet2025_gnn_agglomeration.md`,
   `pvem2025_polytopal_vem.md`). The leg stays alive solely through measured
   experiments; `POLY-AGGLOM-CFD1` is the decisive keep-or-drop gate
   (`gap_search_3d_agglomeration.md`, Verdict).
5. **The repair lane gains a merge/split operator pair with concrete rules.**
   Merge: PVEM's node-preserving merge-with-best-neighbor absorbs sliver/pancake
   dual cells without moving a single node (`pvem2025_polytopal_vem.md`,
   `POLY-QUALITY-AGGLOM1`). Split: Antonietti's deterministic 2-seed k-means
   cutting plane with vertex snapping, validity gates, and perturbation retry
   is the concrete plane-choice rule Garimella's `POLY-CONCAVE-SPLIT1` lacked
   (`antonietti2022_ml_agglomeration.md`, `garimella2013_general_dual.md`).
   Both sit behind MAGNET's face-adjacency connected-component guard
   (`POLY-AGG-CONNSPLIT1`) so no repair can emit a disconnected cell.
6. **Route-1 conforming Voronoi stays long-term; its CVT lane starts honest.**
   Du 1999 gives frozen-boundary interior Lloyd a real license — monotone energy
   descent survives restriction to interior seeds — but every convergence proof
   is 1D-only and the converged state can be a saddle
   (`du1999_cvt_review.md`). `POLY-CVT-LLOYD1` therefore ships with explicit
   per-iteration guards (energy-monotone assert, centroid containment,
   boundary-face bit-identity) and full rollback, plus density-graded sampling
   (`POLY-CVT-DENSITY1`, alpha swept not assumed). The current fake Lloyd loop
   (`voronoi.py:1017-1149`, arithmetic mean of Voronoi vertices) is replaced,
   not tuned (evidence_matrix.md, current-code audit).
7. **Route-1 is NOT the near-term default.** The current Voronoi code snaps
   outside Voronoi vertices to surface vertices, invalidating the orthogonal
   dual contract (`voronoi.py:2128-2160` audit), and VoroCrust-grade boundary
   protection requires faithful watertight input and degrades at sharp features
   (`vorocrust2020_without_clipping.md`). Route 1 is rebuilt behind the
   VoroCrust protection cards on its own timeline (Phase 4), while polydual
   carries the product.
8. **Rejections (binding; details in section 5).** (a) Raw ML/GNN agglomeration
   — MAGNET's own honest finding is a near-zero quality margin over METIS and
   k-means, with disconnected 3D cells needing post-hoc repair. (b) R3MG as a
   generator — it is a hierarchy builder whose "cells" are unmerged fine facets
   with hanging nodes. (c) Transferring DG/VEM shape tolerance to FV gates —
   Bassi's admissibility bar is connectedness only; PVEM's note says explicitly
   do NOT relax FV gates on VEM evidence. (d) Voronoi-only route as near-term
   default (point 7).
9. **No card claims a theoretical guarantee.** Juretić's truncation analysis is
   2D with a 3D face-pair argument; Katz reports no OpenFOAM-metric thresholds;
   Du's convergence theory does not cover restricted 3D Lloyd; Gersho's
   conjecture is open in 3D. All acceptance is by measurement on our fixtures.

## 2. Current measured bottleneck

Numbers from ROADMAP.md A-2 (revalidated 2026-07-19, S1→S5) and the
evidence_matrix.md current-code audit:

| Quantity | Value | Source / consequence |
| --- | ---: | --- |
| Cube solid invariants | 4/4 permanent gates | Surface/void 0.000/volume/degenerate — floor for every card. |
| Cylinder E2E (N=2,000) | 1,781 cells; 0 negative volumes; skew 2.17; non-ortho 16.66; surface-area dev 0.154% | S5 permanent quality gate; no card may regress it. |
| Face planarity of dual cells | unmeasured | Missing gate; Katz first-order risk applies directly to curved interior dual faces (`POLY-FVERR-PLANAR1`). |
| Face pairing / uniformity fx | unmeasured | The dominant FV shape drivers per Juretić; no checker measures them today. |
| Skew definition | unreconciled vs `psi = |m|/|d|` | "skew 2.17" cannot be compared to paper thresholds until `POLY-FVERR-SKEWDEF1`. |
| Patch semantics | single `defaultWall` | `dual.py:862` loses multi-patch/material mapping — blocks per-patch BL and real cases. |
| Cell-drop repair | present | `quality.py:369-432` may drop whole cells and manufacture holes; must be replaced by the no-drop contract. |
| Route attribution | ambiguous | `tier_native_poly.py` may route budgeted output through a hex base; benches must report which route ran. |
| Volume overfill (cube) | 1.026x after S4 smoothing | Residual of sliver-tet dual overestimation; repair-lane target. |
| Agglomeration leg | zero FV evidence | 5 DG/VEM-only full reads; survives only until `POLY-AGGLOM-CFD1` says otherwise. |

## 3. Card sequence

Effort: S ≈ 1 card-day, M ≈ 2-4, L ≈ 5+. Every card's acceptance additionally
requires: cube 4-invariant gates green, cylinder S5 quality gate green,
byte-identical repeat runs, and an explicit statement of which route produced
the measured mesh (tier_native_poly audit).

### Phase 0 — Gate calibration and measurement (report-only, no mesh change)

Cards: `POLY-FVERR-PLANAR1` [M] — per-face max deviation from area-weighted
best-fit plane, normalized by sqrt(area); reported for every poly/hex mesh,
gated only after fixtures quantify the dual cells' worst faces (Katz);
`POLY-FVERR-SKEWDEF1` [S] — conversion table our-skew ↔ OpenFOAM ↔ `psi`,
measured on the cylinder mesh; fail if not monotonically related (Juretić);
`POLY-FVERR-UNIFORMITY1` [S] — `fx` distribution per engine, fraction with
`|fx-0.5| > 0.1` (diffusion-order driver); `POLY-FVERR-FACEPAIR1` [S] —
per-cell face-pairing residual `min over pairings of sum|S_i n_i + S_j n_j| /
sum|S_i|`; confirms (or falsifies) that our duals score near hex, far from tet;
`POLY-QUALITY-HCHAR1` [S] — `h = 6V/A` per cell; catches pancake cells a volume
gate misses (PVEM); `POLY-QUALITY-UFBR1` [S] + `POLY-AGG-METRIC1` [S] — UF/BR
and CR/sphericity/volume-difference as report-only diagnostics (Antonietti
2022, MAGNET); `POLY-QUALITY-VECTOR1` + `POLY-VALIDITY-FIRST1` [M] — the
validity-first quality vector on analytic fixtures (Sorgente 2022); AR-gate
audit [S] — verify the current AR gate cannot reject aligned BL stretching
(Katz AR-1e6 evidence); relax to alignment-aware if it can.

Acceptance: zero mesh diffs anywhere; every metric lands in the evaluator
report with fixture-verified analytic values. Rollback: n/a (read-only).

Decision tree:
- If `POLY-FVERR-FACEPAIR1` shows our duals are NOT face-paired → the Juretić
  accuracy claim for polydual is downgraded and Phase 2 gains a face-pairing
  repair objective before any agglomeration work.
- If `POLY-FVERR-PLANAR1` finds warped faces beyond the Katz first-order
  threshold on the cylinder fixture → planarity becomes a hard gate and
  Phase 2's repair lane prioritizes face flattening/splitting over cell shape.
- If `POLY-FVERR-SKEWDEF1` finds non-monotone mapping → our skew gate is
  measuring something Eq. 22 does not predict; re-derive before citing 2.17.

### Phase 1 — Polydual main-generator hardening (topology/patch coverage)

Cards: `POLY-DUAL-CLASSIFY1` [M] — entity-classified primal-to-dual mapping so
multi-patch/multi-material fixtures preserve all geometric entity mappings
(fixes `dual.py:862` defaultWall loss — Garimella); `POLY-DUAL-POINT1` +
`POLY-STAR-VALID1` [M] — classified dual point placement + star-shaped
signed-subtet validity, zero invalid cells on convex and non-manifold fixtures
(Garimella); `POLY-NO-DROP-HOLES1` [M] — the repair contract: every accepted
repair preserves boundary components, patch ownership, owner-neighbor
consistency, and domain volume (retires `quality.py:369-432` cell-drop as a
repair primitive — Sorgente 2022); `POLY-FVERR-RANDPERT1` [L] — the Katz MMS
protocol on our meshes (perturb nodes 0-25%, 3+ refinement levels, scalar
Laplacian/advection) mapping our gate numbers to solution error — the first
native data point linking gates to accuracy.

Acceptance: multi-patch round-trip on sphere/cylinder + a 2-patch fixture;
star-validity 100% on the fixture set; RANDPERT1 confirms second-order
convergence for gate-passing meshes. Rollback: per-card transactional.
Evidence: Garimella 2013, Sorgente 2022, Katz 2011.

### Phase 2 — Repair lane (merge/split pair, FV-objective-directed)

Cards: `POLY-AGG-CONNSPLIT1` [S] FIRST — face-adjacency connected-component
guard on every grouping/merging step (MAGNET); `POLY-QUALITY-AGGLOM1` [M] —
node-preserving merge-with-best-neighbor for cells failing the h/star gate:
union with the neighbor maximizing agglomerate h, volume conserved to 1e-10,
boundary bit-identical (PVEM); `POLY-AGGLOM-KMEANSCUT1` [M] — deterministic
2-seed k-means cutting-plane split with vertex snapping (`diam*1e-3`),
small-edge/face rejection, bounded perturbation retry (Antonietti 2022);
`POLY-CONCAVE-SPLIT1` [M] — apply the k-means cut rule to Garimella's concave
boundary failure class; `POLY-DUAL-UNTANGLE1` [M] — condition-number
untangling for residual inverted subtets (Garimella).

Decision tree:
- Merge (`POLY-QUALITY-AGGLOM1`) is tried before split: it moves no nodes and
  is the cheaper transaction. Split handles what merge cannot (oversized or
  concave cells, which merging only worsens).
- If Phase 0 flagged face pairing or planarity as the weak axis, repair
  acceptance is judged on those FV metrics (decision 3), not on
  sphericity/BR — those remain diagnostic.
- If the cube 1.026x overfill persists after merge repair of sliver duals →
  escalate to interior-tet-vertex smoothing (the S4 mechanism) rather than
  inventing a new operator.

Acceptance: repaired meshes pass `POLY-STAR-VALID1` and the no-drop contract;
min(h) increases by the PVEM-observed order on the sliver-dual fixture; no
boundary node moves. Evidence: PVEM 2025, MAGNET 2025, Antonietti 2022,
Garimella 2013.

### Phase 3 — Agglomeration experiments (quality-gated secondary leg)

Cards: `POLY-AGGLOM-FACEGEOM1` [M] FIRST — every merged interface collapsed to
explicit polygonal faces and measured (facet-normal deviation, planarity,
non-ortho/skew); "union of facets" geometry above threshold is rejected or
split, never exported (Bassi — this card operationalizes the DG-vs-FV gap);
`POLY-AGGLOM-GRAPH1` + `POLY-AGGLOM-PAIR1` [M] — constrained adjacency graph +
union-quality pair energy (Sorgente 2023; 2D-DFN caveat recorded);
`POLY-AGGLOM-VSTAR1` [S] — greedy vertex-star agglomerator as deterministic
baseline; a measurement, not an endorsement (Pan-Persson);
`POLY-AGGLOM-RTREE1` [M] — R*-tree AABB candidate generator, connectivity
verified, benchmarked vs METIS on speed AND downstream FV-gate pass rate
(R3MG); `POLY-AGGLOM-SHAPE1` [M] — MGridGen-style two-phase agglomerator with
AR objective and per-cell budget (Bassi); `POLY-AGGLOM-LOOKAHEAD1` [M] —
beyond-pair unions (Sorgente 2023); `POLY-AGGLOM-CFD1` [L] — the decisive
preregistered CFD benchmark.

Decision tree:
- `POLY-AGGLOM-FACEGEOM1` gates the whole phase: if merged interfaces cannot
  meet the same FV thresholds dual cells meet on identical fixtures, the leg
  drops to reference-only *without* running the remaining cards.
- Candidate generators (VSTAR1/RTREE1/SHAPE1/GRAPH1) compete on the FACEGEOM1
  FV metrics; keep at most one default (avoid unexercised complexity).
- `POLY-AGGLOM-CFD1` failure ends the leg permanently (gap-search verdict);
  success caps it as a cell-budget reducer under the hard gates.

Evidence: Bassi 2012, Pan 2022, R3MG 2025, Sorgente 2023,
`gap_search_3d_agglomeration.md`.

### Phase 4 — Route-1 conforming Voronoi + CVT lane (long-term, independent)

Cards: `POLY-VOROCRUST-PROTECT1` + `POLY-VOROCRUST-SEEDPAIR1` [L] — stratum-aware
ball protection + paired surface seeds; conforming unclipped Voronoi boundary
passes topology, label, and two-sided fidelity gates (Abdelkader 2020);
`POLY-VOROCRUST-SLIVER1` + `POLY-VOROCRUST-EDGE1` [M] — half-covered-pair
elimination + minimum interior edge control; `POLY-CVT-DENSITY1` [M] —
density-graded interior sampling `rho = h^-alpha`, alpha swept in {3..6}
(1D theory gives 3; 3D uncalibrated — Du 1999); `POLY-CVT-LLOYD1` [M] —
frozen-boundary interior Lloyd with monotone-energy assert, centroid
containment, boundary-face bit-identity, full rollback (Du 1999; replaces the
`voronoi.py:1017-1149` fake Lloyd).

Decision tree:
- PROTECT1/SEEDPAIR1 are the entry: without a conforming boundary the CVT
  cards optimize a lattice that the snapping bug then corrupts. No CVT card
  lands on the current snapped-Voronoi code.
- If no alpha beats uniform sampling on the bench grades → `POLY-CVT-DENSITY1`
  is falsified for our fixtures and recorded as such (its own pass criterion).
- Route-1 promotion to default is decided only after it beats polydual on the
  Phase 0 FV metrics (face pairing, planarity, fx) on the same fixtures.

### Phase 5 — Correlation and weights (closes the loop)

Cards: `POLY-QUALITY-CORRELATE1` [L] — preregistered CFD benchmarks justify
the quality-vector weights (Sorgente 2022's VEM correlation replaced by our
own FV data from `POLY-FVERR-RANDPERT1` + `POLY-AGGLOM-CFD1`). Entry: Phases
0-2 closed. Output: calibrated gate thresholds with measured error backing —
the first time any native engine's gates are solver-correlated.

## 4. Invariant compliance table

Boundary motion must be NO (poly inherits the surface-preservation invariant;
route-1 boundary seeds are frozen by construction).

| Card (family) | Moves boundary vertices? | Changes cell count? | Determinism risk |
| --- | --- | --- | --- |
| POLY-FVERR-* (5) | No (read-only metrics; RANDPERT1 perturbs test copies only) | No | None |
| POLY-QUALITY-HCHAR1 / UFBR1 / AGG-METRIC1 | No (report-only) | No | None |
| POLY-QUALITY-VECTOR1 / VALIDITY-FIRST1 | No | No | None |
| POLY-DUAL-CLASSIFY1 / POINT1 / STAR-VALID1 | No (dual-point placement is interior/entity-constrained) | No | Low (classification order pinned) |
| POLY-NO-DROP-HOLES1 | No | Contract card: forbids silent cell drops | None |
| POLY-AGG-CONNSPLIT1 | No | Yes (splits disconnected proposals) | Low (hash-map order pinned) |
| POLY-QUALITY-AGGLOM1 | No (node-preserving by definition) | Yes (merges) | Low (greedy tie-break pinned) |
| POLY-AGGLOM-KMEANSCUT1 / CONCAVE-SPLIT1 | No (vertex snapping is interior; seeded deterministic) | Yes (splits) | Low (fixed seed, bit-identical rerun is a pass criterion) |
| POLY-DUAL-UNTANGLE1 | No (interior dual points only) | No | Low |
| POLY-AGGLOM-GRAPH1 / PAIR1 / LOOKAHEAD1 / VSTAR1 / RTREE1 / SHAPE1 / FACEGEOM1 | No | Yes (merges, budgeted) | Low-medium (priority queues need pinned tie-breaks) |
| POLY-AGGLOM-CFD1 | No (benchmark only) | No | None |
| POLY-VOROCRUST-* (4) | No (boundary defined by protected seed pairs, not moved) | Yes (seed count) | Low (sampling seeded) |
| POLY-CVT-LLOYD1 | No (interior seeds only; boundary-face bit-identity is a pass criterion) | No (seed count fixed) | Low (float summation order pinned) |
| POLY-CVT-DENSITY1 | No | Yes (seed count from density) | Low (seeded sampling) |
| POLY-QUALITY-CORRELATE1 | No | No | None |

## 5. What we will NOT do

- **Raw ML/GNN agglomeration** — MAGNET's own results show the GNN quality
  margin over METIS/k-means is essentially zero, 3D PDE validation is absent,
  and agglomerates arrive disconnected (`magnet2025_gnn_agglomeration.md`).
  ML stays advisory-only per the Antonietti template: ML picks a branch,
  deterministic code gates it (`antonietti2022_ml_agglomeration.md`).
- **R3MG as a mesh generator** — it is a multigrid-hierarchy builder; its
  output is a labeling plus a tree, with unmerged fine facets and hanging
  nodes; merged owner-neighbor faces are never constructed
  (`r3mg2025_rtree_agglomeration.md`). Candidate-generator use only.
- **Transferring DG/VEM shape tolerance to FV gates** — Bassi's admissibility
  bar is connectedness alone; PVEM's shape tolerance exists *because* VEM
  stabilization absorbs badness FV cannot (`bassi2012_agglomeration_dg.md`,
  `pvem2025_polytopal_vem.md`: "do NOT relax FV gates on this evidence").
- **Voronoi-only route as near-term default** — current snapping invalidates
  the orthogonal-dual contract (`voronoi.py:2128-2160` audit) and VoroCrust
  needs faithful watertight input, degrades at sharp features
  (`vorocrust2020_without_clipping.md`). Long-term lane, Phase 4.
- **Hardening the AR gate** — Katz proves AR up to 1e6 is acceptable for
  aligned BL cells; Juretić explicitly does not analyze AR. An AR gate that
  rejects aligned stretching is a calibration bug, not rigor
  (`katz2011_mesh_quality_cfd_accuracy.md`).
- **Optimizing generic shape beauty** — sphericity/BR/CR are diagnostics; FV
  error follows face pairing, planarity, uniformity, non-ortho, skew
  (decision 3). Effort spent rounding cells that already pass FV gates is
  deleted, not shelved (THINSLIVER2 precedent, ROADMAP.md).
- **Cell dropping as repair** — `quality.py:369-432` can manufacture holes;
  `POLY-NO-DROP-HOLES1` retires it (`sorgente2022_quality_indicator.md` row).
- **Claiming CVT convergence or optimal cell shapes** — no Lloyd convergence
  proof exists in N>=2, converged states can be saddles, Gersho's conjecture
  is open in 3D (`du1999_cvt_review.md`). Guards + rollback, never proofs.
- **Citing paper thresholds before definition reconciliation** — the skew-unit
  mismatch (`POLY-FVERR-SKEWDEF1`) blocks any "paper says X is safe" argument.

## 6. Measurement-first protocol

Per ROADMAP's method note ("measure before planning — guessing refuted 4+
times"), every phase opens with measurement; no mechanism lands on a stale
baseline:
- Phase 0 *is* the measurement phase: it exists because the gate audit found
  the checker measuring the wrong things (missing planarity, unreconciled
  skew) — fixing the ruler before using it.
- Phase 1 opens by re-running the canonical smoke
  (`scripts/smoke_native_poly.py`) plus the new Phase 0 metrics on
  cube/sphere/cylinder, and recording which route produced each mesh
  (tier_native_poly hex-base routing audit).
- Phase 2 opens by counting cells failing the h/star/planarity gates per
  fixture — the repair lane's target population — before any operator lands.
- Phase 3 opens with `POLY-AGGLOM-FACEGEOM1` in diagnostic mode: measure FV
  metrics on merged interfaces before any generator competes.
- Phase 4 opens by measuring the current Voronoi path's boundary fidelity and
  dual-orthogonality against the audit findings, establishing the "before"
  for the VoroCrust rebuild.
- Phase 5 is itself the correlation measurement.

Canonical fixtures: cube.stl (4-invariant permanent gates), sphere/cylinder
N=2,000 (S5 permanent quality gate: cylinder 1,781 cells, 0 negative volumes,
skew 2.17, non-ortho 16.66, 0.154% surface-area deviation), plus a 2-patch
fixture added in Phase 1 for `POLY-DUAL-CLASSIFY1`. Every card stores
before/after evidence against the phase's opening measurement, uses relative
(never absolute) guards, and is reverted whole on any permanent-gate failure.
