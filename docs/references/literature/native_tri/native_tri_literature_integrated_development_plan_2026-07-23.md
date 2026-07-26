# Native Tri Engine: Literature-Integrated Development Plan

Date: 2026-07-23
Status: implementation plan for a from-scratch engine, not a solved-quality claim
Primary target: build `native_tri` — deterministic triangular surface
meshing/remeshing for CFD/structural pre-processing (ROADMAP.md, "Surface mesh
(3D)") — satisfying the surface hard gates (manifold/watertight, no degenerate
or flipped faces, feature-edge preservation, geometry drift bound,
deterministic output, explicit rejection with original preserved). Evidence:
24 FULL_READ papers in `evidence_matrix.md` plus the screened inventories
`citation_snowball_batch1.md` / `citation_snowball_batch2.md`; per-paper
notes cited by filename (same directory).

## 1. Executive decision

1. **The engine is a guarded serial local-operator loop, not an unguarded global
   pass.** Skeleton: Botsch-Kobbelt/Dunyach split/collapse/flip/relocate/project
   (`botsch2004_remeshing.md`, `dunyach2013_adaptive.md`); every operation is a
   transaction — simulate, check hard gates (manifold link condition,
   fold-over, feature class, drift), commit or roll back. This is the
   evidence_matrix.md "First synthesis decision" plus the guarded-commit
   precedents of El Topo (Brochu & Bridson 2009, batch 2 §B) and the
   wildmeshing toolkit's per-element invariants (Jiang 2022, batch 2 §E).
   Final-output-only checks, as in L2 remesh today, do not replace per-op gates.
2. **Loop ordering is refine-first-then-angle-improve.** Cheng 2019's rescue
   experiment — seeding Hu/EBFR with a refine-to-bound result cuts failures
   38 -> 11 of 107 (`cheng2019_error_bounded_refinement.md`) — is direct
   evidence that refinement into the error-bounded space runs first, the gated
   worst-angle queue (`hu2016_error_bounded.md`) on top of it.
3. **Sizing is the shared metric algebra, not a private field.** native_tri
   consumes the metric contract the BL plan committed to
   (`native_bl_literature_integrated_development_plan_2026-07-23.md` §1
   item 3), backed by `frey2005_anisotropic_cfd_adaptation.md`: unit-mesh
   contract, eigenvalue truncation, simultaneous-reduction intersection,
   monotone interpolation, curvature source metric (`SIZING-METRIC-ALG1`,
   `SIZING-CURV-SOURCE1`, `SIZING-BL-INTERSECT1`). Dunyach's curvature sizing
   becomes one source metric feeding that algebra, not a competing system.
4. **The error/provenance contract is tiered from the three-level hierarchy**
   (evidence_matrix.md batch-2 refinement): sampled Hausdorff (cheap, misses
   maxima, no correspondence — Hu 2016/2017, Cheng 2019, Zhang 2022) <
   accumulated local envelope (`borouchaki2005_envelope.md`) < static bijective
   shell (edit-order-independent containment + provenance transfer —
   `liu2024_bijective_shell_projection.md`). The practical provenance target is
   Jiang 2020's linear shell; the high-order shell (Liu/Ji 2024, 3.3-4.6x build
   cost) is a smoothness upgrade only — **now evidence-backed by the Jiang 2020
   full read** (`jiang2020_bijective_shell.md`): all proofs in-paper, 100% on
   10.5k clean models, discrete CFD payloads insensitive to the linear field's
   kinks; beveling + singularity pinching mandatory. The mmg contrast: `hausd`
   is LOCAL and non-accumulated, drift unbounded (`dapogny2014_mmg.md`) — our
   contract must be strictly stronger (accumulated envelope or shell).
5. **Feature handling = provenance-owning skeleton + dynamic spacing control
   inside it.** The skeleton (fixed corners, sliding degree-two bone vertices,
   protected bone edges — `vorsatz2003_dynamic.md`) owns feature identity;
   Liu 2024's election/gap-fill/ostracism spacing control
   (`liu2024_sharp_feature_remeshing.md`) operates strictly inside it — its
   feature-blind RVD extraction, which breaks provenance, is not adopted.
