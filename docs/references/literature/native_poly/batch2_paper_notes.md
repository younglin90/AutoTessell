# Native Poly Literature Review - Batch 2 Paper Notes

## 1. Uniform Random Voronoi Meshes

**Citation.** Mohamed S. Ebeida and Scott A. Mitchell, 2011. DOI:
`10.1007/978-3-642-24734-7_15`.

**Method.** Generate a maximal uniform Poisson-disk sample in the volume,
protect reflex boundary edges with denser samples, construct each Voronoi cell
by local perpendicular-bisector cuts, clip against the domain, and weld short
edges. A uniform background grid supplies locality: only seeds in a fixed
neighbor template can bound a cell.

**Validity and guarantees.** Maximality gives an outradius bound and sample
separation gives an inradius bound. Before welding, an interior cell has aspect
ratio at most 2. Boundary-cell bounds degrade with local feature size and input
angles. Interior dihedral angles are bounded; input boundary dihedrals remain
controlled by the domain. The guarantee is for the pre-weld clipped cells.

**Limits.** Welding can make faces non-planar. The implemented version does not
yet handle the promised two-sided non-manifold boundary path. Sharp and close
features require smaller local radii or more elaborate protection. This is an
important warning against copying only the sampling step and assuming the
boundary proof still applies.

**Native impact.** Replace jittered Cartesian interior seeds with an optional
maximal Poisson sampler, but do not adopt weld-on-output without a transactional
face-planarity and incidence check. Seed classes and protection provenance must
be stored explicitly.

## 2. Efficient Computation of Clipped Voronoi Diagram for Mesh Generation

**Citation.** Dong-Ming Yan, Wenping Wang, Bruno Levy, and Yang Liu, 2013.
DOI: `10.1016/j.cad.2011.09.004`.

**Method.** Compute a Delaunay diagram, detect surface-restricted Voronoi cells
by propagating incident cell/triangle pairs, then construct boundary clipped
cells by propagating cell/tetrahedron pairs through a conforming background tet
mesh. FIFO queues and adjacency replace repeated global nearest searches. CVT is
optimized with L-BFGS; boundary sites are constrained by tangential gradients.

**Validity and topology.** The implementation uses exact predicates for
side-of-plane decisions. Completeness depends on a valid, closed 2-manifold
surface and a conforming tetrahedralization with consistent triangle/tet
adjacency. The paper reports robust clipped diagrams, including degenerate test
configurations, but does not prove arbitrary non-manifold support.

**Quality evidence.** Reported metrics apply to the primal tetrahedral output:
minimum/maximum dihedral angle, radius ratio, a normalized volume/edge metric,
and Hausdorff boundary error. CVT alone leaves slivers, requiring a separate
perturbation stage.

**Native impact.** The most transferable piece is the incident-pair propagation
dataflow. Native Poly needs boundary triangle adjacency, tet adjacency, Delaunay
neighbor relations, per-cell incident sets, and exact predicates. Current
nearest-surface snapping cannot preserve the same Voronoi dual structure.

## 3. Exact General Remeshing by Topology-Preserving Clipping

**Citation.** Devon Powell and Tom Abel, 2015. DOI:
`10.1016/j.jcp.2015.05.022`.

**Method.** Represent a convex polyhedron by its planar one-skeleton in a
half-edge-like, triply linked vertex structure. During clipping, traverse the
connected component behind the plane and insert intersection vertices in cyclic
order. Face loops remain implicit in the graph. The same graph is traversed to
decompose the result and integrate polynomial moments.

**Validity and topology.** Each cut preserves a planar, three-vertex-connected
graph. Spatially degenerate vertices and zero-length edges encode high-valence
events without an ambiguous geometric reconstruction. This is a strong design
for convex clipping, but it is topological consistency rather than exact
arithmetic and does not make non-convex or self-intersecting input valid.

**Numerical quality.** This paper measures conservation and robustness, not
cell shape. It shows why volume/moment evaluation should be shifted into a local
coordinate frame: otherwise cancellation error grows cubically with the ratio
between absolute coordinates and cell size.

**Native impact.** Adopt a shared oriented face-loop representation for clipping,
validation, volume, centroid, and output. This avoids the current pattern of
rebuilding each cell with a generic convex hull, which can erase intended face
classification and adjacency.

## 4. Field-Guided Polyhedral Agglomeration

**Citation.** Xifeng Gao, Wenzel Jakob, Marco Tarini, and Daniele Panozzo,
2017. DOI: `10.1145/3072959.3073676`.

**Method.** Optimize orientation and position fields on an input tet mesh. Use
those fields to classify edges, then alternate edge collapse, edge dissolve,
face dissolve, edge split, face split, and polyhedral split operations. Splits
can unlock later coarsening instead of forcing a greedy monotone reduction.

**Topological guarantee.** Each face must remain topologically a disk and each
cell boundary a sphere. Before a local edit, the method extracts a surrounding
topological sphere by BFS, applies the operation to that temporary neighborhood,
and commits only if invariants hold. This preserves manifoldness and genus.

**Geometric limitation.** Topological validity is not geometric validity. The
paper reports rare inverted, self-intersecting, and collapsed cells. Its scaled
Jacobian metric covers the hexahedral portion better than arbitrary residual
polyhedra. A second geometric validity gate is therefore mandatory.

