# Surazhsky and Gotsman - Explicit Surface Remeshing

## Bibliography and access

- Vitaly Surazhsky and Craig Gotsman.
- *Eurographics Symposium on Geometry Processing*, pages 20-30, 2003.
- Publisher: The Eurographics Association; ISSN `1727-8384`; ISBN
  `3-905673-06-1`.
- DOI: `10.2312/SGP/SGP03/020-030`.
- Official record and full text:
  `https://diglib.eg.org/items/8f1dac05-aca1-4973-87e8-27a340397957`.
- Review status: `FULL_READ` on 2026-07-23. All 11 pages were text-read.
  Pages containing the fidelity equations, area objective, curvature density,
  patch parameterization, connectivity algorithm, experiment table, visual
  results, limitations, and complete references were rendered at 150 DPI and
  visually checked against the extracted text.

## Problem, scope, and input contract

The paper calls its method *explicit* because it modifies the triangle mesh
directly instead of resampling a single global parameter domain. Its intended
output has a user-specified vertex count, a uniform or curvature-sensitive
sampling distribution, well-shaped triangles, and mostly regular valence.
The central contributions are area-based relocation, a dynamic overlapping
local parameterization that follows changing connectivity, and a valence
regularizer that escapes local minima of ordinary valence-improving flips.

The stated input is a piecewise-linear 2-manifold triangle mesh, except at
boundaries, with arbitrary genus and possible holes. It is treated as an
approximation of a smooth surface that is `C1` except along boundaries and
feature curves. Features are supplied by the user or detected from a dihedral
threshold. If source vertex normals are absent, they are constructed as
angle-weighted incident-face averages, which implicitly requires a usable
local orientation. A feature vertex receives separate normal estimates as if
the mesh were cut along its feature edges.

This is a remesher, not an input-repair engine. It gives no contract for
triangle soups, inconsistent orientation, non-manifold junctions,
self-intersections, duplicate faces, or overlapping components. Those cases
must be rejected or repaired before this algorithm is considered.

## Reference surface and dynamic provenance

The original mesh `M_O` remains immutable while the evolving mesh `M` is
modified. Each evolving vertex stores an exact source reference `(f, b)`,
where `f` is a face of `M_O` and `b = (b1,b2,b3)` are barycentric coordinates.
For a planar triangle `f=(q1,q2,q3)`, the paper uses

```text
b1 = A(q,q2,q3) / A(q1,q2,q3),
b2 = A(q,q3,q1) / A(q1,q2,q3),
b3 = A(q,q1,q2) / A(q1,q2,q3).
```

The source triangle vertices and normals define a cubic PN triangle, so
`(f,b)` identifies both a reconstructed source position and normal. PN
triangles are chosen as an efficient approximation; unlike the more expensive
alternative cited by the paper, they do not provide a general exact `G1`
continuity guarantee across source edges.

After relocating a current vertex in a flattened one-ring, the method does
not use a global nearest-point query. If the relocated point lies in a current
triangle whose three vertices reference source faces `f1,f2,f3`, it:

1. builds or reuses a flattened source patch containing `f1,f2,f3`;
2. uses the current triangle's barycentric coordinates to interpolate a point
   in that flattened source patch;
3. walks source-patch triangles in the direction of a negative barycentric
   coordinate until it finds the containing face; and
4. stores that source face and the new barycentric coordinates, then evaluates
   the corresponding PN triangle.

The authors report that starting the face walk from the vertex's prior source
face, or the closest of `f1,f2,f3`, reduces the average search to about `1.2`
tested faces. This is a useful persistent-provenance design, but its smooth PN
surface is an approximation rather than an exact envelope around the original
piecewise-linear triangles.

## Fidelity tests and an important source inconsistency

Every local operation is accepted only if all created or affected faces pass
two source-normal criteria. For a candidate face `f=(v1,v2,v3)`, the prose
defines:

- `E_smth`: agreement of the candidate face normal with source normals at its
  three vertices; and
- `E_dist`: variation among consecutive source vertex normals, used as a proxy
  for the gap between the candidate face and the reconstructed source.