6. **Relocation is upgradeable to gate-barrier DE behind a runtime budget.**
   MVP relocation is tangential smoothing/ODT + projection; CREVO's per-vertex
   DE with infinite-barrier gates
   (`zhang2022_evolutionary_vertex_optimization.md`) is a drop-in replacement
   for exactly that step (connectivity untouched), quality-tier-gated (~60% of
   its runtime is Hausdorff evaluation), seeded-RNG for determinism.
7. **Rejections (as binding as adoptions; citations in section 5).**
   (a) Global parameterization/CVT routes as production default. (b) The
   unguarded Botsch loop. (c) ML/AI-driven decisions in the deterministic
   path. (d) Sampled-Hausdorff-only provenance for the final contract.
8. **Exact predicates are the foundation — reads done, verdict: vendor.**
   Shewchuk 1997 + Attene 2020 are FULL_READ; both conclude vendor-not-port.
   Recorded gap, not fixed: the `_shewchuk` build line omits `-ffp-contract=off`
   (unsafe on FMA targets). Constructed points (LPI/SSI) route through indirect
   predicates; irrational constructions commit as explicit doubles, re-verified
   with direct predicates.
9. **Parallelism is LAST, after serial semantics stabilize.** Nunes 2011's own
   1.2-1.3x end-to-end result (`nunes2011_parallel.md`) shows the payoff is
   small before correctness settles; the batch-2 §E evidence (wildmeshing
   toolkit, Loseille cavity primitive, deterministic-commit designs) all
   presupposes fixed serial semantics. Deterministic output is a ROADMAP hard
   gate, so parallel commit is designed against bit-identical acceptance.
10. **No card claims a theoretical guarantee.** Every angle bound in the corpus
    is empirical (Hu can loop; Wang uncertified; Cheng has no termination
    proof, theta_min down to 11.2 deg; CREVO's ~40 deg is a single-model
    figure; Liu/Ji bijectivity rests on tolerance-float conservative checks).
    All acceptance is by corpus measurement.

## 2. Current state and gap

native_tri has **no implementation**. The nearest code is the L2 remesh
preprocessor (`core/preprocessor/native_remesh/`) — preprocessing-grade, not a
product engine. Gap audit (evidence_matrix.md "Current-code mapping";
ROADMAP.md surface hard gates):

| Aspect | L2 remesh today | Product contract requires |
| --- | --- | --- |
| Operator loop | `isotropic.py`: correct Botsch thresholds (`split > 4L/3`, `collapse < 4L/5`), valence 6/4 goals | Same skeleton, but every op transactional with per-op gates |
| Sizing | One global target scaled by feature-vertex fraction (`face.py`) | Per-vertex metric from the shared algebra (Frey 2005) |
| Error control | Final output checks only | Per-op drift gate at a tier-selected level of the three-level hierarchy |
| Feature handling | Locks every detected feature vertex; may project to nearest original vertex | Corner pinning vs degree-two feature sliding under a provenance-owning skeleton |
| Provenance | None | Patch/attribute transfer surviving remesh (shell or per-op link) |
| CVT | `cvt.py` is area-weighted centroid motion, not CVT/RVD | Not required (global routes rejected); honest naming or removal |
| Conformity | Face-wise longest-edge split; shared edge not one atomic two-face transaction | Zero T-junctions; audit required before any optimizer is layered on |
| Predicates | Floating-point ad hoc | Filtered exact predicates (Shewchuk/Attene) for orientation/fold-over |
| Determinism | Unmeasured | Byte-identical repeat runs (ROADMAP hard gate) |
| Rejection path | Silent fallback possible | Explicit rejection with original geometry preserved |
| Dependencies | pyacvd/igl, WSL-only (lessons-learned) | C++ native kernels, no external mesh dependency (ROADMAP) |

