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

## 7. Phase 0b — rescue-dependency isolation (blocks Phase 1 until closed)

**Policy decision (2026-07-24, user-confirmed):** exact-surface (native-only,
all named rescues OFF) is now the permanent reporting default. A rescue may
still exist as a disclosed B+C fallback (CLAUDE.md policy), but no permanent
gate, xfail(strict), or ROADMAP percentage may ever be satisfied by a
rescue-produced mesh without that fact being visible in `result.route` /
`result.fallback_reason`. ROADMAP's native_tet ~85% / naca ~60.3 narrative is
suspended pending this isolation, not asserted or corrected yet.

### 7.1 What the working tree actually contains right now

The 2026-07-24 continuation audit ran on top of a large pre-existing
uncommitted change set (near_wall.py, radial_wedge.py, torus_wedge.py,
qopt.py, ftetwild_worker.py, pytetwild_worker.py, rescue_gate.py, and ~50
modified core files), not on a clean `eb846f43` tree. The naca/dual_torus
numbers in section 6 are **not yet attributable** to "rescue off" alone vs.
this other WIP. Rescue control itself is not one switch; grep of
`tier_native_tet.py` / `native_tet/mesher.py` finds 13 independent env-gated
mechanisms, most still defaulting **ON** in the current working tree:

| Flag | Working-tree default |
| --- | --- |
| `AUTO_TESSELL_FLAT_OPEN_BOX_RESCUE` | `1` (ON) |
| `AUTO_TESSELL_PLANAR_SHEET_RESCUE` | `1` (ON) |
| `AUTO_TESSELL_LARGE_SPHERE_RADIAL_RESCUE` | `1` (ON) |
| `AUTO_TESSELL_CONVEX_HULL_TET_MANY_COMPONENTS_RESCUE` | `1` (ON) |
| `AUTO_TESSELL_CAPPED_SPHEROID_HULL_RESCUE` | `1` (ON) |
| `AUTO_TESSELL_CONVEX_HULL_TET_RESCUE` | `1` (ON) |
| `AUTO_TESSELL_THIN_EXTRUSION_RESCUE` | `1` (ON) |
| `AUTO_TESSELL_CONVEX_EXTRUSION_RESCUE` | `1` (ON) |
| `AUTO_TESSELL_OPEN_CAP_HULL_GRID_RESCUE` | `0` (already OFF) |
| `AUTO_TESSELL_COMPACT_CONVEX_HULL_RESCUE` | `0` (already OFF) |
| `AUTO_TESSELL_GRID_RESCUE` | `0` (already OFF) |
| `AUTO_TESSELL_COMPONENT_GRID_RESCUE` | `0` (already OFF) |
| `AUTO_TESSELL_TORUS_WEDGE_RESCUE` | `0` (already OFF) |

`AUTO_TESSELL_TORUS_WEDGE_RESCUE` defaulting OFF already means the
dual-torus false-XPASS was **not** produced by a torus-specific mechanism —
it was almost certainly a generic hull/many-components rescue whose trigger
heuristic references bounding-box aspect ratio and Euler characteristic
(`AUTO_TESSELL_GRID_RESCUE_LOW_ASPECT_GENUS_LIMIT`,
`..._MODERATE_EULER_MIN/MAX` in `rescue_gate.py`/`mesher.py`), i.e. a
convex-hull-family fallback that can fill a multiply-connected torus as a
solid blob and still pass a volume-ratio + skew-only checker. **This is a
topology-blindness gap in the checker itself, not only a rescue-honesty
gap** — `NativeMeshChecker` should be able to detect genus/Euler-number
mismatch against the input surface independent of any rescue question.

### 7.2 Isolation protocol (run before any Phase 1 card)

1. Safety snapshot, never discard: `git stash push -u -m "tet-wip-2026-07-24-preisolation"`
   captures the *entire* current working tree (tracked + untracked) and
   returns to clean `eb846f43`. Nothing is deleted.
2. **Cell A (sanity check)** — bench the clean `eb846f43` tree as-is
   (all rescues running their original unconditional/heuristic behavior,
   no env-gates exist yet) on `naca0012.stl` and `high_genus_dual_torus.stl`.
   Expect to reproduce ROADMAP's recorded ~60.3 skew / non-timeout numbers.
   If it does NOT reproduce them, the ROADMAP numbers were already stale
   before any of tonight's work — a different, prior regression, not this one.
