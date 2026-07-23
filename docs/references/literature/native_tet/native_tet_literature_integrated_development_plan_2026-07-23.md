# Native Tet Quality: Literature-Integrated Development Plan

Date: 2026-07-23
Status: implementation plan, not a solved-quality claim
Primary target: close the four open native_tet problems (FSL 61 wedges, naca residual
skew ~60.3, CYLSKEW near-wall skew, thin-disk/needle wedge fallback) using only the
20 ledger cards in `evidence_matrix.md`, without violating the exact-surface invariant
(ROADMAP.md, Governing invariant 1). Evidence base: 12 FULL_READ papers consolidated
in `docs/references/literature/native_tet/evidence_matrix.md`; per-paper notes cited
inline.

## 1. Executive decision

1. **The FSL wedge attack is sequenced diagnosis-first, not fix-first.** The "61
   unflippable wedges" label was established against plain 2-3/3-2/4-4 flips
   (ROADMAP.md FSL1-FSL4). Dassi 2018 (`dassi2018_moving_mesh_lazy_flips.md`) and
   Ni 2017 (`ni2017_sliver_shape_matching.md`, TET-SHAPE-3a) independently predict
   that stronger compound topology ops — lazy recursive edge removal and multi-face
   removal — may unlock a *combinatorially* blocked subset. So `TET-LAZY-1` +
   `TET-SHAPE-3(a)` run FIRST: cheap, transactional (bit-exact rollback), and their
   outcome partitions the 61 wedges into search-unlockable vs needs-topology-change,
   which decides everything downstream (weight pumping, insertion, or nothing).
2. **Interior-only weight pumping is the second FSL wave, gated by a classifier.**
   Cheng & Dey 2003's boundary machinery is unusable (Steiner points *on* input
   facets, non-acute input assumption — `cheng2003_weighted_delaunay_refinement.md`),
   but its forbidden-interval analysis transplants cleanly: `TET-WDEL-2` classifies
   survivors PUMPABLE/LOCKED (diagnostic), then `TET-WDEL-1` pumps only PUMPABLE
   interior-vertex slivers. LOCKED/surface-pinned wedges skip to wave three.
3. **Guarded contract/split/insert is last resort, not default.** Dassi 2018 states
   exactly-coplanar wedges are unflippable at any search depth; their remedy is the
   stagnation schedule, not deeper search. `TET-MM-2` (and `TET-SHAPE-3(b)`
   GSM-gradient-directed insertion) run only on the residual after waves 1-2, with
   cell-count budgets — they are the only FSL cards that change cell count by
   design.
4. **Smoothing is upgraded along two explicitly separated axes.** The Dassi-vs-Leng
   ablation nuance is encoded in the metrics each stage owns: Dassi 2018's ablation
   shows *MMPDE smoothing* is where that paper wins (distribution: mean dihedral
   ~69.6°, smallest sigma), while Leng 2013's 92-grain ablation shows *flips, not
   geometric motion, drive worst-case gains* (min Q 0.009 smoothing-only vs 0.26
   with transforms — `leng2013_geometric_flow.md`). Therefore smoothing cards
   (`TET-MM-1`, `TET-FLOW-2`, `TET-SHAPE-2`) own distribution metrics (mean skew,
   sigma, non-ortho percentiles); flip cards (`TET-LAZY-2`, `TET-FLOW-3`) own
   worst-case metrics (max skew, min dihedral). A card is judged only on the axis
   it owns; improving one axis while silently regressing the other is a rollback.
5. **Recovery/Steiner minimization is a separate bounded lane.** Chen 2017 *is* the
   bounded recovery policy we wanted (`l_max` escalation, 3-strike stall, BRC
   monotone budgets — `chen2017_shell_transformation.md`) and contributes nothing
   to sliver quality by its own admission. `TET-SHELL-1/2/3` live in the
   recovery/repair lane only — never the main insertion loop, never gating the
   quality phases.