The printed equations (1) and (2) show maxima of normal dot products compared
with `cos(theta_smth)` and `cos(theta_dist)` using a less-than sign. Read
literally, that is inconsistent with the surrounding angular explanation:
bounding a maximum normal angle requires a minimum dot product greater than a
cosine threshold. The paper also calls `E_dist` a distance measure although it
contains only normal directions. Therefore the printed inequalities must not
be transcribed as production predicates without consulting an erratum or
re-deriving the intended angular tests.

Even under the intended angular interpretation, these are local normal-based
proxies, not a certified point-to-surface or symmetric Hausdorff envelope.
The final experiment uses Metro to measure normalized Hausdorff distance, but
that is post hoc evaluation and not the acceptance predicate.

## Complete remeshing schedule

Starting from `M=M_O`, the paper applies four top-level stages:

1. adjust the mesh to the requested vertex count using edge collapses or
   splits;
2. perform curvature-sensitive area-based remeshing;
3. regularize connectivity; and
4. polish geometry with weighted angle-based smoothing.

Edge flips are accepted when they increase the minimum angle of the adjacent
triangles during the basic remeshing stage. Vertex relocation is computed in
a flattened one-ring that approximates a geodesic polar map: radial edge
lengths are preserved, and incident angles are proportionally rescaled to sum
to `2*pi`. The paper uses the weighted angle-based smoother from its 2002
compatible-triangulation work rather than ordinary Laplacian averaging.

To reach an exact requested vertex count, independent sets of candidate edges
are collapsed or split, prioritizing edges whose incident faces have minimum
or maximum error metrics respectively. One area-remeshing step is interleaved
between count-adjustment batches to preserve sampling fairness. The paper does
not fully specify the combined error priority, independent-set construction,
tie breaking, or the topological validity predicate for collapse.

This algorithm does **not** introduce the later Botsch-Kobbelt thresholds
`4l/5` and `4l/3`. Those thresholds should not be attributed to this paper.

## Area-based relocation and sampling control

Area equalization alone can generate skinny triangles, but alternating it
with Delaunay angle-improving flips gives uniform spatial sampling and nearly
regular triangles. The paper explicitly states that this alternation usually
does not converge: after reaching uniform density it oscillates among similar
distributions. The later regularization and smoothing stages are relied upon
to polish one of those states.

Let a flattened vertex be `p=(x,y)`, its ordered neighbors be
`p_i=(x_i,y_i)`, and `A_i(x,y)` the signed area of incident triangle
`(p,p_i,p_{i+1})`:

```text
A_i(x,y) = 1/2 det([[x_i,     y_i,     1],
                    [x_{i+1}, y_{i+1}, 1],
                    [x,       y,       1]]).                 (3)
```

If `A` is the area of the neighbor polygon and positive target ratios `mu_i`
sum to one, relocation minimizes

```text
(x,y) = argmin sum_i (A_i(x,y) - mu_i A)^2.                 (4)
```

Because each signed area is affine in `(x,y)`, this reduces to two linear
equations with a unique solution according to the paper. That statement
presumes a valid nondegenerate flattened one-ring; a production implementation
still needs singularity and inversion guards.

For curvature-sensitive density, source vertices away from features and
boundaries receive

```text
Psi(v) = 1 / (alpha |K(v)| + beta H(v)^2),
alpha > 0, beta > 0, alpha + beta = 1,
```

where `K` and `H` are discrete Gaussian and mean curvature. The usual choice
is `alpha=beta=0.5`. Boundary values average non-boundary neighbors. Feature
values are averaged separately on each smooth side, consistent with the
split-normal treatment. Extreme density values are truncated, the field is
Laplacian-smoothed `k_smooth` times, and user contrast is applied with
`g(Psi,gamma)=Psi^gamma`.

For incident triangle `(v,v_i,v_{i+1})`, the preliminary target ratio is the
average of `Psi(v_i)` and `Psi(v_{i+1})`; all ratios are then normalized to sum
to one. A larger `Psi` is described as a larger required density, although
the field is inverse curvature magnitude. The area objective associates that
ratio with desired triangle area, so the terminology and direction should be
validated experimentally rather than inferred from the word "density."

Implementation guidance is empirical: alternate area relocation and Delaunay
flips for `n_step=5..10`; each area phase needs only `n_area=1..3` relocation
iterations. Final weighted angle smoothing uses `m_step=5..10` iterations.
These are fixed iteration ranges, not convergence guarantees.