There is no measured bottleneck yet because there is no engine; Phase 0
creates the corpus and baseline every later claim is measured against. The
external engineering benchmark is mmg/mmgs (Dapogny 2014, batch 2 §F), the
closest open-source analogue of the target contract.

## 3. Card sequence

Effort: S ~ 1 card-day, M ~ 2-4, L ~ 5+. Global acceptance once the bench
exists: all surface hard gates green (ROADMAP.md), byte-identical repeat runs,
explicit rejection path exercised, corpus wall-clock within the Phase-0
budget. `TRI-*`/`SIZING-*` cards are from evidence_matrix.md rows; cards
marked (new) are minted by this plan.

### Phase 0 — Foundations and measurement (no engine output yet)

Cards: `TRI-CORPUS-BENCH1` (new) [M] — define the native_tri deterministic
quality corpus + one canonical measurement script (ROADMAP delivery item 4);
metrics fixed up front: worst/mean min-angle, two-sided drift estimate,
feature-edge recall, valence stats, vertex budget, wall clock.
`TRI-L2-GAP-AUDIT1` (new) [S] — measure L2 remesh against those metrics (the
"current state" column of section 2 becomes numbers), including the T-junction
audit of the face-wise split (evidence_matrix.md flags shared-edge splits as
not atomic). `TRI-PRED-FOUND1` (new) [M] — exact predicate layer
(orient2d/orient3d/incircle + indirect predicates for constructed points),
written only after the Shewchuk 1997 + Attene 2020 FULL_READs; unit-tested on
degenerate fixtures. `TRI-SG-PROVENANCE1` [S] — source-face/barycentric
provenance representation (`surazhsky2003_explicit.md`), the data structure
later phases upgrade to a shell; spec only in Phase 0.

Phase-0-adjacent read queue — **COMPLETE (2026-07-24)**, all seven FULL_READ:
`shewchuk1997_robust_predicates.md` + `attene2020_indirect_predicates.md`
(unblocks `TRI-PRED-FOUND1`), `brochu2009_eltopo.md`,
`jiang2022_wildmeshing_toolkit.md`, `wang2020_exact_envelope.md` +
`jiang2020_bijective_shell.md` (Phase 3), `dapogny2014_mmg.md`.

Acceptance: corpus + baseline report stored; predicate layer green on
fixtures; zero engine code beyond predicates. Rollback: n/a (read/measure).

### Phase 1 — Operator-loop MVP with hard gates (serial, isotropic, uniform sizing)

