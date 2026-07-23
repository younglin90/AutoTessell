# Mandad et al. - Isotopic Approximation within a Tolerance Volume

## Bibliography and access

- Manish Mandad, David Cohen-Steiner, and Pierre Alliez.
- *ACM Transactions on Graphics*, 34(4), Article 64, August 2015; presented
  at SIGGRAPH 2015. Twelve pages.
- DOI: `10.1145/2766950`.
- Local full text supplied by the user: `C:/Users/user/Downloads/mandad2015.pdf`.
- Review status: `FULL_READ` on 2026-07-23. All 12 pages were text-extracted.
  Pages 1, 3, 4, 6, 9, 10, and 12 were rendered at 2x resolution; the
  bibliography, inequalities, refinement conditions, visibility-kernel
  figures, isotopy theorem, comparison plots, timing table, limitations, and
  references were visually checked against the extracted text.

## Problem and input contract

The input is a tolerance volume `Omega`, ideally a topological thickening of a
target surface `S`: a compact subset of `R^3` homeomorphic to `S x [0,1]`.
The base exposition assumes two boundary components, `dOmega_1` and
`dOmega_2`. The desired output is a low-complexity triangle mesh contained in
`Omega`, separating its boundary components, intersection-free, and isotopic
to `S` under the theorem's separation and sampling assumptions.

This is not ordinary remeshing of an already valid surface. It constructs a
surface inside a volumetric admissible region. If only points or a polygon
soup are available, a separate procedure must first construct a well-behaved
tolerance volume, for example an offset in the noise-free case or a sublevel
set of a robust distance function. Therefore robustness to defective source
data is delegated to tolerance-volume construction; it is not free robustness
of the meshing kernel.

The inclusion `Z subset Omega` is a geometric contract relative to the
tolerance volume. It becomes a Hausdorff-style error contract relative to a
reference surface only when `Omega` itself is constructed and certified as
the corresponding offset or error tube.

## Piecewise-linear classifier and refinement

The method samples the tolerance boundary with a `sigma`-dense set `S`, where
balls of radius `sigma` centered at the samples cover `dOmega`. Samples on the
two components receive labels

```text
F(s) = +1,  s in dOmega_1,
F(s) = -1,  s in dOmega_2.
```

An initial 3D Delaunay triangulation `T` is built from the eight corners of a
loose bounding box. A piecewise-linear function `f` interpolates the vertex
labels on `T`; its zero-set is `Z`. For every boundary sample,

```text
epsilon(s) = |F(s) - f(s)|.
```

A sample is bad when `epsilon(s) >= 1`. Each tetrahedron stores its contained
samples, and a global modifiable priority queue exposes the maximum-error
candidate. Inserting only until all finite samples are classified is
insufficient because `Z` could cross the tolerance boundary between samples.
The full refinement processes the following conditions in order:

1. For `0 < alpha < 1`, every sample must satisfy
   `epsilon(s) <= 1 - alpha`. The experiments use `alpha = 0.2`.
2. Every heterogeneous tetrahedron contributing to `Z` must have height at
   least `2 sigma / alpha`. Height is the distance between the supporting
   primitives of its maximum-dimensional same-label simplices. Since the
   local Lipschitz constant is twice the inverse height, this enforces the
   required upper bound `alpha / sigma`.
3. The piecewise-linear function of each tetrahedron must classify the nearest
   samples on both tolerance boundaries to the vertices of a shrunk copy of
   the tetrahedron. The experiments use a 70 percent shrink factor. This is a
   normal-orientation heuristic, not part of the topological proof.
4. If the zero-set still has the wrong genus, refine the heterogeneous
   tetrahedron with largest circumradius by inserting the sample nearest its
   circumcenter.

Condition 1 inserts the maximum-error sample. Conditions 2 and 3 insert the
sample nearest the bad tetrahedron's circumcenter. Condition 4 is deliberately
blind to the actual location of a topological defect; the authors retained it
for the proof but report that their experiments already had the correct genus
after the earlier refinement.

On termination, the union of tetrahedra contributing to `Z` is the simplicial
tolerance volume `Gamma`; its boundary is `dGamma`.

## Conservative simplification and mutual tessellation

After refinement, the algorithm stops maintaining Delaunay connectivity and
allows anisotropic cells. It simplifies the tetrahedral embedding rather than
decimating `Z` in isolation. Every collapse must preserve:

- combinatorial topology via the edge-collapse link condition;
- a valid 3D embedding by placing the target inside the visibility kernel of
  the collapsed edge's one-ring polyhedron;
- sample classification, by excluding invalid parts of that kernel; and
- the locally inferred normal condition from refinement.

The stages proceed from cheaper, discrete choices to more expensive,
continuous choices:

```text
1. Collapse edges of dGamma.
2. Mutually tessellate Z into T.
3. Collapse edges of Z.
4. Collapse edges between Gamma and Z, enabling more collapses of Z.
```

A halfedge collapse targets an endpoint and is attempted before a general
edge collapse. A general target is searched inside the admissible visibility
kernel. Candidate priority and target optimization use the sum of squared
distances from the target to supporting planes of zero-set faces in the
collapsed edge's 2-ring.