**Native impact.** This is the clearest architecture for safe agglomeration:
explicit incidence, atomic edits, local extraction, rollback, and independent
topology/geometric validators. Patch and material interfaces should be added as
hard edit barriers. Field optimization itself is optional for a pure polyhedral
engine.

## 5. Voronoi Grids Conforming to Lower-Dimensional Objects

**Citation.** Runar Lie Berge, Oystein Strengehagen Klemetsdal, and
Knut-Andreas Lie, 2019. DOI: `10.1007/s10596-018-9790-0`.

**Method.** Represent wells, fractures, their intersections, and the volume as a
mixed-dimensional hierarchy. Paired sites create boundary-aligned Voronoi faces;
sites on a curve create control-point-aligned cells. A necessary and sufficient
"fracture condition" checks conformity before the complete grid is built.
Constraint sites remain fixed during force-based or L-BFGS/CVD optimization.

**Topological consistency.** Shared intersection sites and the
Delaunay/Voronoi incidence relation connect the 0D, 1D, 2D, and 3D grids. The 2D
algorithm explicitly handles well-well and fracture-fracture conflicts by
sharing, resizing, or merging construction circles.

**Limits.** In 3D, constraints are communicated upward in dimension but not
fully between different objects of the same dimension. Very sharp or narrowly
separated fractures can interfere. Exact capture of some 3D fracture boundary
vertices is not implemented. The MATLAB prototype also rebuilds PEBI grids
during CVD optimization and is comparatively slow.

**Native impact.** Patch IDs alone are insufficient. Preserve a hierarchy of
model entities, generated site pairs, shared intersection entities, and fixed
optimization masks. This directly complements existing patch-role provenance
and supplies principled barriers for later agglomeration.

## 6. Survey of Mesh Quality Indicators

**Citation.** Teresa Sorgente, Silvia Biasotti, Gianmarco Manzini, and
Michela Spagnuolo, 2023. DOI: `10.1111/cgf.14779`.

**Main finding.** Mesh quality is application dependent. A scalar that is fair
for tetrahedra is not automatically meaningful for generic polyhedra. The paper
separates element geometry from global consistency, structure, distribution,
gradation, and solution alignment.

**Polyhedral validity and metrics.** Candidate gates and indicators include
positive volume, convexity or star-shapedness, cell and face kernels,
inradius/circumradius ratios, kernel-volume ratios, warpage, skewness, scale
ratios, combinatorial counts, and interpolation-oriented measures. Many methods
assume a valid tetrahedralization of each polyhedron, which must not be treated
as automatic for concave cells.

**Topology.** Geometry consistency means faithful boundaries and features;
topology consistency means coherent incidence plus preserved connected
components and holes; solution consistency means alignment and resolution where
the PDE requires it. These are separate acceptance dimensions.

**Native impact.** Implement a vector report and staged failure policy:

1. closed incidence, owner/neighbour symmetry, patch/interface pairing;
2. signed volume, self-intersection, face cycles, and star-kernel existence;
3. face warpage and minimum edge/face/cell scale ratios;
4. non-orthogonality, skewness, gradation, and solver-specific metrics.

An average score must never hide a failed validity gate.

## Combined implementation sequence

1. Add an oriented polyhedral incidence representation and deterministic local
   validator.
2. Implement robust half-space clipping on that representation with filtered or
   exact predicates.
3. Add incident-pair propagation over a conforming background tet mesh.
4. Introduce boundary/interface/mixed-dimensional site provenance.
5. Add maximal Poisson interior sampling behind a feature flag and benchmark it
   against current seeds.
6. Replace destructive cell dropping with transactional collapse, dissolve,
   split, and rollback.
7. Gate every output through topology, geometric validity, quality-vector, and
   solver-specific checks in that order.

## 7. An Efficient Approach for Solving Mesh Optimization Problems Using Newton’s Method (2014)

**Citation.** Jibum Kim, Mathematical Problems in Engineering, 2014, 9 pages,
DOI: `10.1155/2014/273732`.

**Method.** The paper applies Newton-style updates (gradient + Hessian) to nonlinear
mesh objectives with Hessian modification and line search when the matrix is not
positive-definite. It compares Newton and quasi-Newton/steepest-descent variants
under both quality and untangling workloads and reports better convergence for
distorted meshes.

**Native impact.** This is directly useful as an in-place, local recovery kernel.
It is optimizer-level, not topology-level: use it after topological decisions
(recovery/agglomeration/rollback) as a constrained local smoothing or
untangling stage with explicit rollback on inversion or quality regression.

## 8. Untangling Polygonal and Polyhedral Meshes via Mesh Optimization (2014)

**Citation.** Jibum Kim and Jaeyong Chung, Engineering with Computers, 2014,
DOI: `10.1007/s00366-014-0379-5`.

**Method.** The method introduces local untangling operators with three energy
variants: size-only, hybrid size/shape, and adaptive-sigmoid hybrid. The hybrid
forms are designed to remove inversions without global remeshing while still
improving shape.

**Native impact.** Good fallback for post-construction inverted-polyhedral
recovery. Treat as hard-gated local optimization: accept only if patch labels,
topology incidence, and geometric validity gates pass.
