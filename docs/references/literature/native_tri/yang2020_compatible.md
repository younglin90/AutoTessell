# Yang et al. - Error-bounded Compatible Remeshing

## Bibliography and access

- Yang Yang, Wen-Xiang Zhang, Yuan Liu, Ligang Liu, Xiao-Ming Fu.
- *ACM Transactions on Graphics* 39(4), Article 113, July 2020, 15 pages.
- DOI: `10.1145/3386569.3392434`.
- Supplied file: `C:/Users/user/Downloads/yang2020.pdf`.
- Review status: `FULL_READ` on 2026-07-23. All 15 pages, including the
  complete reference list, were read. Pages 1, 3, 5, 6, 8, 11, 14, and 15
  were rendered at 2x resolution and visually checked; equations, flowcharts,
  algorithm conditions, the results table, limitations, and bibliography were
  legible and consistent with the extracted text.

This is the paper previously represented by the inaccessible DOI
`10.1145/3386569.3392434`. The supplied PDF proves that the author key is
**Yang 2020**, not Diamanti 2020.

## Problem and scope

The input is a pair of oriented, topologically equivalent triangle surfaces
`P` and `Q`, plus sparse corresponding landmark vertices. The outputs `P_r`
and `Q_r` seek five properties simultaneously:

1. identical connectivity;
2. low distortion of the piecewise-linear inter-surface map;
3. fairly regular triangles;
4. two-sided Hausdorff bounds `d_H(P_r,P) <= epsilon_p` and
   `d_H(Q_r,Q) <= epsilon_q`;
5. low vertex count.

The compatible-pair requirement is outside AutoTessell's current single-mesh
surface-remeshing contract. The paper is nevertheless directly relevant for
curvature sizing, transactional local error guards, conservative fusion of
multiple sizing demands, and cap-aware complexity reduction.

## Two-stage algorithm

### Stage 1 - initialize compatible meshes

The two inputs are cut to disks and bijectively parameterized onto a common
planar domain. The parameterization minimizes symmetric Dirichlet distortion
with a common boundary and bijectivity constraints. Cut paths are refined by
mapping `P` to `Q`, minimizing an ARAP-plus-closeness energy, and recovering
new corresponding seams. The local-global cut solver stops at relative energy
change below `1e-6` or 1000 iterations; the reported weight is `alpha=0.1`.

For input vertex `v_i`, the curvature-derived target length is

```text
F_p(v_i) = sqrt(6 epsilon_p / kappa_i - 3 epsilon_p^2),
kappa_i = max(|kappa_i^max|, |kappa_i^min|).
```

`F_q` is defined analogously and both are linearly interpolated over faces.
The common-domain demand is the conservative fusion

```text
F_d(z) = min(F_p(g_p^-1(z)), F_q(g_q^-1(z))).
```

Corresponding cut segments are first mapped by arc length to a common 1D
segment. Their vertex sets are overlaid and mapped back so that both seams
have identical combinatorics. On the common segment, the target is likewise
the minimum of the two surface demands. A segment is split above `4F/3` and
collapsed below `4F/5`; seam endpoints are fixed. Non-endpoint relocation is
a weighted average of adjacent segment barycenters, with the paper's weight
`omega_l = Length(e_l) F_s(c_l)`. These operators are alternated ten times.
The planar interior is then remeshed while its boundary is fixed, avoiding a
separate chart-stitching step.

The initial output need not meet the error tolerance. The method recomputes
the two distances, decreases target lengths near violations following Cheng
et al. 2019, and regenerates the pair, with a maximum of 100 iterations. The
authors explicitly state that this loop has no convergence guarantee. If it
fails, an overlay construction supplies zero-approximation compatible meshes,
at the price of poor triangle regularity and high complexity.

### Stage 2 - reduce compatible complexity

The initial compatible target field is

```text
F_c(x) = F_c(y)
       = min(F_p(Lambda_p(x)), F_q(Lambda_q(y))),
```

where `x` and `y` are corresponding points and `Lambda` denotes nearest-point
projection to the respective input surface. Each iteration performs paired
local operations and then multiplies the target field by `rho`; `rho=1.2` is
the reported default.

The paired local operators are precise:

- split corresponding edges simultaneously only when **both** lengths exceed
  `4F_c/3`;
- collapse both simultaneously only when **both** lengths are below `4F_c/5`;
  landmark endpoints are preserved and a two-landmark collapse is rejected;
- flip both corresponding edges only when the sum of six deviations from
  60 degrees decreases on **both** meshes;
- relocate a corresponding vertex pair by parameterizing the two one-rings
  to a common boundary, relocating both in that domain, averaging the two
  parameter positions, inverse-mapping, and finally closest-point projecting
  to the respective inputs.

After every candidate operation, both error conditions are checked using the
local method of Hu et al. 2017; a violation rejects the transaction. The four
operators are iterated ten times. The outer loop stops when either average
per-triangle minimum-angle metric falls below
`min(45 degrees, theta_p^0-1 degree, theta_q^0-1 degree)` or when the vertex
count no longer changes, and returns the previous iteration. The angle metric
is an average, not a hard lower bound on every triangle.

## Evidence

