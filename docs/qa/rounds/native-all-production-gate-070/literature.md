# Literature and public-code review — round 070

## Sources read

- Shewchuk, *What Is a Good Linear Element?*,
  `https://people.eecs.berkeley.edu/~jrs/papers/elem.pdf` (2002). Use a
  metric family: topology/positive measure, shape/angle, and CFD-relevant
  quality must be independently recorded; no single scalar is sufficient.
- CGAL commit
  `cac3e9d75e254928db0e38a3161564216cb01919`, including `exude_mesh_3.h`
  and `Slivers_exuder.h`. Transfer explicit target quality and deterministic
  termination/receipt ideas only. GPL-3.0-or-later/commercial; no code or
  dependency is copied.
- OpenFOAM-13 commit
  `18870c24d21c6b982e2cdec27b2f59738cca5f90`, including `polyMesh.H` and
  `checkMesh.C`. Transfer the persisted `points/faces/owner/neighbour/
  boundary` audit boundary and separate topology/geometry thresholds. GPL-3;
  no code or linkage is copied.

## Equations or mechanisms adopted

The live producer must seal a source/config/build contract, fsync the staged
tree, and be checked by a fresh child that receives paths and receipts only.
The destination is reread after atomic publish. Raw-tree and semantic
digests must agree across stage, destination, and three replays. User
parameters retain requested/effective/origin values. BL=0 is identity; BL>=1
is refused without a writer-owned exact schedule and persisted geometry.

## Deliberately not transferred

Shared serialization is not treated as a shared validator for Hex/Poly/Tri/
Quad. CGAL/OpenFOAM code is not copied. Fixture-written tetrahedra and
synthetic receipts are not production CAD/STL evidence. Gmsh and the
Edelsbrunner work were located but not read sufficiently in this pass and
are not claimed as reviewed sources.
