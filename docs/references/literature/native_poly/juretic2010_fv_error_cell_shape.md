# Error Analysis of the Finite-Volume Method with Respect to Mesh Type

## Bibliography and access

- F. Juretić (AVL-AST, Zagreb) and A. D. Gosman (CD-Adapco, London).
- *Numerical Heat Transfer, Part B: Fundamentals*, vol. 57, no. 6, 2010, 414-439.
- DOI: `10.1080/10407791003685155`
- Local copy: `docs/references/papers/source/pdf/17_juretic_2010_fv_error_cell_shape.pdf`
- Status: `FULL_READ` (27/27 PDF pages = journal pp. 414-439). Read 2026-07-23.
- Provenance: outgrowth of Juretić's Imperial College PhD (ref [40]) under Gosman;
  same lineage as Jasak's thesis [32], i.e., the direct theoretical ancestry of
  OpenFOAM's discretization and of its `checkMesh` quality measures. Juretić is
  also the author of cfMesh. This is the P0 "bridge" paper between mesh quality
  metrics and actual FV solution error.

## Problem and setting

Derives truncation-error terms for the face-flux approximations of a second-order
colocated FVM (linear interpolation / CD for convection, over-relaxed-style
orthogonal + non-orthogonal split for diffusion) on convex polyhedral CVs, then
assembles per-cell truncation errors for squares, equilateral triangles, and
regular hexagons (2-D proxies of hexahedra, tetrahedra, and polyhedra) to rank
cell types at equal cell count. Validated on two laminar 2-D cases.

## Mesh-quality parameters (paper definitions)

Defined per face, independent of cell shape (Sec. 2):

1. **Non-orthogonality** `alpha_N`: angle between `d = x_N - x_P` and face area
   vector `S`.
2. **Skewness** `psi = |m| / |d|`, with `m = x_f - x_fi` where `x_fi` is the
   intersection of `d` with the face. Dimensionless, normalized by the P-N
   distance (NOT identical to OpenFOAM `checkMesh` skewness normalization).
3. **Uniformity** `fx = |x_fi - x_N| / |d|`; uniform mesh means `fx = 0.5`.

## Error decomposition (key equations)

**Convection / face interpolation** (Eq. 22): the linear-interpolation error at a
face is

```
e_interp = -(1/2)|d|^2 { fx(1-fx) [d^2 : (grad grad phi)_fi]
                        + psi |d| m_hat . [d_hat^2 : (grad grad grad phi)_fi] }
           + (psi^2/2)|d|^2 [m_hat^2 : (grad grad phi)_fi] + HOT
```

- Second order on every mesh; minimized at `psi = 0`, `fx = 0.5`.
- **Non-orthogonality does NOT appear** — it does not affect convection
  interpolation accuracy at all.
- Cell convection error: `e_conv = sum_f F * e_interp` (Eq. 23), so faces with
  `F ~ 0` (flow-aligned faces) contribute nothing.

**Diffusion / surface-normal gradient** (Eq. 34), using `S = Delta + k`,
`|Delta| = |S|/cos(alpha_N)`, `|k| = |S| tan(alpha_N)`:

```
e_sng = - (|S|/cos aN) (|d|/2)(2fx - 1) [d_hat^2 : (grad grad phi)_f]
        - (|S|/(6 cos aN)) |d|^2 [(1-fx)^3 + fx^3] [d_hat^3 :: (g g g phi)_f]
        - |S| tan(aN) (|d|^2/2) fx(1-fx) k_hat . [d_hat^2 : (g g g phi)_f] + HOT
```

- **First order unless `fx = 0.5`** (the `(2fx-1)` term); second order on
  uniform meshes.
- Non-orthogonality amplifies error via `1/cos(alpha_N)` and adds a
  `tan(alpha_N)` term. **Skewness does NOT appear** in the diffusion error
  (it only re-enters via interpolation of a variable diffusivity, Eq. 35).

**Source term** (Eq. 39): error scales with cell *size* (second moments about
`x_P`), not cell *shape* — not a sum of face errors.

**Face-pair cancellation** (Eq. 26 and Sec. 3): for two faces with
`S_1 + S_2 = 0` (a "face pair": opposite orientation, equal area), the leading
truncation errors cancel. This is the paper's central structural result: the
dyadic/triadic normal tensors satisfy `n_e^2 - n_w^2 = 0`, `n_n^3 + n_s^3 = 0`
for paired faces, so cells built of face pairs resolve entire solution classes
exactly.

