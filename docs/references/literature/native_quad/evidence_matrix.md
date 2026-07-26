# Native Quad / Quad-Dominant Literature Evidence Matrix

Status: batch 1 complete. `FULL_READ` means the complete paper, equations,
algorithms, experiments, limitations, and references were inspected.

| Paper | Status | Main evidence | Candidate cards | Critical caution |
| --- | --- | --- | --- | --- |
| Alliez et al. 2003 | FULL_READ | Curvature tensor, anisotropic spacing, curvature-line sampling, feature-side smoothing, umbilic fallback, conforming hybrid extraction | `QUAD-METRIC-FIELD1`, `QUAD-FEATURE-SIDE1`, `QUAD-UMBILIC-MODE1`, `QUAD-CONFORMING1` | Genus-zero/global-parameterization assumption; sampling bottleneck; no hard fidelity or quality guarantee |
| Jakob et al. 2015 | FULL_READ | 4-RoSy plus 4-PoSy, intrinsic/extrinsic energies, multiresolution colored relaxation, singularity-aware extraction | `QUAD-ROSY1`, `QUAD-POSY1`, `QUAD-MULTIRES1`, `QUAD-SINGULARITY1`, `QUAD-EXTRACT1` | Local minima and extra singularities; extraction can become non-manifold or lose elements |
| Huang et al. 2018 | FULL_READ | Integer-offset regularity, multiresolution min-cost flow, inversion cleanup, constrained continuous solve, simple quad extraction | `QUAD-OFFSET-LEDGER1`, `QUAD-MCF1`, `QUAD-INVERSION1`, `QUAD-FEATURE-SLIDE1`, `QUAD-FIDELITY1` | SAT is incomplete in practice; roughly 20% watertightness failures reported; topology regularity can erase detail |

## Code audit and decision

`core/preprocessor/native_remesh/quad_dominant.py` is a deterministic,
quality-gated triangle-pair merger. It rejects boundary/feature/wall crossings,
non-convex pairs, poor scaled Jacobian, excessive aspect ratio, and warpage.
Tests cover a planar pair, cube pairing, and warped-pair rejection. This is a
useful conservative fallback, but not a quad meshing engine: it has no field
construction, singularity representation, global consistency, or independent
surface sampling.

Implement in evidence order:

1. Common hard contract: manifold orientation, patch/feature provenance,
   bidirectional fidelity, deterministic rollback.
2. Curvature/size metric and 4-RoSy orientation field.
3. 4-PoSy position field plus explicit integer-offset/singularity ledger.
4. Transactional conforming extraction; retain the pair merger as fallback.
5. Only then add min-cost-flow singularity reduction and bounded inversion
   cleanup. Never accept topology regularity at the expense of fidelity.

Primary metrics: quad fraction, singularity count/type, minimum scaled
Jacobian, angle/area distortion, maximum bidirectional distance, feature
coverage, manifold/watertight status, determinism, peak memory, and runtime.

## 2026-07-26 QUAD-ROSY1 result (measured, diagnostic only, zero mesh edits)

