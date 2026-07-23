# Mesh Quality Effects on the Accuracy of CFD Solutions on Unstructured Meshes

## Bibliography and access

- Aaron Katz and Venkateswaran Sankaran (US Army Aeroflightdynamics Directorate).
- *Journal of Computational Physics* 230 (2011) 7670-7686.
- DOI: `10.1016/j.jcp.2011.06.023`
- Local PDF: `papers/pdf/16_katz_2011_mesh_quality_cfd_accuracy.pdf`
- Status: `FULL_READ` (17/17 PDF pages, journal pages 7670-7686), read 2026-07-23.
- Visual check: pages 7, 10, 13, and 15 were rendered and inspected. Table 1
  (source-discretization rates), Fig. 7 (isotropic convergence), Fig. 10 (stretched
  viscous), and Fig. 12 (non-planar 3D faces) were consistent with extracted text.
- Companion evidence to Juretic & Gosman 2010 for calibrating AutoTessell quality
  gates.

## Problem and scope

Quantifies how mesh irregularity degrades the *solution error* (not just truncation
error) of node-centered and cell-centered finite-volume schemes, using the Method of
Manufactured Solutions (MMS). Covers 2D isotropic grids (quad, equilateral tri,
right tri), 2D stretched boundary-layer grids (flat and curved wall, aspect ratios
1e2 / 1e4 / 1e6), and 3D prismatic grids with non-planar control-volume faces.
Scalar linear advection/diffusion is used as the proxy after verifying that Ringleb
(exact Euler), manufactured Euler, and manufactured scalar solutions all give
identical convergence rates (Table 2).

## Method (key relations)

**Truncation vs solution error.** For a linear steady discretization
`D Q_h = B Q_b + C S`, substituting the exact solution gives
`D Q = B Q_b + C S + E_t`, so the solution error satisfies

```
E_s = Q - Q_h = D^{-1} E_t     (equivalently D E_s = E_t)
```

Truncation error *drives* solution error but converges at a different (usually
lower) rate on unstructured FV meshes — e.g. the linear node-centered scheme has
first-order truncation error on arbitrary meshes yet second-order solution error.
Truncation error alone is therefore an unreliable accuracy indicator (their
Section 3.1; this reframes conclusions of earlier TE-only studies such as Juretic-
style analyses: a first-order TE does not automatically mean first-order solution).

**MMS source-term discretization.** A point source (`C = I`) understates the true
order on regular meshes by one; a Galerkin-weighted source
`C_i S = (2/3) s_i + (1/(6 dx_i)) (s_{i-1} dx_{i-1/2} + s_{i+1} dx_{i+1/2})`
recovers rates matching exact-solution tests. Sufficient condition: the MMS-modified
PDE must have the same truncation-error order as the original PDE.

**Perturbation protocol (random skew).** Perturbed meshes move every node a random
distance in [0, 25%] of the minimum adjacent-node spacing, in a random direction.
Each refinement level is *independently* re-perturbed and statistically scaled with
h, so mesh quality is constant across refinement and meshes are never of the same
"family". Effective mesh size: `ds = (V_total / ndof)^(1/d)` with ndof = nodes
(node-centered) or cells (cell-centered) — an accuracy-per-DOF comparison.

**Corrected node-centered scheme.** Adds a flux correction
`C_0 = sum_i (1/4) (dr_0i . (grad F_i - grad F_0)) . A_0i`
with quadratic least-squares gradients, giving formal third order on arbitrary
triangulations without extra quadrature or stored second derivatives.

## Quantitative results

Solution-error convergence orders (regular / randomly perturbed):

| Scheme, terms | Quad | Equil. tri | Right tri |
|---|---|---|---|
| Node-centered inviscid | 2 / **1** | 3 / 2 | 3 / 2 |
| Corrected inviscid | - | 3 / 3 | 3 / 3 |
| Cell-centered inviscid | 2 / 2 | 2 / 2 | 2 / 2 |
| Node-centered viscous | (not run) | 2 / 2 | 2 / 2 |
| Cell-centered viscous | 2 / 2 | 2 / 2 | 2 / 2 |

- **Random perturbation costs node-centered schemes one order** (3→2 on triangles,
  2→1 on quads via the median-dual approximation), but **cell-centered schemes hold
  second order under the same perturbation for every cell type, inviscid and
  viscous**. Error *magnitude* still rises on perturbed meshes (Fig. 7).
- **Stretched BL meshes (AR up to 1e6):** orders are retained, but the cell-centered
  viscous discretization produces **~4x less error** than node-centered on the same
  triangles (Fig. 10c,d; curved-wall Fig. 11 similar). Cell-centered quads give the
  lowest error, then right triangles, then equilateral triangles. Error grows
  mildly with wall-cell aspect ratio for all schemes. The corrected scheme failed to
  converge on many curved high-AR cases (LSQ ill-conditioning).
- **3D non-planar faces (Table 5, cell-centered prisms):** single-point face
  quadrature on non-planar faces → **first order**; triangulating each non-planar
  face (one quadrature point per triangular facet, two per quad face) restores
  **second order**. One diffusive-flux evaluation per face remained sufficient.
- Prism/hex space-filling: a tri-prism replaces 3 tets, a hex 5 tets — accuracy per
  DOF strongly favors prismatic/hex BL cells.

## Which quality effects matter for which discretization

- **Cell-centered FV (OpenFOAM-like):** remarkably insensitive in *order* to random
  isotropic node perturbation; sensitive in *magnitude* to cell shape under
  stretching (quad >> tri); order-destroying failure mode is **face non-planarity
  with single-point flux integration** — a polyhedral-mesh concern, not a
  skewness/non-orthogonality concern per se.