3. **Cell B (rescue-only isolation)** — from clean `eb846f43`, hand-apply
   *only* the env-flag additions (the 13 flags above, all set to their
   ON-preserving default so behavior is unchanged) plus explicitly export
   the 8 "still-ON" flags as `=0` at bench-invocation time (not as a code
   default edit). Re-run the same two shapes. This isolates "what does
   turning off every rescue, with zero other code changes, do to naca and
   dual_torus" — the number this cell produces is the true native-only
   capability floor.
4. **Cell C (current full WIP, rescue off)** — `git stash pop` (or
   `git stash apply`) to restore the full working tree exactly as it was
   for the 2026-07-24 audit. This reproduces skew `1436.78` / TIMEOUT
   (section 6) for comparison against Cell B.
5. **Cell D (current full WIP, rescue restored ON)** — same tree as Cell C,
   but export all "still-ON" flags back to `1` explicitly (or unset the
   overrides). This tells us whether near_wall.py/radial_wedge.py/qopt.py/
   etc. changed anything *independent* of the rescue question.
6. Decision rule: if Cell B ≈ Cell C, the regression is fully explained by
   the rescue toggle alone — the other WIP is orthogonal and can be
   evaluated on its own separate merits/cards. If Cell B and Cell C differ
   materially, some of the other ~50 modified files also regressed
   naca/dual_torus and must be bisected file-by-file before Phase 1 resumes.
   If Cell D ≠ Cell A, some of the other WIP already regressed the
   rescue-assisted path too, independent of the rescue question entirely.
7. Whatever Cell B measures becomes the new honest Phase 0 baseline recorded
   in ROADMAP.md (replacing "~60.3" / "~85%" with the measured floor and an
   explicit note that the prior number was rescue-contaminated). Do this
   edit only after Cell B is measured, not before.

### 7.3 What Phase 1 must NOT do until 7.2 closes

No FSL-wedge card (`TET-LAZY-1`, `TET-SHAPE-3`, `TET-WDEL-1`, `TET-MM-2`)
may be implemented against the naca/dual_torus baseline until Cell B's
number is the one being improved against — improving a sliver-quality
metric on top of a mesh whose area-ratio is 4.298x or that cannot terminate
in 120 s is not a meaningful measurement. The two open problems are
different in kind: naca0012's area-ratio blowup and dual_torus's timeout
are native **coverage/robustness** gaps (the algorithm cannot yet produce a
valid mesh at all), not the sliver **quality** gaps the literature cards
target. Root-causing those two failures (why does incremental insertion
balloon the boundary 4.3x on a thin sharp-trailing-edge profile; why does
the high-genus case not terminate) is new investigation work, outside the
12-paper card ledger, and should be scoped as its own measurement card
(e.g. `TET-NACA-ROOTCAUSE-1`, `TET-DUALTORUS-TIMEOUT-1`) once 7.2 confirms
they are real native gaps and not artifacts of the other WIP.

### 7.4 Phase 0b result (2026-07-24, measured; isolation incomplete)

The four-cell table and raw values are recorded in `evidence_matrix.md`.
Cell A did not reproduce the historical non-timeout dual-torus result: the
canonical 120 s driver timed out, while a diagnostic direct run completed in
126.9 s with skew `2.210e6`. Cell B matched Cell A exactly for both shapes.
The reason is mechanical and important: clean `eb846f43` predates all 13
rescue env-gate additions, so exporting the eight still-ON flags at invocation
time had no effect. Cell B is thus not a valid rescue-only measurement.

After `git stash pop`, Cell C reproduced the prior WIP naca failure
(`skew=1436.7757`, `area-ratio=4.298046`, `vol-ratio=0.835571`, `degen=2`)
and dual-torus timeout. Cell D was identical to Cell C when the eight flags
were explicitly restored to `=1`; the rescue toggle alone did not recover the
WIP path. Decision: **Cell B ≠ Cell C, and Cell D = Cell C**. Treat this as a
WIP/native-path regression isolation failure, not rescue-only closure. The
next card must be file-level root-cause bisection; Phase 1 remains blocked.

