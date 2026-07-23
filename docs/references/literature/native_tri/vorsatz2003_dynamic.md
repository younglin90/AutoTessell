# Vorsatz et al. - Dynamic Remeshing and Applications

## Bibliography and access

- Jens Vorsatz, Christian Rossl, and Hans-Peter Seidel.
- *Proceedings of the Eighth ACM Symposium on Solid Modeling and
  Applications (SM '03)*, pages 167-175, 2003.
- DOI: `10.1145/781606.781633`.
- Local full text supplied by the user:
  `C:/Users/user/Downloads/vorsatz2003.pdf`.
- Review status: `FULL_READ` on 2026-07-23. All nine pages, equations,
  algorithm descriptions, feature rules, applications, figures, and 26
  references were inspected. PDF pages 2, 4, 5, 6, and 8 were rendered at
  2x resolution and visually checked. The rendered formulas and feature-rule
  bullets agree with the extracted text.

## Problem and contract

The paper incrementally remeshes a triangle mesh `M` while constraining its
vertices to a fixed triangle-domain mesh `D`. Its objectives are approximately
uniform vertex distribution, bounded edge lengths, valence regularity, and
preservation of a selected feature skeleton. Unlike global-parameterization
methods, it constructs only the small local parameter domains required by
each one-ring relaxation.

The main presentation starts from `M = D`, so every remesh vertex initially
has an exact one-to-one domain association. The conclusion says an arbitrary
initial `M` is possible only after a preprocessing step constructs a valid
link from `M` to `D` and maps remesh triangles to sets of domain triangles.
The paper assumes a usable manifold input surface. It does not define repair
for triangle soups, non-manifold input, holes, inconsistent orientation, or
self-intersections.

This is an isotropic remesher. The authors mention that curvature-direction
weights could produce anisotropy but do not develop or test that extension.

## Domain link and local relaxation

Every remesh vertex `v_i in M` is linked to a containing domain triangle
`D_j in D` and barycentric coordinates:

```text
v_i -> (D_j, (alpha_i1, alpha_i2, alpha_i3)),
sum_j alpha_ij = 1, alpha_ij >= 0.
```

Flattening a local portion of `D` therefore also maps its associated part of
`M` to the plane. With parameter positions `p_i` and one-ring neighbors
`p_ij`, the weighted umbrella update is

```text
U(p_i) = p_i
       + [1 / sum_j omega_ij] sum_j omega_ij (p_ij - p_i),
omega_ij >= 0.
```

The new parameter point is lifted through the domain link rather than through
an unconstrained 3D displacement or nearest-vertex projection. The move is
restricted to the part of the local domain assigned to the vertex and covered
by its one-ring, so the lifted point remains defined.

For each remesh triangle `Delta`, the implementation maintains

```text
C(Delta) = {D_triangle in D |
            Phi(Delta) intersects Phi(D_triangle)}.
```

The union of these sets over a vertex one-ring supplies the minimal local
domain. A local domain additionally contains one domain triangle when the
vertex is in a face, two triangles when it is on an edge, or a full domain
one-ring when it coincides with a domain vertex. Intersection results and
parameterizations are cached and updated only where a vertex or connectivity
operation changes coverage.

For nearly planar normal cones, projection onto a fitting plane is allowed.
Otherwise the paper uses Floater's shape-preserving parameterization after
projecting the local boundary to a plane. If the map folds, the implementation
usually skips that vertex for the current iteration. Only after repeated
failure does it remap the boundary to a circle and retry. This is a recovery
heuristic, not a proof that every local domain can be processed.

Uniform `omega_ij` gives uniform samples in the almost-isometric local charts
but may skip a geometrically important part of `D` when `M` is coarse. The
paper therefore makes `omega_ij` proportional to the 3D areas of the domain
triangles covered by the corresponding remesh one-ring. The intent is to
distribute samples according to actual domain area rather than chart area.

## Dynamic connectivity schedule

The Dynamic Connectivity Mesh component targets three conditions:

- every edge has length at least `epsilon_min`;
- every edge has length at most `epsilon_max`; and
- interior valence is near six.

The operations are incremental:

1. Collapse all edges shorter than `epsilon_min`.
2. Split all edges longer than `epsilon_max`.
3. Flip an interior edge shared by triangles `(A,B,C)` and `(A,B,D)` when the
   flip decreases

```text
sum_{p in {A,B,C,D}} (valence(p) - 6)^2.
```

4. Immediately reschedule vertices affected by a split or collapse for
   relaxation, and retest their neighborhoods for flips.

The paper requires

```text
epsilon_max > 2 epsilon_min
```

so splitting a long edge cannot immediately create two edges that violate the
lower bound. This interval differs from the later Botsch-Kobbelt schedule:
`epsilon_max/epsilon_min = (4/3)/(4/5) = 5/3`, which does not satisfy the
Vorsatz inequality. These are different algorithms and their thresholds must
not be combined without testing.

A split initially places the new vertex on one endpoint, called its parent,
and therefore creates degenerate triangles transiently. This avoids a new
point-location search because the child inherits a valid domain link; the
immediate relaxation is expected to remove the degeneracy. AutoTessell must
not expose this transient state across an acceptance boundary and should not
adopt it unless operations are transactional.

The paper states that the three local topological operations keep `M` a valid
2-manifold, but it does not provide the link-condition predicate, candidate
conflict rules, orientation test, or rollback pseudocode needed to reproduce
that claim independently.

## Feature skeleton

The fixed domain skeleton is selected automatically from sharp geometry or
interactively by the user. Its counterpart on `M` changes with the mesh. The
paper distinguishes:

- **bone edges**: selected feature edges;
- **bone vertices**: vertices incident to exactly two bone edges; and
- **corner vertices**: vertices incident to a number of bone edges other than
  two, plus explicitly selected vertices.

The exact operational restrictions are:

1. Corner vertices remain fixed and no topological operation may touch them.
2. Bone vertices move only on bone edges of `D`. The umbrella result is
   projected to the bone edge having the smallest enclosing angle.
3. A bone edge can collapse only when both endpoints belong to the skeleton.
   A non-skeleton vertex may collapse into the skeleton and then becomes part
   of it.
4. Bone edges are never flipped.
5. Splitting a bone edge creates a bone vertex. If its parent is a corner, the
   child is assigned to the reachable domain bone edge with the smallest
   enclosing angle to the split edge.

This is materially stronger than freezing both endpoints of every detected
sharp edge. Degree-two feature vertices can slide along the feature curve,
while junctions and explicit corners remain fixed. The domain skeleton also
provides persistent feature identity while the remesh skeleton is split and
collapsed.

The rules still depend on correct feature selection. No geometric tolerance,
feature-curve approximation error, patch-interface semantics, or proof that
two nearby feature branches cannot be confused is supplied.

## Applications and experiments

- Interactive multiresolution modeling uses a global map for a small selected
  region when possible and falls back to local maps after foldovers. A region
  of roughly 5,000-10,000 triangles reportedly parameterizes in a fraction of
  a second, but no table or repeated timing is given.
- Region-restricted remeshing schedules only vertices and edges in the chosen
  region, leaving its boundary connected to the fixed mesh without zippering.
- A user-editable scalar field changes `omega_ij` to control local density.
- A two-phase square-root-three remeshing variant first coarsens with dynamic
  connectivity and then applies hierarchical 1-to-3 refinement. Two refinement
  levels are grouped so feature edges correspond between levels.
- The largest stated interactive example has 77,000 triangles and response
  time below 4-5 seconds. Hardware details, memory, corpus statistics,
  geometry error, worst angle, and determinism are not reported.
- The remeshed Tweety, horse, fandisk, Max-Planck, and tooth examples are
  visual evidence. They do not establish worst-case topology, fidelity, or
  quality guarantees.

## Guarantees, assumptions, and limitations

What the paper supports:

- every accepted vertex move is represented in a local chart and lifted via
  an explicit triangle/barycentric domain link;
- a selected skeleton is transported through local topology changes;
- the edge-length band and valence objective can be changed interactively;
  and
- no global patch layout or global cut is required for the general remesher.

What the paper does not guarantee:

- no one-sided or symmetric Hausdorff/envelope bound;
- no minimum angle or triangle-quality lower bound;
- no normal-deviation or feature-curve error bound;
- no self-intersection, duplicate-face, or fold-over-free 3D output proof;
- no explicit topology predicate or genus/component invariant;
- no semantic patch or CAD-curve provenance model;
- no output face/vertex cap or exact sample budget;
- no convergence proof or deterministic candidate order; and
- no robust procedure for local parameterizations that repeatedly fail.

Because output vertices lie on `D` but output chords need not lie on `D`, the
barycentric link is not itself a surface-envelope certificate. A coarse face
can bridge across curved or thin geometry even when all its vertices are on
the source.

## AutoTessell mapping

The existing four-stage loop in
`core/preprocessor/native_remesh/isotropic.py` already splits, collapses,
flips for valence, and relocates. It differs from this paper in important ways:

- splitting uses a 3D midpoint, not a parent endpoint with inherited domain
  linkage;
- collapsing merges to one endpoint without a published domain-coverage map;
- relocation uses a 3D neighbor centroid and the higher-level engine projects
  afterward, rather than updating through a local bijective chart;
- feature detection freezes all vertices incident to a sharp, boundary, or
  non-manifold edge instead of separating sliding degree-two bone vertices
  from fixed corners;
- protected edges are original index pairs, not a persistent dynamic skeleton;
  and
- there is no per-remesh-face coverage set `C(Delta)` or barycentric source
  provenance.

`core/preprocessor/native_remesh/face.py` improves the production contract by
requiring a closed manifold input and rejecting results that fail
watertightness, manifoldness, degeneracy, orientation, drift, protected-edge,
or triangle-quality gates. Those are final gates; this paper suggests how to
retain exact source and feature provenance during each local operation, but
its own guarantees remain insufficient for AutoTessell.

Adopt:

- persistent domain-triangle and barycentric provenance for every vertex;
- a dynamic skeleton with fixed corners and feature-edge sliding;
- immediate reconsideration of the local queue after topology edits;
- region-local remeshing with immutable boundary/patch constraints; and
- coverage-aware sampling weights when the output is much coarser than the
  source.

Do not adopt directly:

- transient degenerate split faces outside an atomic operation;
- the unproved claim that local operations automatically preserve manifoldness;
- local-chart success as a geometry-error certificate; or
- the `epsilon_max > 2 epsilon_min` band as a drop-in replacement for the
  existing, separately sourced `4/5` and `4/3` thresholds.

## Falsifiable implementation cards

1. `TRI-DOMAIN-LINK1`: attach `(source_face, barycentric_coordinates)` to every
   remesh vertex and update it transactionally after split, collapse, flip,
   and relocation. Pass only if all coordinates remain finite, sum to one
   within `1e-12`, stay within a declared tolerance of the source triangle,
   and reproduce the stored 3D point under deterministic replay.
2. `TRI-FEATURE-SKELETON1`: replace all-feature-vertex locking with persistent
   feature chains: junction/corner vertices fixed, degree-two vertices sliding
   along their source chain, and bone edges never flipped across patch roles.
   Pass only if feature graph components, junction degree, patch adjacency,
   and curve provenance are identical before and after remeshing, while
   feature-edge length variation improves over full locking.
3. `TRI-COVERAGE1`: maintain conservative source-face coverage for every
   output face and use it for local two-sided envelope tests before commit.
   Test thin gaps, high curvature, close sheets, and coarse output. Pass only
   if no accepted face bridges an unrelated source region and the independent
   symmetric-distance verifier stays within tolerance.
4. `TRI-LOCAL-QUEUE1`: after each successful local operation, deterministically
   reschedule only its affected one-ring for length, valence, orientation,
   feature, and quality checks. Compare with full rescans. Pass only if final
   topology and diagnostics are identical across face/index permutations and
   runtime improves on meshes above 100,000 faces.
5. `TRI-LOCAL-CHART1`: prototype bounded one-ring parameterization only as a
   relocation candidate generator. Reject maps with non-positive parameter
   triangles, excessive condition number, or source-provenance ambiguity, and
   fall back without moving the vertex. Promote only if minimum quality and
   convergence improve without envelope, feature, topology, or determinism
   regression.

## Backward references and follow-up priority

- Kobbelt, Bareuther, and Seidel, *Multiresolution Shape Deformations for
  Meshes with Dynamic Vertex Connectivity* (2000): DCM foundation and the
  missing lower-level topology details.
- Vorsatz et al., *Feature Sensitive Remeshing* (2001): feature snapping when
  `M` and `D` do not initially coincide.
- Floater, *Parametrization and Smooth Approximation of Surface
  Triangulations* (1997): local shape-preserving maps.
- Alliez, Meyer, and Desbrun, *Interactive Geometry Remeshing* (2002), and
  Lee et al., *MAPS* (1998): global-parameterization contrast.
- Rossl, Kobbelt, and Seidel, *Recovering Structural Information from
  Triangulated Surfaces* (2001): automatic skeleton extraction.
- Botsch and Kobbelt (2004): later split/collapse thresholds and tangential
  smoothing; its hysteresis must remain documented separately from this
  paper's `epsilon` condition.
