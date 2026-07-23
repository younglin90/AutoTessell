# Alliez et al. - Centroidal Voronoi Diagrams for Isotropic Surface Remeshing

## Bibliography and access

- Pierre Alliez, Eric Colin de Verdiere, Olivier Devillers, Martin Isenburg.
- *Graphical Models* 67(3), pages 204-231, 2005.
- DOI: `10.1016/j.gmod.2004.06.007`.
- Author-hosted full text:
  `https://ligm.univ-eiffel.fr/~colinde/pub/02remesh.pdf`.
- Review status: `FULL_READ` on 2026-07-23. All 32 PDF pages, formulas,
  pipeline figures, experiments, implementation details, limitations, and 62
  references were inspected. Representative pages 5, 17, 21, 25, and 28 were
  rendered and visually checked.

The 2005 journal paper is the expanded version of the 2003 SMI paper
*Isotropic Surface Remeshing*, DOI `10.1109/SMI.2003.1199601`.

## Problem and input contract

The method remeshes an oriented manifold triangle surface of arbitrary genus,
possibly with boundaries. It assumes the input already captures the intended
geometry. It is a resampling method, not a repair method for triangle soups,
non-manifold topology, inconsistent orientation, or self-intersections.

The input is a tuple `(M, F, d_s, d_f)`:

- `M`: the input triangular manifold;
- `F`: sharp, boundary, and artificial cut edges;
- `d_s`: surface sampling density; and
- `d_f`: feature-curve sampling density.

The user specifies an exact global vertex budget. Curvature or other signals
can define the density, and low-pass filtering controls gradation.

## Pipeline

The method has four main stages.

1. Calibrate surface and feature sampling rates and distribute the exact
   vertex budget with error diffusion directly on faces and feature chains.
2. Cut closed or positive-genus surfaces to a disk-like domain and compute a
   conformal parameterization.
3. Build a constrained Delaunay triangulation of the samples and optimize a
   density-weighted centroidal Voronoi diagram in parameter space.
4. Lift samples to their source triangles or feature edges with barycentric
   coordinates, then stitch duplicated cut vertices.

This is a global resampling architecture, unlike the incremental local
split/collapse/flip family.

## Exact-budget sampling

For uniform isotropic sampling, an equilateral tiling relates the number of
surface samples per unit area `R_s` and feature samples per unit length `R_f`:

```text
R_s = 2 R_f^2 / sqrt(3).
```

The rates are calibrated by

```text
R_s integral_M d_s + R_f integral_F d_f + C = V,
```

where `C` is the number of protected corners and `V` is the requested vertex
budget. The same idea is adapted to nonuniform density.

The paper generalizes image error diffusion to the mesh. It provides region-
growing, single-strip, and spanning-tree traversals. The spanning-tree variant
works for arbitrary connected surface topology: child subtrees are processed
before their parent, and quantization residuals propagate toward the root.
Consequently, no rounding error is dropped and the final sample count matches
the requested budget.

Feature edges are chained into backbones and receive separate one-dimensional
error diffusion. Disconnected chains may require residual teleport between
backbones. Surface, feature, corner, and connected-component allocations
therefore share one ledger.

The paper notes that a boundary receiving fewer than three samples can be
closed as a filtering effect. AutoTessell must explicitly forbid this for
physical boundaries and semantic patch loops. Exact budget accounting is
useful, but topology cannot be traded away to satisfy a cap.

The initial face samples are locally random, using a Sobol sequence. The
authors explicitly state that this initial distribution does not itself have a
blue-noise spectrum; the subsequent CVT is responsible for regularity.

## Feature, cut, and parameterization treatment

Feature edges consist of:

- geometric sharp edges detected by a dihedral threshold;
- boundary edges; and
- cut edges inserted to obtain a disk-like parameter domain.

Each group is sampled as curves. Constrained edges act as barriers during CVT:
Voronoi cells are clipped at a feature chain, preventing samples on opposite
sides from influencing each other. One-dimensional Lloyd relaxation is run on
feature backbones first; feature samples are frozen during the later 2D
relaxation. Cut twins are reflected on paired halfedges so they stitch exactly
after lifting.

The global cut is the method's main weakness. A cut that does not coincide
with a true feature is nevertheless sampled as a curve, making the result
inconsistent with isotropic surface sampling. The paper considers this
unacceptable for high-genus surfaces and identifies parameterization-free
local methods as the better direction.

AutoTessell should therefore reuse feature-barrier and budget ideas, not the
global cut-and-stitch architecture.

## Weighted CVT

The initial samples are connected by a filtered-exact 2D constrained Delaunay
triangulation. The surface parameterization is conformal, preserving angles
and local isotropy. Area distortion remains and is compensated with a vertex
stretch factor:

```text
s(v) = sum area_surface(f_i) / sum area_parameter(f_i),
d_parameter(v) = s(v) d_surface(v).
```

The corrected density is linearly interpolated in parameter space. Lloyd
iterations then:

1. build the Voronoi diagram;
2. intersect each cell with the density-domain triangles;
3. integrate the piecewise-linear density to obtain the cell centroid;
4. move each site to its centroid; and
5. repeat.