The clean dual-torus checker reported `mesh_ok=true` without a genus/Euler
mismatch field despite skew `2.210e6`. This supports recording the
topology-blindness hypothesis for a later checker card; no checker change was
made here.

Commit `8a226df8` isolates two accepted fixes from the full WIP:

- CVT3D now receives the complete current boundary/lock ID set in both passes;
  clean-tree probes measured zero boundary movement.
- Klingner local candidates are accepted only when the canonical boundary
  face set and total boundary area are preserved.

The naca collapse-lock refresh is intentionally not in this commit. With the
correct lock set (`358/358` boundary IDs and `1,068` protected edges), the bulk
collapse still changed boundary faces `712 -> 974` and area-ratio `1.000 ->
1.206`. The stale-caller diagnosis is superseded by
`TET-COLLAPSE-BULK-ROOTCAUSE-1`. The dual BSP insertion/recovery issue is tracked
as `TET-BSP-INSERT-ROOTCAUSE-1`. Both cards are open; Phase 1 remains blocked,
and the 61 structurally unflippable wedges remain strict-xfail.

## 8. 2026-07-24/25 closure: both root-cause cards resolved, hard-12 reconfirmed

`TET-COLLAPSE-BULK-ROOTCAUSE-1` root cause: `_collapse_vectorized_single_pass`
moves the keeper to the collapsed edge's midpoint; this can sign-flip a
tet that contains neither endpoint, and the naive sign-flip cleanup deleted
that tet without checking whether its removal exposed a previously-internal
face as new boundary. `flip_edges_44` had an independent instance of the same
defect class (`sorted(set(ring))` instead of the real 4-cycle order, corrupting
owner-tet reconstruction). Both fixed with the same pattern: simulate the
candidate, reject on any influence-tet duplicate/zero-volume/sign-flip or any
boundary-face-set change, never partially apply. A follow-on general
per-stage `boundary_invariant.py` checkpoint (log-only) found two further
instances in the same class — `stellar.py`'s sliver-longest-edge and
anisotropic-edge splits, and the metric-tensor/GAP-SELF AMIPS smoothing pass
(a stale-lock variant, same class as the earlier CVT fix). All four are now
fixed and committed (`8a226df8`, `b5dea314`, harness `41f4bb1b`). Net result:
naca0012 boundary skew `1436.78 -> 38.54`, degenerate tets `0`,
`test_native_tet_thin_sliver.py` `3 passed` — below the pre-WIP-regression
historical baseline (`~60.3`).

Hard-12 reconfirmed clean of new regressions: 6 PASS (cube, cylinder, sphere,
sphere_watertight, trimesh_box, external_flow_isolated_box), 4 FAIL on
pre-existing, unrelated contract gaps (thin_disk/needle BL-cell-count
contract, multi_scale_sphere disconnected components, perforated_plate cell
count — none touched by this campaign), 2 TIMEOUT (naca0012,
high_genus_dual_torus) at the hard-12 harness's 10,000-cell + 3-BL-layer
target within a 300 s budget. **Correction (2026-07-25): the naca0012
timeout is not a native_tet issue at all — `TET-NACA-SCALE-PERF-1` is
withdrawn.** Root-cause profiling of the exact harness invocation
(`tests/stl/verify_autoresearch_mesh_matrix.py:377-408`) found the case
runs `--tier wildmesh --strict-tier`, and `--strict-tier` removes every
fallback tier including `tier_native_tet` from consideration —
`generate_native_tet()` is never called for this case. The 300 s figure
measures `tier_wildmesh.py` invoking the external `wildmeshing`/TetWild
library (or, in an environment where that package isn't installed,
failing near-instantly — the two prior sessions' "26 s isolated
`generate_native_tet()` profile" and "300 s hard-12 timeout" were always
measuring two disjoint code paths, never the same one). This is a
`tier_wildmesh` / external-dependency question, out of native_tet's scope
entirely, and needs no native_tet card.

