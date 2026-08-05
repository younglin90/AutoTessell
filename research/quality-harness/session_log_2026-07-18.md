# Session Log — 2026-07-18: Solid-Invariant Campaign (tet/hex/poly) + Boolean Merge Kickoff

One continuous harness-driven session. Advisor (main session) planned and verified;
Worker subagents (`code_planner`/`code_maker`/`generator`) designed and implemented each
card. Every commit below was independently re-run and verified by the Advisor before
landing — a worker's self-report was never trusted as-is. Commit range:
`54bf77bf..09940409` (37 commits), followed by BOOLMERGE3 (`30f75c41`) after
independent review and verification resumed (see "Resumed completion" below).

## 1. What this session set out to do

Continue native_tet hardening (skew, TIMEOUT bench shapes), then broadened into: closing
the same solid-invariant methodology on native_hex and native_poly, root-causing a
12-STL hard-geometry bench's failure clusters, and finally starting a genuinely new
capability (A-1 S2 boolean merge) once the polish work hit diminishing returns.

## 2. Successes, by cluster

### 2.1 native_tet performance + a real correctness bug
- **BETA2830** (`f010399d`) — SI-detection memoization in the rebudget loop. Correct
  and safe, but the card's premise (17.8s/call bottleneck) was wrong — an existing AABB
  prefilter had already made detection fast (~1.2s/call). Kept as harmless cleanup;
  redirected the actual perf investigation.
- **BETA2831** (`84a66498`) — cProfile (not log-gap inference) found the *real*
  bottleneck: `core/utils/aabb.py`'s BVH leaf routine called once per query point
  (660k scalar calls, 71% of wall time) instead of batched. Vectorized it:
  cumtime 62.4s → 2.8s. Took `sphere.stl`/`sphere_watertight.stl` from 143s TIMEOUT to
  29s PASS.
- **Critical bug found in the same investigation**: `TriangleBVH.build()`'s recursive
  split wrote a local argsort rank as if it were a global triangle id, corrupting
  `tri_order` below the root (reproduced on HEAD: 27/137 triangles duplicated/dropped).
  This backs every envelope/hausdorff/cdt_recovery/signed_distance query project-wide —
  could have silently returned the wrong nearest triangle anywhere. One-line fix,
  ~80 BVH-adjacent tests reconfirmed unchanged.
- **`9e1c0d88`** — unrelated cp949 encoding bug found and fixed in passing
  (`Path.read_text()` missing `encoding="utf-8"`, violating a standing lessons-learned
  guardrail).