- The authors report success on 108 shape pairs. In the illustrated tests,
  Stage 1 converged within 20 iterations, although its distance was not
  monotone.
- Tightening the tolerance on one example from 1.2% to 0.3% to 0.2% of the
  bounding-box diagonal increased the output from 1992 to 2401 to 2828
  vertices and runtime from 2.02 to 2.37 to 4.81 minutes.
- With a 0.1% bound on the octopus example, the overlay baseline used 73,901
  vertices while the proposed result used 6,842, at similar mapping
  distortion.
- For the main 44,026/16,000-vertex example, initialization and optimization
  took 5.15 and 4.23 minutes and yielded 3,405 vertices.
- Error checks account for about 80% of Stage 2 runtime. Parameterization is
  the dominant Stage 1 cost.

These experiments support practicality, not a universal guarantee. The paper
describes Metro as an exact distance computation in Stage 1, while its Stage 2
guard is inherited from Hu et al.'s sampled local approximation. An
implementation must not upgrade that evidence to an exact continuous
Hausdorff theorem without an independent certified verifier.

## Guarantees, assumptions, and limitations

- Synchronous operations preserve identical connectivity of the pair.
- Stage 2 accepts operations only after both reported error checks pass, but
  the cited local estimator is sample based.
- Stage 1 has no convergence proof; its overlay fallback sacrifices regularity.
- The inputs must be oriented, topologically equivalent triangle surfaces and
  require user-provided corresponding landmarks.
- The final inter-surface map is not theoretically guaranteed bijective.
- There is no hard minimum-angle guarantee and near-degenerate triangles can
  remain; landmark relaxation is empirical.
- Parameterization distortion affects remeshing quality, and detected
  distortion points are manually added as landmarks.
- Sharp-feature preservation is tolerance driven: the CAD and tree examples
  require smaller epsilon. The method does not provide AutoTessell-style
  semantic feature classes or an explicit crease provenance contract.
- The method is computationally expensive and the paper does not address
  parallel execution.

## Difference from the current AutoTessell engine

The current implementation in `core/preprocessor/native_remesh/isotropic.py`
does use the same scalar split/collapse bands (`4h/3`, `4h/5`) and the usual
split-collapse-flip-relocate schedule. However:

- it operates on one surface, not a compatible mesh pair;
- `target_edge_length` is a scalar. The `adaptive_sizing` path in `face.py`
  globally scales that scalar by the fraction of detected feature vertices;
  it does not construct a per-vertex principal-curvature field;
- split, collapse, and flip are committed before the final acceptance gate;
  there is no operation-local symmetric error transaction and rollback;
- the final drift gate samples output vertices and output face centers against
  the input. It is not a symmetric continuous Hausdorff check because the
  input-to-output direction is absent;
- feature vertices are frozen wholesale and feature edges are protected,
  rather than maintaining explicit corner/curve/semantic provenance;
- the flip objective is valence deviation, not the paired six-angle objective;
- there is no landmark/correspondence/common-parameterization machinery;
- the engine returns the original mesh if a post-hoc gate fails, losing all
  otherwise feasible progress instead of rejecting only the bad operation.

## Falsifiable implementation cards

### `TRI-CURVATURE-SIZE-1` - spatial target-length field

- Implement a finite, clamped per-vertex sizing field from principal-curvature
  estimates and requested error tolerance; combine it with hard semantic
  feature sizes using pointwise minimum.
- Pass criterion: on a planar-plus-cylinder benchmark, median target length on
  the cylinder is smaller than on the plane, achieved two-sided error is below
  the configured tolerance plus verifier margin, and repeated runs are
  bitwise deterministic.
- Reject criterion: non-finite radii, cap violation, or worse certified error
  than the existing scalar baseline at equal vertex count.

### `TRI-LOCAL-ERROR-TXN-1` - candidate-level rollback

- Simulate split/collapse/flip/relocate on a bounded affected patch and commit
  only after link, orientation, semantic-feature, minimum-quality, and
  conservative two-sided local-error checks pass.
- Pass criterion: injected bad candidates are rejected without changing mesh
  hashes; good candidates remain committed even when a later candidate fails;
  final certified error is within tolerance.
- Reject criterion: any topology/orientation regression, non-local mutation,
  or case where only the final global gate detects a candidate violation.

### `TRI-SYMMETRIC-VERIFY-1` - honest output contract

- Add both result-to-input and input-to-result error measurements with a
  conservative sampling-gap margin or exact envelope verifier at finalization.
- Pass criterion: adversarial thin-feature and missed-face-center fixtures that
  pass the current one-way samples are rejected; certified fixtures report the
  bound and verification method in diagnostics.
- Reject criterion: labeling a sampled one-way maximum as Hausdorff distance.

### `TRI-COMPAT-PAIR-1` - optional future paired mode

- Treat each paired local edit as one atomic transaction over two meshes and
  require the topology edit, feature constraints, and error guards to succeed
  on both before commit.
- Pass criterion: every accepted step leaves identical indexed connectivity,
  both error bounds pass, and a forced rejection on either side leaves both
  meshes unchanged.
- Scope rule: do not make this machinery a dependency of the ordinary
  single-surface remesher until a compatible-remeshing product requirement
  exists.

