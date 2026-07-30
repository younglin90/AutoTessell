# Native Hex Quality: Literature-Integrated Development Plan

Date: 2026-07-23
Status: implementation plan, not a solved-quality claim
Primary target: continue native_hex (~45%, ROADMAP.md A-2) past its three open fronts —
post-snap boundary skew (2.84 vs gate ≤ 3.0), the unproven all-hex claim of the
adaptive octree transitions, and the missing truthful cell census — using the card
ledger in `evidence_matrix.md` (8 FULL_READ papers + forward sweep), without
violating the wall-fit surface contract (fine wall_dev_max 0.008 vs gate < 0.02).
Evidence base: `evidence_matrix.md`, `forward_citation_sweep_2026-07-23.md`,
per-paper notes cited inline (all in `docs/references/literature/native_hex/`).

## 1. Executive decision

1. **Three lanes, ordered honesty → quality → topology.** (1) The *honesty lane*
   (truthful census) goes first: read-only, cheap, and every later claim depends on
   it — HEX-HD-1/HEX-OCT-1 counts (`gao2017_field_guided_agglomeration.md`,
   `marechal2009_octree_all_hex.md`) plus HEX-HD-5 ScoreCHE/cluster distribution
   (`chen2026_hex_quality.md`). (2) The *post-snap quality lane* attacks the
   measured bottleneck (boundary skew 2.84): surface-constrained optimization is
   the exact shape of our problem — HexOpt maximizes scaled Jacobian **while
   constraining surface points to stay on the input triangle mesh** (augmented
   Lagrangian); Edge-Cone Rectification is the canonical positive-Jacobian
   post-pass (`forward_citation_sweep_2026-07-23.md` section 2, both P0 OPEN).
   (3) The *octree-template lane* resolves the all-hex transition question:
   the Livesu 2022 dual schemes (the actual template paper: 20 transitions, 8+5
   atomic schemes, CinoLib MIT) + a pairing stage replace Zhang 2013 as the
   candidate; Pitzalis 2021 is the pairing ILP *preprocessing* (minimal extra
   refinement, 2.1x vs 3.3x growth), not the templates
   (`pitzalis2021_generalized_adaptive_refinement.md` correction). Livesu 2022
   decides when all-hex may even be claimed (HEX-OCT-2 decision input).
2. **Four P0 full reads are Phase-0-adjacent tasks, before their cards can be
   implemented.** Pitzalis 2021, Edge-Cone Rectification 2015, HexOpt, and Gao 2019
   are all OPEN access (`forward_citation_sweep_2026-07-23.md` access column); no
   user download needed. No mechanism lands until its FULL_READ note exists — the
   Knupp full read already corrected a sweep-level subsumption claim
   (`evidence_matrix.md`), proving screening-level adoption is unsafe.
3. **Sheet operations are the surgical fallback of the quality lane, not its main
   path.** Ledoux & Shepherd 2010 proves sheet extraction, pillowing, and chord
   collapse all-hex-preserving by construction with exact preconditions, but zero
   geometric guidance (`ledoux2010_sheet_operations.md`, Decision). HEX-SHEET-1
   (extract a worst wall-adjacent sheet) runs only when optimization stalls AND
   the bad cells form one coherent sheet; its stop rule redirects scattered-skew
   cases to chord collapse or relaxation.
4. **The negative-volume gate is hardened to a margin, not just a sign.** Knupp
   2001's survivals: a volume-scaled beta positivity margin, and persistent
   untangler failure implicating connectivity, not the optimizer
   (`knupp2001_untangling.md`, HEX-UNTANGLE-1). Falsifiable: if every passing mesh
   already clears any reasonable beta, the card closes as "margin already implicit".
5. **HEXHOOP is rejected; its cost gate survives.** ~49-60x cell multiplication,
   systematic ~0.4 scaled-Jacobian mode, patent-pending flag, wrong input class
   (`yamakawa2002_hexhoop.md`, Verdict). What survives is HEX-ALLHEX-1: any future
   all-hex conversion must report multiplication < 8x and no secondary SJ mode
   below 0.5, with provenance-split histograms — bounds HEXHOOP cannot meet.
6. **Feature preservation follows Gao 2019, whose code is vendored in-repo**
   (`Feature-Preserving-Octree-Hex-Meshing/`, verified via git remote —
   `forward_citation_sweep_2026-07-23.md`). Its feature-curve snapping with
   positive-SJ-by-construction is the strongest published answer to the
   ridge/corner provenance card (P1, `evidence_matrix.md`); primary-source diffs
   against the vendored code replace guesswork.
7. **Hex-dominant honesty is a reporting contract, not a quality pass.** The census
   (HEX-HD-1 counts + HEX-HD-5 QHED/ScoreCHE) reports *how much* hex and *how
   usefully distributed* — it never gates generation. Chen 2026's own pipeline
   (B-rep input, commercial CAD kernel, hour-scale PSO) is explicitly not ported
   (`chen2026_hex_quality.md`).
8. **The two-engine architecture decision stands.** `octree_hex_dominant` is
   production near-term; `field_hex_dominant` (HEX-HD-2/3) stays research/
   medium-term; `octree_all_hex` is optional and only after proof
   (`evidence_matrix.md`, Architecture decision). Frame-field/CubeCover is rejected
   as the next production path (`nieser2011_cubecover.md`).
9. **BL all-hex claims route through pillowing.** The auto BL route may add prism
   cells, invalidating any pre-BL hex claim (`evidence_matrix.md`, BL row). Ledoux
   pillowing (HEX-SHEET-2) is the provably all-hex-preserving per-patch
   layer-insertion primitive; post-BL output is re-classified by the census
   (falsification rule: pre-BL hex dominance is never carried forward).
10. **No card claims a theoretical guarantee.** Ledoux is topology-only; HEXHOOP's
    validity is topological plus experimental; QHED is descriptive, not a validity
    gate; Knupp gives no positivity bound. All acceptance is by measurement.

## 2. Current measured bottleneck

Numbers from `ROADMAP.md` A-2 native_hex (~45%) and the `evidence_matrix.md` audit:

| Quantity | Value | Source / consequence |
| --- | ---: | --- |
| cube solid gates | surface 6.000 / void 0.000 / vol 1.000 / degen 0, skew 3.6e-16 | Permanent gates, green — the solid-preservation baseline every card must keep. |
| cylinder wall_dev_max | standard 0.0032 (from 0.0466); fine 0.008 (from 0.0353), gate < 0.02 | Per-vertex wall-fit snap + partial backtracking (largest t* passing the unmodified guard); the wall-fit contract the quality lane must not break. |
| post-snap boundary skew | 2.84, gate ≤ 3.0 | After freezing surface vertices and relaxing free interior vertices of flagged sliver cells (from 4.64). Headroom 0.16 — the quality lane's target is to push this down, not merely hold the gate. |
| negative_volumes | 0, gated both quality levels | Fine's undetected 8 dropped to 0 as a bonus of the interior relaxation; HEX-UNTANGLE-1 upgrades this gate to a beta margin. |
| cell-type census | absent | Adaptive result reports count + generic quality only; `test_native_hex_sphere_produces_only_hexahedra` uses an indirect face-count check — its name overstates its assertion (`evidence_matrix.md`). |
| adaptive transitions | conforming polyhedral, NOT proven all-hex | Split coarse faces via generic writer; the all-hex route, if pursued, is Pitzalis 2021, not template conversion (`evidence_matrix.md`, engine audit). |
| BL linkage | auto route may add prisms; `extrude_hex_bl` test-only | All-hex claim invalid after BL until re-classified. |
| ridge/corner provenance | partial geometric snap; provenance/topology absent | Gao 2019 feature-curve snapping is the published answer; vendored code available. |

## 3. Card sequence

