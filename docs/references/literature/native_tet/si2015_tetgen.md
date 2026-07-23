# Si 2015 - TetGen, a Delaunay-Based Quality Tetrahedral Mesh Generator

## Bibliography and access

- Hang Si, *ACM Transactions on Mathematical Software* 41(2), Article 11,
  36 pages, 2015.
- DOI: https://doi.org/10.1145/2629697
- Public copy read: https://albertsk.org/wp-content/uploads/2011/12/si-atms-2015-10-1145_2629697.pdf
- Project page: https://wias-berlin.de/software/tetgen/
- Status: `FULL_READ` (36/36 pages); rendered inspection of pp. 19, 22, and 25.

## Pipeline and input contract

TetGen consumes a surface triangulation of a 3D PLC. Its pipeline is:

1. incremental Delaunay tetrahedralization of input vertices;
2. constrained mesh generation, either preserving constraints exactly or
   subdividing them;
3. quality refinement followed by local mesh optimization.

The PLC may contain internal boundaries and nonmanifold topology, but cells must
still form a valid complex: intersections are unions of lower-dimensional PLC
cells. "Arbitrary geometry" is therefore not equivalent to arbitrary triangle
soup.

## Robust Delaunay core

TetGen uses spatially sorted incremental insertion, stochastic-walk point
location, Bowyer-Watson cavities, filtered exact `orient3d` and `insphere`, and
symbolic perturbation for cospherical degeneracy. Its tetrahedron data structure
stores explicit neighbor, subface, and subsegment incidence, including exterior
dummy tetrahedra. This enables local transactions without reconstructing global
adjacency after every operation.

## Boundary recovery

For subdivisible constraints TetGen constructs a Steiner CDT. Strongly Delaunay
segments imply CDT existence without Steiner points; otherwise points are added
mainly on segments. Polygon insertion uses flips or cavity
retetrahedralization. Finite-precision non-coplanarity may still force polygon
Steiner points.

For strict constraint preservation, TetGen applies edge recovery, face recovery,
then Steiner-point suppression. For an edge `e`, it forms the set `F_e` of faces
whose interiors intersect `e`. It removes an intersecting face with a 2-3 flip,
or recursively removes the blocking edge with `flipnm`. Recovered constraints
are locked. Every accepted action monotonically reduces `|F_e|`; if recovery
fails, the constraint is split. Increasing recursion levels recover easy cases
first. This is qualitatively different from sampling an edge and running an
unconstrained global Delaunay again.

## Refinement, termination, and slivers

- Radius-edge `rho = R/L` is useful for Delaunay-refinement analysis but does
  not detect all slivers.
- Constrained Delaunay refinement terminates for `B >= 2`. Away from small PLC
  angles, tets satisfy the radius-edge bound.
- Near small angles, TetGen uses relaxed insertion radii. Unreasonably short
  edges are prevented from driving infinite refinement, so some skinny tets may
  remain, localized near the sharp feature.
- A minimum-dihedral request is empirical; the paper reports practical success
  up to roughly 20 degrees, not a theorem.
- An isotropic sizing field `H` is enforced by checking circumradius
  `r < H(c)` at tet circumcenter `c`.
- Final improvement is monotone hill climbing over the worst elements using
  flips, recursive edge removal, and smoothing. It can stop in local optima.

## Experiments and limitations

The paper compares Delaunay construction, boundary recovery, and output quality.
Most tested constraints are recovered at shallow recursion levels; few Steiner
points remain necessary. The author cautions that the comparisons are not
comprehensive. Open problems include certifying edge recovery/vertex deletion,
bounding optimal Steiner count, and proving nontrivial dihedral bounds.

## Evidence for Native Tet

- `face_recovery.py` never changes connectivity in its current implementation;
  it only calls a face recovered when three vertices already occur in one tet.
- `edge_recovery.py` generates midpoint/subdivision candidates. It has no
  intersecting-face set, recursive `flipnm`, protected-constraint locking, or
  monotone `|F_e|` transaction.
- `cdt_check.py` direct face/edge membership is a useful output metric, but it
  does not certify a CDT's visibility/local-Delaunay condition.
- Native input preprocessing targets watertight manifold surfaces, a stricter
  contract than TetGen's valid PLC contract. If generation proceeds after that
  gate fails, it needs an explicitly different soup semantics.

## Falsifiable implementation cards

### TET-CDT-1 - Real protected-complex recovery

- Add explicit subsegment/subface records and locks.
- For each missing edge, build `F_e`, try legal 2-3/3-2/recursive edge-removal
  transactions, and require monotone reduction before commit.
- Test: all PLC edges/faces recover on the paper's public examples or terminate
  with a typed blocker; no recovered constraint disappears later.

### TET-CDT-2 - CDT predicate audit

- Validate every unconstrained interior face as locally Delaunay using filtered
  exact `insphere`, with visibility across constraints.
- Test: a mesh with 100% input-edge presence but one deliberately non-CDT
  interior face must fail the CDT gate.

### TET-CDT-3 - Relaxed insertion radius

- Store `r_v` and relaxed `rr_v`; suppress refinement driven only by protected
  short edges near sharp features.
- Test: a 64-blade acute fan terminates at `B=2`, and every surviving skinny
  tet is incident to a tagged small-angle feature.

### TET-CDT-4 - Multi-metric monotone optimizer

- Rank worst tets by max dihedral/min dihedral/AMIPS, not only one proxy.
- Roll back any local transaction that worsens the current worst accepted
  metric, violates a constraint, or creates a nonpositive tet.
