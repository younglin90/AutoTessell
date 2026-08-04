# Literature review — native-all-production-gate-068

## Question

native-all-production-gate-068

## Sources read

-

## Equations or mechanisms adopted

-

## Rejected assumptions

-

## Planner-reviewed primary and public-code sources

- CGAL `cgal` v6.2, commit `cac3e9d75e254928db0e38a3161564216cb01919`, Mesh_3 GPL-3.0-or-later/commercial: planner read `Mesh_3/include/CGAL/exude_mesh_3.h`, `sliver_criteria.h`, `Slivers_exuder.h`, and unit/determinism tests. Transfer only star-local monotone minimum-dihedral acceptance and serialized-repeat principles; no code or dependency.
- Gmsh `gmsh_4_14_0`, commit `8425b99f055c905f8986878b272c3652c53d7341`, GPL-2.0-or-later with exception: planner read `src/mesh/BoundaryLayers.cpp` and `examples/api/naca_boundary_layer_3d.py`. Transfer cumulative layer scheduling and separation of front/outer fill; no code.
- TetGen manual v1.4, Hang Si (2006): use robust orientation/insphere and boundary recovery; `R/l_min` alone is rejected because it misses slivers.
- Edelsbrunner & Guoy (2002), accessible full paper: boundary-adjacent slivers can remain after exudation, so wall quality is an independent gate.
- Fidkowski, DOI `10.2514/1.J064644`, author preprint: metric-front/validity ideas are useful, but the reported implementation is 2-D and is not evidence for 3-D release.
- Code references were planner-reviewed at the exact snapshots above; no source was copied and no GPL dependency will be introduced.

## Rejected transfer assumptions

- BL=0 is not a zero-cell identity shortcut; it must yield a persisted volume artifact.
- XDE names/colors/layers/assembly display metadata are not physical-group authority.
- A Python parse followed by native metrics is not an independent disk reread.
- The existing 8×19 inventory is not a release corpus until authoritative maps and fresh-process replays exist.
