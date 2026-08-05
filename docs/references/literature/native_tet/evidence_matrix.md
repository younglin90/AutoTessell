# Native Tet evidence matrix

## Full-read primary sources

| Source | Status | Boundary/recovery evidence | Quality/termination evidence | Native Tet decision |
|---|---|---|---|---|
| Shewchuk 1998, DOI `10.1145/276884.276894` | FULL_READ, 10/10 pages | encroached subsegment/subfacet priority; conforming PLC recovery | `B > 2` grading/termination under projection condition; no sliver guarantee | implement proof-carrying refinement only in clean PLC mode |
| Si 2015, DOI `10.1145/2629697` | FULL_READ, 36/36 pages | protected CDT, recursive flip/edge removal, face recovery, Steiner suppression | constrained refinement terminates at `B >= 2`; relaxed radii localize small-angle debt; empirical dihedral cleanup | replace midpoint-only recovery with protected-complex transactions |
| Hu et al. 2020, DOI `10.1145/3386569.3392385` | FULL_READ, 18/18 pages | incremental triangle insertion, snapping, 41-case subdivision table, rejected-face retry | exact-positive validity and epsilon tracked-surface guarantee; no final quality theorem | separate Wild engine; do not label present BSP+B-W loop fTetWild-equivalent |
| Si 2010, DOI `10.1134/S0965542510010069` | FULL_READ, 16/16 pages | constrained segment/facet recovery and quality-aware Delaunay refinement for finite-volume compatible meshes | bounded-angle assumptions for guaranteed behavior; finite-volume context informs why quality is tied to recovery schedule | apply as PLC-side quality policy reference with explicit angle/termination prechecks |
| Wang & Yu 2012 (Feature-sensitive BCC), DOI `10.1016/j.cad.2012.01.002` | FULL_READ, 13/13 pages | adaptive octree + BCC lattice with lambda-snapping and optimal stencil decomposition; output boundary only *approximates* the input surface — authors state the method is inappropriate when the input surface must be precisely preserved | the "guaranteed > 5.71°" min-dihedral floor (lambda = 0.2) is a **sampled computer-aided verification** (200-point discretization per edge segment, no interval/continuity argument), not a continuous theorem; lambda-dependent (2.86°–14.3°); interior regular BCC tets are 45° analytic | REJECTED as engine path — violates the surface-preservation invariant; reuse local mechanisms only: lambda-snap at insertion (`TET-BCC-SNAP-LAMBDA`), dihedral-aware diagonal selection (`TET-BCC-DIAG-OPT`), BCC interior seeding (`TET-BCC-SEED-INTERIOR`), sampled worst-case certification harness (`TET-BCC-CERT-HARNESS`) |
| Cheng et al. 2000, DOI `10.1145/355483.355487` | FULL_TEXT_READ, 22/22 pages | weighted regular triangulation + sliver exudation via deterministic weight pumping; full algorithm path reviewed under ratio-property-like assumptions | radius-edge-only bounds are insufficient; can be evaluated as long-horizon sliver robustness layer after robust PLC/Wild foundations are stable | mark as `future` unless ratio-property prechecks and bounded-boundary assumptions are both represented in API |
| Cheng & Dey 2003, DOI `10.1137/S0097539703418808` | FULL_READ, 25/25 pages | QualMesh Rules 1/2/4 insert Steiner vertices *on* input segments/facets and re-triangulate facet interiors — **violates the exact-surface invariant by design**; the non-acute (>= 90°) input-angle assumption is fatal for real CAD | first deterministic boundary-conforming no-sliver theorem (Thm 7.6 + 7.2), but the authors admit the constants are "miserably unsatisfactory" — `rho0 > 4`, `sigma0` extremely small, so the guarantee is practically vacuous; only near-exact degeneracies are excluded | boundary-conformity machinery unusable; only **interior-only weight pumping** is transplantable: `TET-WDEL-1` (interior pumping over locked-sliver stars), `TET-WDEL-2` (forbidden-interval PUMPABLE/LOCKED classifier, diagnostic), `TET-WDEL-3` (clearance-triggered near-wall refinement) |
| Chen et al. 2017 (Shell transformation), DOI `10.1016/j.apm.2017.07.011` | FULL_READ, 27/27 pages | recursive shell transformation (DP-optimal partial triangulations + lexicographic quality vector + BRC monotone budgets, `l_max` escalation, 3-strike stall exit) — the bounded-recovery-policy verdict is **confirmed**: the paper *is* that bounded policy; ~TetGen-level Steiner counts, 5–10x fewer than GHS3D, 0 Steiner points on F16 CFD workloads | contributes **NOTHING to sliver quality** — FSL-class geometrically flat wedges yield no valid better covering mesh and the transform correctly refuses; recovery is markedly slower than TetGen's (0.4–6.3 s vs 0.05–0.33 s on the 7-model bench) | strong for Steiner minimization in the recovery/repair lane only, never the main insertion loop: `TET-SHELL-1` (recursive ST recovery), `TET-SHELL-2` (intersection-metric Q2 flip objective), `TET-SHELL-3` (Christmas-tree Steiner suppression) |
| Leng et al. 2013, DOI `10.1016/j.cad.2013.05.004` | FULL_READ, 16/16 pages | normal-motion fairing (curve diffusion + averaged mean-curvature flow) *deliberately moves boundary vertices off the input surface* — **EXCLUDED**; only the tangential-only regularization/smoothing branches are separable, and even those need an exact re-projection step onto the input triangulation (tangents come from a smooth quadratic-fit proxy) | their own 92-grain ablation shows **flips, not geometric motion, drive worst-quality gains** (geometric optimization alone reaches min Q 0.009 vs 0.26 with topological transforms); no vertex insertion by design — admitted open problem near non-manifold boundaries; no termination proof | port only tangential/interior machinery with exact re-projection: `TET-FLOW-1` (tangent-projected boundary smoothing + exact re-projection), `TET-FLOW-2` (penalized active-set interior smoothing, replaces plain Laplacian), `TET-FLOW-3` (rising-threshold smoothing/flip ladder scheduler) |
| Ni et al. 2017, DOI `10.1016/j.cagd.2017.02.004` | FULL_READ, 30/30 pages | boundary is resampled and slid along the surface (vertex budget re-estimated via BCC model, tangent-slide + closest-point projection) — **only interior-vertex GSM smoothing is importable**; the energy has **no inversion barrier** (validity rests solely on line-search rejection) | GSM = `sum 1/lambda_i^2` — exactly the inverse half of symmetric Dirichlet — finds **no sliver class AMIPS misses** (both diverge on every near-degenerate tet); what changes is a much steeper barrier (`lambda_min^-2` vs AMIPS `lambda_min^-2/3`); results are empirical only (theta_min not monotone, no theorem); **2–3 orders of magnitude slower** than CGAL local optimizers | top actionable: **re-test the 61 FSL wedges against edge/multi-face removal** before concluding insertion is mandatory (`TET-SHAPE-3`); `TET-SHAPE-1` (cheap GSM score as secondary rollback gate), `TET-SHAPE-2` (interior GSM-blended smoothing, boundary hard-pinned, keep AMIPS/signed-volume guard) |
| Dassi et al. 2018, DOI `10.1016/j.cad.2017.11.010` | FULL_READ, 12/12 pages | lazy recursive edge removal (`flipnm`) targets **exactly our "no adjacent improving flip" failure** — when no adjacent face flips, remove an *adjacent edge* first (in-array flip log, bit-exact reversal, depth-bounded); the RBF pass **smooths the input surface** and must be dropped; frozen-boundary mode (MMPDE interior smoothing + lazy interior flips, TetGen `-Y`) still beats Stellar and is invariant-compliant | **exactly-coplanar wedges remain unflippable at any search depth** (their remedy is contract/split/1-to-4 insert, not deeper search); the MMPDE validity guarantee requires energy-diminishing integration, which the explicit Dormand–Prince RK used does **not** formally satisfy; no timing data anywhere in the paper | adopt the frozen-boundary subset as `TET-IMPROVE-1`-style transactions: `TET-LAZY-1` (recursive compound flips — run FIRST, cheaply splits combinatorial vs geometric blockers among the 61 wedges), `TET-LAZY-2` (dual flip criterion), `TET-MM-1` (frozen-boundary MMPDE smoothing), `TET-MM-2` (guarded contract/split/insert stagnation schedule) |
| Wang et al. 2024, DOI `10.1016/j.advengsoft.2024.103782` | FULL_READ, 12/12 pages | conflict neighborhood = cavity + one-ring ambient, guarded by **vertex-token try-lock** (pessimistic postpone, serial kernel unchanged, no rollback) + coordinate-sort partitioning; **boundary/surface preservation is absent from the conflict model** — our #1 invariant is never addressed | **explicitly non-deterministic** — the paper itself admits task overlap introduces "unpredictable randomness"; equivalence claim is statistical parity only (extreme metrics drift both directions vs serial, e.g. AR_max 194.4 → 4.23); ~10.2x at 16T, but **graph coloring is the scaling bottleneck** (~25–27% of time at only ~55–62% efficiency) | determinism gate **confirmed and strengthened**; prefer Wang's pessimistic pre-lock over Mahmoud-style speculative rollback for our guarded-transaction architecture (slots in as one more guard before commit); bench-only cards, parallel enable LAST: `TET-PAR-0` (conflict-neighborhood instrumentation, serial), `TET-PAR-1` (deterministic round-based parallel pass, env-flag OFF) |