## Cell-type comparison (theory, equal cell count)

| Solution class | square | hexagon | triangle |
|---|---|---|---|
| `grad phi = const` | exact | exact | exact |
| `grad grad phi = const` (convection) | exact | exact | **error** (Eq. 46) |
| `grad^3 phi = const` (convection) | error (Eq. 50) | 1.155x square (Eq. 53) | worse |
| `grad^3 phi = const` (diffusion) | exact | exact | **error** (Eq. 58) |
| `grad^4 phi = const` (diffusion) | error (Eq. 62) | 1.155x square (Eq. 64) | worse |

- Triangles are worst *because they have no face pairs* (odd face count), not
  because of any conventional quality number — the equilateral triangle meshes
  used are orthogonal, uniform, and unskewed, yet still least accurate.
- Hexagon vs square error ratio is exactly 1.155 (= 2/sqrt(3)) for both terms:
  polyhedral cells are only ~15% worse in truncation error than quads at equal
  count, because they still consist of face pairs (plus more active faces).
- Stated 3-D transfer: hexahedra best (fewest face pairs), tetrahedra worst (no
  face pairs); general polyhedra (dual-type, hexagon-like) slightly below hex.

## Numerical validation

- **Planar jet** (Re = 520, analytical Schlichting solution): 5 mesh levels per
  type (Table 1; quality near-ideal, e.g. avg `psi <= 0.06`, avg
  `alpha_N <= 16 deg`). Max and mean errors: quad < poly ~ quad << tri;
  second-order convergence for all types.
- **Channel + cavity** (Re = 200, 500k-cell Richardson-verified benchmark):
  triangles need **~10x more cells** than quads for equal mean velocity error;
  polygons (mostly hexagons, cfMesh-style Delaunay dual) need only **~2x**.
  Pressure-drop coefficient Cp (Table 3): quad and poly converge to the
  mesh-independent 1.5203 at similar rate and error magnitude; triangles lag
  badly (1.963 -> 1.536 over the same refinement span).

## Which metrics actually drive FV error

- **Cell topology (face pairing)** is the dominant shape driver on good meshes —
  and it is measured by NO conventional quality metric. A perfect-quality tet
  is still the worst FV cell.
- **Skewness** drives convection interpolation error only (linear in `psi` at
  third-gradient order, quadratic at second-gradient order). Smooth growth; no
  threshold/cliff is derived.
- **Non-orthogonality** drives diffusion (sng) error only, via `1/cos(alpha_N)`
  and `tan(alpha_N)`. Also smooth; note `1/cos(16.7 deg) = 1.04` — mild at our
  levels, blows up only near 70-80 deg.
- **Uniformity `fx`** is the sleeper metric: `fx != 0.5` reduces the diffusion
  term to FIRST order. Neither OpenFOAM `checkMesh` nor our evaluator gates it.
- **Aspect ratio: explicitly NOT analyzed** — named as future work in Sec. 5
  along with the orientation of low-quality faces relative to solution
  gradients.
- **Negative volume**: out of scope (analysis presumes valid convex CVs);
  trivially necessary, not evidenced here.

## Limitations

- Truncation-error analysis is 2-D (squares/triangles/hexagons); the 3-D claims
  (hex vs tet vs polyhedra) are asserted by the face-pair argument, not derived
  or numerically tested in 3-D.
- "Polygonal" meshes tested are near-regular Delaunay-dual hexagon meshes — NOT
  agglomerated or arbitrary-topology polyhedra; high quality throughout
  (`psi <= 0.06`). Says nothing about strongly distorted polyhedral cells.
- Laminar, steady, smooth solutions; linear (CD) convection scheme only; no
  turbulence, no boundary-layer anisotropy, no shocks (only a remark that
  `|DU.S| >> 0` degrades cancellation).