`TET-BSP-INSERT-ROOTCAUSE-1` (dual_torus) root cause: `bsp_insert_triangles_batch`
deleted tets intersected by an inserted surface triangle but did not always
regenerate replacement tets, silently returning a partial mesh that the
caller accepted as a valid candidate (minimal repro: inserting triangle
`[4,5,6]` into tet `[0,1,2,3]` produced `subdivide_set={0}` and 0 output
tets). Fixed by recomputing the actual missing-face set, enforcing
boundary-area preservation, stabilizing the point-index prefix, and
rejecting any candidate that decreases tet count. Committed `3ab4d709`
(single file, `mesher.py`, +60/-17). Verified: dual_torus low-res boundary
area restored (`163.41` candidate -> `78.57` post-guard, matching the
`78.58` pre-insertion baseline), `test_native_tet_dual_torus_limit.py`
`1 passed, 1 xfailed` maintained, `thin-sliver`+Phase-F `11 passed`,
solid-volume `4 passed`. dual_torus fine still separately times out at
330 s in the CDT stage *before* BSP even runs — a distinct, already-marginal
performance characteristic (confirmed present even on clean `eb846f43`,
119.9 s vs the 120 s canonical budget), not a new regression from this fix.

Both root-cause cards are now closed. `TET-NACA-SCALE-PERF-1` is withdrawn
(not a native_tet issue — see correction above). The dual_torus CDT-stage
timeout got a plateau-exit/caching fix (commit `1de66fee`: cache
`check_edge_recovery` across reverted cycles, exit after 3 consecutive
zero-insertion rounds instead of burning the full budget; 15-23% faster on
the profiled benchmark state, `inserted=0` outcome unchanged since the
wedges are structurally unrecoverable, `test_native_tet_dual_torus_limit.py`
stays `1 passed, 1 xfailed`). Remaining open items: the 61
structurally-unflippable wedges (still strict-xfail, out of scope for this
closure), and whether dual_torus fine now clears the 330 s budget end to
end (not independently re-measured after the plateau-exit fix).

One canonical measurement script per geometry (ROADMAP method); benches:
`tests/stl/verify_autoresearch_mesh_matrix.py`, `tests/bench_quality_matrix.py`,
`tests/verify_goal.py`; permanent-gate suites include
`tests/test_native_tet_dual_torus_limit.py` (xfail-strict cure alarm + 0.99 tiling
lock) and `tests/test_native_tet_thin_sliver.py`. Every card stores before/after
evidence against the phase's opening measurement, uses relative (never absolute)
guards, and is reverted whole on any permanent-gate failure.

## 9. 2026-07-26 -- Phase 2 opened: `TET-FLOW-2` landed (default OFF)

Phase 0 is closed (12-STL hard-geometry sweep re-run in section 8;
`TET-BCC-CERT-HARNESS` harness present) and Phase 1 Wave 1 landed as
`core/generator/native_tet/fsl_wave1.py` (commit `4c4a621a`), resolving 60 of the
61 core-unflippable coplanar wedges; the last one is structurally blocked
(ring-size 4, no improving retriangulation at any tested depth). Waves 2/3 are
**not** pursued -- the prior round's own recommendation was to skip weight
pumping with only one wedge left, and one wedge out of 12,219 tets does not
justify a dedicated near-wall-insertion wave. Phase 1 is therefore closed as
far as this campaign takes it, and the plan's next card in its own priority
order is Phase 2's cheapest [S] card, which its decision tree says to run
first: `TET-FLOW-2`.

### 9.1 What landed

`core/generator/native_tet/flow2.py` (new, ~470 lines) implements Leng et al.
2013 Eqs. 3.13-3.16: the penalized active-set energy
`E = sum_{Q <= 0.9} (1/Q - 1/0.9)^4`, minimized Gauss-Seidel style vertex by
vertex along the analytic negative first variation, with the paper's line
search (worst *local* quality must strictly improve), Remark 3.1 backtracking
(`tau <- 0.618 tau`), the 1%-of-mean-edge-length displacement cap, and the
active set recomputed after every accepted move.

Deliberate deviations, all recorded in the module docstring:

- The energy's `Q` is the smooth volume-to-length-**RMS** ratio
  `6*sqrt(2)*|V| / l_rms^3` rather than the engine's canonical
  `e_max`-denominator `quality.tet_shape_quality`, which is not
  differentiable. The canonical quality is still measured and reported
  before/after so the numbers stay comparable with every other card.
- Inversion is decided by **exact Shewchuk `orient3d`**: a move is accepted
  only if every incident tet keeps its exact pre-move orientation sign. A
  cheap float signed-volume screen is used only to *pre-reject* (conservative,
  never to accept).
