# Reberol et al. — *All-hexahedral boundary layer meshing* (2021)

## Access and scope

- Status: FULL_READ, 17-page 2021 preprint; journal version published in 2023.
- Authors: Maxence Reberol, Kilian Verhetsel, Francois Henrotte, David Bommes,
  Jean-Francois Remacle.
- Public source: `https://raw.githubusercontent.com/mxncr/mxncr.github.io/master/pdf/hexbl_2021.pdf`
- DOI: `10.1145/3577196`, confirmed by the ACM/AlgoHex publication page.

The method begins with a watertight all-quad (or practical quad-dominant)
surface and creates a **single** all-hex boundary layer. It keeps the boundary
fixed while untangling/smoothing interior layer vertices. It is not an octree
surface-snapping method and does not solve the arbitrary all-hex core.

## Relevant evidence

- Page 1: boundary geometry is stated to be strictly respected; boundary-edge
  valences are selected by a global integer optimization based on local
  dihedral angles and preferences.
- Page 3: the pipeline computes ideal boundary valences, solves coupled local
  boundary-vertex configurations by branch-and-bound, glues them, then
  untangles geometry with the boundary fixed. It explicitly distinguishes this
  one-layer goal from complete constrained all-hex volume filling.
- Page 13: smooth regions admit simple extrusion, but ridge/corner topology is
  globally coupled. Pinched regions with irregular/highly distorted boundary
  quads can retain inverted elements after untangling.
- Page 13: even valid layer hexes can self-intersect across thin regions. The
  paper proposes reducing thickness as mitigation, but says its implementation
  does not yet handle this generally; convex feature curves may also need
  boundary-mesh refinement.

## AutoTessell interpretation

`HEX-EXACT-SOURCE-QUAD-SHELL-L1/L2` matches the paper's prerequisite only at
the surface level: our three-quads-per-triangle adapter produces a watertight,
source-exact quad surface. The centroid-scaled shell is not the paper's
algorithm. Its hard-bracket `390/1248` flips are consistent with the paper's
warning that feature/pinched cases require topology and geometry treatment,
not a global shrink factor.

No direct port is authorized yet. A future `HEX-BL-TOPOLOGY-OPT1` must first
be report-only and prove all of the following before creating cells:

1. authoritative ridge/corner provenance (the single-STL identity adapter is
   insufficient for CAD feature classification);
2. local configuration/valence feasibility around every feature vertex;
3. conservative local thickness and opposite-front collision certificate;
4. fixed-outer-boundary, interior-only untangling with positive-Jacobian
   rollback; and
5. exact source-quad identity after every accepted operation.

This paper does not remove the existing all-hex-core/interface blocker and
does not permit an approximate projection or sparse-grid writer route.