- Effects of skewness/non-orthogonality/non-uniformity magnitudes are derived
  but deliberately NOT parametrically studied ("vast number of possible
  cases"); no gate thresholds are proposed anywhere.
- Boundary-condition error contribution excluded by construction.

## AutoTessell applicability

This is the closest primary-source FV-theory support for the native_poly
direction: a face-paired polyhedral (dual) mesh is theoretically and
experimentally near-hex accuracy (1.155x truncation, ~2x cells for equal mean
error) and far superior to tet. It justifies polydual as a first-class engine
but only for well-shaped, face-paired polyhedra.

Per-metric verdict on the evaluator gates (`core/evaluator/native_checker.py`):

| Gate | Verdict | Basis |
|---|---|---|
| Non-orthogonality | **Supported as a metric; threshold not derived** | Appears explicitly in Eq. 34 (`1/cos`, `tan`); degradation is smooth, so 65-70 deg style limits are calibration choices, not theory. Cylinder's 16.66 deg implies only ~4% amplification — safely fine. |
| Skewness | **Supported as a metric; definition and threshold unverified** | Eq. 22 uses `psi = |m|/|d|`; the paper's meshes have `psi <= 0.06` while we report cylinder skew 2.17 — almost certainly a different normalization (OpenFOAM-style). Must reconcile formulas before quoting this paper for the gate. |
| Aspect ratio | **Unsupported (not contradicted)** | Explicitly deferred to future work; no evidence either way. |
| Negative volume | **Out of scope (trivially necessary)** | Analysis presupposes valid convex CVs. |
| (missing) Uniformity `fx` | **Gap in our gates** | `fx != 0.5` makes diffusion first-order (Eq. 34); we do not measure it. |
| (missing) Face pairing | **Gap in our gates** | The paper's dominant shape driver; no conventional checker (ours or OpenFOAM) measures it. |

Nothing in the paper *contradicts* our gates; it validates non-ortho and
skewness as the right axes for convection/diffusion error, leaves aspect ratio
unevidenced, and shows our gate set is incomplete (uniformity, face pairing).

## Falsifiable measurement / calibration cards (no code now)

### `POLY-FVERR-SKEWDEF1`

Reconcile skewness definitions: derive the exact formula used by
`native_checker.py` and by OpenFOAM `checkMesh`, and map both to the paper's
`psi = |m|/|d|`. Measure `psi` directly on the cylinder native_poly mesh
(currently "skew 2.17" in our units). Pass if the note gains a conversion table
and the cylinder's `psi` distribution is reported; fail if the two measures are
not monotonically related on that mesh (then our gate is measuring something
Eq. 22 does not predict).

### `POLY-FVERR-UNIFORMITY1`

Add uniformity `fx` (Eq. 12) as a *reported* (not gated) statistic in the
evaluator. Measure the `fx` distribution on native_poly, native_hex, and
native_tet outputs for the bench fixtures. Pass if the fraction of faces with
`|fx - 0.5| > 0.1` is reported per engine and the poly duals are no worse than
tet; use the data to decide whether a gate threshold is warranted.

### `POLY-FVERR-FACEPAIR1`

Define a per-cell face-pairing residual, e.g. the minimum over pairings of
`sum |S_i n_i + S_j n_j| / sum |S_i|` (0 = perfectly paired like a hex/regular
hexagon, ~1 = tet-like), and measure its distribution on native_poly vs
native_hex vs native_tet meshes. Pass if polydual cells score close to hex and
far from tet, confirming the paper's mechanism transfers to our actual duals;
fail (and downgrade the polydual accuracy claim) if our duals are unpaired.

## Snowball references (<= 5)

1. **[32] H. Jasak, PhD thesis, Imperial College, 1996** — *Error Analysis and
   Estimation in the Finite Volume Method with Applications to Fluid Flows.*
   Source of the `S = Delta + k` non-orthogonal split (Eqs. 28-31); the direct
   theoretical basis of OpenFOAM's discretization and quality checks.
2. **[40] F. Juretić, PhD thesis, Imperial College London, 2004** — *Error
   Analysis in Finite Volume CFD.* Fuller version of this paper's analysis by
   the cfMesh author.
3. **[44]+[45] Perez-Segarra et al. / Farre et al., Numer. Heat Transfer B 49,
   2006 (Parts I & II)** — scheme-accuracy analysis on 3-D unstructured grids
   including mesh-quality influence; the closest prior work, but without the
   cell-type comparison.
4. **[48] Vasconcellos & Maliska, Numer. Heat Transfer B 44, 2004** — FV method
   on Voronoi discretizations; primary source for Voronoi-polygon FV flow
   solutions (relevant to `voro_poly` tier).
5. **[38] Jasak & Gosman, Numer. Heat Transfer B 39, 2001** — residual error
   estimate for FVM; candidate a-posteriori error measure to complement
   geometry-only gates.