### 2.2 Coverage-collapse cluster — closed (3/3)
All three were the *same* bug pattern (an unconditional "keep only the largest
component/body" clamp discarding legitimate geometry), found at three different layers:
- **BETA2832** (`0188efc1`) — `core/preprocessor/pipeline.py`'s `_final_validate` was
  discarding an entire disjoint torus body from `high_genus_dual_torus.stl`
  (area/vol-ratio 0.56/0.47). Fixed with a relative-area guard (keep any component
  ≥5% of the max component's area). area/vol-ratio → 1.01/1.01.
- **BETA2833** (`38296799`) — same clamp lived one layer upstream too: L1 pymeshfix's
  `remove_smallest_components` was collapsing `many_small_features_perforated_plate.stl`
  from 65 bodies to 1 before BETA2832's fix ever saw it. Fixed with per-component
  repair + an **aggregate guard** (Advisor's own addition: the per-component 5% rule
  alone still let 64 features, each individually below 5% but jointly 68% of the
  surface, get filtered away — filtering may never drop >5% of *total* area).
- **SHARPRIDGE1** (`2f93c229`) — `sharp_features_micro_ridge.stl`'s L2 Laplacian
  smoothing had no free-boundary pin and was collapsing a thin open ridge to a point
  (area 6.16→0.0). Added the same monotone area/Hausdorff revert-guard pattern.
  Verified via WSL (Windows Bash tool's python lacks `igl`/`pyacvd` — a new
  lessons-learned entry).
- All three verified via the same canonical bench script; all three are relative
  guards that no-op on healthy single-body input.

### 2.3 native_hex curved-wall fidelity — closed on both quality levels
- **`54bf77bf`** (start of session) — per-vertex wall-fit snap closed cylinder standard
  wall_dev_max 0.0466→0.0032.
- **`ad02a29f`** — envelope generalized to per-vertex local sizing (fTetWild-style) —
  measured harmless but *not* the actual fine-quality blocker (n_reject_envelope=0
  before/after; hypothesis correctly falsified by measurement).
- **`48b3000b`** — root cause found: the guard's all-or-nothing structure reverted the
  *entire* move on any face flip even though 39/39 rejected vertices had a safe partial
  move (binary-search fraction t*, min 0.706). Backtracking to the largest safe t*
  (same unmodified guard, no relaxation) took fine wall_dev_max 0.0353→0.008.
- **`be08aa1f`** — post-snap boundary skew (4.64) decomposed to its root: snapping
  collapsed the boundary cell's wall-normal thickness. Freezing surface vertices and
  relaxing only free interior vertices of flagged sliver cells restored it to 2.84
  (new permanent gate ≤3.0). Bonus: fine's pre-existing undetected
  `negative_volumes=8` dropped to 0 too.
- **`311467ba`** — locked that negative_volumes fix as a permanent gate on both quality
  levels (root cause of the relax-off path not diagnosed, deliberately left open).
- **HEX-SKEW2 (no commit — a deliberate no-op)**: investigated further skew reduction;
  found current parameters already sit at the Pareto frontier between boundary skew and
  non-orthogonality (they're structurally coupled — pushing one worsens the other).
  Concluded "no card needed" rather than force a parameter-sweep card.

### 2.4 native_poly — 0% to 4/4 permanent solid gates
- **POLY-S1** (`2be67872`) — first-ever measurement. cube.stl: surface 6.000 and degen 0
  PASS; void 7.588 (more phantom interior wall than actual input surface!) and volume
  1.177x both xfail — the prior verdict=PASS had been blind to both.
- **POLY-S2** (`0f464e06`) — S1's working hypothesis ("boundary open-wall") was
  disproved by measurement. Real cause: `tet_to_poly_dual`'s per-cell ConvexHull
  triangulated each non-planar interior dual interface differently, so adjacent cells'
  shared face never vertex-matched and leaked as void on both sides. Replaced with a
  topological path (each interior tet edge's ordered centroid ring emitted directly as
  the shared face — guarantees 2-cell sharing by construction). void 7.588→2.435 (-68%).
- **POLY-S3** (`596d849c`) — two more boundary-only bugs in the same file (cap faces
  over-classified as boundary; boundary-edge seams had no separating face). void
  →**0.000 exactly** (permanent gate). Volume 1.177→1.077 (missed <=1.05, xfail kept).
- **POLY-S4** (`a5d6f52b`) — root-caused the volume overfill with a controlled
  experiment: dual.py's *unmodified* code on a well-formed Kuhn tetrahedralization gives
  Sigma|vol|=1.0000 exactly, proving the dual construction itself was never the bug —
  native_tet's interior Steiner points make sliver tets whose non-convex dual cells the
  pyramid measure overestimates. Laplacian-smoothing only interior tet vertices
  (boundary fixed) → 1.026, even improved skew as a side effect. **All 4 solid
  invariants now permanent on cube**, matching tet and hex.
- **POLY-S5** (`f4da0252`) — generalized to cylinder.stl (test-only, zero lines changed
  in dual.py): all 4 gates hold on a curved surface too. Curved skewness (173.8°) is a
  separate, deliberately out-of-scope quality axis for later.

### 2.5 Flat-all-surface-sliver sequence on dual_torus (FSL1→FSL4) — honestly closed
- **FSL1** (`481e8349`) — read-only detector: classifies flat all-surface slivers by
  face topology and 2-3 flip validity.
- **FSL3** (`4973b578`) — wired guarded 2-3 flip. Honest result: **0/9 eligible slivers
  were actually flippable in a way that improved quality** — the mechanism was proven
  safe (3 synthetic tests) but is a structural no-op on the real target (eligible
  slivers turned out not to be the FAIL driver at all).
- **FSL4** (`9d8b7a0d`) — locked the real driver (61 unflippable coplanar wedges) as a
  known structural limit: gate A permanently locks the volume-tiling win BETA2832
  earned (0.9913, can't silently regress); gate B pins the cure target as
  `xfail(strict)` so a future fix trips a loud alarm. **Also fixed a real interpreter
  crash found while verifying this card** (see §3).

### 2.6 Near-wall insertion sequence for cylinder (CYLSKEW1-4) — safe infrastructure, not yet default-on
- **CYLSKEW1** (`27aa94c1`) — Garimella offset-ring seeding skeleton, default OFF,
  seeding-stage-only hook (no downstream logic touched). Unplanned bonus: even this
  unrefined seeding measured skew 44.9→40.8.
- **CYLSKEW2** (`37e11a1a`) — the *planned* card (filter seeds to true side-wall
  vertices) was measured and falsified: cylinder has only 2 z-rings, so no vertex is a
  pure side-wall normal, and any subset filter erases the improvement. Redirected to
  swapping absolute-value guards (dedup, offset floor) for scale-invariant equivalents.
- **CYLSKEW3** (`8f8ab4e6`) — tested default-ON on sphere.stl: **regressed badly**
  (non-ortho 10.6→79.7, cells 4.4x at N=500) — a holistic seed-density effect, not
  something any per-vertex filter could catch. Added a pure `select_offset_ring_variant`
  monotone-dominance decision function (no caller yet), verified against all 3 measured
  cases (cylinder keep, sphere-N500 revert, sphere-N1000 keep).
- **CYLSKEW4** (`02f92315`) — wired the selector via a cheap raw-Delaunay proxy (full
  best-of-two doubles bench time past budget). Default path fully unchanged
  (byte-identical, reconfirmed). On the one case checked, the cheap proxy actually
  decided "revert" for cylinder even though the known-good full pipeline says "keep" —
  flagged as an open correlation question for CYLSKEW5, not resolved.

### 2.7 Thin/sharp-feature sliver cluster on naca0012
- **THINSLIVER1** (`bb37f871`) — naca0012's 17 fully-interior degenerate slivers are
  flip-ineligible; added an interior edge-collapse phase. Result: 22→11 in this
  fixture's config (real, partial win) — the remaining 11 have vertex-star valence
  12-26 that the orientation guard correctly refuses to collapse in one step. Locked
  as a permanent regression gate (<=15) + xfail(strict) for the <=2 target.
- **THINSLIVER2 — implemented, then discarded** (`6762faaa`): tangential-recenter apex
  relax was designed and safety-verified (3 discriminating experiments ruled out naive
  and zero-inversion inward pushes) but **independently reconfirmed to have zero
  measured effect** on the current codebase — the plan's 82.44 baseline had already
  dropped to ~60.3 via FSL3/FSL4/CYLSKEW1-3 stacking by the time this card actually
  ran, so its target had moved. Did not commit the 123-line mesher.py mechanism;
  committed an honest regression-lock on the ~60.3 state those *other* cards had
  already earned instead.

### 2.8 A-1 S2 Boolean merge — kickoff (new capability, not polish)
- **BOOLMERGE1** (`5b5ae256`) — `inside_union_winding_number`: per-input-surface GWN
  evaluated independently and OR-combined (fTetWild §3.6 — volume judgement, not
  surface CSG, so invariant 1 holds automatically). Verified against synthetic
  overlapping/disjoint cubes. Zero lines changed in orchestrator/server.
- **BOOLMERGE2** (`09940409`) — lifted the same primitive to a tet-mesh filter
  (`filter_tets_to_union`), proven on real background-grid tets: union filter recovers
  volume 1.9229 (analytic 1.875) vs. a single-surface control's 1.0307 — direct
  evidence the merge is real, not just returning one input body. Still zero production
  callers.
- **BOOLMERGE3** (`30f75c41`) — verified and committed after session resume.

## 3. Bugs found and fixed along the way (not part of any planned card)

1. **`tri_order` corruption in `TriangleBVH.build()`** (§2.1) — pre-existing, backs
   nearest-triangle queries project-wide.
2. **Non-deterministic interpreter crash**: calling `generate_native_tet` twice in the
   same pytest process on a heavy mesh (dual_torus, 12k+ cells) produced a Windows
   access violation with a *different* native stack trace each run (aabb.py once,
   mean_curvature.py the next — the signature of native-heap corruption). Reproduced
   2/2 in pytest, 0/2 in a bare script calling the function twice — pytest-specific
   trigger, root cause in the native extension not found. Fixed practically: FSL4's and
   THINSLIVER1's test files now share one module-scoped fixture run instead of each
   test calling the pipeline independently. Documented as a new
   `.claude/rules/lessons-learned.md` guardrail.
3. **Windows-vs-WSL Python environment split**: the Windows Bash tool's `python3` lacks
   `igl`/`pyacvd` (installed only in the WSL venv) — SHARPRIDGE1's actual fix path was
   silently untested until verification switched to `wsl.exe -d ubuntu`. Also
   documented as a guardrail.
4. **Stray truncated file**: `tests/stl/native_tet_bench_latest.json` had been reduced
   to 0 bytes by some earlier, unrelated process in this session — found while chasing
   an unrelated test failure, restored via `git checkout`.

## 4. Resumed completion

- **BOOLMERGE3** — the first S2 card touching real user-facing code
  (`core/pipeline/orchestrator.py`, `desktop/server.py`). Plan: relax the multi-surface
  gate to allow exactly 2 `mesh_type="tet"` surfaces, using GWN additivity
  (`wn_{A∪B} = wn_A + wn_B`) to pre-merge the two input STLs into one combined soup fed
  through the *existing* single-input pipeline — avoiding a 5-file plumbing change to
  carry a multi-surface list all the way to the mesher. `git status` shows
  `orchestrator.py` and `server.py` modified (worker finished writing) but **the Advisor
  had not yet reviewed the diff, re-run tests, or committed** when the session paused.
  Resumed verification passed the union E2E, server gate, and BOOLMERGE1/2 guards.
  The focused card guard finished at 30/30 tests; union volume and
  surface-preservation checks remained inside their locked bands. A broader
  orchestrator/server run was 147/150, with the three pre-existing mock-checker
  retry failures unchanged and outside this card. Commit: `30f75c41`.

## 5. Remaining work (roadmap-ordered)

- **A-1 S2 boolean merge**: BOOLMERGE3/4/5a complete. Remaining work is
  intersection/difference, hex/poly wiring, and per-source patch/BL provenance.
- **CYLSKEW5**: resolve the proxy/final-metric correlation question CYLSKEW4 left open
  before considering default-ON.
- **A real naca0012 skew fix**: needs fresh diagnosis against the current ~60.3
  baseline (not the stale 82.44 THINSLIVER2 analysis).
- **Cylinder skew below 8.0** and **dual_torus's 61 unflippable wedges**: both
  structurally need a full Garimella near-wall interior-point insertion (multi-card,
  same underlying technique) — CYLSKEW1-4 only proved the seeding mechanism is safe,
  not that it reaches the target.
- **12-STL hard-geometry bench**: shapes beyond the ones closed this session
  (very_thin_disk, extreme_aspect_ratio_needle — flagged in THINSLIVER1's plan as
  structural known-limits, same class as the wedges above, not yet attempted).
- **A-1 S3** (defect localization + per-item auto-fix UI), **B0** (Track B data
  contract) — untouched, further out in the roadmap sequencing.

## 6. Methodology notes worth remembering

- Every "honest negative result" this session (FSL3's 0 flips, THINSLIVER2's 0 effect,
  HEX-SKEW2's no-card-needed conclusion) came from *directly re-measuring* rather than
  trusting a worker's or a plan's self-report — several would have shipped as false
  wins otherwise (THINSLIVER2 especially: the code was "correctly implemented" by every
  local measure, and only an isolated git-stash A/B against the *current* HEAD exposed
  that its target had already moved).
- The recurring root-cause pattern across the coverage-collapse cluster (§2.2) was the
  same bug at three different pipeline layers — worth checking early next time a
  similar "silently drops legitimate geometry" symptom appears elsewhere.
- Aggregate guards (§2.2, BETA2833) matter alongside per-item relative guards — many
  small items each individually below a relative threshold can still jointly be most of
  the signal.

## 7. Continuation after session resume

- **BOOLMERGE3** (`30f75c41`) wired two-surface tet union into the orchestrator and
  desktop upload path; focused guard: 30/30.
- **BOOLMERGE4** (`8847f467`) found BOOLMERGE3's measured `1.7574` was the symmetric
  difference (`1.750`), not an approximate union. Combined-soup ray parity cancelled
  the overlap. Per-original-surface GWN OR restored volume to `1.891203768` versus
  analytic `1.875`, with 2,859 positive-volume cells, zero negative volumes, and PASS.
- **BOOLMERGE5a** (`3a012d70`) generalized the same native-tet path to any `N >= 2`
  input surfaces. Server path ordering and three-input OR behavior are locked by 35
  focused tests.