Before mutual tessellation, `Z` is implicit in `T` and may contain triangular
and quadrilateral sections. Mutual tessellation explicitly inserts its
vertices and faces into the 3D triangulation, assigns those vertices `F=0`,
and labels the surrounding tetrahedra by tolerance-boundary component. Sample
classification thereafter becomes a label-containment constraint.

For an edge of `dGamma`, candidate targets are tolerance-boundary samples
inside the visibility kernel. For an edge of `Z`, the target may be any point
in the valid kernel subset. The implementation described by the paper uses an
octree to sample the kernel and culls octree cells contained in analytically
constructed invalid regions. Collapsing edges between `Gamma` and `Z` enlarges
otherwise inaccessible kernels and exposes additional zero-set collapses.

## Guarantees and exact assumptions

Let `epsilon` now denote the radius of the largest ball contained in `Omega`,
and let `delta` be the minimum separation between its two boundary components.
For subsets `A` and `B`, their margin is the maximum thickness of a separating
slab. `Omega` is `(rho,h)`-separated when the portions of its two boundary
components inside every ball `B(x,rho)` have margin at least `h`.

Condition 2 is satisfied at termination when `sigma < delta` and `Omega` is
`(epsilon + sigma, 2 sigma / alpha)`-separated. A stronger local-separation
assumption yields condition 3, although the paper does not spell out its
constants because condition 3 is unnecessary for topology.

Theorem 3.1 states: let `kappa` bound boundary geodesic distance by `kappa`
times Euclidean distance for boundary-point pairs at Euclidean distance at
most `2(epsilon + sigma)`. If `Omega` is a

```text
((5 + kappa)(epsilon + sigma) / 2, 2 sigma / alpha)-separated
```

topological thickening of `S`, then the output is isotopic to `S`. The proof
uses three facts: the zero-set is a 2-manifold; classification and the height
condition keep it inside `Omega` and separating the two boundaries; and the
genus condition rules out linked homogeneous cycles representing a spurious
handle. The paper also gives the sufficient alternative

```text
2(epsilon + sigma) / sqrt(kappa^2 - 1) < delta.
```

These guarantees are conditional. A poorly separated volume can still produce
a manifold output with excessive genus. The paper does not guarantee optimal
triangle count, requested minimum angle, bounded normal deviation in every
case, or feasible construction of `Omega` from arbitrary corrupt data.

For surfaces with boundaries, a separate detector identifies boundary samples
and omits them from classifier enforcement; the zero-set is clipped by
`Omega`. During simplification the boundary of `Z` must remain within a
two-sided Hausdorff distance `delta` of the detected boundary samples, with an
additional supporting-edge fitting term. This extension can preserve or fill
holes, but the authors explicitly state that complicated hole repair needs
more work.

For non-manifold targets, the classifier is evaluated separately against each
tolerance-boundary component. Tetrahedra incident to three or more components
receive a centroid-based junction construction. The paper claims the correct
homotopy type for this extension but says an isotopy-style guarantee is much
harder to formulate and beyond existing tools. This must not be reported as
the same theorem as the closed 2-manifold case.

## Experimental evidence

- The C++ implementation uses CGAL triangulations and Intel TBB. Tests ran on
  a 2.4 GHz 16-core machine with 128 GB RAM. Tolerance is reported as a
  percentage of the input bounding box's longest edge; `alpha=0.2` throughout.
- For the blade at `delta=0.6%`, refinement produced 20,447 zero-set vertices,
  simplification of `dGamma` left 5,346, mutual tessellation and zero-set
  simplification left 1,015, and the final output had 752. The full run took
  about three hours and 2.1 GB peak RAM.
- The same timing table reports 655 s for refinement, 326 s for halfedge
  collapses on `dGamma`, 4,658 s for general collapses on `dGamma`, 153 s for
  zero-set halfedge collapses, 1,478 s for general zero-set collapses, and
  4,537 s for the all-edge stage. General kernel search dominates.
- On the blade, increasing tolerance from `0.15%` to `1.5%` reduced output
  vertices from 3,020 to 254 and runtime from roughly seven hours to 34
  minutes.
- Against simplification envelopes, Lindstrom-Turk, MMGS, anisotropic MMGS,
  and OpenFlipper on the fertility model, the method used fewer vertices at a
  given measured error but took longer. Compared with simplification envelopes
  on Armadillo it averaged about 10 percent fewer vertices across most of the
  curve. The comparison directions are plotted separately; the primary
  claimed bound is output-to-input, not an automatic exact symmetric
  Hausdorff certificate to an arbitrary source mesh.
- Without normal condition 3, measured deviations can exceed 90 degrees.
  Stricter normal preservation can over-refine sharp creases, and the paper
  supplies no universal quantitative normal guarantee.
- Operations over samples and tetrahedra parallelize well in the reported
  implementation; the paper shows near-linear multicore speedup on one model,
  not a general complexity proof.

## Limitations and claim boundary