6. **The near-wall skew lane continues CYLSKEW, measurement-first.** CYLSKEW5
   (proxy/final correlation — the one case checked disagreed, ROADMAP.md) resolves
   first so new near-wall mechanisms do not stack on an uncorrelated selector.
   Then `TET-WDEL-3` (clearance-triggered refinement: simulate the worst-case
   repair perturbation before attempting it) and `TET-BCC-SEED-INTERIOR` extend
   the lane Garimella offset-ring seeding (CYLSKEW1, 44.9→40.8) opened.
7. **Rejections (as binding as adoptions; details in section 5).** (a) Whole-engine
   BCC resampling — approximates rather than preserves the surface (Wang & Yu 2012)
   — violates Governing invariant 1. (b) Boundary-moving passes (Leng fairing, Ni
   resample/slide, Dassi RBF) — excluded; only tangential+exact-reprojection
   (`TET-FLOW-1`) is even considered, behind a surface-hash gate. (c) GSM as
   primary energy — no inversion barrier, 2-3 orders slower (Ni 2017); gate/blend
   term only. (d) Non-deterministic parallelism — Wang 2024 itself admits
   "unpredictable randomness"; extreme metrics drift both directions.
8. **Test-only certification becomes permanent infrastructure.** `TET-BCC-CERT-HARNESS`
   (sampled worst-case dihedral floor per decomposition template) would have caught
   the FSL coplanar wedge template's zero angle floor before it shipped
   (`wang2012_feature_sensitive_bcc.md`). Phase 0; CI fails on any zero floor.
9. **Parallelism is LAST, behind a deterministic round-based design.** `TET-PAR-0`
   (serial instrumentation, zero output change) precedes `TET-PAR-1` (deterministic
   fixed-priority rounds, bench-only, env-flag OFF), per ROADMAP's "parallelism
   deliberately LAST" invariant; Wang 2024 confirms the determinism gate is the
   real risk, not the speedup.
10. **No card claims a theoretical guarantee.** Every quality theorem in the corpus
    is practically vacuous (Cheng & Dey), sampled rather than proven (Wang & Yu
    5.71° floor), or empirical (Ni, Dassi, Leng). All acceptance is by measurement.

## 2. Current measured bottleneck

Numbers from `ROADMAP.md` section A-2 (revalidated 2026-07-19) and the current
canonical bench baseline (`tests/stl/verify_autoresearch_mesh_matrix.py`,
`tests/bench_quality_matrix.py`):

| Quantity | Value | Source / consequence |
| --- | ---: | --- |
| naca residual max skew | ~60.3 | Regression-locked baseline after THINSLIVER2 falsified the stale-diagnosis fix; a real fix needs fresh diagnosis against *this* state (ROADMAP.md). |
| FSL unflippable wedges (dual_torus) | 61 | Structurally coplanar-flat; 0/9 eligible under plain 2-3 flips; cure target pinned xfail(strict) in `tests/test_native_tet_dual_torus_limit.py`. |
| dual_torus volume tiling lock | 0.99 | Permanent floor — no card may trade tiling for shape quality. |
| cylinder max skew | 40.8 | After CYLSKEW1 offset-ring seeding (4160→44.9→40.8); CYLSKEW5 proxy/final correlation open. |
| worst mean-ratio quality (worst_mq) | 0.208 | Current bench baseline; distribution-axis target for the smoothing upgrade. |
| bench wall-clock budget | 59.1 s | Full best-of-two already falsified for doubling this (CYLSKEW4); every card must fit the budget or run off-default. |
| NACA / torus pass states | skew 1.98 / non-ortho 57.41 at N=2,000; skew 3.53 / non-ortho 58.36 at 2,317 cells | Permanent gates — must not regress. |
| thin disks / needles | legacy wedge fallback | Requested thickness and N cannot both form quality tets; `TET-BCC-DIAG-OPT` targets the split quality inside the fallback. |
| 12-STL hard-geometry sweep | pending | Phase 0 measurement closes this gap before any new mechanism. |

