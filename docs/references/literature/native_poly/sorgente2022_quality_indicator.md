# Polyhedral Mesh Quality Indicator for the Virtual Element Method

## Bibliography and access

- Tommaso Sorgente, Silvia Biasotti, Gianmarco Manzini, and Michela Spagnuolo.
- *Computers & Mathematics with Applications* 114, 2022, 151-160.
- DOI: `10.1016/j.camwa.2022.03.042`
- Legal full text: <https://arxiv.org/pdf/2112.11365>
- Status: `FULL_READ` (22/22 pages).
- Visual check: pages 10, 12, and 18 were rendered and inspected. The 3D quality
  equations, sampling layouts, and Voronoi/polyhedral convergence graphs matched
  extracted text.

## Scope

This is a solver-aware quality study, not a universal CFD quality theorem. It
predicts lowest-order conforming Virtual Element Method behavior for the isotropic
Poisson problem using only mesh geometry. Its value for AutoTessell is the explicit
separation of star-shapedness, size degeneration, and combinatorial complexity.
OpenFOAM non-orthogonality/skewness must remain separate finite-volume metrics.

## Regularity assumptions and indicator

The sufficient 3D VEM regularity assumptions are:

- G1: each polyhedron and every face is star-shaped with a kernel radius bounded
  relative to element/face diameter;
- G2: face diameters and edge lengths are bounded below relative to cell/face
  diameter;
- G3: the number of faces per cell and edges per face is uniformly bounded.

The paper converts these binary assumptions into element indicators in `[0,1]`:

- `rho1`: polyhedron kernel-volume ratio multiplied by all face kernel-area
  ratios. It is one for convex cell+faces, positive for star-shaped concavity, and
  zero if either cell or any face is not star-shaped.
- `rho2`: average of a cell-scale minimum-size ratio and face-level minimum-size
  ratios.
- `rho3`: average of `4 / n_faces` and face edge-count indicators.
- global mesh quality is the root mean of the coupled terms
  `rho1*rho2` and `rho1*rho3` over all cells.

The multiplicative use of `rho1` is important: a non-star-shaped cell cannot be
made acceptable by good edge sizes or low face count.

## Experiments

Datasets combine uniform, anisotropic, plane-perturbed, body-centered lattice,
Poisson, and random samples with tet, hex, Voronoi, or agglomerated-polyhedral
connectivity. Polyhedral datasets merge 20% of tet pairs, selecting large tets and
their widest shared face; these merged cells remain star-shaped.

The indicator correlated with VEM `H1`/`L2` error magnitude and convergence rate.
Strong anisotropic violations of G2 caused the only clear underperformance even
when G1 and G3 held. Random Voronoi datasets violated G2/G3 yet still converged,
showing the regularity assumptions are sufficient, not necessary. `L-infinity`
oscillations were less reliably predicted.

## Limitations

- The tested PDE/solution is isotropic and the main method is lowest-order VEM.
- Correlation is empirical; the scalar score is not a validity certificate or a
  CFD convergence guarantee.
- Kernel computation is geometrically expensive and must be made robust against
  warped faces and numerical tolerance.
- The score favors tetrahedral combinatorics (`rho3 = 1` for a tet), which is not
  necessarily the desired cost/accuracy balance for finite-volume poly meshes.

## Current-code gap

- `quality.py` reports internal-face non-orthogonality and skewness plus face count.
  It does not test cell/face star-shapedness, kernel volume, minimum edge/face/cell
  scale ratios, warped faces, or combinatorial tails.
- `drop_degenerate_poly_cells` does not evaluate its declared non-orthogonality or
  skewness parameters. It drops a cell on near-zero face geometry or edge ratio
  above 50. Dropping a volume cell without a classified cavity contract can create
  a new boundary/hole and should not be considered quality repair.
- The best-of-three score rewards cell count and mean-style scalar terms; it lacks
  a hard validity-first ordering.

## Falsifiable implementation cards

### `POLY-QUALITY-VECTOR1`

Compute a per-cell vector containing signed volume, star-kernel fraction,
face-kernel minimum, minimum edge/face/cell scale ratios, face/edge count,
face warpage, non-orthogonality, and skewness. Pass on analytic convex,
star-shaped-concave, non-star-shaped, sliver, and warped-face fixtures with expected
monotone ordering and rigid-transform/scale invariance.

### `POLY-VALIDITY-FIRST1`

Define lexicographic acceptance: topology and positive/star-shaped validity first,
boundary/interface fidelity second, finite-volume quality tails third, complexity
last. Pass only if no candidate with more invalid cells can beat a valid candidate
through cell count or average quality.

### `POLY-NO-DROP-HOLES1`

Replace unconditional cell deletion with transactional merge/split/relocation or
explicit domain reclassification. Pass if every optimization preserves domain
volume, boundary components, patch ownership, internal-face pairing, and owner /
neighbor consistency.

### `POLY-QUALITY-CORRELATE1`

Measure the proposed vector against OpenFOAM matrix conditioning and representative
CFD error/residual behavior. Pass only after preregistered monotonic correlations
hold on convex, concave, anisotropic, narrow-gap, and boundary-layer benchmarks;
otherwise retain components without claiming a universal scalar grade.