- Tolerance-volume construction is an upstream unsolved reliability problem.
- Dense 3D Delaunay state, stored boundary samples, kernel probing, and mutual
  tessellation make the method compute- and memory-intensive.
- Small tolerances increase both refinement and classification cost; general
  collapse-target search becomes more expensive as kernels grow.
- Halfedge collapses are about two orders of magnitude faster in the reported
  example but are insufficient for the coarsest outputs.
- A sharp crease with a small subtended angle may demand extremely dense
  sampling. Normal constraints can confuse geometry recovery with topology
  recovery and leave an unnecessarily dense mesh.
- The theorem assumes a separated topological thickening. It is not a repair
  theorem for an arbitrary voxel band, self-overlapping offset, or noisy
  unsigned-distance shell.
- The method has no hard minimum-angle or maximum-complexity guarantee and no
  proof that its greedy output is the minimum nested polyhedron.
- Out-of-core partitioning is future work because stitching must preserve the
  global guarantees.

## AutoTessell code mapping

AutoTessell's current `isotropic.py` and `quadric_decimate.py` do not implement
this contract. The isotropic kernel uses split/collapse/flip/relocate on the
surface itself. Its collapse merges short edges without a link condition,
visibility kernel, candidate simulation, tolerance-volume classifier, or
intersection proof. Its optional projection snaps relocated vertices to the
nearest original vertex rather than to a certified surface or admissible
volume. The QEM decimator likewise collapses its cheapest edge without link,
fold-over, feature, self-intersection, or envelope guards.

The higher-level remeshing pipeline may reject a bad final result, but a final
gate is not equivalent to conservative per-operation invariants: a topology
change or local self-intersection cannot in general be repaired by snapping the
final vertices back to the source.

Adopt from this paper:

- the explicit separation between a hard feasible region and a soft
  simplification objective;
- link-condition and orientation/embedding checks before every collapse;
- classifying conservative reference samples against changed local cells;
- halfedge-first search with bounded general-target search;
- topology signatures checked during refinement, not only at output; and
- a volumetric tolerance mode for difficult repair/simplification cases.

Do not initially adopt the complete dense 3D mutual-tessellation pipeline as
the default remesher. It is too expensive for routine clean surfaces and
depends on a certified tolerance shell that AutoTessell does not yet build.
Use it as a high-assurance mode or as design evidence for local operation
gates.

## Falsifiable implementation cards

1. `TRI-TOL-BAND1`: construct a signed, two-sided tolerance band for a clean
   watertight reference mesh and certify that its inner and outer boundaries
   are disjoint 2-manifolds. Fail rather than claim a band when separation or
   orientation is ambiguous. Test nested thin shells, high curvature, sharp
   creases, and two components closer than `2 delta`.
2. `TRI-CLASSIFY1`: maintain deterministic stratified samples on both sides of
   the reference band. Simulate each local collapse and reject it when any
   affected sample crosses its assigned side or when a conservative
   Lipschitz/sampling-gap margin is exhausted. Pass only if an independent
   dense two-sided audit finds zero tolerance violations on the corpus.
3. `TRI-TOPO-KERNEL1`: add link condition, duplicate-face rejection,
   orientation preservation, and a non-empty local admissible-target kernel
   to every collapse. Pass only if component count, Euler characteristic,
   boundary-loop count, orientability, and self-intersection count remain
   invariant after every accepted operation.
4. `TRI-HALFEDGE-FIRST1`: compare endpoint-only collapses with bounded kernel
   search under equal topology and error gates. Enable continuous target
   search only when it reduces face count or improves worst angle enough to
   repay at least a fixed runtime multiple; enforce deterministic node and
   sample budgets.
5. `TRI-TOL-HIGHASSURANCE1`: prototype the paper's refinement plus explicit
   mutual-tessellation path as an opt-in mode. Promotion requires an isotopy
   oracle on analytic genus-controlled fixtures, zero intersections, certified
   band containment, deterministic output, and bounded memory at the declared
   production mesh size.
6. `TRI-TOL-NORMAL1`: implement the paper's normal-classification condition as
   a separately toggleable gate. Reject it as a default if it increases face
   count by more than the declared budget without improving the 99.9th
   percentile normal deviation and downstream volume-mesh quality.

## High-value references from this paper

- Chazal and Cohen-Steiner (2004), *A Condition for Isotopic Approximation*:
  theorem used for the isotopy argument.
- Dey, Edelsbrunner, Guha, and Nekhayev (1998), *Topology Preserving Edge
  Contraction*: link-condition foundation.
- Cohen et al. (1996), *Simplification Envelopes*: closest bounded-error
  simplification comparison.
- Borouchaki and Frey (2005), *Simplification of Surface Mesh Using Hausdorff
  Envelope*, DOI `10.1016/j.cma.2004.11.016`: local accumulated-envelope and
  normal-cone comparison.
- Boissonnat and Oudot (2005), *Provably Good Sampling and Meshing of
  Surfaces*: Delaunay refinement with guarantees.
- Chazal, Cohen-Steiner, and Merigot (2011), *Geometric Inference for Measures
  Based on Distance Functions*: robust tolerance construction used for noisy
  examples.