## Claim audit

| Claim | Verdict | Reason |
|---|---|---|
| "Input edge presence implies CDT" | REJECT | CDT also requires locally Delaunay unconstrained faces with constraint visibility. |
| "Boundary vertices inside epsilon imply Hausdorff <= epsilon" | REJECT | Edge/triangle interiors and reverse coverage are unchecked. |
| "Radius-edge bound eliminates slivers" | REJECT | Canonical slivers can have acceptable radius-edge and arbitrarily bad dihedrals. |
| "The current main loop implements fTetWild" | REJECT | Core incremental insertion table, cover tracking, atomic rollback, and retry queue are absent. |
| "Watertight manifold is required by every tet engine" | REJECT | Clean CDT needs a valid PLC; Wild accepts soup but only gives approximate/heuristic region semantics. |
| "Deleting bad interior tets is a valid sliver fix" | REJECT | It creates void boundaries; quality must improve through topology/geometry transactions. |

## Priority implementation cards

| Priority | Card | Mechanical acceptance criterion |
|---|---|---|
| P0 | TET-WILD-1 incremental triangle transaction | all 41 cut classes and adjacency pairs preserve exact-positive, conforming connectivity |
| P0 | TET-WILD-3 triangle envelope containment | adversarial interior excursion fails despite endpoints passing |
| P0 | TET-CDT-1 protected-complex recovery | recovered segments/faces never disappear; blockers are typed |
| P0 | TET-CDT-2 local CDT certificate | deliberate non-CDT interior face fails despite 100% input-edge coverage |
| P1 | TET-CDT-3 relaxed insertion radius | acute fan terminates and skinny debt is feature-localized |
| P1 | TET-WILD-2 tracked cover/retry | rejected near-degenerate face inserts after optimization without provenance loss |
| P1 | TET-WILD-4 stable AMIPS | all vertex permutations yield the same transaction decision |
| P1 | TET-DR-2 honest sliver gate | canonical sliver passes radius-edge but fails dihedral/volume gate |
| P2 | TET-WILD-5 volume semantics | open/nested adversarial models return explicit heuristic/unsupported flags |
| P1 | TET-IMPROVE-2 shape-energy gate | canonical sliver should fail a shape-distance score even when radius-edge bound passes |
| P2 | TET-IMPROVE-3 parallel determinism replay | parallel-improvement run on fixed seed produces identical boundary/topology deltas on replay |

## 2026-07-27 full-read addition - thin-section coverage

| Paper | Coverage | Pages | DOI | Evidence status | Production decision |
|---|---|---:|---|---|---|
| Garimella & Shephard 1999 | deficient thickness-path detection; opposite-entity search; anisotropic split and wedge realignment | 17/17 | `10.1007/s003660050013` | full text + rendered first page | add `TET-THIN-COUNT-1` as report-only coverage audit before any repair. A requested through-thickness element count is distinct from sliver quality. Do not port boundary-node repositioning or unguarded swaps; any later interior-only repair needs boundary hash/key/area, signed-volume, and deterministic-transaction gates |

## Candidate card ledger (2026-07-23 full-read batch)

All cards contributed by the seven FULL_READ upgrades above, grouped by open
problem. One line each: card — mechanism (source note). Details, acceptance
signals, and risks live in the per-paper notes.

### FSL: 61 structurally coplanar-flat unflippable wedges (dual_torus)

