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
