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