## Dynamic overlapping parameterization

When three referenced source faces are needed, breadth-first searches grow
neighborhoods from each face until all three are connected. Faces are added
only while the patch remains disk-like; boundary "ear" triangles are trimmed
unless they are one of the required faces. The boundary is mapped to a convex
unit-circle polygon with boundary distances proportional to 3D lengths, and
the interior is flattened using Floater mean-value coordinates.

The authors reject conformal flattening here because it does not guarantee a
foldover-free embedding. Mean-value coordinates with a convex boundary do
provide the validity property required by their local lookup. Patches overlap,
so a local operation is not forced to occur near a fixed atlas seam. This
supports arbitrary genus and holes without a global cut.

Patches are cached. Each source face keeps a list of patches containing it;
intersecting the lists for three faces finds a reusable patch. Average and
maximum list lengths are reported as `3.5` and `5`, making the nominal
`O(k^2)` lookup effectively constant in their tests. Move-to-front ordering
exploits spatial coherence. Unused patches expire through queue-based timers
after an empirically chosen interval of `0.1..0.3` times the output face count,
which bounds cache memory in the authors' scheme.

These statements concern parameter-domain validity and cache behavior. They
do not prove that the 3D topology operations preserve manifoldness or avoid
self-intersections.

## Connectivity regularization

The regularizer minimizes the valence energy

```text
R(M) = sum_v (d(v) - d_opt(v))^2,                            (5)
d_opt = 6 for interior vertices, 4 for boundary vertices.
```

A basic or *easy* flip decreases `R`. Once no easy flips remain, the algorithm
classifies edges from endpoint valence signs:

- **long edge:** both endpoints have excessive valence; split it;
- **short edge:** both endpoints have deficient valence; collapse it; and
- **drifting edge:** one endpoint has excessive and the other deficient
  valence; flip an adjacent edge to migrate this defect pair across regular
  mesh regions without changing `R`.

Easy edges have highest priority, drifting edges lowest, and long and short
edges equal intermediate priority unless count balancing requires otherwise.
After every modification the priority queue is updated. The process continues
until no easy, long, short, or drifting edge remains. The stated result is that
remaining irregular vertices are isolated by regular vertices and are usually
few, not that `R` reaches its global minimum or that every vertex is regular.
Every 3D operation must still pass the paper's fidelity proxies, and one local
angle-smoothing iteration follows each accepted operation.

The paper sketches a further move for an isolated irregular vertex but leaves
global construction of subdivision connectivity to future work. It does not
prove termination under rejected geometric candidates, preservation of the
requested sample distribution, or preservation of mesh topology.

## Experimental evidence

The implementation ran on a 2.4 GHz Pentium 4 with 512 MB RAM. The user
controlled output vertex or face count and a curvature-contrast parameter.
Reported output statistics include:

| Output | Vertices | Irregular | Min angle | Avg angle | Metro error x1e-3 | Time |
|---|---:|---:|---:|---:|---:|---:|
| Venus, uniform | 9,240 | 4.4% | 25.8 deg | 53.3 deg | 3.5 | 15.4 s |
| Venus, nonuniform | 8,705 | 6.7% | 25.9 deg | 52.4 deg | 2.7 | 16.5 s |
| Cow (a) | 4,551 | 9.5% | 8.1 deg | 48.8 deg | 5.8 | 8.2 s |
| Feline | 10,825 | 13.8% | 7.4 deg | 48.3 deg | 6.4 | 74 s |
| Horse | 5,695 | 10.3% | 9.1 deg | 50.1 deg | 6.1 | 28.4 s |
| Triceratops | 2,758 | 13.3% | 5.6 deg | 42.2 deg | 8.4 | 12.3 s |
| Fan disk | 5,135 | 8.43% | 16.8 deg | 49.1 deg | 0.4 | 17.3 s |
| Helmet | 2,728 | 6.08% | 14.8 deg | 47.8 deg | 8.9 | 17.7 s |

