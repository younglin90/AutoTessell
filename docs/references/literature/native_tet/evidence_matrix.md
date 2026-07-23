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
