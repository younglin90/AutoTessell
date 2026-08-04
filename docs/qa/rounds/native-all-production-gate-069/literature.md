# Literature and public-code review — round 069

## Planner-reviewed sources

- J. R. Shewchuk, *What Is a Good Linear Element? Interpolation,
  Conditioning, and Quality Measures*,
  `https://people.eecs.berkeley.edu/~jrs/papers/elemj.pdf`. Use the
  metric-family view: no single scalar is sufficient. Recompute positive
  measure/Jacobian and shape/angle-related metrics independently; do not
  make radius-edge alone the release gate.
- TetGen v1.4.1 manual,
  `https://web.mit.edu/tetgen_v1.4.1/tetgen-manual.pdf`. Use explicit PLC,
  input/output, and consistency checks as the model for a sealed source and
  persisted-output certificate. Do not copy TetGen code or use its
  radius-edge criterion as the sole quality test.
- CGAL 6.2, commit
  `cac3e9d75e254928db0e38a3161564216cb01919`; reviewed Mesh_3
  `exude_mesh_3.h`, `Slivers_exuder.h`, `sliver_criteria.h`, and deterministic
  serialization tests. Transfer explicit quality targets, repeatability,
  and deterministic serialization. CGAL Mesh_3 is GPL-3.0/commercial; no
  code or dependency is copied.
- OpenFOAM 13 snapshot, commit
  `18870c24d21c6b982e2cdec27b2f59738cca5f90`; reviewed `polyMesh.H`,
  `polyMeshUpdate.C`, `checkMesh.C`, and `checkMeshQuality.C`. Transfer the
  persisted-file and face-set audit idea. OpenFOAM is GPL-3; no code is
  copied.

## Design consequences

The sources support a layered contract: source authority and topology first;
then independently recomputed positive measure and a family of quality
metrics; then BL geometry and schedule; counts last. The persisted
`points/faces/owner/neighbour/boundary` tree is the evidence boundary, not an
in-memory mesh object. A fresh child process is required because a same-
process reader can accidentally reuse producer state. Engine-specific
validators are required because a Tet, Hex, polygonal volume, triangular
surface, and mixed Tri+Quad surface have different admissible topology.

## Relevant code review not treated as authority

The planner located Gmsh source and the Edelsbrunner work, but did not read
enough of them in this pass to claim a reviewed method. They remain
follow-up references, not acceptance evidence. The user-supplied Fidkowski
and Aubry PDFs are retained in the project research archive for later
boundary-layer design work; this round's persisted-output card does not
infer production readiness from them.