- `TET-SHAPE-3` — re-test the wedges against edge/**multi-face removal** (stronger than the 2-3/3-2/4-4 flips the "unflippable" label was set against), then GSM-gradient-directed Steiner insertion for survivors (Ni 2017). **Top actionable.**
- `TET-LAZY-1` — reversible recursive compound flips (`flipnm`, depth 1–2, in-array flip log, bit-exact rollback); run FIRST to split combinatorial vs geometric blockers (Dassi 2018).
- `TET-WDEL-1` — interior-only weight pumping over locked-sliver vertex stars, atomic rollback (Cheng & Dey 2003).
- `TET-WDEL-2` — forbidden-interval PUMPABLE/LOCKED sliver classifier, diagnostic-only (Cheng & Dey 2003).
- `TET-MM-2` — guarded contract/split/1-to-4-insert stagnation schedule for wedges surviving `TET-LAZY-1` (Dassi 2018).
- `TET-BCC-SNAP-LAMBDA` — lambda-threshold vertex snapping at insertion, preventing near-degenerate children at birth, envelope-gated per snap (Wang & Yu 2012).
- `TET-FLOW-2` — penalized active-set interior smoothing (`sum (1/Q - 1/0.9)^4`) replacing plain Laplacian, boundary bitwise untouched (Leng 2013).

### naca residual skew ~60.3

- `TET-LAZY-2` — dual flip criterion: alternate (max theta_min AND min theta_max) with aspect ratio across rounds (Dassi 2018).
- `TET-SHAPE-2` — interior GSM-blended smoothing with the steeper `1/h^2` barrier, boundary hard-pinned, signed-volume guard kept (Ni 2017).
- `TET-FLOW-1` — tangent-projected boundary vertex smoothing + **exact closest-point re-projection** onto the input surface (Leng 2013).

### CYLSKEW near-wall skew

- `TET-MM-1` — frozen-boundary MMPDE gradient-flow smoothing (Huang functional, analytic velocities, energy-monotone transactional stage) (Dassi 2018).
- `TET-WDEL-3` — clearance-triggered near-wall refinement (Rule-4 transplant: simulate worst-case repair perturbation before attempting it) (Cheng & Dey 2003).
- `TET-BCC-SEED-INTERIOR` — BCC interior lattice seeding inside the envelope so the bulk starts at 45°/60°/90° quality (Wang & Yu 2012).

### Boundary recovery / Steiner minimization

- `TET-SHELL-1` — recursive shell transformation: DP-optimal partial triangulations + lexicographic Qv + BRC budgets + `l_max` escalation (Chen 2017).
- `TET-SHELL-2` — intersection-count (Q2) flip objective for recovery stalls where shape-based flips plateau (Chen 2017).
- `TET-SHELL-3` — Christmas-tree Steiner/vertex suppression post-pass (Chen 2017).

### Thin-disk / needle fallback

- `TET-BCC-DIAG-OPT` — worst-dihedral-aware quad-face diagonal selection (lambda comparison + dihedral tie-break) in wedge/prism decomposition (Wang & Yu 2012).

### Quality gating

- `TET-SHAPE-1` — per-tet GSM score (face areas + volume; no SVD, no orientation branch) as secondary rollback gate beside dihedral + signed-volume (Ni 2017).

### Scheduling

- `TET-FLOW-3` — rising-threshold smoothing/flip ladder (epsilon 0.4 -> 0.8; per bad tet try all face/edge removals, apply argmax-of-worst) (Leng 2013).

### Test-only

- `TET-BCC-CERT-HARNESS` — sampled worst-case dihedral certification harness over our own split/wedge templates; CI fails on any zero-floor template (Wang & Yu 2012).

### Parallelism (LAST — only after the determinism gate)

- `TET-PAR-0` — cavity + one-ring-ambient conflict-neighborhood instrumentation and P_overlap measurement, fully serial, no output change (Wang 2024).
- `TET-PAR-1` — deterministic round-based vertex-token parallel topology pass; bench-only, env-flag OFF by default (Wang 2024).

## Current conclusion

Native Tet should become two native engines sharing predicates, adjacency, and
quality metrics: a protected **CDT engine** for valid PLC input and an
epsilon-tolerant **Wild engine** for triangle soups. The present mixed pipeline
contains useful pieces but cannot inherit either literature guarantee as a whole.

## TET-SHAPE-2 measured result (2026-07-26)

Status: **accepted as default-OFF, opt-in implementation**. The pass uses the
Ni et al. (2017) inverse-height GSM term blended with AMIPS for interior
vertices only. Boundary vertices are hard-pinned; no topology changes are
performed. Each candidate keeps signed-volume and exact Shewchuk orientation
guards and rolls back transactionally on any invariant failure.

Fixed-primal A/B used GSM weight `0.35` and three sweeps. Results are shown as
before -> after:

| Mesh | dihedral sigma | p10 Q | mean Q | Q < 0.01 | min dihedral |
| --- | ---: | ---: | ---: | ---: | ---: |
| naca | 38.0361 -> 37.7855 | 0.0090373 -> 0.0090719 | 0.147488 -> 0.147886 | 286 -> 283 | non-regression |
| cylinder | 37.5345 -> 36.9345 | 0.0156791 -> 0.0176092 | 0.124164 -> 0.127693 | 0 -> 0 | improved |
| sphere | 23.9885 -> 23.5983 | 0.110698 -> 0.112298 | 0.252632 -> 0.254319 | 5 -> 0 | improved |

Combined A/B wall time was approximately `22.5 s`, below the `59.1 s`
budget. Repeated metrics were bit-identical. Focused verification passed
`7 passed, 2 xfailed`; the dual-torus strict-xfail status was preserved. The
production flag remains OFF pending broader shape coverage.

## TET-MM-1 falsification evidence (2026-07-26)

Decision: **KILL; no production implementation retained.** The fixed offline
inputs were `/tmp/flow2/naca.npz` (SHA-256
`11b0edb1abbbeb1aa725895289e2ca0cbb7f86ed65174068bf6d728d01842c7f`,
902 points / 3,968 tets / 320 surface-prefix vertices) and
`/tmp/flow2/cyl.npz` (SHA-256
`79cd4d87e66dcc176db61aca962ff000a7e66a4da224918ac2e5fce00b79887f`,
764 points / 3,439 tets / 256 surface-prefix vertices). FLOW2 was not invoked
or stacked.

The transient implementation reproduced Huang/Dassi `theta=1/3`, `p=3/2`,
reference volume `1/#T_h`, analytic Eq. (5) velocities, and Eq. (6)
simultaneous assembly. Adaptive Euler candidates required strict energy
decrease and exact Shewchuk orientation-sign identity; all boundary vertices
were hard-frozen, float volume was pre-reject-only, and every whole pass was
transactional. Ten transient tests passed, including analytic velocity vs
central finite differences and forced rollback.

| Mesh | sigma deg | p10 Q | mean Q | Q<0.01 | worst-axis deg | energy | runtime |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| naca | 49.8757425641 -> 49.8694148005 | 0.00282716828546 -> 0.00282901034042 | 0.114134158101 -> 0.114139899338 | 1,233 -> 1,230 | 109.409377256 -> 108.927329223 | 1.444518818e9 -> 2.886145637e7 | 0.438 s |
| cylinder | 53.1846875244 -> 53.1425416062 | 0.000806259842474 -> 0.000806259841863 | 0.0542198110543 -> 0.0542350375272 | 1,349 -> 1,348 | 109.436098944 -> 109.386629583 | 7.965874710e10 -> 1.056072997e8 | 0.355 s |

Invariant gates all passed on both meshes: every accepted energy step was
strictly decreasing; exact orientation, boundary bytes/face set/area,
input/connectivity/count, and deterministic replay were preserved. Combined
mechanism runtime was `0.792 s`, below the `59.1 s` budget. The decisive gate
was cylinder p10: it decreased by `6.11e-13` instead of strictly increasing.
A 32-cell step-count/step-fraction sweep found no GO cell; cylinder p10 was
negative in every cell (best delta `-9.29e-15`). Per the diagnostic-first stop
rule, the mechanism was removed instead of integrated or tuned behind a flag.
## 2026-07-27 — TET-CDT-SCALE-PERF-1

- **Measured:** native-tet dual-torus fine reached CDT recovery but did not
  finish within 480 s. Three zero-insert outer rounds took about 102/107/112 s;
  plateau exit worked, while later edge-flip/BSP recovery was still running.
- **Wrong-tier exclusion:** the naca hard-12 300 s timeout was `tier_wildmesh`,
  so it is not native-tet performance evidence.
- **Fixed replay:** `/tmp/cdt_state_dump.npz`, 3,251 points / 17,720 tets /
  2,047 surface vertices / 4,096 faces. `check_edge_recovery` 0.081 s; one CDT
  cycle 15.15 s; targeted flip 13.35 s of that time.
- **Opt-in implementation:** `AUTO_TESSELL_TET_EDGE_FLIP_INDEX=1` adds stable
  row and adjacency indexes. Result is byte-identical to legacy: 152 recovered,
  452 missing, same tetra array. Targeted flip 12.72 s -> 1.34 s (9.48x);
  one-cycle CDT 15.15 s -> 3.79 s (4.00x). Three focused tests passed.
- **Decision:** promising opt-in performance card; default remains OFF pending
  fine end-to-end replay, permanent gates, strict-xfail, and determinism.

## 2026-07-27 — TET-BSP-SCALE-PERF-1

- Fixed state: 1,032 missing faces / 17,720 tets / 500-point budget. Scalar BSP
  proposal `59.537 s`; existing batch proposal `1.503 s`. Proposal point/tet
  sets differ, so no equivalence is claimed.
- Opt-in controls were added only for measurement:
  `AUTO_TESSELL_TET_BSP_BATCH=1` and optional
  `AUTO_TESSELL_TET_BSP_MAX_POINTS`; scalar remains the default.
- Real fine replay with indexed edge flip + batch BSP + 500-point cap reached
  downstream in about 246 s but failed integrity/quality:
  `cdt_face_ratio=0.452`, `n_val_flipped=4621`, `n_val_degen=6`, grade B, then
  timed out during retry. The combination is falsified as default-on.
- **Decision:** retain measurement hooks, keep scalar BSP default, and open a
  correctness-first BSP recovery card before further optimization.

## 2026-07-27 — TET-BSP-RECOVERY-CORRECTNESS-1

- **Measured violation:** on `/tmp/cdt_state_dump.npz`, a 500-point BSP/B-W
  candidate changed the missing constrained-face count from `1,032` to
  `1,076`; adding points was therefore not evidence of recovery.
- **Guard:** after B-W plus surface snap, compare missing-face count and
  physical boundary area against the pre-candidate state. Reject and restore
  the whole candidate when the missing count is not strictly lower, the
  boundary area changes, or the scale-relative non-positive/degenerate tet
  count increases. Apply the same rule to the full re-Delaunay fallback.
- **Scope:** no change to default scalar-vs-batch selection; batch remains
  opt-in and no equivalence is claimed. The guard is correctness-first and
  does not yet prove full PLC conformity.
- **Verification:** `python3 -m py_compile` plus Phase-F, CDT-recovery, and
  draft dual-torus tests: `16 passed, 2 xfailed`.
- **Status:** implemented minimal guard; fine replay and permanent-gate sweep
  remain before card closure.
- **Fine replay:** indexed edge flip + opt-in batch BSP + 500-point cap still
  timed out at the 480 s case limit (`504.7 s` wall including runner cleanup);
no final quality verdict was available. Keep the guard and both optimization
hooks out of the default path.

### Fixed-state timing split

The same fixed state (`17,720` tets, `1,032` missing faces) was measured
without changing the production path:

| stage | time | result |
|---|---:|---|
| scalar BSP | `60.1438 s` | 500 points proposed, 2,046 tets subdivided |
| batch BSP | `1.4736 s` | 500 points proposed, 445 tets subdivided |
| Bowyer–Watson | `13.3494 s` | 139 points inserted, cavity total 1,783 |

After batch BSP plus B-W, missing faces worsened `1,032→1,076`, boundary
area stayed `103.399255187455`, and non-positive/degenerate count improved
`8964→8587`. The candidate is still rejected because constrained-face
recovery did not strictly improve. The measured B-W adjacency rebuild cost is
not a valid optimization target until a conforming candidate exists.

## 2026-07-27 — TET-CDT-EDGE-FACE-MONOTONE-1 diagnostic

On the fixed state, indexed targeted 2-3 edge flips (200 attempts) recovered
`152` edges. Missing edges changed `604→452`; missing faces changed
`1032→779`; boundary face keys and physical area were unchanged. The
scale-relative non-positive/degenerate count changed `8964→9071`; a follow-up
orientation audit showed 107 additional negative orientations, while the
degenerate count stayed `131→131`. The existing final orientation-normalization
stage repairs those signs by swapping vertices.

All `1,032` missing faces already had all three surface vertices in the mesh,
but no missing face had all three input edges present. `176` missing faces had
one present edge and `856` had two. This makes edge recovery a prerequisite
for face recovery and falsifies a point-only BSP interpretation.

Decision: **measured and guarded opt-in**. `AUTO_TESSELL_TET_EDGE_FLIP_GUARD=1`
now performs a candidate-level local boundary-key and scale-relative
non-degeneracy check before each indexed 2-3 flip. The synthetic valid
bipyramid case was accepted and the coplanar case was rejected with rollback.
On the fixed state, the guard preserved missing edges `604→452`, missing faces
`1032→779`, and boundary keys/area; with a sorted candidate order, the bounded
run produced missing edges `604→455`, one guard rejection, and identical
`17,869×4` tetra arrays across two repetitions. Boundary faces remained
`1320→1320` and area remained
`103.399255187455→103.399255187455`. Negative orientation alone is not
rejected because the existing deterministic orientation-normalization stage
handles it. The flag remains OFF by default pending full-pipeline fine replay,
permanent gates, and repeated-run byte-identity evidence.

### 2026-07-27 — edge candidate-order determinism

Before the fix, the fixed state gave `152/452`, `149/455`, and `144/460`
recovered/missing edges for raw, sorted, and reversed candidate orders. The
recovery function now canonicalizes and sorts candidate edge keys before the
bounded loop. Raw, sorted, and reversed inputs now all give `149` recovered,
`455` missing, one guard rejection, and the same `17,869×4` tetra array
(`a4890384ba9752aea224a9f35a255922d475e832c75923591ce16f4b3723156f`). A
two-bipyramid regression test passes. The focused native-tet gate is
`19 passed, 2 xfailed`; full-pipeline fine determinism remains open.

## 2026-07-27 — BETA2832 multi-body coverage

The preprocessor component-filter WIP was remeasured on
`high_genus_dual_torus.stl`: `num_components=2`, `n_kept=2`, `n_dropped=0`,
`area_ratio=1.0094878`, `vol_ratio=1.0097687`, `cells=11071`, `degen=0`, and
`neg_vol=0` in `129.1 s`. This passes the card's `area_ratio≥0.9` and
`vol_ratio≥0.9` coverage gates and falsifies the earlier half-body loss.
`max_skew=2.2101786e6` and low CDT recovery remain; they are a separate
quality/recovery card, not evidence against the component-preservation fix.
Cube/cylinder smoke and the solid-volume/dual-torus regression set remained
green (`7 passed, 1 xfailed`); cylinder's known quality lane still reports
`skew=44.9` and `non-ortho=89.2`.

## 2026-07-27 — BETA2834 edge-recovery comparison

The production harness still passes `enable_edge_recovery=False`; the indexed
environment flag alone therefore had no effect, and the real dual-torus run
remained at `cdt_ratio=0.005`, `max_skew=2.21e6`. A direct opt-in run with
`enable_edge_recovery=True` improved `cdt_ratio .881→.925`,
`cdt_face_ratio .707→.800`, and `mean_q .1482→.1524`, but worsened plane
coverage `.897→.880` and runtime `6.73→14.24 s`. This is a measured
trade-off, not an accepted fix; a surface-conformity transaction is required
before any wiring or default promotion.

An opt-in stage snapshot further showed `50` midpoint/B-W insertions with
missing edges unchanged at `682`, while the complete edge-recovery lane
preserved boundary faces `1352→1352` and area
`103.399255187455→103.399255187455`. Thus the plane-coverage decrease is not
caused by a boundary-key/area violation in the edge lane. The residual issue
belongs to the later recovery/BSP/quality interaction and is not repaired by
adding another local boundary guard without new evidence.

### 2026-07-27 — fixed-condition direct A/B replay (`target_cells=600`)

Using the same high-genus dual-torus input, P4C disabled, indexed candidate
ordering, and the guard enabled, the direct replay gave:

| lane | cells | points | cdt edge | cdt face | plane | plane area | mean q | elapsed |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| edge OFF | 12219 | 2855 | 0.89665 | 0.73291 | 0.93168 | 0.94605 | 0.15154 | 6.41 s |
| edge ON | 12616 | 2903 | 0.93229 | 0.81763 | 0.91149 | 0.93789 | 0.15749 | 13.66 s |

The edge lane preserved its own boundary snapshot, but a later BSP candidate
was rejected by the boundary guard (`1195` added faces, `492` removed, area
`84.3611→115.1185`). Edge recovery improves constraint ratios while worsening
surface coverage and roughly doubling runtime. It remains opt-in; this replay
does not justify default promotion.

### 2026-07-27 — full-fine direct A/B replay (`target_cells=15000`)

The same fixed-condition replay was extended to the fine-sized target. The
results were:

| lane | cells | points | cdt edge | cdt face | plane | plane area | mean q | degen | wall |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| edge OFF | 17458 | 4453 | 0.80518 | 0.46509 | 0.68116 | 0.66596 | 0.14912 | 6 | 29.16 s |
| edge ON | 17914 | 4535 | 0.80518 | 0.46509 | 0.68116 | 0.66596 | 0.15234 | 6 | 36.93 s |

The ON lane inserted `85` midpoint points and recovered `55` targeted edges
in its own stage while preserving the boundary snapshot, but downstream
stages converged to the same final constraint/coverage/degen values. The only
material changes were a small mean-quality increase, `456` extra cells, and a
`7.77 s` wall-time penalty. Indexed edge recovery and its guard remain opt-in
measurement hooks; no default promotion or gate relaxation is justified.

### 2026-07-27 — bounded replay revalidation

The same `target_cells=600`, P4C-off, indexed-order, guard-on protocol was
rerun against the current worktree. It reproduced the prior final counts and
ratios: edge OFF `12219/2855`, `0.89665/0.73291`, plane/area
`0.93168/0.94605`, mean q `0.15154`; edge ON `12616/2903`,
`0.93229/0.81763`, plane/area `0.91149/0.93789`, mean q `0.15749`.
Measured wall time was `26.53 s` OFF and `34.15 s` ON (the result object's
mesher elapsed was `6.59 s` and `12.88 s`). This confirms the bounded replay
is current-code reproducible at the statistic level. It does not close the
full-fine card: the existing `480 s` fine BSP replay remains a timeout with no
final quality result, so the opt-in lane stays OFF.

### 2026-07-27 — current fine-route edge A/B revalidation

The current worktree was replayed at `target_cells=15000` with the indexed
edge-flip guard enabled. This route entered the existing `_phase_bc_skip`
fallback, so it is not equivalent to the earlier fixed-condition CDT/BSP
replay and must not be used to close that card.

| lane | wall | cells | points | grade | mean q | boundary snapshot |
|---|---:|---:|---:|---|---:|---|
| edge OFF | `14.35 s` | `13,970` | `3,920` | A | `0.3255` | not entered |
| edge ON + batch/BSP cap 500 | `134.42 s` | `13,788` | `3,881` | A | `0.3237` | exact before/after: `1560` faces, area `103.399255187455` |

The ON lane inserted `85` edge points and recovered `48+7` indexed flips;
the boundary snapshot remained exact, but the final fallback cells and points
differed and `cdt_ratio/cdt_face_ratio/plane_coverage/plane_area` were `-1`
because the phase gate was skipped. The rerun confirms no observed boundary
violation in the guarded edge-recovery snapshot, but it does not provide a
conforming fine replay or justify default promotion. Both lanes remain
measurement-only. The same run logged metric/GAP as skipped because
`_tet_boundary_faces` was unbound in that current WIP route; this is recorded
as a separate caller bug and not folded into the BSP card.

### 2026-07-27 — TET-METRIC-GAP-BOUNDARY-IMPORT1

The current fine-route log exposed a caller-scope defect: `_tet_boundary_faces`
was imported only inside the conditional JJ3 smoothing block, while the later
metric-tensor and GAP-SELF blocks referenced that name even when
`_phase_bc_skip=True`. Both stages were therefore silently reported as
skipped. The minimal fix imports the same helper locally in each of those two
blocks; no lock set, operator, acceptance threshold, or boundary policy was
changed.

After the fix, the `target_cells=600` replay executed both stages in OFF and ON
runs (`native_tet_metric_tensor_sweep` and
`native_tet_gap_self_amips_multistage` appeared in both logs). OFF returned
`15,353` cells / `4,044` points, grade A, mean q `0.3448`, wall `12.02 s`; ON
with batch cap 500 returned `16,483` / `4,303`, grade A, mean q `0.3672`, wall
`72.45 s`. The edge ON boundary snapshot remained exact at `1,320` faces and
area `103.399255187455`. Focused regression tests were `15 passed, 1 xfailed`;
the unrelated `test_native_tet_stellar.py` import mismatch remains outside
this two-import fix.

The fixed-condition recovery gate itself also remains green: edge-recovery,
CDT-recovery, and dual-torus-limit tests reported `7 passed, 1 xfailed`.

### Fixed-condition full-fine revalidation after caller fix

With `AUTO_TESSELL_P4C_PYTETWILD=0`, indexed ordering, boundary guard, and the
same target `15000`, the current worktree reproduced the fixed-condition fine
comparison:

| lane | wall | cells | points | cdt edge/face | plane/area | mean q | grade |
|---|---:|---:|---:|---:|---:|---:|---|
| edge OFF | `31.40 s` | `17458` | `4453` | `.80518/.46509` | `.68116/.66596` | `.14912` | B |
| edge ON + batch cap 500 | `151.75 s` | `17914` | `4535` | `.80518/.46509` | `.68116/.66596` | `.15234` | B |

The ON lane retained its local boundary transaction and reached the same
final constraint/coverage/degen statistics as OFF, with only `456` extra
cells, a mean-quality increase, and a runtime penalty. This closes the
fixed-condition **measurement** portion of `TET-BSP-RECOVERY-CORRECTNESS-1`:
the opt-in edge/BSP lane remains OFF because it does not improve the final
constraint metrics and costs about `4.8x` wall time at this fine target.
The current-route `_phase_bc_skip` replay remains a separate route and is not
used for this conclusion.

### 2026-07-27 — FSL wave-1 lazy-removal recheck (`TET-LAZY-1` + `TET-SHAPE-3(a)`)

The current fixed FSL mesh (`research/quality-harness/_fsl4_mesh.npz`, input point digest
`698e6fd3eca2982d88ef590ba04f2d29dbbcd7d2f78ff83e3405a2e9eb6bcff3`, tet
digest `1c5c190f596395339df5a9a5c9a2ae5ce9c24832299c58c6004b64ce68e1cc8f`)
was reclassified with the existing diagnostic-only wave-1 runner. It contains
61 core flat wedges. Depth-1 Dassi-style edge removal found an improving,
transactionally admissible retriangulation for 60 wedges; 1 wedge remained
structurally blocked after depth-1, depth-2 side-edge attempts, and the
exhaustive multi-face-removal fallback. The read-only classification itself
did not mutate the input.

Applying the same guarded sequence only to a private copy changed the tet count
from `12,219` to `12,159`, preserved the exact `4,588`-face boundary set, and
changed mean shape quality `0.1515436139 → 0.1522083893`. The global minimum
quality remained `7.3576387e-09`, so this wave does not close the worst-case
quality gate. No surface vertex moved. The one residual is consistent with the
literature's exactly-flat geometric obstruction, not an untested boundary
topology failure. The wave remains `AUTO_TESSELL_FSL_WAVE1` opt-in; no default
promotion is justified without the permanent-gate, full-engine replay.

### 2026-07-27 — bounded dual-criterion recheck (`TET-LAZY-2`)

The same mesh was passed to the read-only dual-criterion diagnostic with two
rounds, the deterministic first `128` sorted interior edges per round, and one
no-progress retry per edge. The mesh has `10,497` interior edges and an initial
boundary of `4,588` faces (area `83.428951465389`). All `128` candidate records
were rejected by `no_improving_retriangulation` before the aspect-ratio round
could be reached: accepted `0`, criteria seen `angle` only, sequence decision
`rollback`. Sampled boundary face sets and areas were exact, and the input
point/tet digests were unchanged. Baseline metrics were mean quality
`0.1515436135`, minimum quality `7.3576387e-09`, minimum dihedral
`1.7160638e-05°`, maximum dihedral `179.9999988°`, and maximum aspect ratio
`3.6828626e7`.

This is a bounded falsification of the current candidate generator/quality
gate on the sampled prefix, not evidence that every deeper candidate is
impossible. It gives no mechanism to promote, and no production code or
threshold was changed. A future LAZY-2 implementation would need a separately
validated orientation-preserving candidate constructor and a larger, explicitly
budgeted scan before any gate decision.

### 2026-07-27 — `TET-FLOW-3` bounded ladder diagnostic

Because no FLOW-3 implementation existed, a default-OFF diagnostic module was
added without mesher wiring. It evaluates candidate-local 2-3 face flips,
4-4 ring-cycle flips, and the existing general edge-removal primitive under
the same boundary, signed-volume/tiling, and global-minimum-quality guards.
The operation tie-break is deterministic (`face23 < edge44 < edge removal`),
and the caller arrays are never mutated.

On the fixed FSL mesh, five epsilon rungs (`0.4, 0.5, 0.6, 0.7, 0.8`), one
round per rung, and a bounded eight bad-tet prefix produced `364` candidate
records and `2` private-copy accepts (`1` edge removal, `1` edge-44). No
boundary or volume guard was violated. The private candidate state was
`12219→12218` tets with boundary `4588→4588`; candidate mean quality changed
`0.1515436139→0.1515648424`, but candidate minimum quality stayed
`7.3576387e-09`, so the whole sequence correctly rolled back and returned the
unchanged input. The returned result is therefore `12219` tets, mean quality
`0.1515436139`, and input digest unchanged.

The cost is not acceptable for promotion in this form: the eight-bad-tet
bounded run took about `26.4 s`, while a 32-bad-tet / five-rung run exceeded
the `120 s` diagnostic timeout. This is a falsification of the naive
candidate-by-candidate global-array implementation, not of Leng's scheduler
itself. The module remains measurement-only; the next implementation card is
to cache local incidence/quality state or use a true cavity-local evaluator
before reconsidering a production ladder.

### 2026-07-27 — `TET-SHAPE-1` / `TET-WDEL-2` diagnostic closure

The missing Phase-0 helpers were added as report-only utilities. The GSM score
implements Ni et al.'s face-area/volume expression with each tet's mean squared
edge as the local scale and is normalized so a regular unit tet scores `1.0`.
Calibration measured regular `1.000000` and a flat calibration tet
`0.00053598`; the focused shape/certification tests passed `3/3`.

The WDEL-2 classifier is explicitly a proxy, not Cheng--Dey's theorem: the
current API has neither a Delaunay-like star certificate nor the exact weight
interval/radius data. It classifies `Q/q_flat` against a configurable floor.
On the fixed FSL mesh it reported `152` candidates (`90` PUMPABLE, `62`
LOCKED), with `75` all-surface candidates. Against the 61 core wedges and the
actual guarded wave-1 result, the proxy predicted only `4` PUMPABLE and `57`
LOCKED, while wave-1 unlocked `60` and left `1` blocked. Agreement was `5/61`
(`8.2%`), far below the `>=90%` acceptance signal. The proxy is therefore
**measured, falsified**, and is not used to route WDEL-1 or WDEL-3. Its
implementation remains diagnostic-only so the failed result is reproducible;
the exact interval classifier needs richer star/weight data before reopening.

### 2026-07-27 — `TET-DET-P4C` determinism obstruction

Before opening the WDEL-3 near-wall classifier, the same native_tet cylinder
route (`target_cells=2000`, BSP/edge-recovery/Phase-B/C off) was run twice in
one process with identical input arrays. The Delaunay stage was byte-stable at
every observed call: all point-input and simplex digests matched. The final
native self-implementation with `AUTO_TESSELL_P4C_PYTETWILD=0` was also
byte-identical (`353` points, `1869` tets in both runs).

The default P4-C external fallback was not stable. Direct calls to the installed
`pytetwild 0.2.3` wrapper produced different outputs on every repeat, including
`num_threads=1` and `optimize=False`. For the same cylinder input and
`edge_length_fac=0.09343`, three runs with `num_threads=0` returned
`581–618` points and `2358–2544` cells; three runs with `num_threads=1`
returned `603–670` points and `2436–2743` cells. With optimization disabled,
`num_threads=1` still returned `2587–2646` points and `7808–7948` cells.

The source-level cause is explicit in the bundled fTetWild source:
`vendor/dependencies/fTetWild/src/TriangleInsertion.cpp` uses `std::random_device` to
seed `std::mt19937` before shuffling input faces. A diagnostic rebuild replacing
that one seed with `42` was compiled and tested, but fresh processes still
returned different outputs. Other fTetWild paths use unordered-container
iteration and additional mutable ordering, so fixing the first shuffle is not
sufficient. This is therefore an external-fallback determinism defect, not a
Delaunay or native local-operator defect. The one-line fixed-seed experiment is
**measured, insufficient/falsified as a complete fix**, and the source/binary
was restored to the original behavior. No production default was changed.
The next card must either normalize all relevant fTetWild order sources or
define a deterministic self-native lane; P4-C cannot satisfy a byte-identical
contract in its current form.

A second A/B disabled the vendored fTetWild TBB build entirely and kept
`max_threads=1`; three fresh-process runs still differed (`584/2400`,
`597/2394`, and `588/2429` points/cells). The TBB-off result is therefore also
**measured, falsified** as a sufficient fix. The build was restored to the
normal TBB-enabled configuration. Full fTetWild ordering normalization is a
structural task, not a safe one-line improvement.

### 2026-07-27 — `TET-FLOW-3` cavity-local cache recheck

Profiling showed that `general_edge_removal` rebuilt full face/edge incidence
maps for every candidate. A private diagnostic-only cache now reuses the
round-local maps until a candidate is actually selected; no production mesher
path is wired to it. The 32-bad-tet, five-rung replay changed from about
`60.3 s` to `1.84 s` with identical candidate count (`1474`), accepts (`5`),
candidate tet count (`12219→12216`), candidate mean quality
(`.1515436139→.1515902449`), unchanged minimum quality
(`7.3576387e-09`), exact boundary `4588`, and final rollback.

The larger bounded replay (`128` bad tets, two rounds per rung, five rungs)
completed in `6.02 s`, examined `11859` candidates, accepted `10` private
operations, preserved boundary faces `4588→4588`, and improved candidate mean
quality to `.1516671466`; the global minimum remained
`7.3576387e-09`, so the sequence correctly rolled back. The cache is a
performance success but not a worst-case quality closure; FLOW-3 remains
diagnostic/default-OFF.

### 2026-07-27 — `TET-DET-RESULT1` and boundary-preservation continuation

The first result-contract audit found that `NativeTetResult.n_points/n_cells`
and the returned arrays could refer to different W3 candidates, while the
on-disk `polyMesh` still referred to the earlier write. A final write and
final-array synchronization were added at the return boundary. The focused
cylinder contract test now verifies array counts, serialized point values,
owner/neighbour cell counts, and disk/in-memory agreement (`1 passed`).

The same audit exposed the previously hidden naca late-pass boundary defects.
The pre-W3 writer had `696` boundary faces; the old bulk collapse path produced
`984` after NN1 by deleting unrelated sign-flipped tets. A candidate-level
collapse lane now rejects duplicate/zero/sign-flip non-edge incident tets and
requires exact boundary key/area preservation in the default lane. The naca
fixture accepted `188` safe collapses in the guarded lane, while boundary
remained `696→696`.

The post-BSP 4-4 lane was independently measured: 2-3 and 3-2 preserved the
boundary, while the old 4-4 `sorted(set(ring))` implementation changed
`984→1008`. A cycle-reconstructing, sequential candidate guard now rejects
non-cycles, non-positive/tile-breaking candidates, and boundary changes. The
post-BSP quality boundary snapshot is now `696→696`.

The VVV8 boundary-Laplacian path was the remaining geometry-only violation:
keys stayed at `696`, but area changed. Its candidate is now accepted only when
the shared boundary invariant (keys and area) passes. The final naca
thin-sliver gate is `2 passed, 1 strict xfailed`; pure-Python boundary skew is
`<=70`, the internal prewrite probe reports `60.399`, boundary faces remain
`696`, and the final run reports `1853` cells, `902` points, mean quality
`0.1852`, and `0` validation degenerates.

These changes are still uncommitted WIP. The log-only stage probes show
`post_best_of`, `post_NN1`, `post_RR1`, `post_EEE`, `post_NNN/CVT`, and
`post_VVV14` preserve the `696` boundary in the fixed path; the old violations
are retained as measured root-cause evidence rather than hidden by the final
write.
### 2026-07-27 hard-geometry matrix continuation

Measurement-only sweep: `scripts/bench_native_tet_matrix.py`, P4C/pytetwild
fallback OFF, draft, target/max cells 2000, per-shape timeout 120 s. The
serialized final-result contract now agrees with the in-memory mesh. Results:

| shape | cells | area ratio | volume ratio | degen | max skew | verdict | time |
|---|---:|---:|---:|---:|---:|---|---:|
| cube | 40 | 1.000 | 1.000 | 0 | 2.36 | PASS | 22 s |
| cylinder | 212 | 1.000 | 1.000 | 0 | 3.32 | PASS | 24 s |
| sphere / sphere_watertight | 2177 | 1.000 | 1.009 | 0 | 2.15 | PASS | 14 s |
| naca0012 | 1844 | 1.000 | 1.001 | 0 | 34.80 | FAIL (quality) | 22 s |
| trimesh_box / isolated_box | 40 | 1.000 | 1.000 | 0 | 4.17 / 2.36 | PASS | 22--23 s |
| very_thin_disk_0_01mm | 1036 | 38.057 | 2957.910 | 7 | 1.18e6 | FAIL (geometry) | 21 s |
| extreme_aspect_ratio_needle | 104 | 1.000 | 1.002 | 0 | 559.20 | FAIL (quality) | 1 s |
| high_genus_dual_torus | -- | -- | -- | -- | -- | TIMEOUT | 120 s |
| multi_scale_sphere_with_micro_spikes | 2108 | 0.996 | 1.005 | 0 | 1.25 | PASS | 6 s |
| many_small_features_perforated_plate | -- | -- | -- | -- | -- | TIMEOUT | 120 s |
| sharp_features_micro_ridge | 853 | 2.304 | 6.168 | 95 | 8.60e28 | FAIL (input/geometry) | 17 s |

This is not evidence for relaxing any permanent gate: naca surface/volume and
degeneracy are now sound, but its all-cell skew remains above the quality gate.
The two timeout cases are performance/coverage cards, and the thin-disk and
micro-ridge rows are geometry/topology cards. No code change is accepted from
this measurement alone.

### 2026-07-27 — result-contract and target-floor continuation

The final-result path now writes the synchronized final arrays exactly once in
FINAL-SYNC. `tests/test_native_tet_pass_runtime_contracts.py` passes `6/6`,
including optional evidence-only diagnostics and the stellar no-op contract;
the focused native-tet set is `19 passed, 1 strict xfailed`.

The W3 best-of selector now rejects candidates below a deterministic floor of
`ceil(0.30 * target_cells)` when the target is positive. This prevents a tiny
40-cell candidate from winning a `target_cells=2000` run merely because its
quality score is numerically better. The current hard matrix therefore selects
near-target meshes, but does not relax any gate: cube `1695` cells (area/volume
`1.096/1.053`, skew `2.44`), cylinder `2105` (`1.000/1.009`, `7.04`), sphere
`2177` (`1.000/1.009`, `2.15`), naca `1844` (`1.000/1.001`, `34.80`),
trimesh/isolated boxes `2202/1695` (skew `2.15/2.44`), thin disk `1883`
(`1.155/3.872`, `204.62`), needle `104` (`1.000/1.002`, `559.20`),
multi-scale sphere `2108` (`.996/1.005`, `1.25`), and sharp micro-ridge
`853` (`2.304/6.168`, `95` degen, `8.60e28` skew). Dual-torus and
perforated-plate remain 120-second timeouts. The matrix is `6/13` PASS under
this measurement protocol.

The micro-ridge input contract independently reports a non-watertight STL;
that row remains an input/geometry failure rather than a relaxed quality gate.
No permanent threshold changed. Remaining work is split into quality cards
for naca/cylinder, geometry/input cards for thin-disk/needle/micro-ridge, and
timeout cards for dual-torus/perforated plate.

### 2026-07-27 — literature follow-up and first report-only cards

The blocker-specific literature review is recorded in
`docs/references/literature/improvement_blockers_followup_2026-07-27.md`. The
current failures are not treated as one smoothing problem: naca/cylinder are
boundary-pinned local-quality candidates; thin disk/needle are thickness-aware
generation; dual-torus/perforated plate are CDT recovery-stage performance;
poly invalidity is concave/star topology; hex wall-fit is a fidelity-quality
Pareto problem.

`TET-THIN-SECTION-1` now has a report-only helper in
`core/generator/native_tet/thin_section.py`. It casts deterministic inward rays
from boundary-face centroids and retains unknown rays instead of guessing. The
synthetic thin-box tests recover thickness `0.05` and `1.0`, preserve input
arrays, and are deterministic (`3 passed`). An unbounded all-face Python ray
replay on the approximately 5k-face naca output was stopped after it showed
prohibitive O(F^2) behavior; this is a measured instrumentation failure, not a
geometry conclusion. A spatially accelerated or bounded-sample implementation
is required before real hard-12 census.

`TET-CDT-PROFILE1` adds report-only stage timings to `CDTRecoveryResult` for
`initial_check`, `edge_flip_recovery`, `cavity_retriangulation`,
`insertion_cycles`, `final_surface_snap`, and `final_check`; the mesher logs
the dictionary without changing acceptance. The focused CDT/thin-section set
is `6 passed`. No heavy dual-torus replay was repeated in this step, so no
stage-level timeout attribution is claimed yet.

No permanent gate, production default, surface policy, or threshold was
changed. Next measurement is a bounded/spatially accelerated thin census or a
single heavy CDT run using the new stage dictionary.

### 2026-07-27 — CDT profile precondition result

The shared permanent-gate replay of `tests/test_native_tet_dual_torus_limit.py`
completed in `135.27 s` with `1 passed, 1 strict xfailed`. It emitted no
`native_tet_cdt_recovery` event because the default test route keeps CDT
recovery disabled. A separate explicit run with
`enable_cdt_recovery=True`, `max_cycles=1`, `outer_iter=1`, and
`points_budget=20` completed in `71.7 s`, but `_phase_bc_skip` bypassed the CDT
block before the stage-timing dictionary could be produced; its result had
`cdt=-1.0`.

Therefore the current dual-torus timeout cannot yet be attributed to CDT. The
next profile must freeze a fine protocol that actually passes the phase-B/C
skip condition, then collect the new stage dictionary once. No CDT algorithm,
retry budget, or gate was changed from this measurement.

### 2026-07-27 — bounded thin-section calibration replay

`TET-THIN-SECTION-1` was changed from all-face comparison to a deterministic
64-nearest-boundary-face cKDTree candidate set. The same three calibration
STLs now complete in under one second each; this removes the observed Python
O(F^2) failure mode without claiming that a missing candidate has zero
thickness. The report retains unknown rays.

| calibration STL | min / p10 / median thickness | rays hit / boundary faces | elapsed |
|---|---:|---:|---:|
| naca0012 | `0.0026338 / 0.0087377 / 0.0989456` | `293 / 636` | `0.926 s` |
| very thin disk | `0.0100000 / 0.0100000 / 0.0100000` | `64 / 128` | `0.162 s` |
| needle | `0.0184776 / 0.0184776 / 5.0092388` | `32 / 32` | `0.020 s` |

These are raw-surface-vertex Delaunay calibration primals, not production
native-tet outputs. They validate the measurement's scale and cost only; no
thickness-driven generation decision is made. The card remains report-only.