Effort: S ≈ 1 card-day, M ≈ 2-4, L ≈ 5+. Lane order follows ROADMAP's stated next
step ("further skew reduction, then extend solid-preservation methodology to
poly"): quality lane before octree-template lane. Every card's acceptance
additionally requires: all native_hex permanent gates green (cube solid gates,
cylinder wall_dev_max < 0.02 both levels, boundary skew ≤ 3.0, negative_volumes = 0
both levels), byte-identical repeat runs.

### Phase 0 — Honesty lane: census + gate hardening + P0 reads (no mesh-output change)

Cards: **HEX-HD-1 / HEX-OCT-1** [S] — truthful cell-type census (six quad faces =
hex, else polyhedron by face count; report `hex_count`, `poly_count`,
`hex_volume_fraction`, counts sum to written cells —
`gao2017_field_guided_agglomeration.md`, `marechal2009_octree_all_hex.md`);
**HEX-HD-5** [S] — ScoreCHE + hex-cluster BFS over hex-hex shared faces
(`score_che`, `n_hex_clusters`, `largest_cluster_frac`; all-hex cube must score
1.0 / 1 cluster — `chen2026_hex_quality.md`); **HEX-UNTANGLE-1** [S] — beta-margin
gate (`min corner Jacobian >= beta * local mean cell volume`, local not global
Vbar, report-first then gate — `knupp2001_untangling.md`); **adaptive generic-cell
validity** [M] — zero negative volume/self-intersection, closed cell shells, face
owner count 1/2 (`evidence_matrix.md` ranked P0).

Phase-0-adjacent reading tasks — **COMPLETE (2026-07-24)**: FULL_READ notes
`gao2019_feature_octree_hex.md`, `pitzalis2021_generalized_adaptive_refinement.md`,
`livesu2022_optimal_dual_schemes.md`, `livesu2015_edge_cone_rectification.md`,
`tong_hexopt.md`; cards HEX-ECR-1..4 / HEXOPT-IMPL-1..3 / HEXOPT-REFINE-1
ledgered in `evidence_matrix.md`; implementation unblocked.

Acceptance: zero mesh diffs anywhere; census + margin reports stored as bench
evidence; expected result recorded honestly — transition cells classify non-hex,
pulling ScoreCHE below 1.0 (`chen2026_hex_quality.md`). Rollback: n/a (read-only).

### Phase 1 — Post-snap quality lane (boundary skew 2.84 → down)

Wave 0, measurement [S]: skew concentration map — does residual skew concentrate
in one wall-adjacent sheet or scatter across layers? Partitions the lane per
HEX-SHEET-1's stop rule (`ledoux2010_sheet_operations.md`), deciding
optimization-vs-surgery before either is written.
Wave 1 [M-L]: surface-constrained optimization — the ECR 2015 / HexOpt pair
(FULL_READ done), compared against each other before either is ported;
HEX-ECR-1/HEX-ECR-4 diagnostics run before any solver code. Contract (corrected
per HEXOPT-REFINE-1, `tong_hexopt.md`): surface vertices move only *on the input
surface* — HexOpt's augmented-Lagrangian constraint is sliding closest-point,
targets recomputed each iteration, not fixed wall-fit targets; bench both frozen
and sliding lanes, wall_dev gates (checked at stage convergence) as hard veto.
HEX-UNTANGLE-1's beta margin is the acceptance floor; per Knupp's diagnostic rule,
persistent failure is a topology signal routed to wave 2, not to optimizer tuning.
Wave 2 [M], surgical fallback: **HEX-SHEET-1** sheet extraction (seed-edge
traversal + simultaneous collapse + geometric-feature guard — never merge nodes
classified on different curves/patches) deletes a worst wall-adjacent layer; chord
collapse (quality tiebreak for its non-determinism) is the narrower alternative
(`ledoux2010_sheet_operations.md`).

Decision tree:
- Wave 0 says sheet-coherent AND wave 1 stalls → wave 2 extraction; scattered →
  extraction is the wrong tool, stay in wave 1 or accept the plateau.
- ECR-vs-HexOpt: keep only one unless stacking is additive on the bench
  (unexercised complexity is deleted — THINSLIVER2 precedent, ROADMAP.md).
- A candidate that improves skew but moves wall_dev_max at all → rejected
  permanently, not tuned (the wall-fit contract is the product's #1 invariant).
- HEX-SHEET-1 output census not 100% hex on all-hex input → Ledoux preconditions
  were violated; revert whole, file as a bug.

Acceptance: boundary skew strictly decreases; census re-run post-repair; all gates
green. Evidence: `ledoux2010_sheet_operations.md`, `knupp2001_untangling.md`,
sweep section 2.

### 2026-07-24 wave 0 result (measured, no code change)

Cylinder fine, 1781 hex, pre-BL: boundary skew max `3.208651` (p50 `0.825`,
p90 `2.237`, p95 `2.860`, p99 `3.192`); 85/676 side faces at skew ≥ 2.0,
spread across **14 disconnected connected components** — not a single
coherent sheet. Decision per the tree above: scattered → extraction is the
wrong tool; **wave 1 (ECR/HexOpt surface-constrained optimization) is the
recommended path, not HEX-SHEET-1.**

Correction to ROADMAP.md's "boundary skew 2.84 (permanent gate ≤3.0)": that
number is `standard` quality only (confirmed by exact reproduction:
`2.840553147`), not a general fine-quality gate. Fine quality's boundary skew
was never separately measured or gated before this audit — ROADMAP's fine-row
only tracked internal skew and negative-volume-count. `3.208651` is a new
measurement, not a regression. Fine now needs its own boundary-skew gate once
wave 1 lands a fix; until then this is an open (not broken) number.

### 2026-07-24 wave 1 result (measured, no code change) — ECR/HexOpt hypothesis refuted for direct porting

- `HEX-ECR-1` (cone-feasibility census on the 85 bad-skew side faces):
  0/85 have an infeasible cone contact, only 5/85 are near-tight. ECR's
  mechanism (edge-cone containment repair) targets cone violations that our
  bad faces mostly do not have — **most of these faces are not cone-infeasible,
  just angularly poor within otherwise-valid geometry**. Direct ECR porting
  would have little to fix here.
- `HEX-ECR-4` (MSJ-vs-OpenFOAM-skew correlation, cylinder fine): overall
  Spearman ρ = -0.8809, boundary-only ρ = -0.7972 (both strong, expected
  sign). **But boundary worst-tail overlap = 0%** — the faces MSJ would flag
  as worst and the faces our skew gate flags as worst are two different sets.
  Optimizing MSJ (what ECR/HexOpt actually drive) would not reliably improve
  our specific worst-skew cells.
- **Verdict: do not port ECR/HexOpt as-is.** Both diagnostics point away from
  a clean match between the literature mechanism and our failure mode.
  Porting on top of this evidence would be exactly the "unexercised complexity"
  pattern this plan forbids (THINSLIVER2 precedent). Blocking issue: only one
  shape (cylinder) has been benchmarked — before discarding the ECR/HexOpt
  route entirely, wave 1 needs ≥3 hard-hex shapes with the same ECR-1/ECR-4
  diagnostics run to confirm the mismatch isn't cylinder-specific. Wave 2
  (HEX-SHEET-1 surgical extraction) is not automatically promoted either —
  the wave-0 scattered-not-coherent finding still argues against it. Next
  step is more diagnostic coverage, not a mechanism choice yet.

### 2026-07-24 wave 1 extended result (4 shapes, no code change) — conclusion finalized

Extended ECR-1/ECR-4 to cylinder, sphere, bracket, gear. Cone-feasibility and
the OpenFOAM-worst-face-vs-cone-infeasible overlap vary sharply by shape:
sphere and bracket show high overlap (24/24, 19/19), cylinder and gear show
zero (0/8, 0/0). Correlation is shape-dependent too — Spearman ranges
-0.886 (cylinder) to -0.476 (gear); pooled worst-5% Jaccard overlap is only
13.1% (per-shape: 23.6/32.4/10.4/5.0%).

**Conclusion, now evidence-backed across 4 shapes, not just cylinder: ECR/MSJ
signals are useful diagnostics but are not a portable cross-shape gate or
solver objective. Direct ECR/HexOpt porting stays off the table.** The
mismatch is not cylinder-specific — it is a real property of MSJ-style
objectives vs our OpenFOAM skew metric across diverse hex geometry. Wave 1
(surface-constrained optimization) is closed as "diagnosed, not adopted."
Next candidate for the post-snap quality lane needs a different mechanism
than ECR/HexOpt's MSJ objective, or a shape-specific dispatch (since sphere/
bracket DO show high overlap — an MSJ-based approach might still work for
that subset even though it fails for cylinder/gear). Revisit wave 2
(HEX-SHEET-1) given wave 1's mechanism is now closed, not merely paused.

### 2026-07-25 shape-adaptive dispatch ruled out — literature gap identified

Tested whether transition-cell density or feature-edge density predicts
ECR/cone-infeasible overlap (the sphere/bracket-vs-cylinder/gear split).
Neither does: gear has the highest transition-cell proxy (65.5%) and
feature-edge ratio (37.9%) of all four shapes, yet its ECR overlap is 0% —
the same as cylinder (9.0% transition, 33.3% feature, also 0% overlap) and
opposite of sphere (49.4%/0%/high-overlap) and bracket (47.3%/33.7%/
high-overlap). No curvature- or feature-density-based predictor survives
this data; a shape-adaptive ECR dispatch is not evidence-backed and is
dropped.

**Wave 1 (ECR/HexOpt) and wave 2 (HEX-SHEET-1, weakened by wave 0's
scattered-not-coherent finding) are both closed for the post-snap quality
lane as currently scoped.** Bad-face topology data (isolated singletons for
cylinder/sphere/gear; 7 components across 6 patches for bracket) suggests the
damage is tied to octree transition-sheet geometry and feature/curve/corner
provenance, not generic hex shape optimization. **New literature is needed**,
targeted specifically at: (a) quality repair for octree adaptive-transition
sheets (as opposed to generic hex untangling), (b) feature/curve/corner
provenance-aware post-snap correction. This is a snowball task, not an
implementation task — do not resume Phase 1 implementation until this gap
is read.

### 2026-07-25 gap search complete, two full-reads in progress

`gap_search_transition_sheet_provenance_2026-07-25.md` screened 19 papers;
P0: Elsheikh 2014 (octree transition preconditioning), Chen 2026 (CJA,
hanging-node transition quality control — distinct from the already-read
Chen 2026/EwC QHED paper), and a since-confirmed duplicate (the "HexOpt 2026"
DOI resolves to the already-FULL_READ `tong_hexopt.md` arXiv preprint — no
re-read needed). Saturated (2 consecutive rounds, no new mechanism). Elsheikh
2014 full-read verdict: it is a **pre-pass** (generation-stage refinement-field
conditioning), not a post-snap repair — a competing mechanism to
Zhang2013/Pitzalis2021/Livesu2022 in the octree-template lane (Phase 2), not
a Phase 1 post-snap fix. Chen 2026 (CJA) full-read verdict: directly
demonstrates ungated hanging-node subdivision collapsing orthogonality
0.088→7.93e-13 on a pure-hex case, and a quality-gate-with-isotropic-fallback
(τw=0.6, τs=0.75, τa=15) recovering ~4x the floor — the gate *pattern* is
portable even though the underlying mechanism is edge-bisection refinement of
an existing mesh, not octree-from-scratch generation. `HEX-TRANS-2`
(diagnostic: cross-tabulate our bad-face population against hanging-node
adjacency to confirm the damage actually concentrates there) is the cheapest
next step before investing in a quality-gate implementation.

### Phase 2 — Octree-template lane (transition contract, HEX-OCT-2)

Cards: **HEX-OCT-2 decision** [M] — reads done; the notes recommend Option A in a
two-stage form: the core is the Livesu 2022 8+5 atomic dual schemes + dualization
(CinoLib MIT — this alone secures the all-hex proof), with pairing first via the
octree rule (OP+WB, growth 2.9x) and the Pitzalis 2021 ILP (GP+WB, 2.1x) as a
later optimization, not a correctness requirement. Our engine currently has **no
pairing check/refinement stage** — until one exists, no dual-scheme all-hex claim
is admissible (balanced+paired is the judgment rule,
`livesu2022_optimal_dual_schemes.md`). Option B retains split-face polyhedra and
formally advertises hex-dominant with hex ratio + ScoreCHE as quality metrics;
Option B is never described as all-hex (`marechal2009_octree_all_hex.md`;
`evidence_matrix.md` falsification rules).
**HEX-OCT-3** [M] — surface intersection + local thickness refinement (no vanished
thin component; two cells across thickness when budget permits; explicit budget
failure — `evidence_matrix.md` ranked P0). **HEX-ALLHEX-1** [S, standing gate] —
any proposed conversion: multiplication < 8x, no secondary SJ mode < 0.5,
provenance-split histograms (`yamakawa2002_hexhoop.md`).

Decision tree:
- Pitzalis read confirms applicability → Option A prototype on adaptive cube /
  L-shape / two-level corner (six quad faces per cell, two owners per internal
  face, positive Jacobian samples); census must read 100% hex, HEX-ALLHEX-1 bounds
  must hold.
- Read reveals a blocker (grid class mismatch, cell-count blowup vs ranked gates)
  → Option B is declared, documentation updated, ScoreCHE becomes the permanent
  distribution metric; the all-hex target moves to the optional `octree_all_hex`
  engine (Architecture decision, `evidence_matrix.md`).
- HEXHOOP-class conversion is never the fallback (rejected, section 5).

### Phase 3 — Feature preservation (ridge/corner provenance)

Cards: **provenance card** [M-L] (ranked P1, `evidence_matrix.md`) — stable
face/ridge/corner provenance per boundary entity, implemented as a primary-source
diff against the vendored Gao 2019 code (`Feature-Preserving-Octree-Hex-Meshing/`);
**HEX-OCT-4** [M] — constrained projection transaction (trial move + line search,
commit only on local validity + quality floor; 30-degree ridge, cube corner,
curved wall — `marechal2009_octree_all_hex.md`).

Decision tree: if Gao 2019's snapping conflicts with our partial-backtracking snap
(t* mechanism, ROADMAP.md), the existing measured mechanism wins — never replace a
measured permanent-gate mechanism with an unmeasured port. Acceptance: ridge/corner
tests keep target identity through all snap iterations; all gates green.

### Phase 4 — BL contract (all-hex layers)

Cards: **HEX-SHEET-2** [M-L] — pillowing as the per-patch BL primitive: verify the
manifold quad set (reject non-manifold selections with a diagnostic), inflate to
hexes, place nodes at first-layer height; every wall-adjacent hex has exactly one
boundary face; skew gate holds after one relaxation pass
(`ledoux2010_sheet_operations.md`); **hex/BL contract** [S] (ranked P1) — the auto
route either explicitly returns mixed cells or uses the pillowing path; post-BL
type ratios re-reported by the census (falsification rule: classify again).

Known risk: the paper guarantees topology only; a thin first layer will re-create
high skew unless relaxation treats the pillow layer anisotropically
(`ledoux2010_sheet_operations.md`, HEX-SHEET-2 risk clause). Repeated pillowing =
multi-layer BL, unblocking the per-patch BL product item.

### Phase 5 — Field-guided hex-dominant (research lane, deferred)

Cards: **HEX-HD-2** [L] (topology transaction kernel, face-circle/cell-sphere
invariants per accepted edit), **HEX-HD-3** [L] (orientation/position field
prototype: deterministic cube/tube/torus, decreasing energy, boundary alignment),
**HEX-HD-4** (geometric validity beyond topology) —
`gao2017_field_guided_agglomeration.md`, ranked P2. Entry: Phases 0-2 closed; this
is the `field_hex_dominant` engine and never blocks the production lane.
CubeCover-like global parameterization stays P3 research (`evidence_matrix.md`).

## 4. Invariant compliance table

Boundary motion must be NO or on-wall-fit-target-surface only with wall_dev veto
(wall-fit contract, ROADMAP.md A-2).

| Card | Moves boundary vertices? | Changes cell count? | Determinism risk |
| --- | --- | --- | --- |
| HEX-HD-1 / HEX-OCT-1 / HEX-HD-5 | No (read-only census + metrics) | No | None (BFS order pinned) |
| HEX-UNTANGLE-1 | No (gate criterion only) | No | None |
| adaptive generic-cell validity | No (checks + transactional revert) | No (reverts only) | None |
| P0 reading tasks / wave-0 skew map | No (docs / measurement only) | No | None |
| ECR/HexOpt-style optimization | Constrained-to-surface only (augmented-Lagrangian on input triangles); wall_dev veto | No | Medium (solver iteration order must be pinned) |
| HEX-SHEET-1 | No (collapse merges respect curve/patch classification guard) | Yes (removes one sheet) | Low (seed-edge traversal order fixed) |
| chord collapse fallback | No | Yes (removes one chord) | Medium (needs quality tiebreak — Ledoux notes the non-determinism) |
| HEX-OCT-2 Option A (Livesu 2022 schemes + pairing) | No (scheme instantiation pre-snap) | Yes (scheme subdivision, bounded vs ranked gates) | Low (canonical signatures under cube symmetry) |
| HEX-OCT-3 | No | Yes (refinement, budget-capped, explicit failure) | Low |
| HEX-ALLHEX-1 | n/a (standing gate) | n/a | None |
| provenance card (Gao 2019) | Snap-target identity only; motion stays inside existing guarded snap | No | Low |
| HEX-OCT-4 | Trial move + line search, commit on validity; wall_dev veto | No | Medium (line-search ties) |
| HEX-SHEET-2 (pillowing) | No (new layer inserted; existing boundary nodes keep targets) | Yes (one hex per selected quad) | Low (manifold set is deterministic) |
| hex/BL contract | No | No (reporting/routing) | None |
| HEX-HD-2/3/4 | No (research lane, transactional) | Yes (agglomeration) | Medium (field init seeding must be pinned) |

## 5. What we will NOT do

- **HEXHOOP conversion of hex-dominant output** — ~49-60x multiplication, systematic
  ~0.4 SJ mode, patent-pending, wrong input class for polyhedral transitions;
  Pitzalis 2021 strictly dominates for the grid case (`yamakawa2002_hexhoop.md`).
  Only the HEX-ALLHEX-1 cost gate survives.
- **Frame-field / CubeCover as the next production path** — long-term research;
  manual meta-mesh and possible flipped parameterization make it unsuitable as
  automatic default (`nieser2011_cubecover.md`, `evidence_matrix.md`). Field work
  stays in the deferred Phase-5 research lane.
- **Chen 2026 generation pipeline** — B-rep input, commercial CAD kernel, hour-scale
  PSO; only the QHED/ScoreCHE metric is adopted (`chen2026_hex_quality.md`).
- **Any boundary-vertex-moving optimization that violates the wall-fit contract** —
  surface vertices move only on their wall-fit target surface, wall_dev gates as
  hard veto; a card trading wall_dev for skew is rejected permanently, not tuned
  (ROADMAP.md wall-fit snap record).
- **Claiming all-hex from method names or indirect checks** — 2:1 balance,
  manifoldness, and hex ratio never substitute for the census; code comments never
  establish equivalence (`evidence_matrix.md` falsification rules; the sphere
  test's overstated name is the standing example).
- **Carrying pre-BL hex dominance past BL** — post-BL output is re-classified,
  always (`evidence_matrix.md` falsification rules).
- **Implementing screened-but-unread P0 papers** — the Knupp read overturned part
  of the sweep's subsumption claim; ECR/HexOpt/Pitzalis/Gao-2019 cards wait for
  their FULL_READ notes (`evidence_matrix.md`).
- **Citing Ledoux 2010 as evidence pillowing/extraction improves skew** —
  topology-only theory; quality claims must come from our own HEX-SHEET-1/2
  measurements (`ledoux2010_sheet_operations.md`, Decision).
- **Keeping mechanisms with zero measured effect** — THINSLIVER2 precedent
  (ROADMAP.md): unexercised complexity is deleted, not shelved.

## 6. Measurement-first protocol

Per ROADMAP's method note ("measure before planning — guessing refuted 4+ times"),
every lane opens with a measurement card; no mechanism lands on a stale baseline:
- Phase 0 *is* the measurement phase: census + ScoreCHE + beta-margin reports
  establish the truthful baseline (transition cells expected to classify non-hex).
- Phase 1 opens with the wave-0 skew concentration map; optimization-vs-surgery is
  decided by that measurement, not preference. Each ECR/HexOpt candidate is
  measured alone against the Phase-0 baseline before stacking.
- Phase 2 opens by measuring transition-cell counts, hex fraction, and ScoreCHE on
  the adaptive bench cases, so Option A's cell-count growth is judged against
  measured numbers (`batch2_core_papers.md` Adaptivity gate).
- Phase 3 opens by measuring ridge/corner target-identity loss on the current snap
  before porting Gao 2019.
- Phase 4 opens by measuring post-BL cell-type ratios on the current auto route —
  the honest mixed-cell number the pillowing path must beat.
- Phase 5 opens with the deterministic HEX-HD-3 field tests before agglomeration.

One canonical measurement script per geometry (ROADMAP method); benches:
`tests/verify_goal.py`, `tests/bench_quality_matrix.py`, the native_hex solid-gate
suites on cube/cylinder (surface 6.000 / void 0.000 / vol 1.000, wall_dev_max
< 0.02, skew ≤ 3.0, negative_volumes = 0). Every card stores before/after evidence
against its phase's opening measurement and is reverted whole on any permanent-gate
failure; orientation-sensitivity and failure-honesty gates from
`batch2_core_papers.md` apply to every new mechanism.

## 7. Phase 1 revised: HEX-MATCH primary mechanism (2026-07-25 synthesis)

Continues directly from "2026-07-25 gap search complete" above: the round-2 gap
search (`gap_search_transition_repair_round2_2026-07-25.md`) closed the literature
gap Phase 1 stalled on, and 5 full-reads (`staten2010_mesh_matching.md`,
`daines2018_octree_transition_repair.md`, `ledoux2013_cad_topology_correction.md`,
`chen2016_quality_sheet_choice.md`, `zhao2023_bc_hexmatching.md`) plus the two
round-1 P0 reads (Elsheikh 2014, Chen 2026 CJA) converge on a single design,
recorded in full in `evidence_matrix.md`'s "2026-07-25 round 2 synthesis" section.
This section adds the resulting card sequence; it does not modify or supersede any
section above.

### 7.1 Converged design

**Staten 2010's depth-bounded local mesh-matching architecture** (pillow / sheet
extraction / column collapse, same operator catalog already scoped topologically in
`ledoux2010_sheet_operations.md`) **gated by our own OpenFOAM skew metric, never a
borrowed proxy** (not scaled/MSJ Jacobian, not Chen 2016's topological `ΔV`). Three
independent findings this campaign all point the same way: `HEX-ECR-4`'s own
MSJ-vs-skew worst-tail Jaccard overlap of only 5.0-32.4% across 4 shapes; Chen
2016's own data showing `ΔV`-guided selection still degrading min scaled Jacobian to
0.18-0.37 and losing to the pure-heuristic original in a head-to-head case; and
Staten 2010's own unmitigated 0.9914→0.4691 drop with no floor check anywhere in
Algorithm 1. No literature-borrowed proxy metric is trustworthy for our specific
failure mode — the fix is the same guarded-transaction pattern (simulate, measure
with our own metric, reject-and-rollback if it doesn't strictly improve) already
validated 6+ times this session in native_tet/native_poly.

Scope split, not to be conflated:

- **Cylinder/sphere/gear (isolated singleton bad faces)** — Staten's demonstrated
  scale fits directly; this is the primary target (`HEX-MATCH-1/2`).
- **Bracket (7-connected-component/6-patch damage)** — NOT validated by any of the
  5 round-2 papers or the 2 round-1 papers. Ledoux 2013 excludes multi-component
  as future work; Staten 2010 restricts to single-surface interfaces; Zhao
  2023/2024's multi-component demo is sequential pairwise inter-part gluing, not
  our intra-mesh multi-cluster case. Must be its own separate, flagged-uncertain
  experiment (`HEX-MATCH-3`), never assumed to work via the same mechanism.
- **Daines 2018, Zhao 2023/2024, Ledoux 2013** are secondary technique donors, not
  primary mechanisms: Daines' iteration-bounded (cap 3) labeling-loop concept and
  its collateral-neighbor-damage measurement discipline (`HEX-DAINES-1/2`); Zhao's
  SLIM/Gao-2017 stitching energy for cleaning up any inversions a local repair
  introduces (`HEX-ZHAO-2`) and its base-complex depth-bounding as a generic
  repair-scope bound (`HEX-ZHAO-1`); Ledoux's dihedral-angle/chord-count rule as a
  secondary input alongside (never a replacement for) our skew measurement, for
  choosing WHERE pillowing helps sharp-feature preservation (`HEX-LEDOUX13-1/2/3`).

### 7.2 Card sequence (measurement-first)

Per this plan's own measurement-first protocol (Section 6): no mechanism lands on
an unmeasured baseline, and diagnostic-only cards precede any mesh-editing code.

1. **`HEX-MATCH-1` diagnostic mode** [S] — port Staten's chord-matching/
   sheet-selection logic (dual column/sheet membership identification for a
   flagged bad hex) in **report-only mode**: for every flagged bad face on
   cylinder/sphere/gear, report which sheet/column would be targeted and which
   operation (pillow-insert vs. column-collapse) would be attempted, with zero
   mesh mutation. Pass = a complete per-bad-face report exists and is
   inspectable before any editing code is written; this is the same
   report-before-mutate discipline already used for Phase 0's census cards.
2. **`HEX-MATCH-2`** [M] — implement the actual pillow/column-collapse operation
   behind a hard quality gate: trial the operation, measure our own OpenFOAM
   skew/non-orthogonality delta on the affected neighborhood only, commit only
   if it does not regress below the existing gate, else increase depth (capped)
   or abandon and report — replacing Staten's un-verified "smooth and hope"
   ending with an explicit reject-and-rollback transaction. Depends on 1's
   report matching what 2 actually executes (falsification check: if the
   diagnostic-mode targets and the real-op targets diverge, the port has a bug,
   not a design gap).
3. **`HEX-MATCH-3`** [research spike, not an implementation card] — bracket
   multi-component experiment, run only after 1-2 are measured on
   cylinder/sphere/gear: apply HEX-MATCH-1/2 independently to each of the
   bracket's 7 connected bad components; if any two components' selected
   sheets/columns overlap, document the conflict and stop — do not proceed to
   a bracket implementation without either a serialization order or reading
   Zhao 2023/2024's base-complex approach first. Explicit non-claim: passing
   cylinder/sphere/gear does not predict bracket's outcome.

Secondary donor cards (`HEX-DAINES-1/2`, `HEX-LEDOUX13-1/2/3`, `HEX-SHEETCHOICE-1/2/3`,
`HEX-ZHAO-1/2`) attach to this sequence as noted per-card in `evidence_matrix.md`'s
round-2 candidate-cards table; none is a prerequisite for `HEX-MATCH-1/2` to land.

### 2026-07-26 HEX-MATCH-1 result (measured, diagnostic only, zero mesh edits)

Delivered `core/generator/native_hex/match_diagnostic.py` (log-only, mirrors
`native_tet/boundary_invariant.py`'s `log_only=True` precedent) +
`tests/test_native_hex_match_diagnostic.py` (7 unit tests, all branches) +
`scripts/diag_hex_match_candidates.py` (fine-quality, pre-BL runner — BL
re-triangulates the wall into prism caps that hide the boundary quads this
card targets, so the census must run before the BL pass).

Flagging uses the project's own canonical boundary-skewness formula, ported
verbatim from `NativeMeshChecker._compute_boundary_skewness`
(`core/evaluator/native_checker.py`), not MSJ or `ΔV`, per this section's own
gating rule. Targeting is a purely combinatorial dual-column trace (two hex
faces are "opposite" iff they share no vertex), decided by Staten's two named
risk conditions only: self-intersection (doublet risk -> forces depth-1
pillow) and thru-boundary spanning (-> forces pillow, an extension of
Staten's node-associativity caveat from sheets to columns).

Census (fine quality, pre-BL, max_cells=8000, skew >= 2.0, max_depth=2):

| Shape | cells | boundary faces | flagged | pillow | collapse | none (footprint conflict) | none (non-hex owner) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cylinder | 6320 | 2232 | 368 | 0 | 312 | 56 | 0 |
| sphere | 4224 | 1896 | 888 | 54 | 289 | 545 | 0 |
| gear | 4914 | 3848 | 111 | 30 | 48 | 33 | 0 |

All collapse candidates used the full depth-2 bound; no self-intersecting
columns occurred in any of the three runs. At this cell budget all three
shapes measured 100% hex fraction (`score_che=1.0`), so the "non-hex owner"
rejection branch never fired — the octree-transition-polyhedron damage
pattern the literature discusses was not reproduced here; every "none"
verdict was a footprint conflict (two flagged faces claiming overlapping
depth-2 neighborhoods), heaviest on sphere (61% of its flagged faces).

**Caveat:** the wave-0/wave-1 numbers cited in Section 7's synthesis (85/676
for cylinder, Jaccard 5-32%) have no committed measurement script behind
them and could not be reproduced from this card's own protocol — the
`HEX-MATCH-1` numbers above are an independent fresh census, not a
reproduction of those earlier figures. Both measurements agree only in
kind (a large, well-targetable class of flagged bad faces exists), not in
exact counts.

**Verdict: proceed to `HEX-MATCH-2`.** 649/1367 flagged faces (~47%) across
the three shapes get a well-bounded collapse candidate, and pillow covers
most of the remainder cleanly; only footprint conflicts block the rest, and
`HEX-MATCH-2`'s own sequential-processing/rollback transaction (rather than
this diagnostic's all-at-once claim order) should reduce that count. No
evidence found against the mechanism's applicability to this damage pattern.

### 2026-07-26 HEX-MATCH-2 result (measured, real gated mesh edits)

Delivered `core/generator/native_hex/match_repair.py` (pillow construction,
chord-collapse boundary guard, local/global quality measurement, sequential
transactional driver) + `tests/test_native_hex_match_repair.py` (24 unit tests)
+ `scripts/diag_hex_match_repair.py` (same three shapes, same settings as
HEX-MATCH-1: fine, pre-BL, `max_cells=8000`, skew >= 2.0, depth <= 2, mesh
cached so the analysis is re-runnable). Wired into `mesher.py`'s octree path
behind `AUTO_TESSELL_HEX_MATCH2=1`, **default OFF**, per the FSL Wave 1 /
TET-FLOW-2 precedent.

**Falsification check: PASS on all three shapes, both gate policies.** The
diagnostic re-run on a pristine copy of each input produced target sets
identical to what HEX-MATCH-2 attempted in round 0 — 344 / 960 / 68 targets,
matching on (face, operation, footprint). HEX-MATCH-2 calls
`match_diagnostic`'s own functions rather than re-deriving targeting, so this
is structural; what the check actually proves is that the executor never
mutates the caller's arrays before the diagnostic view is taken.

**Two `match_diagnostic` bugs found and fixed** (the card's own
"diagnostic-and-executor must agree" trigger fired immediately — HEX-MATCH-2
could not reproduce the skewness of the faces HEX-MATCH-1 told it to repair):

1. **Face normal was neither area-weighted nor evaluated on the face's cyclic
   order.** `compute_boundary_face_skew` iterated the face-owner map, whose keys
   are *sorted* vertex tuples, and `_quad_skewness` built the normal from only
   the first fan triangle. `NativeMeshChecker._compute_face_normals_areas` uses
   the full area-weighted fan sum on the stored cyclic order. On a planar quad
   the two agree; on a *warped* quad — precisely what wall-snapping produces and
   precisely this card's target population — they diverge, and a sorted-order
   traversal of a quad is generally the bow-tie diagonal rather than its
   boundary. Measured on a warped grid face: 2.594 reported where the checker's
   own formula gives 1.502, a 73% overstatement. After the fix,
   `match_repair.mesh_quality` reproduces `NativeMeshChecker`'s headline numbers
   exactly (cylinder max skew 9.4861 vs. checker 9.48613, max non-orthogonality
   26.855 vs. checker 26.8549).
2. **Cell centre was the vertex mean, not the face-centre mean.** Fidelity fix
   only: for a topological hex the two are provably identical (every vertex lies
   on exactly 3 of the 6 faces), so it moves no number here. It matters for
   cells of unequal vertex face-degree — octree transition polyhedra, prisms —
   where a module claiming to be a verbatim port must not quietly diverge.
3. **Collapse branch was a mis-target** — see below; fixed by adding a
   boundary-admissibility precondition.

Census, before vs. after those fixes (identical meshes; the `@HEAD` column
reproduces the 2026-07-26 HEX-MATCH-1 numbers above exactly, which validates
the comparison):

| Shape | @HEAD flagged | @HEAD pillow / collapse / none | fixed flagged | fixed pillow / collapse / none |
| --- | ---: | ---: | ---: | ---: |
| cylinder | 368 | 0 / 312 / 56 | 344 | 288 / 0 / 56 |
| sphere | 888 | 54 / 289 / 545 | 960 | 368 / 0 / 592 |
| gear | 111 | 30 / 48 / 33 | 68 | 36 / 0 / 32 |

**Finding 1 — column collapse is not executable under this card's own boundary
invariant, at all.** A chord collapse merges the two opposite node pairs of
*every quad the chord passes through* (`ledoux2010_sheet_operations.md`, "Chord
collapse"). HEX-MATCH-1 seeds every column at a flagged **boundary** quad, so
that quad is the chord's own first quad and all four of its nodes are surface
nodes; both of the operation's two available pairings therefore merge boundary
nodes, which deletes or drags a surface node either way. Raising the depth bound
cannot help — the offending quad is the seed. This is not specific to our seeds:
in a hex mesh whose dual chords are not cycles, every chord terminates at a
boundary quad at both ends, so *no* chord collapse preserves a boundary; Ledoux
2010 states the same restriction topologically ("atomic ops are not allowed to
modify a mesh boundary"; a boundary-crossing sheet operation needs a temporary
ghost layer, which this card does not build). Measured, not argued: the executor
evaluated the guard on 100% of the branch's 649 candidates across the three
shapes and rejected 100% of them on exactly this ground, and a unit test sweeps
every boundary face of a 4^3 grid. The 649/1367 (~47%) "well-bounded collapse
candidate" figure in the HEX-MATCH-1 verdict above should be read as **0
executable collapse candidates**; those faces now fall through to the
boundary-preserving depth-1 pillow, which is what raised pillow from 84 to 692
across the three shapes.

**Finding 2 — pillow insertion works exactly as designed and the quality gate
rejects it anyway, ~99% of the time.** The construction is sound: 1 hex becomes
7, volumes partition the original exactly, the result is conforming and all-hex,
every original face is re-emitted verbatim so neighbours are bit-identical, no
boundary vertex moves, and the flagged face's skewness goes to ~0 (measured mean
2.755 -> 0.000 on the four gear faces that committed). The cost is
non-orthogonality: the single-cell "onion" pillow inflates all six faces, so its
rung faces radiate from the inner hex, and on snapped graded octree cells those
land at 70 deg where the cell's own faces were at 29 deg.

Outcomes under both defensible readings of "does not regress below the existing
gate" (the policy is an explicit `gate_policy` parameter, not a silent choice):

| Shape | policy | committed | rejected by gate | no candidate | cells | global max b-skew | global mean b-skew |
| --- | --- | ---: | ---: | ---: | --- | --- | --- |
| cylinder | neighbourhood | 0 | 288 | 56 | 6320 -> 6320 | 9.4861 -> 9.4861 | 1.1244 -> 1.1244 |
| sphere | neighbourhood | 0 | 368 | 592 | 4224 -> 4224 | 8.7786 -> 8.7786 | 2.2023 -> 2.2023 |
| gear | neighbourhood | 0 | 36 | 32 | 4914 -> 4914 | 2.7748 -> 2.7748 | 0.3688 -> 0.3688 |
| cylinder | mesh | 0 | 288 | 56 | 6320 -> 6320 | 9.4861 -> 9.4861 | 1.1244 -> 1.1244 |
| sphere | mesh | 0 | 368 | 592 | 4224 -> 4224 | 8.7786 -> 8.7786 | 2.2023 -> 2.2023 |
| gear | mesh | 4 | 64 | 64 | 4914 -> 4938 | 2.7748 -> 2.7336 | 0.3688 -> 0.3674 |

`neighbourhood` (the default) caps a repair at the grade-A thresholds or at
whatever that neighbourhood already had. `mesh` additionally lets a repair spend
headroom that exists *elsewhere* in the mesh; it is what admits the four gear
repairs, and their local non-orthogonality goes 29 -> 70 deg while the mesh's
reported maximum is unchanged at 75.487 because a 75 deg face already existed
somewhere else. Global mean non-orthogonality still rises 7.661 -> 7.837 and
global max internal skewness 0.3040 -> 0.5785, so even the four accepted repairs
are a real trade rather than a free win. Rejection causes are spread across all
four gate arms (cylinder: 134 internal-skew ceiling, 116 non-orthogonality
ceiling, 28 boundary-skew regression, 10 degenerate), i.e. this is not one
tunable threshold standing in the way.

**Finding 3 — the predicted footprint-conflict reduction did not materialise,
and the reason is structural rather than tunable.** Section 7.2's verdict
expected HEX-MATCH-2's sequential processing to shrink the "none" count. It did
not: 56 -> 56 (cylinder), 545 -> 592 (sphere), 33 -> 32 (gear). Two reasons, both
measured. First, with ~0 commits the sequential mechanism never runs — the
executor's own conflict deferral (`rejected_conflict`) fired zero times on every
shape. Second, and more fundamental: once collapse is ruled out, every footprint
is the single owner cell, so a "none" verdict now means *two flagged faces on the
same cell*. A single-cell pillow can be normal-aligned to only one of its six
faces, so those faces are genuinely mutually exclusive under this operation, at
any depth.

**Verdict: the mechanism is implemented, verified and honest, but it does not
currently pay for itself on cylinder/sphere/gear.** Nothing here is a coding
defect to chase — the operation does what the literature says and the gate does
what the card asked. The diagnosis is that a *single-cell* pillow is the wrong
shrink set: inflating all six faces of one cell is what generates the bad rung
faces. Pillowing the whole wall-adjacent layer (shrink set = every boundary
cell, interface = the manifold quad set separating them from the interior) gives
each wall cell exactly **one** inflated face, no rung radiation, and is the
construction Ledoux 2010 and Mitchell & Tautges 1995 actually describe — it is
already scoped in this plan as `HEX-SHEET-2` / the per-patch BL primitive. That
is the recommended next step on this lane, and it is a change of shrink set, not
of mechanism: `match_repair`'s gate, transaction and measurement all carry over.

### 7.3 Invariant table addition

| Card | Moves boundary vertices? | Changes cell count? | Determinism risk |
| --- | --- | --- | --- |
| HEX-MATCH-1 (diagnostic) | No (report-only) | No | None (traversal order fixed) |
| HEX-MATCH-2 | **No** — boundary vertices are never repositioned; only new interior/pillowed layers are inserted or an interior column is collapsed, matching Ledoux 2013's own boundary-compatibility finding (pillowing adds structure without moving geometry already classified on S/C/V) | Yes (one sheet/column edited per accepted repair) | Medium (depth-cap and rollback order must be pinned) |
| HEX-MATCH-3 (bracket spike) | No (inherits HEX-MATCH-2's contract) | Yes, if executed | High (unvalidated for multi-component; may not converge or may conflict across components) |

### 7.4 Explicit rejections

- **Chen 2016's `ΔV`/EEVS as a primary (or even fallback) repair-pass metric.**
  It is not geometric (pure edge-valence/hex-count bookkeeping), has no
  established correlation with either MSJ or our OpenFOAM skew, and the
  source paper's own experiments show substantial scaled-Jacobian degradation
  despite `ΔV`-guided selection being active throughout, including one
  head-to-head loss to the unguided original algorithm. `HEX-SHEETCHOICE-2`
  is the standing diagnostic that could overturn this — until it runs and
  shows otherwise, `ΔV` stays rejected.
- **Daines 2018's mixed-element mechanism ported wholesale.** Its `J_ENS`
  metric and surface-pattern-collision repair are defined over an 8-split
  mixed tet/pyramid/wedge/hex octree family that does not exist in our
  pure-hex/hex-dominant engine. Only the loop-structure and
  measurement-discipline patterns transfer (`HEX-DAINES-1/2`); the metric and
  the mixed-element repair target do not.
- **Assuming the bracket works without its own validation.** No round-2 or
  round-1 paper demonstrates a many-cluster-at-once intra-mesh repair. Bracket
  work is gated entirely behind `HEX-MATCH-3`'s own measured spike, not
  inferred from cylinder/sphere/gear success.

### 2026-07-26 HEX-SHEET-2 layer-wide shrink-set diagnostic (falsified, no topology edits)

Added `core/generator/native_hex/sheet_diagnostic.py`,
`scripts/diag_hex_sheet2.py`, and
`tests/test_native_hex_sheet_diagnostic.py` as a report-only precondition
census. On the same actual meshes as HEX-MATCH-2 (fine, pre-BL,
`max_cells=8000`), the proposed shrink set `S` is every owner of a physical
boundary quad and `Q` is every face with one owner in `S` and one in the core.
The wall-cell contract is measured, not inferred: every cell in `S` must be a
clean hex with exactly one physical-boundary face and exactly one `Q` face.

| Shape | cells / points | `n_shrink` / nonhex | `Q` quad / nonquad | `Q` edge incidence | components / open / nonmanifold | `Q` vertices on physical boundary | predicted points / cells |
| --- | --- | --- | --- | --- | --- | ---: | --- |
| cylinder | 6320 / 9261 | 1640 / 0 | 1816 / 0 | `{2: 3632}` | 1 / 0 / 0 | 380 | 9261 -> 11079 / 6320 -> 8136 |
| sphere | 4224 / 9261 | 968 / 0 | 1560 / 0 | `{2: 3120}` | 1 / 0 / 0 | 756 | 9261 -> 10823 / 4224 -> 5784 |
| gear | 4914 / 11767 | 2594 / 0 | 2152 / 0 | `{2: 4304}` | 1 / 0 / 0 | 363 | 11767 -> 13911 / 4914 -> 7066 |

Per-shrink-cell incidence distributions (histogram syntax is
`face-count: cell-count`):

| Shape | physical-boundary faces per `S` cell | `Q` faces per `S` cell |
| --- | --- | --- |
| cylinder | `{1:1096, 2:496, 3:48}` | `{0:112, 1:1240, 2:288}` |
| sphere | `{1:360, 2:288, 3:320}` | `{1:528, 2:288, 3:152}` |
| gear | `{1:1733, 2:570, 3:208, 4:64, 5:19}` | `{0:858, 1:1352, 2:352, 3:32}` |

**Measured verdict: reject this shrink set before implementation.** `Q` passes
the narrow Ledoux topological check on all three shapes: it is a nonempty,
single-component, all-quad closed manifold and every `Q` edge has incidence
exactly two. The stronger wall-layer contract fails on all three shapes.
Boundary edge/corner cells have multiple physical-boundary faces, 112 cylinder
and 858 gear shrink cells have no `Q` face, and many cells have two or three
`Q` faces. In addition, 380/756/363 `Q` vertices respectively are also physical
boundary vertices. Globally duplicating and moving those vertices on the
shrink side would therefore violate the required bit-identical physical
boundary, while leaving them fixed would violate the proposed
"move duplicated internal interface vertices only" placement model.

No `AUTO_TESSELL_HEX_SHEET2` production path, topology constructor, or mesh
mutation was added. Consequently the predicted growth above was not executed
and there is no before/after quality claim. This falsifies the all-wall-owner
shrink set as currently defined; a future card needs a different, explicitly
separated patch/layer selection before layer-wide pillowing can be reconsidered.

### 2026-07-26 HEX-PATCH-LAYER-DIAG1 result (strict patch/layer classification, KILL)

Added `core/generator/native_hex/patch_layer_diagnostic.py`,
`scripts/diag_hex_patch_layer1.py`, and
`tests/test_native_hex_patch_layer_diagnostic.py`. The runner reads the actual
fine pre-BL cache blobs used by HEX-MATCH-1/2 and HEX-SHEET-2
(`cylinder_8000.npz`, `sphere_8000.npz`, and `gear_8000.npz`; `max_cells=8000`).
It does not regenerate a mesh and does not call a topology constructor.

The cache format contains points and cell faces but not the OpenFOAM boundary
file. The diagnostic therefore reconstructs the writer's deterministic
feature-patch grouping from the cached physical boundary faces and attaches
the current native_hex single-source `defaultWall` provenance. This is a
reporting label reconstruction, not a new production provenance path.

For each shape, the initial wall population is restricted to clean hex cells
with exactly one physical-boundary face. `Q` is then measured against the
complement of that initial population. A cell is retained only when it has
exactly one Q face, that Q is a quad with exactly two owners, its vertices are
disjoint from all physical-boundary vertices, and its boundary-face
patch/provenance label is retained. The retained Q faces are split into
same-label shared-edge components. A component is operation-eligible only if
its Q set is closed (`edge incidence == 2` everywhere), has no open or
non-manifold edge, and remains one-to-one with its S cells.

| Shape | cells | physical boundary | S exact1 / nonhex | Q interface / nonquad | eligible S / Q | components | strict component edge incidence | open / nonmanifold | Q vertices on physical boundary | predicted / approved pillow ops | hypothetical points / cells | decision |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | --- |
| cylinder | 6320 | 2232 | 1096 / 0 | 2024 / 0 | 544 / 544 | 6 | `{1:272,2:952}` | 272 / 0 | 0 | 6 / 0 | +686 / +544 | KILL |
| sphere | 4224 | 1896 | 360 / 0 | 1128 / 0 | 24 / 24 | 6 | `{1:48,2:24}` | 48 / 0 | 0 | 6 / 0 | +54 / +24 | KILL |
| gear | 4914 | 3848 | 1733 / 0 | 2901 / 0 | 888 / 888 | 22 | `{1:656,2:1448}` | 656 / 0 | 0 | 22 / 0 | +1228 / +888 | KILL |

The component populations are deterministic: cylinder has four `wall_0`
components of 32 S/32 Q and one 208/208 component on each of `wall_2` and
`wall_4`; sphere has six `wall_0` components of 4 S/4 Q; gear has one 420/420
component on each of `wall_0` and `wall_1`, four 4/4 components on `wall_32`,
and sixteen 2/2 components on the remaining labels. Every component has
open Q edges; none has a non-manifold edge. The apparent raw union can hide
some of those openings when adjacent labels share an edge, which is why the
gate is evaluated per same-patch/provenance component.

The two repeated measurements per cached shape were identical at the report
level, and the input points/cells remained unchanged. Thus the strict
classification finds candidate counts but no valid subset and no approved
operation on any shape. This is an honest `KILL`: no next implementation card
is proposed, no topology mutation or production pillowing/sheet-extraction
path was added, and the existing wall_dev and skew gates are unchanged. There
is no before/after quality claim and no predicted growth was executed.

### 2026-07-26 HEX-TRANSITION-PROVENANCE-DIAG1 result (report-only, BLOCKED)

Added the opt-in diagnostic module
`core/generator/native_hex/transition_provenance.py`, builder-side collection
in `core/generator/native_hex/octree.py`, writer-boundary logging in
`core/generator/native_hex/mesher.py`, the runner
`scripts/diag_hex_transition_provenance1.py`, and regression tests in
`tests/test_native_hex_transition_provenance.py`. The environment flag is
`AUTO_TESSELL_HEX_TRANSITION_PROVENANCE_DIAG=1`; the default path remains OFF
and mesh output is unchanged.

At `max_cells=8000`, fine pre-BL runs produced the following deterministic
builder-to-writer census:

| Shape | builder / writer cells | builder metadata / unique origins | target-level histogram | generic template | transition cells / faces | writer loss |
| --- | ---: | ---: | --- | --- | ---: | ---: |
| cylinder | 6320 / 6320 | 6320 / 6320 | `{4: 6320}` | `{uniform: 6320}` | 0 / 0 | 0 |
| sphere | 4224 / 4224 | 4224 / 4224 | `{4: 4224}` | `{uniform: 4224}` | 0 / 0 | 0 |
| gear | 4920 / 4914 | 4920 / 4920 | `{4: 4920}` | `{uniform: 4920}` | 0 / 0 | 6 cells |

Thus these three exact benchmark runs do not contain emitted mixed-level
transition cells, even though the existing octree summary has approximate
coarse/fine counters. The current data cannot support a transition-sheet
quality or repair claim. Separately, the generic writer does not forward the
builder metadata (`writer_metadata_forwarded=False`); authoritative lineage,
transition-chain/hanging-node, emitted-template, feature, and patch/source
provenance are still absent from the final cache. The prior
`HEX-TRANSITION-DIAG1` `BLOCKED` status therefore remains unchanged.

The gear-only six-cell drop occurs at the generic writer's existing
degenerate-cell filtering boundary and is recorded as a separate
`HEX-WRITER-DEGENERATE-DROP-DIAG1` audit target. The provenance census was
report-only, did not alter surface/snap/quality behavior, and did not create a
production repair flag. Relevant native_hex tests passed (`55 passed`; the new
targeted group `4 passed`), with deterministic repeat output.

Next measurement is `HEX-OCT-ADAPTIVE-TRANSITION-REALIZATION-DIAG1`: construct a
mixed-level synthetic/adaptive fixture and first prove that a real transition
template is emitted. No transition repair implementation is authorized before
that measurement.

### 2026-07-26 HEX-OCT-ADAPTIVE-TRANSITION-REALIZATION-DIAG1 result

The finest-first `block_sz == 1` branch was isolated behind the new
`AUTO_TESSELL_HEX_MIXED_LEVEL_REALIZATION` flag, default OFF. With the flag ON,
a direct 4×4×4 synthetic input requesting `{level 1: 8, level 2: 56}` emitted
57 cells (`level 1: 1`, `level 2: 56`), one transition cell, three transition
directions, and 12 coarse→fine interface faces. Face incidence was
`{1:87, 2:132}`, and the template histogram was `t21:1, uniform:56`.

The same change was not safe as a default production change. A forced-ON real
shape run changed the builder populations to cylinder `2463`, sphere `2684`,
and gear `4542`, and the relevant native_hex regression suite failed five
permanent gates (curved-wall fidelity, boundary skew, fine negative-volume,
and adaptive cell-budget-related assertions). The flag is therefore retained
as an experimental default-OFF lane; the original default path remains green
(`57 passed`).

This closes the realization existence question but does not close transition
quality. The next card is `HEX-OCT-TRANSITION-QUALITY-1`: measure signed volume,
face warpage, local skew, boundary face-set, and writer cell drops on the
opt-in output before any default change or repair template is considered.

### 2026-07-26 HEX-OCT-TRANSITION-QUALITY-1

The opt-in quality census in `transition_quality.py` measures signed emitted
volume, orientation-free volume, face warpage, canonical face skew, boundary
face-set/area, face incidence, and generic-writer cell drops. It is report-only.

On the synthetic mixed-level fixture (`{1:8,2:56}`), the census observed one
transition cell, three transition faces, 12 coarse-to-fine interface faces,
boundary face count 87, and no negative emitted signed volume. On the real
fine pre-BL opt-in runs (`max_cells=8000`), cylinder/sphere/gear produced
transition cell/face counts `173/229`, `63/111`, and `11/36`. Builder-to-writer
cell counts were `2463→2445`, `2684→2684`, and `4542→4534`; boundary face-set
was changed for cylinder and gear and equal for sphere. Gear had five negative
emitted signed volumes at builder and four after writer; cylinder's transition
skew p95/max was `2.123554/133.752485`, sphere's was `1.268530/1.620019`, and
gear's was `1.149741/1.422732`.

Decision: **measured, production promotion rejected**. The realization flag
remains default-OFF. Before any transition repair implementation, isolate the
generic-writer drop/boundary-set contract and emitted face-winding orientation
contract. Targeted quality tests passed (`3 passed`), and the full native_hex
file group passed (`113 passed in 141.77s`).

### 2026-07-26 HEX-OCT-TRANSITION-WRITER-1

The writer-boundary audit mirrored the generic writer's public degenerate-face
contract without changing the writer. Predicted versus actual drops matched
exactly: cylinder `18/18`, sphere `0/0`, and gear `8/8`. Predicted internal faces
exposed by those drops also matched the actual added boundary keys: cylinder
`60/60` and gear `23/23`; boundary keys removed were 44 and 19 respectively.

The first cylinder evidence is cell 145, face 5,
`[1113,1134,1135,1114]`: after snap, two pairs of the four coordinates are
identical, giving face area `0.0` under `writer_area_eps≈3e-24`. The first gear
evidence is cell 329, face 3, with the same two-pair coincidence. The writer is
therefore **exonerated**; it deterministically removes upstream degenerate
faces, and the boundary-set change is owner reclassification after removal.

Next card: `HEX-OCT-TRANSITION-SNAP-ROOTCAUSE-1`, a stage-bisected measurement
of zero-area faces and boundary keys after builder, iterative snap, wall-fit,
and skew-relax. No transition repair or writer relaxation is authorized before
that card closes.

### 2026-07-26 HEX-OCT-WALLFIT-FACE-AREA-GUARD-1

The stage bisection found the first cylinder/gear zero-area faces after
`_wall_fit_snap`, not after iterative snap. An opt-in face-area check was added
to the wall-fit candidate guard under
`AUTO_TESSELL_HEX_WALLFIT_FACE_AREA_GUARD=1`; the default remains OFF. The
check rejects/backtracks a candidate if an incident face area falls below a
small scale-dependent floor, without changing the existing sign/volume,
distance, or envelope guards.

On mixed-level fine pre-BL runs, writer drops changed cylinder `18→0` and gear
`8→0`, and boundary sets became equal. However transition skew/warpage remained
high (cylinder skew p95/max `2.150564/133.752485`; gear
`3.279938/11.460936`) and gear still had five builder-side negative emitted
signed volumes. Decision: **partial, default-OFF, not a quality fix**. The next
card must test a transition-aware wall-fit quality constraint; writer
relaxation and broad repair ports remain blocked.

### 2026-07-26 HEX-TRANS-2 — transition adjacency cross-tab (measured, falsified)

The report-only census cross-tabulated boundary faces with canonical skew
`>=2.0` against metadata-labelled transition-cell ownership and a broad
transition-vertex adjacency proxy. The benchmark was the opt-in mixed-level
fine pre-BL cylinder/sphere/gear run at `max_cells=8000`, default wall-fit, and
face-area guard OFF. Since the current metadata has no authoritative hanging-
node chain ID, vertex adjacency is explicitly not treated as exact hanging-node
provenance.

| Shape | bad faces after wall-fit/final | transition owner | owner rate | transition-vertex adjacent | vertex rate |
|---|---:|---:|---:|---:|---:|
| cylinder | 550 | 36 | 6.545% | 168 | 30.545% |
| sphere | 960 | 0 | 0% | 0 | 0% |
| gear | 135 | 10 | 7.407% | 22 | 16.296% |

All three shapes had zero bad boundary faces before and after iterative snap;
the bad population first appeared at wall-fit. The total transition-owner /
transition-vertex-adjacent boundary populations were cylinder `588/1705`,
sphere `267/677`, and gear `63/275`.

Decision: **measured, falsified**. Bad faces do not concentrate on transition
cells or their one-ring vertex proxy; sphere has no overlap, and most cylinder
and gear bad faces are outside both populations. The next card is not a
transition-only repair. It is `HEX-WALLFIT-CANDIDATE-QUALITY-1`, a report-only
measurement of each wall-fit candidate's local skew, face warpage, signed
volume, and boundary invariant before any transactional quality gate is
implemented. The mixed-level realization and face-area guard remain
default-OFF.

### 2026-07-26 HEX-WALLFIT-CANDIDATE-QUALITY-1 — measured

The opt-in audit snapshots each `_wall_fit_snap` boundary-vertex candidate's
incident cells before projection, after the full projection trial, and after
the existing full/partial/reject decision. It also records the global boundary
face-key set and boundary area. No value participates in acceptance, rollback,
or permanent gates.

At `max_cells=500`, mixed-level realization ON, default wall-fit, and face-area
guard OFF:

| Shape | candidates | full/partial/reject | trial regressions | applied regressions | area changes | max applied skew Δ | max applied warpage Δ |
|---|---:|---:|---:|---:|---:|---:|---:|
| cylinder | 128 | 128/0/0 | 128 | 128 | 128 | +1.5313 | +0.4064 |
| sphere | 128 | 128/0/0 | 104 | 104 | 128 | +1.4238 | +0.0571 |
| gear | 271 | 241/12/18 | 207 | 186 | 238 | +1.2518 | +0.7688 |

Boundary face keys remained equal, but boundary area changed on the moved
surface vertices. A larger cylinder `max_cells=2000` run measured
`560` candidates, `358/179/23` full/partial/reject, `515` trial regressions,
`481` applied regressions, and `521` area changes. Its `2.7756e13` maximum
skew delta is a near-zero-normal-distance numerical outlier and is not a gate
candidate.

Decision: **measured, quality regression observed**. Wall-fit's existing
distance/envelope/no-inversion guards do not imply local quality monotonicity.
This is a generic wall-fit candidate issue, not a transition-only issue. The
next card is `HEX-WALLFIT-QUALITY-TRANSACTION-1`: resolve denominator and
signed-orientation contracts, then measure a relative quality transaction with
surface-area tolerance. It remains report-only until that contract is closed;
mixed-level realization and face-area guard remain default-OFF.

#### HEX-WALLFIT-QUALITY-TRANSACTION-1 contract precheck

The checker and candidate diagnostic share the same skew denominator
`max(abs(normal_dist), 1e-30)`. In the small cylinder census, minimum trial
`|normal_dist|` was `0.0149533` with zero near-zero faces, while applied skew
still increased by `+1.5313`. Therefore the small-run quality regression is
real under the project's own metric; the much larger `2.7756e13` result is a
separate denominator-sensitive outlier and cannot define a gate.

The production wall-fit no-inversion contract is face-sign preservation against
the pre-projection reference. The report-only centroid-fan signed-volume sum
depends on face winding and is not an authoritative validity signal. Before
implementing a transaction, reuse the existing face-sign contract and define a
relative local-quality delta plus a boundary-area tolerance.

### 2026-07-26 HEX-WALLFIT-QUALITY-TRANSACTION-1 result

Two hypothetical report-only policies were evaluated: strict max skew/max
warpage non-regression and p95 skew/p95 warpage non-regression. `combined`
requires both. At the low-budget `max_cells=500` mixed-level opt-in wall-fit
stage:

| Shape | candidates | strict | p95 | combined | max relative boundary-area change |
|---|---:|---:|---:|---:|---:|
| cylinder | 128 | 0 | 0 | 0 | 0.2266% |
| sphere | 128 | 24 | 0 | 0 | 0.3641% |
| gear | 271 | 85 | 66 | 66 | 0.1702% |

Boundary face-key changes were zero. Decision: **measured, naive monotone
transaction is too restrictive**. A quality-only rollback would reject every
measured cylinder candidate and may block wall-distance improvement. Do not
implement it. The next card is a report-only cross-tab of candidate surface
distance/wall deviation improvement against local quality delta, after which a
relative trade-off transaction can be considered. Mixed-level realization and
face-area guard remain default-OFF.

### 2026-07-26 HEX-WALLFIT-QUALITY-TRANSACTION-1 surface-distance cross-tab

The candidate audit also recorded actual surface-distance reduction
`d_before - d_after` for accepted full/partial candidates.

| Shape | candidates | strict | p95 | combined | distance-improved | distance-improved + quality regression |
|---|---:|---:|---:|---:|---:|---:|
| cylinder | 128 | 0 | 0 | 0 | 128 | 128 |
| sphere | 128 | 24 | 0 | 0 | 128 | 104 |
| gear | 271 | 85 | 66 | 66 | 253 | 186 |

Total reductions were cylinder `5.2117`, sphere `10.8663`, and gear `16.9085`;
maximum single-candidate reductions were `0.06122`, `0.17648`, and `0.10862`.
Boundary face keys remained equal for every distance-improved candidate.

Decision: **measured, quality-only rollback conflicts with surface fitting**.
Every measured cylinder distance improvement had a local quality regression.
Do not add a monotone quality gate. The next diagnostic must cross-tab final
wall deviation/surface fidelity benefit against candidate local quality delta at
representative mesh sizes before any Pareto-style transaction is considered.

### 2026-07-26 HEX-WALLFIT-SURFACE-TRADEOFF-1 result

Full wall-fit stage surface-distance measurements at the same low-budget
mixed-level opt-in setting were:

| Shape | boundary vertices | mean before→after | p95 before→after | max before→after |
|---|---:|---|---|---|
| cylinder | 380 | `0.027915→0.014200` | `0.061217→0.003791` | `0.373194→0.373194` |
| sphere | 334 | `0.078905→0.046371` | `0.562459→0.562459` | `0.995472→0.995472` |
| gear | 672 | `0.026542→0.001380` | `0.096807→0.005295` | `0.108621→0.019445` |

Decision: **measured, surface-fidelity benefit confirmed**. Wall-fit reduces
mean/p95 surface distance but can worsen local cell quality. Quality-only
rollback conflicts with the surface contract. No transaction or new absolute
threshold is enabled; the next validation connects candidate deltas to the
existing final wall-dev/skew gates at representative mesh sizes.

### 2026-07-26 HEX-WALLFIT-FINAL-GATE-CROSS1 — representative final-gate connection

The diagnostic runner was extended to print the existing evaluator/checker
summary from the same report-only run as the candidate snapshots. This did not
change wall-fit acceptance. Conditions were mixed-level realization ON,
default wall-fit, face-area guard OFF, `max_iterations=1`, and no BL layers.

| shape / budget | candidates | distance-improved | distance-improved + local quality regression | combined local quality non-regressing | final verdict | final cells | final max boundary skew | negative volumes | final area deviation |
|---|---:|---:|---:|---:|---|---:|---:|---:|---:|
| cylinder / 500 | 128 | 128 | 128 | 0 | FAIL | 412 | 2.73027 | 0 | 4.59347% |
| sphere / 500 | 128 | 128 | 104 | 0 | FAIL | 276 | 2.85183 | 0 | 10.0102% |
| gear / 500 | 271 | 253 | 186 | 66 | FAIL | 408 | 1.38997 | 0 | 11.4375% |
| cylinder / 2000 | 560 | 537 | 481 | 49 | FAIL | 1384 | 125.761 | 0 | 87.0928% |

At budget 500, the final checker retained zero negative-volume cells and the
final boundary skew remained below the permanent `3.0` threshold for all three
representative shapes, although the overall evaluator verdict was FAIL because
other quality/coverage criteria also apply. At budget 2000, the same cylinder
run exposed a severe final skew failure (`125.761`) despite zero negative
volumes. The candidate report recorded `537` surface-distance improvements,
`481` of them with a local quality regression, and only `49` satisfying the
combined hypothetical local non-regression test. The final gate failure is
therefore not a transition-only signature and cannot be safely repaired by a
candidate quality-only rollback.

The surface-fidelity fields in this run are the evaluator's Hausdorff/distance/
area-deviation metrics; they are reported alongside, but are not silently
renamed to, the native_hex wall-fit `wall_dev` contract. No permanent threshold,
transaction, or default flag was changed. Decision: **measured, final-gate
connection established; quality-only transaction remains rejected**. The next
card is a new scale/performance and final-gate root-cause diagnosis for the
large-budget cylinder, not a production wall-fit change.

### 2026-07-26 HEX-OCT-MIXED-LEVEL-ROOTCAUSE-1 — measured, root cause isolated

The large-budget cylinder was split by the two opt-in mechanisms, with
candidate-quality logging disabled so diagnostic overhead could not explain the
result.

| condition | cells / census | final boundary skew | negative volumes | surface area deviation | verdict |
|---|---|---:|---:|---:|---|
| mixed OFF, wall-fit ON | 1781 hex | 3.20865 | 0 | 0.2637% | PASS_WITH_WARNINGS |
| mixed ON, wall-fit OFF | 1363 hex + 22 other | 1.16279 | 0 | 93.4942% | FAIL |
| mixed ON, wall-fit ON | 1363 hex + 22 other | 125.761 | 0 | 87.0928% | FAIL |
| mixed OFF, wall-fit OFF | 1781 hex | 0.974374 | 0 | 15.3787% | FAIL |

The mixed-level builder itself is already invalid before wall-fit: at
`max_cells=2000`, its `before_snap` report contained `22` transition cells,
`1479` boundary faces, and `2` negative report-only signed volumes. The source
mechanism is visible in `_build_nlevel_cells`: the coarse cell face is split
into four sub-quads when a finer neighbor is found, but the fine-neighbor side
continues to emit ordinary fine quads. No conforming transition template or
matching hanging-node face partition is created on both sides. The writer then
preserves the resulting nonconformal geometry; it is not the primary cause.

Decision: **measured, root cause found**. Wall-fit is an amplifier, not the
origin of the large-budget mixed-level surface/topology failure. Do not enable
mixed-level realization by default and do not add a wall-fit quality rollback
to mask it. Open `HEX-OCT-TRANSITION-TEMPLATE-1` as a separate implementation
card: introduce a documented conforming transition template/face partition,
with boundary area/face-set, signed-volume, census, and deterministic output
gates before any default promotion. The current diagnostic remains report-only.

### 2026-07-26 correction — HEX-OCT-TRANSITION-WINDING-1 supersedes the preceding sub-claim

The preceding paragraph's claim that the fine-neighbor side lacked a matching
partition was too strong and is superseded by a direct synthetic face-key
audit. For a 2:1 block, the four coarse sub-quads and the ordinary fine-neighbor
quads do have matching vertex keys; the synthetic incidence histogram remains
`{1: 87, 2: 132}` and is deterministic. The concrete correctness defect was
different: every table emitted by `_sub_quads_on_face` had the cyclic order
opposite to `_HEX_FACES`.

The minimal fix keeps the coordinate tables unchanged and reverses each
sub-quad once at the helper boundary. A new test checks that all faces of the
synthetic transition cell have a positive outward normal dot product. Results:

| check | before | after |
|---|---:|---:|
| synthetic negative signed transition cells | 1 | 0 |
| synthetic transition cells | 1 | 1 |
| synthetic face incidence histogram | `{1:87,2:132}` | `{1:87,2:132}` |
| targeted transition tests | — | 4 passed |

On the real mixed cylinder, the builder report-only negative signed count fell
from `2` to `0` and the mixed+wall-fit-OFF writer emitted `1385` cells without
drops. The remaining mixed-level surface/quality failure is not closed:
mixed+wall-fit-OFF still has area deviation `93.4942%`, and mixed+wall-fit-ON
still has final boundary skew `125.761` (cells `1383`, area deviation
`87.7568%`). Therefore `HEX-OCT-TRANSITION-WINDING-1` is a correctness
subcard completed, while the broader `HEX-OCT-TRANSITION-TEMPLATE-1` /
mixed-level surface root cause remains open. No all-hex claim or default flag
was changed.

### 2026-07-27 HEX-OCT-MIXED-LEVEL-COVERAGE-1 — measured, implemented, gated

The remaining mixed-level defect was isolated at two concrete points in
`_build_nlevel_cells`. First, the loop checked only `covered[fi, fj, fk]`, so a
finer leaf could consume the block origin while target-level-3 cells in the
same block were skipped. In the reproduced cylinder grid,
`(4,6,6)=level4` while `(5,6,6)` and `(4,7,6)` were `level3`; the resulting
internal face was emitted as a boundary. Second, the coarse-face neighbor
test sampled one neighbor index instead of the complete face-adjacent slab,
so a fine neighbor at `(6,3,5)` was missed by the coarse block at `(6,4,4)`.

The minimal opt-in fix does three things: normalizes mixed target blocks by
promoting them to finest cells before emission, promotes any residual partial
covered block without overlap, and computes the maximum level over the full
adjacent face slab before deciding whether to emit four sub-quads. The
existing sub-quad winding correction remains unchanged. The default mixed
level flag is still OFF.

| check | before coverage fix | after coverage fix |
|---|---:|---:|
| synthetic transition tests | 4 passed | 5 passed |
| synthetic internal boundary faces | present | 0 |
| real builder inner-looking boundary faces | 155 | 0 |
| real mixed cylinder writer cells | 1383–1385 | 1655 |
| real builder signed-negative cells | 2 | 0 |
| writer dropped cells | 2 or predicted malformed | 0 |
| writer boundary face-set equal | not reliable | `True` |

At the representative 2,000-cell cylinder pipeline condition, the result is
`PASS_WITH_WARNINGS`, `1655` cells, max boundary skew `3.20865134`, negative
volumes `0`, min volume `0.00014462409`, max warpage `0.05652146`, surface-area
deviation `0.263700907%`, boundary area `4.68488421` versus input `4.69727095`,
and writer boundary-area delta `-1.13e-9`. The 85 non-transition boundary
faces above the diagnostic threshold remain a separate scale/quality issue;
the catastrophic mixed-level area/topology failure is closed, but the
permanent `3.0` boundary-skew gate is not relaxed and mixed-level is not
promoted to the default path.

Direct repeated builder runs were deterministic (`points_equal=True`,
`cells_equal=True`, 1627 cells in both direct runs). The native_hex regression
suite is `118 passed` including the new partial-covered-block test.

Decision: **HEX-OCT-MIXED-LEVEL-COVERAGE-1 measured, implemented, and gated**.
The next native_hex card is the remaining large-budget boundary-skew/quality
card (`HEX-OCT-SCALE-QUALITY-1`); default promotion and any permanent-gate
relaxation remain prohibited.

### 2026-07-27 HEX-OCT-SCALE-QUALITY-1 — measurement, implementation deferred

With the coverage fix active, builder-side boundary skew is zero bad faces.
The bad-face population appears only after `_wall_fit_snap`: a direct
report-only comparison produced `0→80` bad faces (the full pipeline reports
`85`). None of those bad faces has a transition-cell owner or a transition
vertex-adjacent label. This isolates the remaining `3.20865134` final skew to
ordinary boundary-vertex wall fitting, not to mixed-level realization.

| condition | cells | max boundary skew | area deviation | bad boundary faces | result |
|---|---:|---:|---:|---:|---|
| mixed ON + wall-fit ON | 1655 | `3.20865134` | `0.263700907%` | 85 | PASS_WITH_WARNINGS |
| mixed ON + wall-fit OFF | 1655 | `0.974373881` | `15.3787224%` | 0 | FAIL |

The direct wall-fit candidate audit found `496/496` distance-improving
candidates, `376` with local quality regression, `120` strict local-quality
non-regressions, `104` combined p95 non-regressions, and zero boundary-key
changes. Surface distance mean improved `0.0167231→0.0007091` and p95
`0.0490482→0.00376990`. A quality-only rollback would remove most of the
surface-fidelity gain, so no production acceptance rule is changed here.

Decision: **measured, root cause narrowed to wall-fit quality trade-off**.
`HEX-OCT-SCALE-QUALITY-1` remains open for a surface-constrained Pareto rule
or another literature-supported local repair; permanent skew `3.0` is not
relaxed, and mixed-level default promotion remains blocked.

### 2026-07-27 HEX-WALLFIT-PARETO-1 — literature-integrated next card

The wall-fit trade-off is now a separate measurement card. Current data are
`496/496` distance-improving candidates, `376` local-quality regressions,
`120` strict local-quality non-regressions, and `104` combined p95
non-regressions. Wall-fit ON gives skew `3.20865134` with area deviation
`0.263700907%`; OFF gives skew `0.974373881` but area deviation `15.3787224%`.

The detailed P0/P1/P2 screening is in
`wallfit_pareto_quality_repair_2026-07-27.md`. It covers transition
preconditioning, transition quality control, surface-constrained HexOpt,
boundary-sheet repair, and feature-aware sheet operations. HexOpt
(`10.1016/j.cad.2026.104073`) is the closest FULL_READ comparator, but it
allows tangential corner/edge/face sliding and is not a drop-in replacement
for the frozen wall-fit lane.

Next: report-only candidate-level Pareto measurement of `Δskew`, `Δwarpage`,
`Δarea`, `Δwall_dev`, and signed-volume effects over cylinder/sphere/gear/
bracket. No acceptance rule, permanent gate relaxation, mixed-level default
promotion, or surface movement policy changes before the queued papers are
FULL_READ and the frontier passes all existing invariants.

### 2026-07-27 HEX-WALLFIT-PARETO-1 — first report-only run

The current full-pipeline cylinder run (`max_cells=2000`, mixed-level and
candidate diagnostics enabled) recorded `350` wall-fit candidates and a
`117`-candidate non-dominated frontier. Boundary key changes were `0`, signed
negative-volume increases were `0`, and strict/p95/combined quality
non-regressions were each `16`. Stage wall distance mean changed
`0.0120959802→0.0005450396`; p95 changed
`0.0380725043→0.0024877153`. The final checker remained
`PASS_WITH_WARNINGS`, with `1655` cells, skew `3.20865134`, negative volumes
`0`, and area deviation `0.263700907%`.

This confirms that a Pareto frontier exists but does not yet yield a safe
acceptance rule: most distance-improving candidates still increase local
skew/warpage, and the production path contains a later skew-relax stage. The
same report-only run must be repeated on sphere, gear, and bracket before any
candidate policy is proposed.

### 2026-07-27 HEX-WALLFIT-PARETO-1 — three-shape extension

The same report-only run was extended to sphere, gear, and bracket at
`max_cells=2000`. The candidate-level results are:

| shape | final cells | final max boundary skew | candidates | frontier | strict / p95 / combined non-regressing |
|---|---:|---:|---:|---:|---:|
| cylinder | 1655 | 3.20865134 | 350 | 117 | 16 / 16 / 16 |
| sphere | 1057 | 14.7384497 | 404 | 157 | 36 / 36 / 36 |
| gear | 1296 | 27.0814284 | 531 | 67 | 117 / 108 / 99 |
| bracket | 538 | 19332.7157 | 342 | 41 | 133 / 118 / 115 |

All four runs reported zero final negative volumes and zero boundary-key
changes in the wall-fit audit. The frontier size and quality-preserving
fraction vary substantially by shape, while all four final boundary-skew
values exceed the permanent `3.0` gate at this budget. This falsifies a single
global candidate threshold and does not support shape-adaptive dispatch yet.

Decision: **multi-shape Pareto measurement complete; repair rule not justified**.
The next action is to compare the frontier records against feature/entity
provenance and local wall-dev, then read the queued transition and feature
repair papers before opening an opt-in transaction card.

### 2026-07-27 — Phase-0 β-margin revalidation

The existing report-only census was revalidated without changing mesh
generation or acceptance. The cube fixture reports `100%` hex,
`score_che=1.0`, one cluster, volume `1.0`, and β pass. A synthetic
positive-volume thin-corner fixture reports corner Jacobian `0.01` and fails a
diagnostic `beta=0.1` margin while leaving the generation and permanent
negative-volume gates untouched. This closes the measurement/diagnostic
sub-card only; it does not authorize replacing the production gate with
β-margin yet.

Verification: Phase-0 metric and transition-related tests `16 passed`, core
native-hex regression subset `66 passed`. The default mixed-level and wall-fit
flags remain unchanged.

### 2026-07-31 HEX-BL-ORIENTED-BOX-CONTRACT-1 — bounded rigid-frame extension

Cycle39's default-OFF fixed-outer inward shell was extended from one AABB to one
certified orthogonal box under rigid rotation. A C++23 certificate assigns every
source vertex, edge, and face exactly one box role before the unchanged inward
constructor runs. Rotated unit BL1 and arbitrary-SO(3) `2x3x4` BL3 requests now
fulfil `2/2` instead of `0/2`, with source drift `0`, invalid/inverted cells `0`,
exact `8/8` point and `6/6` face provenance, and deterministic three-run hashes.

The `%.9g` writer serialization envelope is frozen at `8*sqrt(epsilon)` and is
tested immediately below and above. A `1e-3` shear and a near-degenerate side
remain byte-preserving refusals. AABB output hashes, BL0/OFF behavior, thickness
bound, validity/Jacobian gates, and atomic transaction remain exact.

Decision: **L1_PASS / EXPERIMENTAL_KEEP, default OFF**. This is not the
`HEX-SHEET-2` general-CAD mechanism and does not pass Gate 7. Ridge/corner
topology, partial patch selection, multi-cell core coupling, narrow gaps, and
layer-front collision remain separate report-first prerequisites. Evidence:
`hex_oriented_box_inward_shell_2026-07-31.md`; full native-Hex tests `241 passed`.
