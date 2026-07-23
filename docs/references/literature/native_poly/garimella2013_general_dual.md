# Polyhedral Mesh Generation and Optimization for Non-manifold Domains

## Bibliography and access

- Rao V. Garimella, Jibum Kim, and Markus Berndt.
- *Proceedings of the 22nd International Meshing Roundtable*, 2013, 313-330.
- DOI: `10.1007/978-3-319-02335-9_18`
- Legal author/proceedings copy (archived Sandia URL):
  <https://web.archive.org/web/20161216071606id_/http://www.imr.sandia.gov/papers/imr22/IMR22_18_Garimella.pdf>
- Status: `FULL_READ` (18/18 pages).
- Visual check: pages 4, 6, 11, and 15 were rendered and inspected. The generalized
  dual diagram, nine-step algorithm, validity decomposition/equations, and concave
  boundary failures were consistent with extracted text.

## Problem and assumptions

The method constructs a conforming general polyhedral mesh by dualizing any valid,
boundary-conforming tetrahedral mesh. It does not require a Delaunay or
well-centered primal. Exact geometric-model classification is the central contract:
primal vertices, edges, faces, and regions should be classified on corresponding
model entities so exterior boundaries, internal material interfaces, creases,
corners, and non-manifold junctions can be reconstructed.

If the primal is Delaunay and well-centered, circumcenter dualization gives a
Voronoi mesh. For a general tet mesh, the output instead has straight edges but may
have curved/non-planar faces; it is a generalized dual, not a Voronoi mesh.

## Dual construction

The paper gives nine topology-driven steps:

1. create one dual vertex at a central point of each primal tet;
2. create one at each boundary primal-face center;
3. create one at the midpoint of each primal edge classified on a model edge;
4. reuse each primal vertex classified on a model vertex;
5. create one interior dual face for every interior primal edge;
6. create one or more interior dual faces for boundary primal edges;
7. create boundary capping faces for boundary primal vertices;
8. assemble one dual region for every interior primal vertex;
9. assemble one or more dual regions for each boundary primal vertex.

For a well-centered tet, the tet dual point is its circumcenter. Otherwise, the
point is chosen inside the tet, as close as possible to the circumcenter on the
circumcenter-centroid segment. Rings of tets around primal edges define dual faces.
Boundary and non-manifold classifications determine where rings open, how many
faces are created, and which caps belong to each region.

Very short edges are collapsed after construction because they can force small
simulation time steps.

## Validity and optimization

The validity test decomposes each polyhedron into signed tetrahedra formed by an
original edge, the arithmetic face center, and the arithmetic region center. Every
sub-tet must have positive volume. This is a conservative star-shaped test with an
unambiguous face interpretation shared by both incident cells.

For a trivalent corner the condition number has the form `kappa = A*L/V`, where
`V` is six times signed sub-tet volume. A regularized denominator
`V + sqrt(V^2 + delta^2)` permits untangling through zero volume; `delta` adapts to
local signed volume. For general polyhedra, the objective averages corner condition
numbers from either the symmetric decomposition or a cheaper region-center
decomposition. Local vertex optimization uses Newton iterations, numerical
gradient/Hessian, positive-definite Hessian repair, damping, validity checks, and an
Armijo decrease condition. Boundary motion remains on the original facetization.

## Results and limitations

- Simple and two-material examples were untangled successfully.
- At sharp concave boundaries, invalid non-star-shaped cells remained. The authors
  explicitly state that geometric smoothing cannot solve these cases; topological
  splitting or direct multiple-cell construction is required.
- No large benchmark suite, timing study, exact fidelity bound, or CFD error study
  is given. The method is presented as preliminary.
- Face planarity remains future work. A conforming generalized dual may still be a
  poor finite-volume mesh if its effective faces are strongly warped.

## Current-code gap

- `native_poly/dual.py` uses tet centroids for every primal region. It does not use
  circumcenters for well-centered tets or the closest-inside circumcenter-centroid
  construction.
- The file reconstructs rings and boundary caps, but it has no persistent geometric
  model classification for regions/faces/edges/vertices or multi-material
  non-manifold ownership. Output collapses all boundary semantics into
  `defaultWall`.
- Each candidate dual cell is replaced by `ConvexHull(pts, QJ)`. This can discard
  the topology of the intended generalized dual and silently converts a
  classification-driven construction into a convex-hull approximation.
- The source-plane projection and area/volume guards are useful empirical checks,
  but the binary path selector is not the paper's entity-classified construction.
- There is no star-shaped sub-tet validity objective or transactional Newton/Armijo
  untangler. A global shrink-to-volume calibration is not a substitute.

## Falsifiable implementation cards

### `POLY-DUAL-CLASSIFY1`

Carry model-region, interface, patch, crease, and corner classification from the
surface/primal tet mesh to every dual entity. Pass on multi-material and
non-manifold fixtures only if each classified model entity has a conforming dual
subcomplex and no interface is emitted as an external wall.

### `POLY-DUAL-POINT1`

Use circumcenters for well-centered tets and a robust closest-inside point on the
circumcenter-centroid segment otherwise. Pass if every dual point is inside/on its
primal tet, exact well-centered fixtures reproduce circumcenters, and no cell count
or topology changes under rigid transform and scale.

### `POLY-STAR-VALID1`

Implement the shared-face-center/region-center signed-subtet validity test and
record minimum normalized determinant per cell. Pass only if every written cell is
positive under both neighboring interpretations of each shared face.

### `POLY-DUAL-UNTANGLE1`

Add a transactional local optimizer with boundary classification constraints,
positive-definite Hessian repair, Armijo decrease, and exact rollback. Pass if it
strictly reduces invalid cells/condition objective without changing boundary
topology or worsening source-surface error; unresolved concave cells must be
reported, never hidden.

### `POLY-CONCAVE-SPLIT1`

Split irreparable concave-boundary dual regions along classification-consistent
faces. Pass if all children pass `POLY-STAR-VALID1`, the union volume matches the
parent within tolerance, and neighboring cells receive identical shared faces.