- Vertices whose ring contains an exactly degenerate tet (`orient3d == 0`) are
  skipped, not repaired. Restoring a zero-volume tet is a topology problem
  (FSL / insertion cards); picking an arbitrary sign would silently re-orient
  the local tiling.
- Scope reduction: the card text says "replace plain Laplacian". It is added
  as an additional guarded pass instead, so it can be measured alone against
  the Phase 0 baseline before any existing pass is removed (plan section 3,
  "each candidate is measured alone before stacking").

Wiring: 33 lines in `core/generator/native_tet/mesher.py` immediately after the
FSL Wave 1 block, gated on `AUTO_TESSELL_TET_FLOW2=1` (**default OFF**, FSL
Wave 1 precedent) with `AUTO_TESSELL_TET_FLOW2_SWEEPS` (default 3).

### 9.2 Measured, on real benchmark meshes

Meshes dumped straight out of `generate_native_tet` via
`AUTO_TESSELL_FSL_WAVE1_DUMP`, then the pass run offline at 5 sweeps.
`Q` below is the canonical `tet_shape_quality`; skew is `mesher._skew_proxy`.

| Mesh | tets | min dihedral (deg) | min Q | mean Q | Q<0.01 | skew proxy |
| --- | ---: | --- | --- | --- | --- | --- |
| naca0012 | 3,968 | 0.0424 -> **0.1859** | 3.55e-5 -> 5.70e-5 | 0.1141 -> 0.1193 | 1233 -> 994 | 1805.2 -> **913.6** |
| 02_medium_cylinder | 3,439 | 0.0051 -> **0.1384** | 9.42e-7 -> 3.38e-5 | 0.0542 -> 0.0555 | 1349 -> 1265 | 16274.8 -> **1012.6** |
| high_genus_dual_torus | 12,219 | 0.0000 -> 0.0000 | 7.36e-9 -> 7.36e-9 | 0.1515 -> 0.1524 | 152 -> 140 | 29394932 -> 29394932 |

Energy: naca `2.55e16 -> 2.18e15` (-91%), cylinder `3.13e21 -> 4.34e15`.
dual_torus's energy and min-Q are unchanged to the last bit, and that is the
expected result, not a failure: its worst tet is one of the FSL
boundary-pinned coplanar wedges, which no *interior* vertex motion can reach.
Its distribution axis -- the axis plan decision 4 assigns to this card -- does
move (mean Q up, p10 Q 0.0584 -> 0.0601, slivers 152 -> 140). Note also that at
`Q ~ 1e-8` the `(1/Q)^4 ~ 3e31` term saturates the float64 energy sum, so the
reported energy has no resolution left for the rest of the mesh; acceptance
never depends on it (it is the per-vertex worst-local-Q line search that
gates every move).

Boundary invariant, all three meshes: `check_boundary_invariant` reports
`preserved=True`, `keys_equal=True`, boundary area identical to 12 decimals,
and boundary-vertex coordinates **bitwise** unchanged.

### 9.3 End-to-end A/B, naca0012, same seed and target

| | flow2 OFF | flow2 ON (3 sweeps) |
| --- | --- | --- |
| cells / points / boundary faces | 3968 / 902 / 696 | 3968 / 902 / 696 (identical) |
| patch sizes | [187, 189, 4, 316] | [187, 189, 4, 316] (identical) |
| run_summary mean_q | 0.1141 | **0.1173** |
| run_summary n_sliver_detected | 481 | **410** |
| hausdorff_rel | 0.089 | **0.08051** |
| plane_area_coverage | 0.889 | 0.864 |
| n_val_degen | 0 | 0 |
| grade | B | B |
| elapsed | 5.968 s | 6.093 s (+2.1%) |

Two honest caveats. (1) `plane_area_coverage` drops 0.889 -> 0.864 and VAL1's
auto-fix count `n_val_flipped` rises 289 -> 357 (with `n_val_degen` still 0).
Neither is a flow2 guard violation -- the pass's own exact-sign check verified
sign equality for all 3,968 tets before accepting -- they are *downstream*
divergence: `native_tet_surface_snap_restore` and the metric-tensor sweep run
after this pass and see different interior coordinates
(`surface_snap max_diff 0.0500 -> 0.0467`). (2) Only three shapes measured.
Both are why the flag stays **default OFF** until the broader sweep runs.