- **Node-centered / median-dual:** loses an order under random perturbation; drops
  to first order on general quads; disfavored on stretched triangles (documented
  excess diffusion, refs [25,26]). Any dual scheme departing from the linear
  Galerkin equivalence (e.g. containment duals on non-Delaunay triangulations)
  risks first order.
- **Random vs systematic skew:** this paper tests *random, statistically
  self-similar* perturbations only, and finds cell-centered order intact. It does
  not test systematic (one-sided, correlated) skew; combine with Juretic & Gosman
  2010, where consistent skewness on the coarse-cell side is what actually shifts
  error. Together: random moderate skew mainly inflates the error constant for
  cell-centered FV, while order loss requires either a structural defect (non-planar
  faces, dual-face misalignment) or systematic skew.

## Limitations

- Linear scalar model equations dominate; Navier-Stokes stiffness, shocks, and
  turbulence-model sensitivity are out of scope.
- Perturbation capped at 25% of minimum spacing — mesh quality stays *moderate*;
  no mapping to OpenFOAM-style metric values (non-orthogonality/skewness numbers
  are never reported), so thresholds cannot be read off directly.
- 3D study is inviscid-only and prism-only; viscous non-planar-face behavior is
  explicitly left open. No general polyhedral (dual) cells tested.
- Corrected third-order scheme unstable on curved high-AR grids; viscous terms of
  the corrected scheme remain second order.

## AutoTessell applicability (gate verdicts)

Our gates: non-orthogonality < 65-70 deg, per-quality skewness thresholds; measured
native_poly cylinder: max skew 2.17, max non-ortho 16.66 deg. OpenFOAM is
cell-centered with single-point face flux — exactly the family this paper favors.

- **Non-ortho < 65-70 gate: indirectly supported, not calibrated.** The paper never
  reports non-ortho values, but the 25%-perturbation results show cell-centered
  order is robust to moderate random distortion; our cylinder value 16.66 is deep
  inside the safe regime. No evidence here for where between 20 and 70 degrees the
  error constant becomes unacceptable — keep Juretic & Gosman as the calibrating
  source for the threshold itself.
- **Skewness gate: same verdict.** Random skew of this magnitude does not break
  second order for cell-centered FV; skew 2.17 (OpenFOAM units) is untested here
  but the mechanism (error-constant inflation, not order loss) suggests a magnitude
  penalty, not a correctness cliff. Systematic skew is the dangerous variant —
  our gates should keep penalizing *correlated* skew (e.g. one-sided dual offsets)
  harder than random jitter.
- **Missing gate exposed: face planarity.** For native_poly this is the paper's
  sharpest lesson: generalized-dual cells have warped faces (flagged already in the
  Garimella 2013 note), and single-point flux on non-planar faces is provably first
  order. Neither our non-ortho nor skew gate detects this. We need a face
  warpage/flatness metric in `NativeMeshChecker` for poly (and perturbed hex)
  meshes.
- **Aspect-ratio / BL design: supported.** Cell-centered prisms/hexes in the BL
  (our native_bl + hex_dominant path) are the lowest-error choice; high AR alone
  (up to 1e6) is acceptable when cells align with the solution. An aspect-ratio
  gate should not reject aligned BL stretching.

## Falsifiable implementation cards

### `POLY-FVERR-PLANAR1`

Add a face non-planarity (warpage/flatness) metric to `NativeMeshChecker` and gate
native_poly output on it, since Katz Table 5 proves single-point flux on non-planar
faces is first order and OpenFOAM integrates fluxes with a single face-centre
point. Measure per-face max vertex deviation from the area-weighted best-fit plane,
normalized by sqrt(face area) (and/or OpenFOAM faceFlatness). Pass only if: the
metric is reported for every poly/hex mesh; the cylinder and cube poly fixtures
quantify their worst faces; and a decimated-planarity fixture (randomly perturbed
prism grid per Katz Fig. 12b) is correctly flagged while the regular grid passes.

### `POLY-FVERR-RANDPERT1`

Empirically reproduce the Katz protocol on our own meshes to calibrate gate
thresholds against solution error rather than folklore: randomly perturb nodes by
0-25% of local min spacing on 3+ refinement levels, record OpenFOAM checkMesh
max/mean non-ortho and skew at each level, and run a scalar Laplacian/advection MMS
case. Pass only if meshes that satisfy our current gates sustain second-order
solution-error convergence, and the report maps measured (non-ortho, skew) pairs to
error-constant inflation — giving the first native data point linking our gate
numbers to solution error (complements Juretic & Gosman's systematic-skew data).

## Snowball references (max 5)

1. B. Diskin, J. Thomas, *Accuracy analysis for mixed-element finite-volume
   discretization schemes*, NIA Report 2007-08 — source of the median-dual
   first-order-on-quads result; systematic (not random) grid-quality analysis.
2. B. Diskin, J. Thomas, E. Nielsen, H. Nishikawa, *Comparison of node-centered and
   cell-centered unstructured finite-volume discretizations. Part 1: viscous
   fluxes*, AIAA 2009-0597 — the companion NC-vs-CC viscous study.
3. E. Luke, S. Hebert, D. Thompson, *Theoretical and practical evaluation of
   solver-specific mesh quality*, AIAA 2008-0934 — directly on solver-specific
   quality metrics, closest to our gate-calibration goal.
4. Y. Liu, M. Vinokur, *Exact integrations of polynomials and symmetric quadrature
   formulas over arbitrary polyhedral grids*, JCP 140 (1998) 122-147 — exact
   polyhedral face/volume integration; remedy path for non-planar poly faces.
5. C. Roy, *Review of code and solution verification procedures for computational
   simulation*, JCP 205 (2005) 131-156 — canonical MMS/verification methodology for
   card `POLY-FVERR-RANDPERT1`.