**Note on "the code audit" above**: `quad_dominant.py` and its test are
uncommitted (`git ls-files` does not track either) and, as found while
committing this card, the test itself no longer imports cleanly against
the current `native_remesh/__init__.py` (`ImportError: cannot import name
'QuadDominantConfig'`) -- the "deterministic, quality-gated triangle-pair
merger" this section describes is currently broken/unverified, not a
working fallback. Not fixed here (out of this card's scope); flagged so
the next quad card doesn't assume it as a working baseline.

Delivered `core/preprocessor/native_remesh/rosy_diagnostic.py` (870
lines) + `tests/test_native_quad_rosy_diagnostic.py` (22 tests, all
passing) -- a faithful, diagnostic-only port of Jakob 2015's 4-RoSy
orientation field (extrinsic/intrinsic smoothness energy, nonlinear
Gauss-Seidel relaxation) with singularity detection gated by a falsifiable
correctness check: Poincare-Hopf (`index_sum == 4 * chi`).

| Shape | V | F | chi | index_sum (ext / int) | singularities | energy (start -> end) | curvature dev |
| --- | ---: | ---: | ---: | --- | --- | --- | --- |
| cube | 8 | 12 | 2 | 8 / 8 (exact) | 8, all +1/4 | 5.79 -> 3.78 | n/a (umbilic) |
| cylinder (genus 1) | 256 | 512 | 0 | 0 / 0 | 18 ext / 16 int | 189.27 -> 48.34 | 2.67 deg vs 22.74 deg random baseline |
| bracket (genus 3) | 204 | 416 | -4 | -16=4*chi (12 reconciled) / -16=4*chi | 36 ext / 54 int | 158.30 -> 45.27 | 16.26 deg vs 23.51 deg baseline |

Cube reproduces the textbook answer exactly (8 corners, index +1/4,
sum = chi). Cylinder shows near-perfect curvature-line alignment
(2.67 deg). Bracket exposes the actual problem: single-resolution
relaxation is stalled (bit-identical energy at 20 and 60 sweeps) and the
extrinsic/intrinsic connections disagree materially on sharp geometry (18
vs 4 ambiguous +-1/2 faces on the same field) -- roughly one singularity
per 8-12 faces, far denser than a usable quad layout.

**Bug found+fixed**: an initial sign convention on the index loop sum
passed Poincare-Hopf on cube/cylinder (both sign-symmetric by their own
chi) but failed on the bracket -- caught by the identity, not by
inspection.

**Verdict: do not proceed straight to `QUAD-POSY1`.** A 4-PoSy
integer-offset ledger built on this field's ambiguous ±1/2 singularities
would reproduce Huang 2018's own ~20% watertightness-failure mode.
Recommended next: `QUAD-MULTIRES1` (coarse-to-fine relaxation, the
paper's own answer to local minima) before `QUAD-POSY1`; `QUAD-SINGULARITY1`
(explicit ledger) is a smaller acceptable substitute since this
diagnostic already produces most of its contents.

## 2026-07-26 QUAD-MULTIRES1 result (measured, diagnostic only, zero mesh edits)

Extended `core/preprocessor/native_remesh/rosy_diagnostic.py` (870 → 1339
lines) with Jakob 2015 §4's coarse-to-fine scheme and added
`tests/test_native_quad_multires.py` (31 tests). Single-resolution is
untouched and still the default (`multires=False`), so all 22 QUAD-ROSY1
tests pass unchanged.

New public surface: `build_coarsening_hierarchy` (deterministic greedy
vertex matching scored by `dot(n_i,n_j) * min(a_i,a_j)/max(a_i,a_j)`),
`prolongate_orientations`, `allocate_sweeps`,
`optimize_orientations_multires`, `run_rosy_diagnostic(..., multires=True)`.
Scope reduction: single-pass maximal matching, so clusters are size 1 or 2
and contraction is at best 2× per level — the paper's aggregation is a
scored multi-pass process. Prolongation and relaxation are the paper's.

Comparison at a **matched total sweep budget** (multires gets `n_sweeps`
across *all* levels, not per level — deliberately harsh, since a coarse
sweep is far cheaper than a fine one):

| Shape | V | hierarchy | budget | E single → multires | singularities (ext) | ±1/2 faces ext/int | Poincaré-Hopf |
| --- | ---: | --- | ---: | --- | --- | --- | --- |
| flat grid 5×5 | 25 | 25→13 | 30 | 8.2e-7 → **5.6e-12** | 0 → 0 | 0/0 | n/a (open) |
| octahedron | 6 | 6→4→2 | 30 | — → **0.0 exact** | 8 (+1/4 each) | 0/0 | exact, all 5 seeds |
| cube | 8 | none (V<16) | 20 | 3.778 → 3.778 (identical) | 8 → 8 | 0/0 | exact |
| cylinder (g1) | 256 | 256→128→72→44→29→21→16 | 20 | 48.34 → **45.99** | 18 → 18 | 0/0 | exact |
| cylinder (g1) | 256 | same | 60 | 48.34 → **44.83** | 18 → **16** | 0/0 | exact |
| bracket (g3) | 204 | 204→103→54→30→17→11 | 20 | 45.27 → **44.11** | 36 → 38 | **18/4 (unchanged)** | reconcilable |
| bracket (g3) | 204 | same | 60 | 45.27 → **44.17** | 36 → 38 | **18/4 (unchanged)** | reconcilable |

**Poincaré-Hopf held in every multires run** (exact on cube / octahedron /
cylinder, reconcilable on the bracket) — the prolongation does not corrupt
the field. The tetrahedron's known coarse-index aliasing is unchanged, as
expected: it is a mesh sampling limit, not an optimization one.

**Answer to the card's falsifiable question — split verdict.**

1. *Does multires reduce the singularity count?* **On the cylinder, yes**
   (18 → 16 at budget 60, and the extrinsic/intrinsic readouts then agree
   exactly at 16/16). **On the bracket, no** — 36 → 38 at seed 0, and 38 at
   every seed. Multires is not finding a topologically simpler field there.
2. *Does multires narrow the extrinsic/intrinsic 18-vs-4 disagreement?*
   **No — not at all.** The split is exactly 18/4 under every seed in both
   modes. This is the card's most useful result and it is a **negative**
   one: the disagreement is a geometric property of the bracket's sharp
   edges (the two discrete connections genuinely differ where the normal
   turns ~90° across an edge), **not** an artifact of the solver stalling.
   Better optimization will never close it, so `QUAD-POSY1` must be
   designed to tolerate it rather than wait for it to go away.
3. *What multires does buy:* **reproducibility.** Across seeds 0–4 on the
   bracket at budget 20, single-resolution energy spans 43.72–45.89
   (spread 2.17, singularity count 36–41); multires spans 44.105–44.109
   (spread 0.0037, always 38) — a ~580× variance reduction. It reliably
   finds the *same* minimum rather than a *better* one. That is the
   property a downstream integer solver actually needs, and it is why the
   matched-budget energy claim is stated with a 2% tolerance, not as a
   strict inequality: multires wins 4 of 5 bracket seeds and *loses* at
   seed 1 (44.11 vs 43.72, ratio 1.0088). It wins 5/5 on the cylinder.
   Multires is also ~2× faster in wall time at equal sweep count.

**Bug/defect found (in the pre-existing single-resolution solver, not
fixed here).** The QUAD-ROSY1 note "bit-identical energy at 20 vs 60
sweeps" is not a stall — it is a **period-2 limit cycle**, parity-locked:

```
cylinder, single-resolution, seed 0
  odd  budgets 19 / 21 / 29 / 31  ->  47.8557 / 47.8542 / 47.8537 / 47.8537
  even budgets 20 / 22 / 30       ->  48.3425 / 48.3419 / 48.3418
```

13 of 30 sweeps *increase* the energy. Cause: the Gauss-Seidel update in
`optimize_orientations` starts with `weight_sum = 0`, so a vertex's new
value is a pure average of its neighbours with no self-term — an undamped
Laplacian smoother, which oscillates on near-bipartite adjacency. Every
QUAD-ROSY1 measurement was taken at an even sweep count and therefore
always sampled the worse phase. Left in place because this card must not
change the existing function's behaviour. Note the multires margins above
survive the correction: 45.99 (multires, 20 sweeps) still beats 47.85, the
*better* phase of the single-resolution cycle.

**Verdict: `QUAD-POSY1` is unblocked, with one caveat and one prerequisite.**
The ±1/2 ambiguity is now proven to be geometric rather than fixable by
optimization, so waiting for a cleaner field is not a plan. `QUAD-POSY1`
should be built on the multires field (deterministic, seed-insensitive)
and must carry the ±1/2 faces explicitly — which is exactly
`QUAD-SINGULARITY1`'s ledger. Recommended order: `QUAD-SINGULARITY1`
(small; the diagnostic already produces most of its contents) → `QUAD-POSY1`.
An optional cheap win first: add a damped/self-weighted Gauss-Seidel
variant to kill the period-2 cycle, as a new function alongside the
existing one.

## 2026-07-26 QUAD-SINGULARITY1 result (measured, report-only, zero field/mesh edits)

Added a frozen, deterministic face ledger over the unchanged extrinsic and
intrinsic `SingularityCensus` objects. The union is sorted by face ID. Every
entry carries the triangle's vertex IDs and centroid, both connection indices,
connection category/agreement, and an `unresolved` guard. A regular readout is
explicit index `0`; centered residue `2` is exposed as admissible indices
`(-2, 2)` (fractional indices `-1/2` and `+1/2`) under that connection. A
consumer may use an entry directly only when both connections report the same
non-ambiguous signed index; exclusive, disagreeing, and half-index entries are
unresolved. This is the explicit data contract for `QUAD-POSY1`: it must branch,
reject, or apply a separately specified resolution policy and must never choose
the positive half-index implicitly.

Measured with `multires=True`, 20 total sweeps, seed 0:

| Shape | singularities ext/int | ±1/2 ext/int | union | shared | ext-only | int-only | shared disagreement | ambiguous union | unresolved | source Poincaré-Hopf |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| cube | 8 / 8 (all +1/4) | 0 / 0 | 10 | 6 | 2 | 2 | 0 | 0 | 4 | exact / exact |
| cylinder (g1) | 18 / 18 | 0 / 0 | 26 | 10 | 8 | 8 | 0 | 0 | 16 | exact / exact |
| bracket (g3) | 38 / 56 | **18 / 4** | 69 | 25 | 13 | 31 | 6 | 18 | 54 | reconcilable / reconcilable |

The cube's two connections each retain the textbook eight `+1/4` indices;
their triangle representatives differ on four exclusive faces, which the
ledger now exposes instead of conflating with shared-index disagreement. The
bracket preserves the measured extrinsic/intrinsic 18-vs-4 half-index split;
the four intrinsic ambiguous faces are contained in the 18-face ambiguous
union.

The ledger reproduces the original census sums exactly: cube `8 / 8`, cylinder
`0 / 0`, and bracket `32 / -8` in quarter-turn units. The bracket values remain
reconcilable to `4 * chi = -16` by the source censuses' existing ambiguity rule.
Pre-card baseline and post-card field values were bit-identical:

| Shape | extrinsic energy start (before → after card) | extrinsic energy final (before → after card) | census count ext/int (before → after card) |
| --- | --- | --- | --- |
| cube | 5.79185018809548 → 5.79185018809548 | 3.7781425115852247 → 3.7781425115852247 | 8/8 → 8/8 |
| cylinder | 189.27339617265298 → 189.27339617265298 | 45.99098451009072 → 45.99098451009072 | 18/18 → 18/18 |
| bracket | 158.29616581517368 → 158.29616581517368 | 44.10917070232732 → 44.10917070232732 | 38/56 → 38/56 |

Synthetic disjoint triangles pin union ordering, all three categories,
zero-on-the-regular-connection semantics, exact face vertices/centroids,
`(-2, 2)` admissibility, shared disagreement, and unresolved classification.
Repeated bracket runs compare equal as frozen dataclasses and as protocol-5
pickle bytes. The diagnostic remains unconnected to mesh generation and has no
environment flag.

## 2026-07-26 QUAD-POSY1 result (measured, report-only; candidate policy KILL)

Added `core/preprocessor/native_remesh/posy_diagnostic.py` and
`tests/test_native_quad_posy_diagnostic.py`. The diagnostic reuses the
unchanged deterministic multiresolution 4-RoSy field and the
`QUAD-SINGULARITY1` ledger, then records an auditable per-face integer-offset
candidate: raw integer offsets, the three quarter-turn rotations into the
face frame, rotated offsets, the regularity residual (their integer sum), and
the signed 2-D orientation determinant of the first two rotated offsets.
There is no min-cost flow, SAT, inversion cleanup, continuous solve, or
extraction in this card.

The local sizing reduction is explicit and deterministic: each triangle uses
the mean of its three edge lengths. Each edge is quantized in the projected
4-RoSy representative at its tail and rotated to a common face frame. A
non-zero residual is counted as a position singularity; a negative determinant
is counted separately as an inversion candidate. These are diagnostics, not
repair instructions.

Measured with `n_sweeps=20`, seed `0`, on the real cube/cylinder/bracket
assets:

| Shape | faces | candidates | position singularities | regularity failures | inversions | unresolved |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| cube, multires | 12 | 16 | 12 | 12 | 3 | 4 |
| cylinder, multires | 512 | 528 | 427 | 427 | 14 | 16 |
| bracket, multires | 416 | 484 | 331 | 331 | 8 | 54 |
| cube, single | 12 | 16 | 12 | 12 | 3 | 4 |
| cylinder, single | 512 | 528 | 401 | 401 | 13 | 16 |
| bracket, single | 416 | 486 | 336 | 336 | 9 | 56 |

The A/B result falsifies a safe policy: multiresolution does not consistently
lower the integer regularity-failure count (cylinder `427` vs `401` single,
bracket `331` vs `336` single), and the unresolved branch contract remains
material. The hard bracket continues to expose the explicit `(-2, 2)` branch
for every half-index entry; no candidate is resolved to `+2` or `+1/2`.

**Verdict: KILL candidate application.** The ledger is useful as an audit
surface, but these data do not support default-on integer balancing or any
mesh mutation. `AUTO_TESSELL_QUAD_POSY1=1` is provided only as a default-OFF
future report-hook switch; no production caller was added. Existing quad
extraction/generation/fallback behavior is unchanged. Synthetic contract
tests cover regular offsets, rotations, zero residual, determinant, half-index
branch preservation, connection disagreement, no mutation, and default-OFF
behavior. The exact `native_quad_literature_integrated_development_plan_2026-07-23.md`
file requested for the initial full read was absent from this worktree and its
Git history; the result is recorded in the current continuation plan instead.