Tests: `tests/test_native_tet_flow2.py` (10 new, including an analytic-gradient
vs central-finite-difference check and an even-permutation check on the
rotation the gradient uses). Regression: flat-sliver + boundary-invariant +
solid-volume + thin-sliver + Phase-F + fsl_wave1 + flow2 = `39 passed,
1 xfailed`; `test_native_tet_dual_torus_limit.py` = `1 passed, 1 xfailed`
(the strict-xfail cure alarm and the 0.99 tiling lock both hold).

### 9.4 Next in plan order

Phase 2 continues with `TET-MM-1` / `TET-SHAPE-2` on the distribution axis and
`TET-LAZY-2` / `TET-FLOW-3` on the worst-case axis, each measured alone against
this section's numbers before any stacking. Unrelated finding to clear first:
`tests/test_native_tet_shape_gate.py` and
`tests/test_native_tet_bcc_cert_harness.py` are untracked and the former fails
at collection -- it imports `quality.tet_gsm_score` (`TET-SHAPE-1`) and
`validate.classify_flat_sliver_wdel2` (`TET-WDEL-2`), neither of which exists
in `core/`. Those two Phase 0 cards have tests but no implementation.


## 10. 2026-07-26 -- `TET-MM-1` diagnostic KILL (no production code retained)

`TET-MM-1` was implemented transiently and evaluated alone on the same fixed,
offline meshes used by section 9.2. It used the Huang functional with
`theta=1/3`, `p=3/2`, a regular reference tet of volume `1/#T_h`, Dassi Eq. (5)
analytic element velocities assembled simultaneously by Eq. (6), and frozen
topological/surface-boundary vertices. Each forward-Euler candidate used
adaptive backtracking and was accepted only on strict Huang-energy decrease
and byte-identical exact Shewchuk `orient3d` signs; float volume was a
pre-reject only. The pass was whole-stage transactional and deterministic.

The deliberate scope reduction was smoothing-only: no RBF reconstruction or
boundary sliding, no lazy flips/contract/split/1-to-4 insertion, no anisotropic
metric, and no FLOW2 stacking. A transient 10-test suite passed analytic
velocity vs central finite differences, strict monotone energy/backtracking,
exact orientation, frozen boundary, input/connectivity/count identity, forced
whole-pass rollback, and deterministic replay.

Default offline A/B (`8` steps, step fraction `0.05`):

| Mesh | dihedral sigma (deg) | p10 canonical Q | mean Q | Q < 0.01 | worst dihedral axis (deg) | elapsed |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| naca0012 (3,968 tets) | 49.8757425641 -> 49.8694148005 | 0.00282716828546 -> 0.00282901034042 | 0.114134158101 -> 0.114139899338 | 1,233 -> 1,230 | 109.409377256 -> 108.927329223 | 0.438 s |
| 02_medium_cylinder (3,439 tets) | 53.1846875244 -> 53.1425416062 | 0.000806259842474 -> 0.000806259841863 | 0.0542198110543 -> 0.0542350375272 | 1,349 -> 1,348 | 109.436098944 -> 109.386629583 | 0.355 s |

`worst dihedral axis` is
`max(theta_regular - theta_min, theta_max - theta_regular)`; lower is better.
Both cases passed strict per-step energy decrease, exact orientation,
byte-identical boundary/input/connectivity/count, deterministic replay, and the
combined mechanism runtime gate (`0.792 s <= 59.1 s`). Naca passed all five
quality gates. Cylinder failed the required strict p10 increase by
`-6.11e-13`, so the simultaneous two-mesh stop rule failed.

A bounded 32-cell parameter sweep (`1,2,4,8,16` steps as applicable; step
fractions `0.005` through `1.0`) found no GO cell. Cylinder p10 decreased in
every cell; the least-negative delta was `-9.29e-15` (1 step, fraction 0.005).
The strict gate was not relaxed as numerical noise. Decision: **KILL**. The
transient `mmpde.py`, MM1 tests, and benchmark script were deleted; no mesher
flag, end-to-end wiring, or permanent production gate was added. Continue
Phase 2 with `TET-SHAPE-2` or the next independently measured card.