## 3. Card sequence

Effort: S ≈ 1 card-day, M ≈ 2-4, L ≈ 5+. Every card's acceptance additionally
requires: all permanent gates green (surface-area identity, zero off-surface
boundary, cylinder wall dev 0.000, volume tiling ≥ 0.99, NACA/torus pass states),
byte-identical repeat runs, bench ≤ 59.1 s unless off-default.

### Phase 0 — Measurement and certification (no mesh-output change)

Cards: 12-STL hard-geometry sweep (ROADMAP open item, not a ledger card) —
re-baselines every downstream claim on the canonical script; `TET-WDEL-2` [S] —
forbidden-interval classifier on the 61 dual_torus wedges and the CYLSKEW near-wall
population → PUMPABLE/LOCKED taxonomy, *reporting* prediction accuracy rather than
assuming Delaunay stars (Cheng & Dey 2003); `TET-BCC-CERT-HARNESS` [M] — sampled
dihedral floor per native_tet split/wedge template, CI fails on floor = 0 (Wang &
Yu 2012); `TET-SHAPE-1` [S] — per-tet GSM score as read-only secondary rollback
gate (4 face areas + 1 volume, no SVD — Ni 2017), calibrated on the sweep output.

Acceptance: zero mesh diffs anywhere; classifier + harness reports stored as bench
evidence. Rollback: n/a (read-only).

### Phase 1 — FSL wedge attack (dual_torus)

