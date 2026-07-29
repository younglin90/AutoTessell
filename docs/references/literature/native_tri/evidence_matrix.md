# Native Tri Literature Evidence Matrix

Status: active systematic review. `FULL_READ` means the full paper, equations,
algorithm, experiments, limitations, and reference list were inspected.

| Paper | Status | Evidence relevant to AutoTessell | Candidate card | Important caution |
| --- | --- | --- | --- | --- |
| Hu et al. 2016/2017, error-bounded feature-preserving remeshing | FULL_READ | Worst-angle priority queue; collapse, relocate, then split; link-condition and fold-over guards; local two-sided sampled Hausdorff gate; feature-sensitive relocation | `TRI-ERROR-GATE1`, then `TRI-WORST-ANGLE1` | Only 2-manifold inputs; sampled Hausdorff underestimates the exact distance; high requested angle can loop or create degenerate edges; noisy input is interpreted as features |
| Botsch and Kobbelt 2004 | FULL_READ | Canonical loop: split above `4L/3`, collapse below `4L/5`, valence flip, tangential smoothing, projection; mixed-Voronoi-area refinement | `TRI-BK-HYSTERESIS1`, `TRI-BK-AREA1`, `TRI-BK-STOP1` | No hard topology, feature, orientation, or surface-error guarantee; mean quality is not worst-case quality |
| Dunyach et al. 2013 | FULL_READ | Curvature sizing `L=sqrt(6 epsilon/kappa - 3 epsilon^2)`; endpoint-minimum edge size; sizing-aware ODT barycenter; feature-corner/feature-line distinction | `TRI-CURV-SIZE1`, `TRI-ADAPT-LOOP1`, `TRI-ODT-RELAX1`, `TRI-FEATURE-SLIDE1` | `epsilon` is not an exact Hausdorff guarantee; curvature noise, invalid radicands, gradation, topology, and fold-over need production guards |
| Alliez et al. 2005 | FULL_READ | Exact global sample budget through error diffusion; feature/corner sample ledger; weighted CVT; constrained Delaunay with filtered exact predicates | `TRI-CAP-LEDGER1`, `TRI-RVD-COMPARE1` | Global cut/parameterize/stitch route is unsuitable as the production default for high genus; no hard fidelity or minimum-angle guarantee |
| Surazhsky and Gotsman 2003 | FULL_READ | Source-face/barycentric provenance; dynamic overlapping mean-value patches; curvature-density area-ratio relocation; connectivity regularization | `TRI-SG-PROVENANCE1`, `TRI-SG-TRANSACTION1`, `TRI-SG-AREA1`, `TRI-SG-REGULARIZE1` | Area equalization can oscillate and is not a quality guarantee; the printed fidelity inequality conflicts with its prose and must not be copied literally |
| Wang et al. 2018/2019 | FULL_READ | Pair large-angle midpoint insertion plus angle-optimal flip with legal small-angle opposite-edge removal to maintain vertex budget; optional error-aware smoothing/collapse/flip | `TRI-ANGLE-PAIR1`, `TRI-ANGLE-BOUNDS1`, `TRI-FEATURE-ANGLE1`, `TRI-ANGLE-AB1` | Reported angle improvement is empirical, not a certified bound; the collapse parameter `Psi` is not defined/tuned; paired edits still need transactional topology, feature, and envelope checks |
| Yan et al. 2009 | FULL_READ | Exact symbolic RVD clipping seeded by kd-tree and propagated through Delaunay neighbors; RCVT-to-CCVT L-BFGS; RDT topological-ball checks | `TRI-RVD-CLIP1`, `TRI-RVD-PRED1`, `TRI-RCVT-LBFGS1`, `TRI-RDT-BALL1`, `TRI-RVD-ENV1` | Exactness is limited to RVD combinatorics/predicates, not output Hausdorff distance or minimum angle; topology-control termination is not guaranteed |
| Borouchaki and Frey 2005 | FULL_READ | Accumulated local Hausdorff envelope; normal-gap cone; edge removal, flip, and relocation under discrete geometric checks | `TRI-ENV-ACCUM1`, `TRI-ENV-BIDIR1`, `TRI-NORMAL-CONE1`, `TRI-COLLAPSE-SAFE1` | The distance is discretely approximated; relative quality improvement is not an absolute minimum-quality guarantee |
| Mandad et al. 2015 | FULL_READ | Sampled tolerance-boundary classification, 3D Delaunay refinement, zero-set mutual tessellation, link/visibility-kernel simplification | `TRI-TOL-BAND1`, `TRI-CLASSIFY1`, `TRI-TOPO-KERNEL1`, `TRI-TOL-HIGHASSURANCE1` | Strongest contract in this batch but compute-intensive; requires a valid two-sided tolerance volume and separation assumptions |
| Vorsatz et al. 2003 | FULL_READ | Persistent source-domain triangle/barycentric link; feature skeleton with fixed corners, sliding bone vertices, and protected bone edges | `TRI-DOMAIN-LINK1`, `TRI-FEATURE-SKELETON1`, `TRI-COVERAGE1` | Its length thresholds differ from Botsch's hysteresis and must not be mixed; some transient-degeneracy/topology claims lack production predicates |
| Zhong et al. 2014 | FULL_READ | Per-vertex Riemannian metric, conformal embedding, weighted CVT, metric-space Delaunay and quality measures | `TRI-METRIC-FIELD1`, `TRI-METRIC-QUALITY1`, `TRI-METRIC-LEGALIZE1`, `TRI-ANISO-LOCAL1` | Global embedding is topology-specific and fragile at high genus; dense input, smooth metric, and moderate anisotropy are material assumptions |
| Yang et al. 2020 | FULL_READ | Compatible target-length fusion, simultaneous paired local edits, candidate-level Hu error checks, explicit symmetric final verification | `TRI-CURVATURE-SIZE-1`, `TRI-LOCAL-ERROR-TXN-1`, `TRI-SYMMETRIC-VERIFY-1` | Pair-compatible initialization has no convergence guarantee and falls back to overlay; no final minimum-angle or bijection theorem; error checks dominate runtime |
| Nunes et al. 2011 | FULL_READ | Parallel read-only B-spline surface fitting; distance-2 independent section interiors before intersections; topology write locks | `TRI-PAR-CONFLICT-BATCH-1`, `TRI-PAR-GEOMETRY-1`, `TRI-PAR-SCALE-BENCH-1` | Reported end-to-end speedups are only about 1.2-1.3x; correctness and deterministic conflict semantics must precede parallelization |
| Cheng et al. 2019 | FULL_READ (11/11 pages) | Iteration-level detect-and-refine loop that allows out-of-tolerance intermediates; violation-driven per-vertex target-length shrinking (`lambda = 0.9`) with field smoothing; progressive S1-S4 sampled two-sided audit before a dense Metro audit; max-allowable-length thresholds `split > L`, `collapse < L/2`; hybrid result: seeding Hu/EBFR with its output cuts EBFR failures 38 -> 11 of 107 — direct evidence for refine-first-then-angle-improve ordering | `TRI-REFINE-REPAIR1`, `TRI-PROGRESSIVE-SAMPLE1`, `TRI-REFINE-PREPASS1` | The error bound is a posteriori sampled (final Metro audit is itself sampled — no continuous certificate); no termination proof and no quality guarantee (`theta_min` down to 11.2 deg); vertex inflation is the price; intermediate meshes may violate the bound and must never be surfaced as results |
| Frey and Alauzet 2005 | FULL_READ (15/15 pages) | Solver-independent metric algebra adopted as the shared sizing contract: unit-mesh contract (`l_M(e) ~ 1` via integrated metric edge length), eigenvalue truncation to `[1/h_max^2, 1/h_min^2]`, simultaneous-reduction metric intersection, monotone size-linear metric interpolation, and the curvature source metric `diag(alpha kappa_1^-2, beta kappa_2^-2, .)`; curvature-for-Hessian substitution justified by the Remark 2.1 equivalence (interpolation error is a surface-to-linear-approximation distance) | `SIZING-METRIC-ALG1`, `SIZING-CURV-SOURCE1`, `SIZING-BL-INTERSECT1` | Hessian-dependent parts (Cea's-lemma justification, least-squares Hessian recovery, relative normalization, solve-adapt fixed-point loop) are excluded until a flow field exists; no explicit anisotropy-ratio cap in the paper (must be added as a flagged extension); no convergence proof; gradation, quadric fitting, and the anisotropic Delaunay kernel are referenced, not specified |
| Liu et al. 2024 (sharp feature) | FULL_READ (11/11 pages) | Dynamic per-iteration feature-sample election by projection distance (`delta = 0.3` x local spacing) with segment-bounds rejection; spacing control via gap-fill recruiting (`lambda = 1.4`) and ostracism clearance (`sigma = 0.75`); exact on-polyline point placement with corners pinned; 1-D CVT relaxation along feature chains | `TRI-FEATURE-DYNID1`, `TRI-FEATURE-CLEAR1` | Feature detection is a fixed 45-deg dihedral pre-detection (NOT threshold-free; cone apex silently lost); RVD extraction regenerates feature edges feature-blind, breaking per-edge provenance as published — the useful piece is the spacing control (election/gap-fill/ostracism) inside a provenance-owning skeleton, not the extraction design; no minimum-angle guarantee (`theta_min` down to 13.2 deg); no noise-robustness evidence |
| Zhang et al. 2022 (CREVO) | FULL_READ (11/11 pages) | Per-vertex derivative-free differential evolution (`Np = 20`, `F = 0.7`, `Cr = 0.9`) with infinite-barrier hard gates (Hausdorff bound, Delaunay/manifold); connectivity untouched — a drop-in replacement for the relocation step of any local-operation loop; DE search cuts vertex count 2.7-4x versus heuristic collapse points under identical gates | `TRI-EVO-RELOCATE1`, `TRI-EVO-COLLAPSE-SEARCH1`, `TRI-EVO-MAXMIN1` | The cited `theta_min ~ 40 deg` is a single-model empirical figure (fleet mean `theta_min` 36.07 deg, worst 10.07 deg — no guarantee); ~60% of runtime is sampled Hausdorff evaluation (minutes per 10k-vertex model, quality-tier only); randomized output needs a seeded RNG; feature-adjacent angles are geometry-locked and cannot be improved within the bound |
| Liu, Ji et al. 2024 (bijective shell) | FULL_READ (13/13 pages) | Static edit-order-independent certificate: shell containment plus the normal condition give a two-sided `epsilon` bound and bijective provenance transfer — exactly the correspondence sampled gates lack; their Fig. 19 shows a Hu-style sampled-Hausdorff-bounded remesh can still miss shell containment; practical path is Jiang 2020's linear shell first, high-order as a smoothness upgrade (3.3-4.6x build cost) | `TRI-SHELL-DOMAIN1`, `TRI-SHELL-PROVENANCE1`, `TRI-SHELL-COST1` | Bijectivity is conditional on Orient3d-reducible conservative checks that are implemented in tolerance floating point, not exact arithmetic (exactness described, not delivered); supplement proofs of Propositions 1-5 not locally verified; manifold, intersection-free, orientable input only; shell build averages minutes per model; no feature-curve constraint — feature handling must come from the remesher |
| Shewchuk 1997 (robust predicates) | FULL_READ (59/59 PDF pages; proof algebra followed structurally, number-critical pages rendered) | Adaptive-precision exact-sign predicates (ORIENT2D/3D, INCIRCLE, INSPHERE) via expansion arithmetic + staged A/B/C/D filters; runtime permanent-based stage-A bound answers the vast majority of calls at ~2x float cost; the predicate substrate under every transactional gate (`TRI-COLLAPSE-SAFE1` fold-over/orientation, envelope audits, determinism) | verdict: **vendor, do not port** — `core/utils/_shewchuk/predicates.c` (public domain, already in-tree) is the canonical layer; native effort goes to build hygiene, FMA TWO-PRODUCT variant, batch stage-A filtering | Contract requires round-to-nearest-even, no FMA contraction, no fast-math: **the build line in `core/utils/_shewchuk/__init__.py` omits `-ffp-contract=off`** (safe on plain SSE2 x86-64, unsafe on AArch64 / `-march=native` FMA targets) — recorded as a gap, not fixed here; exponent range `[-142, 201]` unchecked at runtime; exact only for explicitly represented double inputs — constructed points are outside the contract (Attene 2020 closes that); `predicates_staged.py` stage-1/2 bounds are heuristic, not the paper's certified coefficients |
| Attene 2020 (indirect predicates) | FULL_READ (9/9 pages) | Closes the constructed-point gap: implicit points as polynomial fractions (2D SSI, 3D **LPI**; TPI postdates the paper text) fed to predicates in unevaluated form through a semi-static filter → interval → expansion cascade; per-configuration instances (EEE/IEE/IIE/III); caching `lambda`/`d` for FP+interval stages only | `TRI-IPRED-VENDOR1`, `TRI-IPRED-SPLITGATE1`, `TRI-IPRED-CACHE1`, `TRI-IPRED-SNAP-AUDIT1`, `TRI-IPRED-SCOPE1`; verdict: **vendor the reference implementation** (filter constants are code-generated, unsafe to re-derive by hand) | Overhead ≤ ~2x (2D) / ~2.5x (3D) at 100% implicit points, gradual with implicit fraction; class-2 only — no cascaded constructions, rational constructions only (no sqrt/normalization/iterative projections — commit those as explicit doubles and re-verify with direct predicates); 3D snap rounding unsolved: exact decisions do not certify the rounded output mesh (snap-once-and-audit discipline required); repository license + compiler flags must be confirmed before bundling |
| Brochu & Bridson 2009 (El Topo) | FULL_READ (24/24 pages) | Per-operation guarded-commit precedent: safe-default (midpoint split), **pseudo-motion CCD** for any relocation (covers tunneling a static post-check misses), compound-op rollback (zippering), severity ordering + bounded sweeps, end-of-run static audit; space-time filtered CCD claims no false negatives | transaction skeleton for the guarded Botsch loop; `TRI-COLLAPSE-SAFE1`'s self-intersection guard should be specified as pseudo-motion CCD (both endpoints to target), not a static final-position test | **Certified invariant is intersection-freedom only** — no envelope, no distance-to-reference bound, no quality/feature guarantee; complementary to the bijective shell: within a valid shell the section property subsumes El Topo's invariant (shell interior needs no CCD), El Topo remains necessary where no shell exists — dirty-input repair, true surface motion (BL inflation fronts), topological merge/pinch; CCD is forward-error-filtered FP, not exact — upgrade predicate layer to Attene-2020-era arithmetic when adopted |
| Wang et al. 2020 (exact envelope) | FULL_READ (14/14 pages) | Exact containment test in a polyhedral envelope provably inside the `L2` `eps`-offset: per-triangle 7-8-halfspace prisms (`delta = eps/sqrt(3)`), Theorem 3.2 C1/C2/C3 reduced to orient3d + LPI/TPI indirect predicates with filter ladder; certificate survives arbitrary later subdivision (the invariant sampled checks break); query cost roughly constant in `eps` — wins at tight `eps` where sampling explodes | tier-2 upgrade of the error gate: `TRI-ERROR-GATE1`/`TRI-ENV-*` sampled inner check → exact `IN` certificate; port or vendor `fast-envelope` (algorithm + filter constants fully printed; Attene 2020 is the predicate layer beneath) | **One-sided**: `IN` certifies within-`eps`; `OUT` does not certify violation (conservative up to sqrt(3) thinning on flat regions → slightly denser output); certifies proximity only — never topology, orientation, or intersection-freedom; input-to-output coverage direction still needs an input-side audit. **Cross-engine flag**: `core/generator/native_tet/envelope.py` cites this paper but implements a sampled point-to-surface BVH check — precisely the documented inexact failure mode (locking, over-refinement, eps-dependent cost); schedule as its own card (TET-ENV-EXACT1) |
| Jiang et al. 2020 (bijective prismatic shell) | FULL_READ (18/18 pages; **all proofs in-paper**, Appendices A-E) | Linear-shell parent of Liu/Ji 2024: generalized prisms, 24-tet I1 positivity via Shewchuk exact predicates, cap-vs-input containment (Guigue-Devillers), normal condition; **100% construction on 5018 Thingi10k + 5545 ABC** (pre-filtered clean input); sections are self-intersection-free by construction; extrusion-direction QP + pinching reusable for `native_bl.py` | `TRI-SHELL-DOMAIN1` / `TRI-SHELL-PROVENANCE1` confirmed with refinements: check list = link condition + 24-tet I1 + cap containment + normal-vs-pillars + optional 89.95-deg distortion bound; **topological beveling and singularity pinching (8% of models) + boundary freezing are mandatory** for the 100% rate; skipping beveling spuriously fails I2 | Evidence-backed decision: **linear shell suffices for discrete CFD payloads** (patch IDs, BC tags — insensitive to the piecewise-constant field's kinks); high-order 2024 upgrade unnecessary unless sizing-field transfer artifacts or pinched remeshing space are demonstrated. **Feature alignment is NOT covered by the shell** (no crease/patch-curve constraint — the skeleton's job); construction mean ~6 min/model (2020 hardware); clean input contract only; projection evaluation is FP (~1e-8 round-trip), checks are predicate-exact |
| Jiang et al. 2022 (wildmeshing toolkit) | FULL_READ (14/14 pages) | IDAS declarative model: before/after hooks with automatic topology+attribute rollback, invariants as first-class runtime-checked predicates, explicit attribute transfer rules, scheduler with stale-entry invalidation, tuple navigation; envelope-as-invariant packaging of Wang 2020 is a few lines; optimistic vertex-mutex 2-ring locking: 11-20x on 32 threads for surface workloads, **saturates at ~8 threads for tet edge ops** | **port the architecture pattern; do not depend on the library** — validates our guarded transactional local-operator loop as published state of the art; cheap borrowings: tuple-tagging queue invalidation, before-hook-only pre-state reads | Parallelism is **explicitly nondeterministic** ("our concurrent implementation is not deterministic", Section 4.1): no seeded replay, postponement-on-conflict reorders the priority schedule (degrades longest-edge-first; leaves AMIPS>400 tets at fixed budget) — conflicts with our bit-identical hard gate; serial overhead 2-8x vs hand-tuned on some workloads; tri/tet simplicial only (no hex/poly) |
| Dapogny et al. 2014 (mmg) | FULL_READ (25/25 pages, 6 rendered) | The closest open-source analogue of the target contract: operator quartet with per-class gates, collapse class hierarchy (interior < surface < ridge/reference < singular/required) = per-entity provenance skeleton in production; split-then-collapse internal swap; staged schedule (geometry→size→polish); convex-hull Hausdorff pre-filter; curvature sizing `h = sqrt(9 eps / (2 max|k_i|))` + `log(hgrad)` gradation; marching-tet cut-then-heal for the L3 implicit route | copy the class hierarchy, staged schedule, and convex-hull bound as fast pre-filter; reference edges (label interfaces) as first-class = CFD patch preservation anchor | **`hausd` is LOCAL and non-accumulated**: each op is gated against a Bezier model rebuilt from the *current* mesh, never against the original input — total drift is unbounded, so our contract must be strictly stronger (accumulated envelope `TRI-ENV-ACCUM1` or shell, plus final two-sided audit); no persistent input-feature link (type tags + rebuilt curves only); FP tolerance gates, no exact predicates; sweep/candidate order unspecified (nondeterministic); quality-constant erratum: printed `alpha = 144*sqrt(3)` gives Q=2 on the regular tet (`72*sqrt(3)` yields 1) — ordering unaffected, do not copy the constant |

## First synthesis decision

The first native-tri implementation should not be an unguarded global
split/collapse/flip/smooth pass. The literature already supports separating:

1. hard feasibility: manifold link condition, no fold-over, feature/patch class,
   and bounded surface error;
2. primary optimization: worst interior angle;
3. secondary optimization: edge-length distribution, valence regularity, and
   vertex budget.

This ordering also matches the project cap-aware policy: fidelity and topology
remain hard constraints while quality and complexity compete inside the user
budget.

Two refinements from the batch-2 full reads:

- The "bounded surface error" element of the hard-feasibility layer now has
  **three competing contract levels**, in increasing strength and cost:
  sampled Hausdorff gates (Hu 2016/2017, Cheng 2019, Zhang 2022 — cheap, can
  miss maxima between samples, no correspondence) < accumulated local envelope
  (Borouchaki-Frey 2005 / `TRI-ENV-ACCUM1` — conservative bookkeeping, still
  discrete) < static bijective shell (Jiang 2020 / Liu-Ji 2024 /
  `TRI-SHELL-DOMAIN1` — edit-order-independent containment plus provenance
  transfer). The error-gate design must pick a level per quality tier rather
  than assume one gate fits all.
- **Ordering evidence for the passes themselves:** Cheng 2019's rescue
  experiment (EBFR failures drop from 38 to 11 of 107 when seeded with a
  refine-to-bound result) supports running a refinement-based pass into the
  error-bounded space *first*, and only then a gated worst-angle improvement
  pass — refine-first-then-angle-improve, not the reverse.

## Current-code mapping

- `core/preprocessor/native_remesh/isotropic.py` already uses the correctly
  ordered Botsch thresholds (`split > 4L/3`, `collapse < 4L/5`) and valence
  goals 6/4.
- Its sizing remains global rather than Dunyach's per-vertex curvature field;
  the `face.py` adaptive switch currently scales one global target from the
  feature-vertex fraction.
- The low-level relocation path locks every detected feature vertex and may
  project to the nearest original vertex. The higher-level face engine does
  provide closest-point-on-triangle projection, but neither path implements
  provenance-aware corner pinning versus degree-two feature sliding.
- Existing output gates are useful final rejection checks. They do not replace
  per-operation link-condition, fold-over, semantic-feature, local-quality,
  and conservative two-sided envelope simulation before each commit.
- `core/preprocessor/native_remesh/cvt.py` is not a CVT/RVD implementation: it
  moves vertices toward incident-face area-weighted centroids without Voronoi
  cells, restricted clipping, seed optimization, or RDT extraction.
- The current face-wise split pass selects one longest edge per triangle. A
  shared edge is not represented as one atomic two-face transaction, so the
  implementation must be audited for nonconforming T-junction creation before
  any literature-derived quality optimizer is layered on top.

## Citation coverage

Backward and selected forward snowballing from the first three local-operation
papers produced 35 primary candidates across local operators, error envelopes,
CVT/RVD, Poisson-disk sampling, anisotropy, repair, and parallel execution.
The screened inventory is in `native_tri/citation_snowball_batch1.md`; six
abstract-only papers and their DOIs are in `inaccessible_papers.md`.

## TRI-SHELL-PROVENANCE1 implementation evidence (2026-07-26)

The Jiang-2020 provenance datum is now implemented on the current DOMAIN1
linear-shell MVP as a default-OFF report lane
(`AUTO_TESSELL_TRI_SHELL_PROVENANCE1=1`). Canonical-tet affine coordinates
provide `(source prism/face, alpha, beta, normalized h)`, an FP inverse and
`h=0` middle projection, frozen source-face/patch payload records, and a
deterministic face-centroid census. Ambiguous, pinched, unmapped, and
non-finite cases are counted and deliberately receive no payload. The lane is
fail-open/report-only: OFF and ON produce byte-identical mesh state and
identical guard/checkpoint histories, including a forced reporting exception.

Measured coverage was 12/12 cube faces, 128/128 cylinder faces, and 1280/1280
sphere faces, with zero ambiguous/unmapped samples. Max FP round-trip errors
were respectively `1.110e-16`, `1.388e-16`, and `2.483e-16`; p95 errors were
`1.110e-16`, `1.039e-16`, and `1.272e-16`. Report runtimes were 0.017120 s,
0.111792 s, and 1.256523 s (build: 0.006744 s, 0.020977 s, 0.364499 s). The
cylinder required `local_scale_fraction=0.2`; the default 0.5 shell failed
I1/I2, confirming that this result is not a general construction guarantee.

Evidence scope: this does **not** close Jiang's 24-tet/all-order I1, full I2,
beveling, singularity construction, feature alignment, or whole-face coverage
contracts. Candidate discovery remains the unchanged brute-force AABB scan.
`TRI-SHELL-CANDIDATE1` was measured on cube/cylinder/sphere and killed because
the deterministic index was slower on all three despite bit-exact candidate,
attribution, and repeat equivalence; see `TRI-SHELL-CANDIDATE1-KILL.md`.
Full DOMAIN completion remains separate.

## 2026-07-27 — TRI-CURV-SIZE1

- Existing implementation: `estimate_curvature_sizing()` with guarded Dunyach
  radicand, flat fallback, and bounded length extension; operator-loop edges
  consume endpoint-mean target lengths.
- `epsilon=0.01` direct measurement: cube `L=0.25/0.25/0.25` (lower bound),
  sphere `L=0.1608498/0.1722745/0.1724617` (min/median/max).
- One sizing-aware round with smoothing disabled preserved watertight edge
  incidence `[2]` on cube and sphere; cube accepted 55 guarded operations,
  sphere accepted 0 at this target.
- `tests/test_native_tri*.py`: `21 passed`.
- **Decision:** scalar sizing measured/retained; anisotropic metric algebra and
  BL metric intersection remain separate cards.

## 2026-07-27 — TRI-METRIC-FIELD1 / SIZING-BL-INTERSECT1

- Added an unconnected primitive module
  `core/preprocessor/native_tri/metric.py`: finite/SPD audit, tangent/normal
  BL source metric, metric edge lengths, and conservative SPD intersection.
- The intersection is a generalized-eigenvalue Loewner upper bound, so neither
  surface nor BL requested resolution is silently relaxed. Equal fields are
  idempotent and rigid coordinate rotations commute with the operation.
- Four analytic tests pass: diagonal intersection/dominance, rotation
  covariance, requested tangent/normal eigenvalues, and endpoint metric edge
  length. Existing native-tri tests remain `21 passed`; the full native-tri
  glob including the eight metric tests is `29 passed`.
- **Not wired:** no split/collapse/flip/smooth behavior changed. The next gate
  is a four-fixture isotropic/curvature/BL measurement before any operator-loop
  integration.

### Four-fixture result

- Cube isotropic: all 8 metrics valid, condition `1.0`, edge metric lengths
  `4.0–5.657`.
- Sphere curvature field: target lengths `0.16077–0.17215`, all 162 metrics
  valid, edge lengths `1.603–1.892`.
- Cylinder curvature field: target lengths `0.25–2.0`, all 66 metrics valid,
  edge lengths `0.784–8.038`.
- Cube BL proxy (`normal_length=0.1`): SPD audit passed, but full 3-D edge
  lengths inflated to `32.8–65.1`. The normal eigenvalue must not participate
  in surface-edge evaluation at sharp corners; tangent surface spacing and
  normal BL placement are separate quantities.
- **Decision:** do not wire the full BL proxy into operators. Open the next
  measurement as tangent-only metric evaluation plus an explicit normal-layer
  handoff/feature-corner rejection rule.
- Feature-aware tangent audit: sphere had `0` vertices above 45 degrees and
  `480/480` evaluable edges; cube had `8` feature vertices and rejected
  `18/18` edges; capped cylinder had `64` feature vertices and rejected
  `192/192` edges. No feature vertex was smoothed or moved.

## 2026-07-27 — SIZING-METRIC-ALG1 guarded operator handoff

- `OperatorTransaction` now accepts an optional per-vertex `(n, 3, 3)` SPD
  `metric_field`; the default `None` path is unchanged.
- With no scalar target override, split/collapse hysteresis uses the endpoint
  metric length and the unit-mesh bounds `4/3` and `4/5`. World-space link,
  fold-over, and exact-orientation guards remain active.
- A split inserts an endpoint-intersection metric; a collapse replaces the
  keeper metric with the same conservative SPD intersection before removing
  the victim. A custom candidate that changes vertex count without this
  transaction handoff is rejected rather than leaving a stale field.
- Verification: single-edge split and cube-edge collapse both remap the field
  with finite positive eigenvalues; metric-only `run_one_round(smooth=False)`
  executes without a scalar target; invalid field length is rejected.
- Full native-tri glob plus the new handoff checks: **33 passed**. No BL normal
  metric is wired into surface operators; tangent-only evaluation and the
  separate normal-layer handoff remain the next card.

## 2026-07-27 — TRI-BL-TANGENT1 guarded surface handoff

- `OperatorTransaction` can now receive endpoint normals and an optional
  feature-vertex mask alongside the SPD field. Surface split/collapse
  hysteresis uses only the tangent projection; the BL normal eigenvalue is
  deliberately ignored for surface edges.
- Edges whose endpoint normals do not define an allowed common tangent plane,
  or which touch a declared feature vertex, are explicitly rejected rather
  than evaluated with a fabricated tangent plane. Declared metric feature
  vertices are also locked against smoothing; topology-changing operations
  conservatively remap normals and the feature mask.
- Synthetic tangent/feature and normal-discontinuity cases plus the complete
  native-tri glob pass: **35 passed**. This closes the surface-side handoff
  only; normal-layer placement remains unimplemented and separate.

## 2026-07-27 — TRI-BL-HANDOFF1 report-only audit

- Added `audit_bl_handoff()` and `BLHandoffReport` to separate reciprocal
  metric strength along the wall normal from the two tangent lengths.
- The analytic BL proxy (`L_t=0.5`, `L_n=0.1`) reports exactly those scales;
  feature vertices are counted as explicit tangent rejections, not assigned a
  fabricated plane. No points, normals, or operator decisions are mutated.
- Full native-tri glob plus the handoff tests: **37 passed**. This closes the
  audit card; production normal-layer placement remains a later feature/BL
  integration card.

### `TRI-METRIC-FIELD1` four-fixture repeat audit — 2026-07-27

The report-only metric diagnostic was repeated and its output was
byte-identical. Cube isotropic metrics had eigenvalues `16/16` and edge metric
lengths `4.0–5.656854`; sphere curvature sizing had target lengths
`0.160770–0.172150` and edge lengths `1.603004–1.892360`; cylinder had target
lengths `0.25–2.0` and edge lengths `0.784137–8.038338`. The BL proxy with
normal length `0.1` had eigenvalues `16–1600`, condition `100`, and full 3-D
edge lengths `32.8013–65.1185`; sharp cube/cylinder features rejected all
`18/18` and `192/192` surface edges from tangent evaluation.

Focused metric/operator verification remained **33 passed**. Decision:
representation, SPD audit, deterministic repeat, and guarded operator handoff
are sound; full normal-layer placement is still not implemented, and the BL
normal eigenvalue remains excluded from surface operators.

## 2026-07-27 TRI-CORPUS-1 expanded L2 baseline

`scripts/diag_native_tri_corpus_expanded.py` isolated each fixture while
reusing the existing L2 `native_remesh.isotropic` measurement. The new
operator-loop was not called. Nine of ten expanded fixtures returned a
measurement; `sharp_features_micro_ridge.stl` raised the existing
`IndexError: too many indices for array` in `_tangential_relocate` after the
remesher produced an empty face array.

| fixture | manifold | watertight | min/max angle | sampled Hausdorff | feature recall proxy |
|---|---|---|---:|---:|---:|
| cube | true | true | `47.64/84.73°` | `0.7833` | `66.7%` |
| sphere | true | true | `54.11/71.78°` | `0.0169` | n/a |
| cylinder | false | false | `11.10/153.53°` | `0.5198` | `26.6%` |
| very thin disk | false | false | `0/176.22°` | `0.5346` | `3.1%` |
| wing with spike | true | false | `1.10/173.40°` | `0.8299` | `5.9%` |
| extreme needle | false | false | `0.156/179.67°` | `5.0000` | `33.3%` |
| perforated plate | false | false | `0.199/179.24°` | `1.5001` | `0.024%` |
| multi-scale sphere | true | false | `0/114.30°` | `0.4178` | `41.7%` |
| sharp micro-ridge | exception | exception | — | — | — |
| high-genus dual torus | false | false | `1.88/175.81°` | `0.2468` | n/a |

This confirms the L2 path is a diagnostic baseline, not a native-tri product
implementation: manifold/watertight, geometry drift, angle, and feature
provenance failures are widespread outside the simple cube/sphere cases. The
expanded corpus is therefore a correctness gate for the new guarded
operator-loop, not a target for silently repairing `native_remesh` in this
card. The raw report is retained at
`tests/stl/tri_corpus_20260727.json`.

## 2026-07-27 TRI-OPERATOR-CORPUS-1 first guarded round

The new native-tri operator loop was exercised directly on five compact
fixtures with one split→collapse→flip round and smoothing disabled. The
report-only runner kept all existing link, fold-over, and exact-orientation
guards active. The output JSON was repeated twice with identical SHA-256
`ff0e18af4504b7fdd8a5e4115ef73bd5e8346105e9042d2c9a68f3b62732ae3c`.

| fixture | accepted/rejected reports | output V/F | manifold | watertight | min doubled area | min/max angle |
|---|---:|---:|---|---|---:|---:|
| cube | `16/3` | `4/4` | true | true | `0.7291` | `50.58/69.71°` |
| sphere | `0/0` | `642/1280` | true | true | `0.01817` | `54.10/71.80°` |
| cylinder | `204/18` | `18/32` | true | true | `0.1404` | `18.95/129.60°` |
| very thin disk | `176/22` | `58/112` | true | true | `0.00750` | `5.62/168.75°` |
| wing with spike | `34/14` | `24/32` | true | false | `0.00418` | `9.65/153.22°` |

All output coordinates were finite and no accepted transaction created a
zero-area triangle. This closes the first correctness smoke wave, not a
quality pass: thin disk has a near-flat angle distribution and wing remains
open/non-watertight. Keep `TRI-OPERATOR-CORPUS-1` as a permanent gate and open
separate quality/feature cards rather than relaxing topology or orientation
guards.

The expanded correctness wave added needle and multi-scale sphere. Needle
completed in `61/17` accepted/rejected reports with manifold/watertight true,
but max angle `179.79°` and sampled Hausdorff `5.0000`; multi-scale sphere
completed in `32/68`, manifold/watertight true, with angles
`31.26/81.79°`. A one-round high-genus dual-torus run exceeded the 120-second
diagnostic budget before returning, so it is recorded as a performance card,
not as a correctness failure. The seven completed rows are retained in
`tests/stl/tri_operator_corpus_20260727.json`.

### 2026-07-27 TRI-OPERATOR-PERF-1 — dual-torus phase timing

The report-only profiler `scripts/profile_native_tri_operator_timeout.py`
mirrored the production split→collapse→flip order and added no operator
behavior. On `high_genus_dual_torus.stl` (2,047 input vertices, 4,096 input
faces, target edge `0.3314317589`), split took `16.26 s` and accepted `1,472`
of `6,144` initial edge candidates. Collapse took `135.56 s`, accepted `2,938`
edits over `2,939` scans, and rebuilt the candidate list to a cumulative
`10,868,702` candidate checks before ending at `585` vertices and `1,172`
faces. Flip then took at least `148.16 s` for its first `225` accepted reports
and timed out at the `300 s` diagnostic limit without reaching its phase end.

This is a deterministic algorithmic scaling issue, not an observed infinite
loop: each accepted edit triggers a full-edge scan, while `should_flip_edge`
also constructs and scores a local candidate for every scanned edge. The
minimum safe next card is a semantics-preserving worklist/priority-queue
experiment with output and report-sequence A/B checks. Do not lower topology,
fold-over, exact-predicate, or quality guards merely to meet a timeout.

### 2026-07-27 TRI-OPERATOR-PERF-1 worklist A/B — falsified as drop-in equivalent

The report-only `scripts/diag_native_tri_worklist_ab.py` implemented a stable
label + heap experiment, refreshing only the local edge neighborhood after an
accepted collapse/flip. This follows the local-priority-queue pattern used in
classical remeshing/simplification literature, but it is not a drop-in
replacement unless its candidate semantics are proven equivalent.

| fixture | current time / accepted / V×F | worklist time / accepted / V×F | topology equal | byte digest equal |
|---|---:|---:|---|---|
| cube | `0.0255 s / 16 / 4×4` | `0.0135 s / 11 / 10×16` | yes | no |
| cylinder | `0.7285 s / 204 / 18×32` | `0.1439 s / 99 / 98×192` | yes | no |
| very thin disk | `2.3853 s / 176 / 58×112` | `0.1608 s / 120 / 84×164` | yes | no |

The candidate is therefore **falsified as semantics-preserving**: it changes
accepted-operation counts and final mesh arrays even though these three small
fixtures remain manifold/watertight. It is retained only as a lower-bound
performance diagnostic. Do not wire it into production or use its quality
numbers as an improvement claim. A future optimization must either preserve
the current full-rescan candidate ordering exactly or introduce an explicit
new operator-loop contract and corpus gate.

### 2026-07-27 TRI-OPERATOR-LOCAL-GUARD1 — opt-in equivalence experiment

An opt-in `AUTO_TESSELL_TRI_LOCAL_GUARDS1=1` path was added to test a narrower
guard domain while leaving the default OFF path untouched. It first proves the
committed state has a valid global link condition, then checks the changed
faces plus every face incident to their changed vertices. Ambiguous candidate
correspondences fall back to the legacy full-mesh guard. Link, fold-over,
exact-orientation, finite, manifold, and watertight rules were not weakened.

The flag passed the core operator/metric/shell suite (`37 passed`) and matched
the OFF path exactly on cube, cylinder, thin disk, needle, and multi-scale
sphere: accepted/rejected reports, final coordinates/faces, quality values,
and topology were byte-identical. On the high-genus dual-torus profiler,
split improved `16.26 -> 11.32 s` and collapse `135.56 -> 129.39 s`; flip
reached `250` accepted reports by `300 s` versus `225` in the OFF run, but
neither run completed the phase inside the bound. This is an equivalence
success on the small corpus but not a sufficient performance win for
promotion. Keep the flag opt-in and record the card as **measured,
insufficient** pending a truly exact-result-preserving reduction of full-mesh
validation cost.

### 2026-07-27 TRI-CURV-SIZE1 repeat and operator smoke

The optional scalar curvature lane was rerun on the current three benchmark
fixtures with `epsilon=0.01`. The sizing field remained finite and
deterministic: cube `0.125/0.137108/1.000` (min/median/max after one guarded
round), sphere `0.160850/0.172274/0.172462`, and cylinder
`0.125/0.125/1.000`. One no-smoothing round accepted `55` cube operations,
`0` sphere operations, and `304` cylinder operations. All three outputs
remained manifold and watertight. The current metric/operator/guard suite is
`34 passed`.

This confirms the scalar Dunyach field and endpoint-mean hysteresis handoff,
but not a production default: the cylinder field spans cap/side curvature
classes and the cube/cylinder sharp-feature mask rejects all surface edges
that lack one common tangent plane. Anisotropic BL normal placement and
ODT-style relocation remain separate, unconnected cards.

### 2026-07-27 TRI-ADAPT-LOOP1 scalar A/B smoke

The current operator loop was compared with constant world-space sizing on
cube, sphere, and cylinder. The curvature lane (`epsilon=0.01`) kept all
outputs manifold and watertight. Relative to the constant lane, it produced
cube `26/48` vertices/faces with `25` accepted smooth moves (constant `8/12`,
`8` smooth moves), sphere unchanged at `642/1280` with `641` smooth moves in
both lanes, and cylinder `59/114` with `46` smooth moves (constant `33/62`,
`33` smooth moves). This is a sizing/relocation interaction measurement only;
the current relocation target is still an area-weighted one-ring centroid, not
the full Dunyach ODT barycenter. No default behavior or quality gate changed.

The sizing handoff was then tightened to use the conservative minimum of the
two endpoint target lengths for each edge. The previous endpoint mean could
relax an edge whose one endpoint required finer resolution; the minimum keeps
the hysteresis decision conservative without changing the topology guards.
The focused metric/operator/local-guard suite passed `35` tests, and the
metric audit remained finite and SPD on cube, sphere, and cylinder. This is
still a scalar sizing-policy change in the opt-in native-tri lane; it is not
the anisotropic ODT/BL relocation card.

### 2026-07-27 TRI-ODT-RELAX1 — sizing-aware barycenter diagnostic

The opt-in `sizing_aware_relocation=True` path now implements Dunyach
equation (6): each incident triangle barycenter is weighted by its area and
the mean of its three vertex target lengths. The existing tangent projection,
surface projection, exact orientation, fold-over, manifold, and rollback
guards remain unchanged; the default centroid path is unchanged.

| fixture | centroid min angle | sizing-aware min angle | accepted smooth | topology/finite |
|---|---:|---:|---:|---|
| cube | `15.3643°` | `17.1170°` | `25 / 25` | pass / pass |
| sphere | `52.8198°` | `53.5676°` | `641 / 641` | pass / pass |
| cylinder | `0.4866°` | `3.8507°` | `50 / 53` | pass / pass |

The six-row report repeated byte-identically. This is a measured opt-in
improvement, not a production-default promotion: feature-line sliding,
two-sided envelope gating, and anisotropic BL intersection remain open.