Cards: `TRI-BK-HYSTERESIS1` [M] (split/collapse hysteresis exactly as
published — Botsch 2004), `TRI-BK-AREA1` [S] (mixed-Voronoi-area tangential
smoothing), `TRI-BK-STOP1` [S] (explicit termination/stagnation criteria —
Botsch has none; a bounded-pass schedule guards against Hu's known
non-termination loop), `TRI-COLLAPSE-SAFE1` [M] (link-condition + fold-over +
normal-flip guards on every collapse/flip — Borouchaki-Frey 2005, Hu
2016/2017, on the Phase-0 predicate layer; self-intersection guard specified as
**pseudo-motion CCD** — both endpoints traced to target against the static mesh,
not a static final-position test — `brochu2009_eltopo.md`),
`TRI-SG-TRANSACTION1` [M]
(simulate-check-commit/rollback wrapper around every operator — Surazhsky-
Gotsman 2003 + El Topo's rollback-before-commit), `TRI-ERROR-GATE1` [M]
(local two-sided sampled Hausdorff gate per op — Hu 2016/2017; explicitly the
*tier-1* gate, upgraded in Phase 3, never the final contract),
`TRI-REFINE-PREPASS1` [S] (loop ordering: refine toward the bound first, angle
work later — Cheng 2019).

Decision tree:
- If the transactional wrapper costs > ~2x the unguarded loop, optimize the
  simulation path (cached one-ring geometry), do NOT drop gates — Yang 2020
  keeps error checks that dominate runtime (`yang2020_compatible.md`).
- If T-junctions appear, the shared-edge split is fixed as one atomic two-face
  transaction before any other card lands (Phase-0 audit finding).
- Exit gate: MVP output passes manifold/watertight, zero degenerate/flipped
  faces, byte-identical repeat runs, and the tier-1 drift gate; angles are
  measured but NOT yet a pass criterion.

Acceptance/rollback: any op that would break a hard gate rolls back bit-exact;
a corpus case that cannot reach the gates is explicitly rejected with the
original preserved. Evidence: Botsch 2004, Surazhsky-Gotsman 2003, Hu
2016/2017, Borouchaki-Frey 2005, Cheng 2019, Brochu & Bridson 2009.

### Phase 2 — Sizing integration (shared metric algebra)

Cards: `SIZING-METRIC-ALG1` [M] (unit-mesh contract, eigenvalue truncation,
simultaneous-reduction intersection, monotone interpolation — Frey & Alauzet
2005; the same algebra the BL plan consumes), `SIZING-CURV-SOURCE1` [M]
(curvature source metric; Remark 2.1 justifies curvature-for-Hessian — Frey
2005), `TRI-CURV-SIZE1` [S] (Dunyach's epsilon-driven length as one source,
with invalid-radicand and curvature-noise guards from its caution row),
`TRI-ADAPT-LOOP1` [M] (endpoint-minimum edge sizing + sizing-aware ODT
barycenter relocation — Dunyach 2013), `SIZING-BL-INTERSECT1` [S] (metric
intersection with the BL source metric so surface spacing and wall-layer
placement cannot diverge — BL-plan §1 item 3), plus `TRI-REFINE-REPAIR1` [M]
(Cheng 2019 violation-driven target-length shrinking, `lambda = 0.9`, with
field smoothing) as the feedback path when the drift gate keeps rejecting ops
in a region.

Decision tree: Frey 2005 has no anisotropy-ratio cap (its caution row) — a
flagged cap is added as an extension, isotropic-limit regression-tested; if
curvature noise oscillates the sizing, smooth the field (Cheng 2019) rather
than clamping per-vertex ad hoc.

Acceptance: unit-mesh edge-length histogram tightens on the corpus without any
hard-gate regression; the BL intersection test consumes the same metric object
the BL plan specifies. Evidence: Frey & Alauzet 2005, Dunyach 2013, Cheng 2019.

### Phase 3 — Error-gate tiers and provenance contract

Draft tier keeps the Phase-1 sampled gate hardened by `TRI-PROGRESSIVE-SAMPLE1`
(Cheng 2019's S1-S4 progressive audit before a dense final audit). Standard
tier: accumulated-envelope family — `TRI-ENV-ACCUM1`, `TRI-ENV-BIDIR1`,
`TRI-NORMAL-CONE1` (Borouchaki-Frey 2005), with Wang 2020's exact polyhedral
envelope containment (FULL_READ, `wang2020_exact_envelope.md`) as the citable
exact primitive for the tier gate: one-sided `IN` certificate, eps-independent
query cost, stable under later subdivision; `OUT` does not certify violation,
and input-side coverage still needs its own audit. Fine/contract tier: bijective shell
family — `TRI-SHELL-DOMAIN1`, `TRI-SHELL-PROVENANCE1` (Jiang 2020 linear shell
as the practical target), `TRI-SHELL-COST1` (high-order shell as an explicitly
optional upgrade — Liu/Ji 2024). `TRI-SYMMETRIC-VERIFY-1` (Yang 2020) is the
final symmetric verification pass for every tier. The shell provides no
feature-curve constraint (Liu/Ji caution row) — Phase 4's skeleton owns it.

Decision tree: if linear-shell construction fails (manifold/intersection-free
preconditions), that case's tier degrades to accumulated-envelope *with the
degradation reported*, never silently.

### Phase 4 — Feature skeleton and dynamic spacing

Card families: skeleton ownership (`TRI-FEATURE-SKELETON1`, `TRI-DOMAIN-LINK1`,
`TRI-COVERAGE1` — Vorsatz 2003), corner-vs-line semantics and sliding
(`TRI-FEATURE-SLIDE1` — Dunyach 2013), dynamic election/gap-fill/ostracism
spacing inside the skeleton (`TRI-FEATURE-DYNID1`, `TRI-FEATURE-CLEAR1` — Liu
2024, corners pinned, on-polyline placement exact), feature-aware angle ops
(`TRI-FEATURE-ANGLE1` — Wang 2018/2019). Fixed 45-deg dihedral pre-detection
is a known Liu 2024 limitation (cone apex silently lost); the threshold is a
reported input parameter, not a hidden constant.

### Phase 5 — Quality upgrades (angle tails, relocation search)

Card families: worst-angle priority queue (`TRI-WORST-ANGLE1` — Hu 2016/2017,
after refine-first per decision 2), both-tail angle ops (`TRI-ANGLE-PAIR1`,
`TRI-ANGLE-BOUNDS1`, `TRI-ANGLE-AB1` — Wang 2018/2019; the undefined `Psi`
collapse parameter is tuned on the corpus and reported), connectivity
regularization (`TRI-SG-REGULARIZE1` — Surazhsky-Gotsman 2003), and the DE
relocation upgrade (`TRI-EVO-*` — Zhang 2022 CREVO) behind a per-tier runtime
budget and a seeded RNG; feature-adjacent angles geometry-locked under the
bound (CREVO caution row) are reported as such, not retried forever.

### Phase 6 — Parallelism (LAST)

Card families: `TRI-PAR-CONFLICT-BATCH-1`, `TRI-PAR-GEOMETRY-1`,
`TRI-PAR-SCALE-BENCH-1` (Nunes 2011 interiors-before-interfaces), designed
against the batch-2 §E stack (wildmeshing-toolkit invariant scheduling,
Loseille cavity primitive as a possible unified-operator refactor,
deterministic-commit precedents). Entry: Phases 1-4 closed, gates permanent.
Acceptance: bit-identical output across repeated runs AND thread counts;
speedup is tertiary — the native_tet Phase-5 posture.

## 4. Invariant compliance table

Surface hard gates (ROADMAP.md): manifold/watertight, no degenerate/flipped
faces, feature-edge preservation, drift bound, determinism, explicit rejection.

| Card / family | Moves feature entities? | Drift-gate level | Determinism risk |
| --- | --- | --- | --- |
| TRI-CORPUS-BENCH1 / TRI-L2-GAP-AUDIT1 / TRI-PRED-FOUND1 | No (measure/predicates only) | n/a | None (exact arithmetic) |
| TRI-BK-HYSTERESIS1 / TRI-BK-AREA1 / TRI-BK-STOP1 | Not in Phase 1 (features frozen until Phase 4) | Tier-1 sampled | Low (fixed traversal order) |
| TRI-COLLAPSE-SAFE1 / TRI-SG-TRANSACTION1 | No (guards only) | Enforces the active tier | None (rollback is bit-exact) |
| TRI-ERROR-GATE1 / TRI-PROGRESSIVE-SAMPLE1 | No | Tier-1 sampled (never final contract) | Low (fixed sample schedule) |
| TRI-REFINE-PREPASS1 / TRI-REFINE-REPAIR1 | No | Active tier | Low |
| SIZING-METRIC-ALG1 / SIZING-CURV-SOURCE1 / SIZING-BL-INTERSECT1 / TRI-CURV-SIZE1 / TRI-ADAPT-LOOP1 | No (sizing field only) | n/a (feeds ops, gated per op) | Low (float summation order pinned) |
| TRI-ENV-ACCUM1 / TRI-ENV-BIDIR1 / TRI-NORMAL-CONE1 | No | Tier-2 accumulated envelope | Low |
| TRI-SHELL-DOMAIN1 / TRI-SHELL-PROVENANCE1 / TRI-SHELL-COST1 | No (shell has no feature constraint; skeleton owns it) | Tier-3 bijective shell | Low-medium (conservative float checks; tie-breaking pinned) |
| TRI-SYMMETRIC-VERIFY-1 | No (verify only) | Final audit, all tiers | None |
| TRI-FEATURE-SKELETON1 / TRI-DOMAIN-LINK1 / TRI-FEATURE-SLIDE1 | Corners pinned; degree-two bone vertices slide ON the feature polyline only | Active tier + feature recall gate | Low |
| TRI-FEATURE-DYNID1 / TRI-FEATURE-CLEAR1 | Inside skeleton only; exact on-polyline placement | Active tier | Low (election order fixed) |
| TRI-WORST-ANGLE1 / TRI-ANGLE-* | Feature-adjacent ops route through skeleton rules | Active tier | Low (priority ties pinned) |
| TRI-EVO-* (CREVO) | No (relocation only, connectivity untouched) | Infinite-barrier hard gates | Controlled: seeded RNG is an acceptance criterion |
| TRI-PAR-* | No (same ops as serial) | Same as serial | Controlled: bit-identical across threads is the acceptance criterion |

## 5. What we will NOT do

- **Global parameterization / CVT / conformal-embedding as production
  default** — high-genus fragility per the authors' own framing
  (`alliez2005_cvt_isotropic.md`, `zhong2014_conformal_anisotropic.md`;
  uniformization variants inherit the caveat, batch 2 §D). RVD cards stay
  comparison-engine candidates only.
- **An unguarded Botsch loop** — no hard topology/feature/orientation/error
  guarantee by its own admission (evidence_matrix.md row); L2 remesh already
  demonstrates the final-check-only failure mode.
- **ML/AI-driven decisions in the deterministic path** — ROADMAP delivery
  item 5: AI predicts advisory fields only; the hard gates own acceptance.
- **Sampled-Hausdorff-only provenance as the final contract** — Liu/Ji 2024
  Fig. 19 containment miss (`liu2024_bijective_shell_projection.md`); no
  correspondence, misses maxima between samples.
- **Liu 2024's feature-blind RVD extraction** — regenerates feature edges
  without provenance (`liu2024_sharp_feature_remeshing.md`); only its spacing
  control is adopted, inside the Vorsatz skeleton.
- **Known literal-copy traps** — Vorsatz's length thresholds must not be mixed
  into Botsch's hysteresis; Surazhsky-Gotsman's printed fidelity inequality
  conflicts with its prose (evidence_matrix.md cautions).
- **Claiming any literature angle/termination guarantee** (decision 10);
  **non-deterministic parallelism or unseeded stochastic search** (determinism
  is a ROADMAP hard gate; CREVO seeded, parallel commit bit-identical); and
  **keeping mechanisms with zero measured effect** (native_tet's THINSLIVER2
  precedent: unexercised complexity is deleted, not shelved).

## 6. Measurement-first protocol

No mechanism lands on a stale or absent baseline (native_tet plan method):

- Phase 0 *is* the measurement phase: corpus + canonical script
  (`TRI-CORPUS-BENCH1`), L2-remesh numeric baseline (`TRI-L2-GAP-AUDIT1`),
  predicate fixture suite, and the P0 read queue completed before dependent
  phases start.
- Phase 1 opens with gates in *reporting* mode: gate cost and hit-rate are
  recorded before enforcement.
- Phase 2 opens by measuring the uniform-sizing MVP's edge-length and angle
  histograms so the sizing win is attributable.
- Phase 3 opens by measuring tier-1 gate misses against a dense reference
  audit (Cheng 2019's Metro-style final audit) — quantifying what the
  envelope and shell tiers buy before they are built.
- Phase 4 opens with feature-edge recall/precision on ground-truth-tagged
  corpus cases, before the skeleton is trusted.
- Phase 5 opens by re-measuring the angle tails post-Phase-4; each quality
  card is measured alone against that fresh baseline before stacking.
- Phase 6 opens with serial conflict-neighborhood instrumentation (zero output
  change), mirroring native_tet `TET-PAR-0`.

Every card stores before/after evidence against its phase's opening
measurement, uses relative (never absolute) guards, and is reverted whole on
any hard-gate failure. A corpus case that cannot satisfy the gates exits via
the explicit-rejection path with the original preserved — itself a tested
feature from Phase 1 onward.

## 7. TRI-SHELL-PROVENANCE1 measured result (2026-07-26)

Status: **implemented as default-OFF, report-only diagnostics on the existing
linear-shell MVP; no complete-bijection claim.** Set
`AUTO_TESSELL_TRI_SHELL_PROVENANCE1=1` to append one immutable provenance
census per completed operator-loop round. The census never participates in a
`GuardReport`, acceptance, stopping, shell-checkpoint rollback, or mesh
mutation; disabling the flag is the complete rollback.

The implementation evaluates Jiang 2020's floating-point
`P(p) = (prism/triangle id, alpha, beta, normalized h)` by mapping each of the
existing canonical physical tetrahedra affinely to its reference-prism tet.
The inverse uses the same reference decomposition, and the middle projection
sets `h=0`. Source face index, original face vertices, and discrete patch ID
are carried by frozen tuple-backed records. The deterministic report samples
target-face centroids in face order and records mapped, ambiguous, unmapped,
pinched, and non-finite outcomes; ambiguous/pinched/invalid queries receive no
payload.

Measured on WSL2 Ubuntu, Python 3.12, face-centroid queries (one timed run;
the deterministic-repeat check reran the census but is excluded from the
reported time):

| Fixture | V / F | Shell local-scale fraction | Coverage | Ambiguous / unmapped | Max / p95 FP round-trip | Build / report runtime |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `cube.stl` | 8 / 12 | 0.5 | 12/12 (100%) | 0 / 0 | 1.110e-16 / 1.110e-16 | 0.006744 s / 0.017120 s |
| `cylinder.stl` | 66 / 128 | 0.2 | 128/128 (100%) | 0 / 0 | 1.388e-16 / 1.039e-16 | 0.020977 s / 0.111792 s |
| `sphere.stl` | 642 / 1280 | 0.5 | 1280/1280 (100%) | 0 / 0 | 2.483e-16 / 1.272e-16 | 0.364499 s / 1.256523 s |

All three repeated reports were value-identical. The cylinder did not build
at the DOMAIN1 default `local_scale_fraction=0.5` (`I1_or_I2_failed`) and was
measured at 0.2; this parameter sensitivity is evidence against claiming a
general shell constructor.

Scope reductions remain binding: one canonical 6-tet decomposition rather
than the 24-tet/all-order I1 certificate; no complete I2, topological bevel,
or production singularity-pinch construction; area-weighted normals rather
than the most-normal QP; centroid payload census rather than whole-face
coverage; no feature-curve constraint. Projection coordinates are FP, while
tet membership continues to use Shewchuk `orient3d`. The existing brute-force
AABB candidate scan was intentionally not optimized. The next card is
`TRI-SHELL-CANDIDATE1`: add and benchmark a deterministic spatial candidate
index without changing attribution semantics; the full 24-tet/I2/bevel/pinch
constructor remains a later DOMAIN follow-up.

Verification: hand-computable prism forward/inverse/middle projection; frozen
patch-payload pullback; forced ambiguous, pinched, unmapped, non-finite, and
report-exception paths; OFF baseline versus ON repeats with byte-identical
mesh state and identical `GuardReport`/checkpoint histories; all native-tri
and required Shewchuk predicate regressions (65 passed); `py_compile`, ruff,
and diff hygiene passed.