The paper reports that most improvement occurs in the first 10-20 iterations,
while 100 iterations polish the distribution. It gives no convergence
guarantee for arbitrary density fields.

For output-sensitive speed, density may be evaluated only at new samples and
interpolated over the new triangulation. Under-sampling can miss narrow
density details or destabilize Lloyd iterations, so the authors correlate
stronger under-sampling with stronger low-pass filtering. Temporal coherence
accelerates triangle location. Cells whose incident Delaunay edges satisfy a
Gabriel condition admit simpler centroid integration; the eligible fraction
rose from roughly 6 percent to over 80 percent on smooth-gradation examples.
Together, the reported optimizations reduced runtime by about two orders of
magnitude in the authors' experiments.

## Geometry, topology, and numerical robustness

Useful safeguards and invariants:

- output samples are lifted to explicit source triangles, feature edges, or
  corners;
- feature and boundary chains are constrained during triangulation;
- paired cut vertices are stitched by identity rather than proximity; and
- the constrained Delaunay implementation uses filtered predicates with exact
  arithmetic when required.

Missing production guarantees:

- no one-sided or symmetric Hausdorff/envelope bound for output faces;
- no minimum-angle or worst-element guarantee;
- no proof that stitching cannot produce duplicate, non-manifold, or flipped
  faces;
- no self-intersection validation;
- no semantic patch/provenance model;
- no deterministic statement for the randomized initial face samples; and
- no convergence guarantee for Lloyd relaxation and the density field.

Although every new vertex lies on an input triangle or feature, the planar
faces between them can deviate from the source surface. Vertex interpolation
is therefore not a surface-fidelity certificate.

## Experimental evidence

- A 25k-vertex David head was remeshed to 50k vertices. On a 1 GHz Pentium III,
  reported times were 7 seconds for parameterization, 0.4 seconds for
  differential analysis, 0.85 seconds for calibration, 2.8 seconds for error
  diffusion, and 26 minutes for 100 Lloyd iterations.
- The paper says the result after about 20 iterations was already visually
  close to the 100-iteration result.
- Uniform and curvature-adaptive examples demonstrate exact vertex counts and
  controlled gradation, including boundaries and a genus-1 rotor.
- The evidence is primarily visual and budget-oriented. It does not report
  worst triangle angle, Hausdorff distance, topology counters, memory, or
  deterministic repeatability.

## AutoTessell decision

Adopt:

- a unified face/feature/corner budget calibration;
- residual-preserving allocation so the requested cap is exact;
- immutable semantic feature chains and one-dimensional sampling;
- constrained barriers between distinct patch roles;
- filtered/exact predicates for constrained triangulation; and
- density low-pass/gradation control tied to under-sampling.

Do not adopt as the primary production route:

- global parameterization and cut-and-stitch for arbitrary topology;
- random initial samples without a deterministic sequence contract;
- boundary deletion when the budget is small;
- Lloyd convergence as a hard quality guarantee; or
- point-on-source lifting as a substitute for a two-sided envelope check.

Modern restricted Voronoi diagrams provide a more direct parameterization-free
path. This paper remains valuable for budget calibration, feature barriers,
density integration, and the distinction between a quick initial sampler and
a slower global regularity optimizer.

## Falsifiable implementation cards

1. `TRI-BUDGET-DENSITY1`: build a deterministic surface/feature/corner sample
   ledger using the paper's calibration relationship. Require exact cap
   compliance, protected-corner retention, at least three vertices per
   semantic loop, and deterministic allocation under permuted face order.
2. `TRI-FEATURE-SAMPLE1`: resample provenance-carrying feature chains with
   one-dimensional density integration and immutable patch barriers. Require
   zero feature/patch-role loss and bounded curve drift.
3. `TRI-RVD1`: compare a parameterization-free restricted Voronoi/CVT candidate
   with the existing local-operation engine at matched vertex count and
   two-sided envelope. Promote only if lower-tail angle and valence regularity
   improve without topology, feature, runtime, or determinism regression.
4. `TRI-CDT-PRED1`: route constrained surface triangulation predicates through
   filtered/exact native predicates and add adversarial near-collinear and
   near-cocircular tests. Require identical topology across repeated runs.

## Snowball priorities

- Surazhsky, Alliez, and Gotsman, *Isotropic Remeshing of Surfaces: A Local
  Parameterization Approach* (2003), for avoiding the global cut.
- Yan et al., *Isotropic Remeshing with Fast and Exact Computation of
  Restricted Voronoi Diagram* (2009), for parameterization-free RVD.
- Du, Faber, and Gunzburger, *Centroidal Voronoi Tessellations: Applications
  and Algorithms* (1999), for CVT convergence and energy foundations.
- Boissonnat and Cazals, *Coarse-to-Fine Surface Simplification with Geometric
  Guarantees* (2001), for stronger approximation contracts.
- Later RVD acceleration, thin-plate robustness, and parallel clipping work,
  which may replace the expensive parameter-domain intersection path.