Metro error is Hausdorff distance normalized by the bounding-box diagonal.
The paper proposes `10 degrees` minimum and `45 degrees` average as desirable
quality heuristics, but several results miss the former. No tolerance sweep,
input corpus protocol, repeated-run variance, memory table, self-intersection
test, or downstream simulation/volume-meshing evidence is reported.

The fan-disk figures qualitatively preserve creases, corners, and boundary
shape. The triceratops horn tips are intentionally left largely untouched
because initial regions that already violate the normal-error criteria are
treated as special features; refining them could require too many vertices.
This is a practical escape hatch, not a complete feature guarantee.

Connectivity compression usually drops below one bit per vertex after
regularization. That supports the claimed valence regularity, but compression
rate is not a surface-fidelity or CFD-suitability metric.

## Guarantees, limitations, and claim boundary

What the paper supports:

- operation-local handling of arbitrary-genus manifold meshes with boundaries
  and holes, without a global parameterization;
- a foldover-free **2D patch embedding** when the constructed patch is a disk
  and the boundary is convex;
- persistent source-face/barycentric correspondence through changing
  connectivity;
- a sequential split/collapse mechanism intended to reach a requested sample
  count when admissible operations remain; and
- strong empirical reductions in valence irregularity.

What it does not establish:

- a certified one-sided or symmetric surface-distance envelope;
- a correct literal implementation of the printed normal inequalities;
- collapse link conditions, genus/component preservation, or manifold output;
- orientation, local inversion, duplicate-face, or self-intersection guards;
- semantic patch and feature provenance through every split/collapse/flip;
- a worst-case minimum-angle bound;
- convergence of area equalization, which the paper says oscillates;
- deterministic ordering or reproducible output;
- a hard face, memory, or runtime cap under tight fidelity constraints;
- proof that a requested sample count remains reachable when fidelity rejects
  candidate splits or collapses; or
- suitability of PN reconstruction for exact CAD boundaries or thin gaps.

The conclusion explicitly identifies inability to control sampling beyond
feature-edge boundaries as an open problem and suggests relaxing feature-edge
error conditions followed by post-processing restoration. Generalization to
quad meshes is also future work.

## AutoTessell mapping

`core/preprocessor/native_remesh/isotropic.py` shares the broad local-operation
vocabulary but not this paper's core mechanisms. The current code uses a
single target edge length, the later `4/3` split and `4/5` collapse thresholds,
valence-decreasing flips, and neighbor-centroid relocation. Its optional
projection snaps relocated vertices to the nearest **source vertex**, not to a
source triangle or a persistent `(face,barycentric)` location. Feature
vertices are globally frozen rather than transported along feature curves.

More importantly, current split, collapse, and flip candidates are committed
without the paper's affected-face source-normal tests. Collapse merges to a
midpoint and deletes degenerate faces without an explicit link condition;
flip is accepted from valence energy alone; and no local source-face
provenance survives reindexing. The paper's own predicates are too weak for a
production CFD contract, but the absence of any candidate-local geometry gate
is still a material gap.

The current split sweep is also organized per face: each face independently
splits only its longest over-threshold edge. The function reuses a midpoint ID
when both incident faces choose the same edge, but it does not atomically
rewrite both faces of a shared edge when only one side selects it. A
conforming edge-based transaction and an explicit post-operation manifold
check are required before treating this as the paper's edge-split operation.

Adopt or adapt:

- persistent source-triangle plus barycentric provenance, propagated by every
  local topology transaction;
- closest-triangle or provenance-local source projection instead of
  nearest-source-vertex snapping;
- independent conflict batches and deterministic priority queues;
- area-ratio relocation as an optional adaptive sampling target;
- target valences 6/4 and the long/short/drifting-edge idea as a secondary
  connectivity pass; and
- local patch construction only where provenance walking cannot remain within
  a small source neighborhood.

Do not adopt unmodified:

- the printed dot-product inequalities;
- PN reconstruction as the certified reference surface;
- normal variation as a substitute for a distance envelope;
- midpoint collapse without topology and local-orientation simulation;
- unbounded special-feature freezing; or
- fixed empirical iteration counts as a termination contract.

For AutoTessell, candidate operations should be simulated and committed as
transactions only after link/manifold, orientation, duplicate, semantic
feature, local quality, and conservative two-sided source-envelope tests pass.
Persistent patch and feature identifiers must be remapped through splits and
collapses rather than represented only by original vertex-index pairs.