Wave 1 [S-M]: `TET-LAZY-1` (recursive compound flips, depth 1-2, in-array flip log,
bit-exact rollback — Dassi 2018) + `TET-SHAPE-3(a)` (edge/multi-face removal under
per-tet-average GSM decrease — Ni 2017). Interior edges only; boundary-edge wedges
recorded out-of-scope (Dassi does not develop the boundary variant).
Wave 2 [M]: `TET-WDEL-1` interior-only weight pumping over the PUMPABLE survivors
from `TET-WDEL-2`'s taxonomy (Cheng & Dey 2003). Atomic rollback; final mesh stores
unweighted vertices (weight selects connectivity only).
Wave 3 [M-L]: `TET-MM-2` guarded contract/split/1-to-4 insert (Dassi 2018) and/or
`TET-SHAPE-3(b)` GSM-gradient-directed Steiner insertion (Ni 2017) on the residual.
Cell-count growth budgeted (< few %, < #wedges x cavity size); contraction near the
boundary forbidden outright.
Prevention [M, parallel track]: `TET-BCC-SNAP-LAMBDA` lambda-snapping at insertion
so near-degenerate children are not born (Wang & Yu 2012); every snap envelope-gated,
surface-area-identity gate as hard veto.

Decision tree:
- If wave 1 unlocks ≥ 30% of the 61 wedges → rerun `TET-WDEL-2`; if the residual
  PUMPABLE set is empty, skip `TET-WDEL-1` and go to wave 3 sizing.
- If `TET-WDEL-2` accuracy < 90% on wave-2 outcomes → demote the classifier to
  advisory and let `TET-WDEL-1` sweep all interior-vertex survivors.
- If waves 1-3 cure the xfail(strict) target in
  `tests/test_native_tet_dual_torus_limit.py` → `TET-BCC-SNAP-LAMBDA` becomes
  optional hardening; if ≥ 20 wedges remain → SNAP-LAMBDA promotes to wave 4.

Acceptance: wedge count strictly decreases per wave; volume tiling ≥ 0.99; the
xfail(strict) alarm is the phase exit. Rollback: any wave that breaks a permanent
gate is reverted whole (transactions make this exact). Evidence: Dassi 2018,
Ni 2017, Cheng & Dey 2003, Wang & Yu 2012.

### Phase 2 — Smoothing/flip upgrade (naca skew ~60.3 + worst_mq 0.208)

Cards: `TET-FLOW-2` [S] (penalized active-set interior smoothing replacing plain
Laplacian — Leng 2013), `TET-MM-1` [M] (frozen-boundary MMPDE, boundary velocities
hard-zeroed, energy-decrease enforced explicitly since the explicit RK is not
algebraically stable — Dassi 2018), `TET-SHAPE-2` [M] (GSM-blended interior pass,
AMIPS/signed-volume guard kept — Ni 2017), `TET-LAZY-2` [S] (dual flip criterion
alternating min/max angle with aspect ratio — Dassi 2018), `TET-FLOW-3` [M]
(rising-threshold smoothing/flip ladder, epsilon 0.4→0.8 — Leng 2013).

Axis ownership (decision 4): `TET-FLOW-2`/`TET-MM-1`/`TET-SHAPE-2` are accepted on
distribution metrics (worst_mq 0.208 → up, sigma down, non-ortho percentiles down);
`TET-LAZY-2`/`TET-FLOW-3` on worst-case metrics (naca max skew < 60, min dihedral
up). Each candidate is measured alone against the Phase 0 baseline before stacking
(THINSLIVER2: zero measured effect → discarded, not kept).

Decision tree:
- Run `TET-FLOW-2` first (cheapest). If naca worst-case does not move (expected per
  Leng's ablation), that is *not* failure — check the distribution axis.
- If `TET-MM-1` and `TET-SHAPE-2` both pass alone, keep only the better one unless
  stacking is additive on the bench (avoid unexercised complexity).
- If the worst-case axis is still ≥ 60 after `TET-LAZY-2` + `TET-FLOW-3` → the
  residual is near-wall class; hand it to Phase 3 rather than deepening Phase 2.

Acceptance/rollback: per-axis as above; per-pass cost must keep bench ≤ 59.1 s
(Dassi has no timing data — the budget check is itself part of acceptance).
Evidence: Leng 2013, Dassi 2018, Ni 2017.

### Phase 3 — Near-wall skew lane (cylinder 40.8, CYLSKEW continuation)

Cards: CYLSKEW5 [S] (proxy/final correlation, default-ON decision — ROADMAP open
item, the phase's measurement card), `TET-WDEL-3` [M] (clearance-triggered near-wall
refinement, budget-capped, < 2% extra vertices — Cheng & Dey 2003),
`TET-BCC-SEED-INTERIOR` [M] (BCC lattice interior seeding behind a feature flag,
complements Garimella offset rings — Wang & Yu 2012), `TET-FLOW-1` [L] (tangential
boundary smoothing + exact closest-point re-projection — Leng 2013).

Decision tree:
- If CYLSKEW5 shows the Delaunay proxy does not correlate → the best-of-two
  selector stays default-OFF; this phase's cards are measured against the plain
  default path.
- `TET-FLOW-1` is the only card in the plan that touches boundary vertices.
  Admissible only under "tangential + exact re-projection with surface-hash gate":
  if the surface hash or surface-area identity changes at all, the card is rejected
  permanently, not tuned. It runs last, and only if `TET-WDEL-3` +
  `TET-BCC-SEED-INTERIOR` leave cylinder skew > 20.

Acceptance: cylinder skew < 40.8 monotone per card; sphere N=500 class regressions
(the CYLSKEW2-4 falsification history) re-checked every card. Evidence: Cheng & Dey
2003, Wang & Yu 2012, Leng 2013, ROADMAP CYLSKEW record.

### Phase 4 — Recovery/Steiner lane + thin-disk fallback (bounded, independent)

Cards: `TET-SHELL-1` [L] (recursive shell transformation, `l_max` escalation,
3-strike stall exit), `TET-SHELL-2` [M] (Q2 intersection-count flip objective,
trendwise gating — transient rises are expected per the paper's Table 3),
`TET-SHELL-3` [M] (Christmas-tree Steiner suppression post-pass) — all Chen 2017;
`TET-BCC-DIAG-OPT` [S] (worst-dihedral-aware diagonal selection in the thin-disk
wedge fallback — Wang & Yu 2012).

This lane never blocks Phases 1-3 and runs only in the recovery/repair path (Chen
2017 contributes nothing to sliver quality; its recovery is measurably slower than
TetGen's, so it stays off the hot path). `TET-BCC-DIAG-OPT` is independent — purely
local, deterministic, no surface motion — and can land any time. Acceptance:
unrecovered-constraint and Steiner counts down with zero recovered-constraint
regressions (BRC monotonicity); thin-disk regression set worst dihedral improves
with no case regressing. Evidence: Chen 2017, Wang & Yu 2012.

### Cross-engine flag (from the native_tri 2026-07-24 read batch)

**TET-ENV-EXACT1** [M, measurement-first]: `core/generator/native_tet/envelope.py`
cites the Wang 2020 exact-envelope idea in its docstring but implements a sampled
point-to-surface BVH check — the inexact failure mode Wang 2020 documents inside
fTetWild itself (invariant breakage → locking, over-refinement, eps-dependent
cost; 895,518 → 50,781 tets once replaced). Upgrade candidate: exact containment
(prisms + LPI/TPI predicates — `../native_tri/wang2020_exact_envelope.md`).
Measurement first: reproduce a locking/over-refinement case before porting.

### Phase 5 — Parallelism (LAST)

Cards: `TET-PAR-0` [M] (serial conflict-neighborhood instrumentation, zero output
change), then `TET-PAR-1` [L] (deterministic fixed-priority rounds, vertex-token
try-lock, thread-local arenas; bench-only, env-flag OFF — Wang 2024). Entry
condition: Phases 1-3 closed and their gates permanent, so correctness gates can
catch parallel nondeterminism (ROADMAP: the dead-zone lesson). Acceptance:
bit-identical polyMesh across repeated runs AND across 1/2/4/8 threads; quality
parity within existing NativeMeshChecker gates; speedup is tertiary. Evidence:
Wang 2024.

## 4. Invariant compliance table

Boundary motion must be NO or "tangential + exact-reprojection with surface-hash
gate" (Governing invariant 1).

| Card | Moves boundary vertices? | Changes cell count? | Determinism risk |
| --- | --- | --- | --- |
| TET-WDEL-2 | No (read-only) | No | None |
| TET-BCC-CERT-HARNESS | Test-only | n/a | None |
| TET-SHAPE-1 | No (scoring only) | No | None |
| TET-LAZY-1 | No (interior edges only) | Yes (local flips, no new vertices) | Low (fixed traversal order) |
| TET-SHAPE-3 | No | (a) flips only; (b) yes, budgeted insertion | Low |
| TET-WDEL-1 | No (interior stars only) | Yes (connectivity flips, no new vertices) | Low (flip-event ordering fixed) |
| TET-MM-2 | No (interior entities; near-boundary contraction forbidden) | Yes (budgeted) | Medium (schedule ordering) |
| TET-BCC-SNAP-LAMBDA | Conditional: snap at insertion, envelope-gated per snap; surface-area-identity gate is the veto | Yes (fewer splits) | Low |
| TET-FLOW-2 | No | No | Low |
| TET-MM-1 | No (boundary velocity hard-zeroed) | No | Low (float summation order pinned) |
| TET-SHAPE-2 | No (boundary hard-pinned) | No | Low |
| TET-LAZY-2 | No | Yes (flips) | Low (needs per-edge no-progress counter) |
| TET-FLOW-3 | No (rejects boundary-facet changes) | Yes (flips/edge removals) | Low |
| CYLSKEW5 (ROADMAP) | No | No (selector decision only) | Low |
| TET-WDEL-3 | No (interior Steiner only) | Yes (< 2% vertices, budget-capped) | Low |
| TET-BCC-SEED-INTERIOR | No (strictly inside envelope) | Yes (seed count) | Low (lattice is deterministic) |
| TET-FLOW-1 | Tangential + exact-reprojection with surface-hash gate | No | Medium (projection ties) |
| TET-SHELL-1/2/3 | No (recovery lane, interior ops) | Yes (flips; SHELL-3 removes points) | Low-medium (DP tie-breaking must be pinned) |
| TET-BCC-DIAG-OPT | No | No | None |
| TET-PAR-0 | No | No (serial, no output change) | None |
| TET-PAR-1 | No | No (same ops as serial) | Controlled: deterministic rounds are the acceptance criterion itself |

## 5. What we will NOT do

- **Whole-engine BCC/octree resampling** — output boundary only approximates the
  input surface; the authors themselves rule it out for exact preservation
  (Wang & Yu 2012, `wang2012_feature_sensitive_bcc.md`).
- **Normal-direction boundary motion of any kind** — Leng 2013's fairing, Ni 2017's
  boundary resample/slide, Dassi 2018's RBF mode all smooth or approximate the
  input surface (per-paper notes; evidence_matrix.md rows).
- **GSM as the primary optimization energy** — no inversion barrier, 2-3 orders of
  magnitude slower; finds no sliver class AMIPS misses (Ni 2017).
- **Cheng & Dey boundary-conformity machinery** — Steiner vertices on input
  segments/facets by design; non-acute input assumption fatal for real CAD
  (`cheng2003_weighted_delaunay_refinement.md`).
- **Full sliver exudation as an engine precondition** — ratio-property assumptions
  not representable in our API today (Cheng 2000, evidence_matrix.md: `future`).
- **Non-deterministic parallelism** — Wang 2024 admits unpredictable randomness and
  only statistical parity; the determinism gate is strengthened, not waived.
- **Claiming literature guarantees for the current engine** — the mixed pipeline
  cannot inherit either the CDT or Wild guarantee as a whole (evidence_matrix.md).
- **Keeping mechanisms with zero measured effect** — THINSLIVER2 precedent
  (ROADMAP.md): unexercised complexity is deleted, not shelved.

## 6. Measurement-first protocol

Per ROADMAP's method note ("measure before planning — guessing refuted 4+ times"),
every phase opens with a measurement card; no mechanism lands on a stale baseline:
- Phase 0 *is* the measurement phase (12-STL sweep, `TET-WDEL-2` taxonomy,
  `TET-BCC-CERT-HARNESS` floors, `TET-SHAPE-1` calibration).
- Phase 1 opens with `TET-LAZY-1`/`TET-SHAPE-3(a)` in *diagnostic* mode: the
  combinatorial-vs-geometric wedge split is the measurement; fixes commit only
  after the split is recorded.
- Phase 2 opens by re-measuring naca/worst_mq on the post-Phase-1 mesh (the ~60.3
  baseline moved under stacked cards once already — THINSLIVER2 — and can again).
- Phase 3 opens with CYLSKEW5 (correlation measurement) before any new mechanism.
- Phase 4 opens by counting unrecovered constraints and Steiner points on the
  bench suite before `TET-SHELL-1` is written.
- Phase 5 opens with `TET-PAR-0` (P_overlap measurement, fully serial).

One canonical measurement script per geometry (ROADMAP method); benches:
`tests/stl/verify_autoresearch_mesh_matrix.py`, `tests/bench_quality_matrix.py`,
`tests/verify_goal.py`; permanent-gate suites include
`tests/test_native_tet_dual_torus_limit.py` (xfail-strict cure alarm + 0.99 tiling
lock) and `tests/test_native_tet_thin_sliver.py`. Every card stores before/after
evidence against the phase's opening measurement, uses relative (never absolute)
guards, and is reverted whole on any permanent-gate failure.