## Falsifiable implementation cards

1. `TRI-SG-PROVENANCE1`: attach `(source_face, barycentric)` provenance to
   every native-triangle vertex and propagate it across split, collapse, flip,
   and relocate transactions. Pass analytic plane, sphere, sharp fan-disk, and
   thin-gap tests only if all coordinates remain finite and inside their source
   faces, semantic patch IDs survive, repeated runs are identical, and the
   conservative two-sided envelope never regresses against closest-triangle
   projection. Nearest-source-vertex snapping is the baseline.
2. `TRI-SG-TRANSACTION1`: simulate each collapse and flip before commit with a
   link condition, signed-area/orientation test, duplicate-face test, protected
   provenance check, minimum-quality floor, and two-sided envelope gate. Pass
   only if genus, component count, boundary-loop count, manifoldness, and
   orientation remain unchanged on adversarial handles, thin shells, creases,
   and near-degenerate one-rings.
3. `TRI-SG-AREA1`: implement equation (4) as an optional proposed relocation
   target with guarded linear solve and an explicitly validated sizing-field
   direction. At matched output count and envelope, require lower edge/area
   coefficient of variation and no regression in 1st-percentile angle,
   feature drift, determinism, or downstream tet/hex-dominant/poly gate rate.
   Reject the card if the loop oscillates past a deterministic improvement
   threshold or operation budget.
4. `TRI-SG-REGULARIZE1`: add the easy/long/short/drifting priority pass behind
   all topology and geometry gates. Compare it with ordinary valence-decreasing
   flips at equal face count. Accept only if irregular-valence percentage and
   lower-tail angle improve without increasing envelope error, topology
   failures, feature loss, or runtime beyond the declared budget.
5. `TRI-SG-PATCH1`: prototype cached mean-value source patches for provenance
   transfers that cross source-face neighborhoods. Require foldover-free 2D
   embeddings, bounded cache memory, no face-walk failure, and equivalent or
   better envelope results than a robust closest-triangle query. Drop the
   patch cache if its complexity does not beat the query baseline on the
   project corpus.

## Backward references and snowball priorities

All 32 references on the rendered final page were checked. The highest-value
backward reads for the native engine are:

- Frey and Borouchaki, *Geometric Surface Mesh Optimization* (1998), for the
  original normal-based fidelity criteria.
- Surazhsky and Gotsman, *High Quality Compatible Triangulations* (2002), for
  weighted angle smoothing and the area-equalization precursor.
- Floater, *Parameterization and Smooth Approximation of Surface
  Triangulations* (1997), and *Mean Value Coordinates* (2003), for the exact
  no-foldover assumptions of convex-boundary local patches.
- Vlachos et al., *Curved PN Triangles* (2001), for the reconstructed-reference
  approximation used by `(face,barycentric)` provenance.
- Owen, White, and Tautges, *Facet-Based Surfaces for 3D Mesh Generation*
  (2002), for the barycentric source-face walk.
- Dyn et al., *Optimizing 3D Triangulations Using Discrete Curvature Analysis*
  (2001), and Surazhsky et al., *Computing Gaussian and Mean Curvatures on
  Triangular Meshes* (2003), for the density field.
- Alliez, Meyer, and Desbrun, *Interactive Geometry Remeshing* (2002), and
  Alliez et al., *Isotropic Surface Remeshing* (2003), for global
  parameterization, sampling, and basic regularization comparators.
- Rassineux et al., *Surface Remeshing by Local Hermite Diffuse
  Interpolation* (2000), Turk, *Re-tiling Polygonal Surfaces* (1992), and
  Hoppe et al., *Mesh Optimization* (1993), for local projection and
  adaptation alternatives.
- Watanabe and Belyaev, *Detection of Salient Curvature Features on Polygonal
  Surfaces* (2001), for more robust feature detection than a lone dihedral
  threshold.

The most urgent verification is Frey-Borouchaki because the fidelity formulas
as printed here are internally inconsistent. Floater and Owen et al. are next
for the exact local-patch and source-face-walk preconditions. Later
error-bounded papers must be preferred for the production envelope contract.
