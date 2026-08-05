# Tet source-facet provenance certificate (Cycle 38)

## Card

`TET-SOURCE-FACET-PROVENANCE-1`

Promotion target: `RUNTIME_READY`, subject to integration validation.  The
card changes only the existing fail-closed source-topology decision and its
evidence.  It never moves a point, rewrites connectivity, changes routing, or
changes target-cell or boundary-layer policy.

## Baseline defect

A five-vertex warped pyramid has two locally valid tetrahedralizations.  The
source base uses diagonal `(0, 2)`; the adverse candidate uses `(1, 3)`.  Both
candidate tets have positive volume.  Its boundary is closed and manifold,
all five source vertices remain exact, and the source/output component map is
bijective.  The replacement nevertheless changes two non-coplanar input
facets.  Before this card, `audit_source_topology.valid` incorrectly returned
`true` and did not measure missing source facets.

An exact-triangle-only certificate closed that defect but was killed before
promotion.  Existing native outputs legally subdivide or re-triangulate a
planar input patch, so exact triangle identity rejected the cube and did not
express replacement-facet ownership.  None of that exact-only candidate was
committed.

## Amended hypothesis and fixed acceptance

Hypothesis: source triangles may be replaced only when an independent audit
proves complete ownership of one edge-connected coplanar source patch.  Exact
face identity remains the fast path.  A replacement path must prove all of:

- every candidate boundary triangle has exactly one source-patch owner;
- its full triangle, not only vertices or centroid, lies inside that patch;
- non-convex boundaries and holes are not crossed or covered;
- candidate triangles have zero positive-area overlap;
- source and candidate patch boundaries cover each other bidirectionally;
- accumulated candidate and source patch areas agree;
- every source patch has owned output;
- component, local manifold, duplicate, degeneracy, and inversion contracts
  remain unchanged.

Primary metric: warped-diagonal false certification `1 -> 0`, with exactly two
missing exact facets.  Acceptance was frozen before the amended implementation:

- exact warped source valid; warped diagonal replacement invalid;
- planar diagonal replacement valid only through complete patch ownership;
- non-convex shortcut, hole cover, gap, and overlap fixtures invalid;
- point, face, and tet permutations preserve the complete report;
- C++23 and independent Python reports match;
- malformed native reports fail closed without Python fallback;
- cube strict-topology regression remains valid;
- known cylinder off-surface output becomes an explicit deterministic failure
  before writer invocation; it must not be hidden by tolerance relaxation;
- 52,192-tet audit median and peak RSS regress by at most `15%`;
- no `vendor/dependencies/` change and no output-geometry repair.

## Frozen numeric policy

Coordinates are translated and normalized by the source bounding-box diagonal
before certification.  Frozen binary64 factors:

- point-to-plane distance: `256 * epsilon`;
- unit-normal comparison: `1024 * epsilon`;
- projected orientation/area: `8192 * epsilon`;
- whole-patch area: `8192 * epsilon * (source faces + candidate faces)`.

Thresholds were not changed after observing results.  Candidate edge
containment is interval-certified: intersections with every patch boundary
split the edge, then every open interval midpoint must lie in the source
triangle union.  A boundary-vertex-in-triangle test separately prevents a
candidate triangle from covering a hole or concavity.  Pairwise overlap,
bidirectional feature-boundary coverage, and total area close remaining gaps.

## Literature and public implementations

- Diazzi, Panozzo, Vaxman, and Attene, *Constrained Delaunay
  Tetrahedrization: A Robust and Practical Approach*, ACM TOG 42(6), 2023,
  DOI `10.1145/3618352`.  Full arXiv text accessible.  PLC faces are explicit
  constraints and swaps do not cross constrained facets.
- CGAL 6.2, *3D Constrained Triangulations*.  Official documentation maps
  constrained facets to input PLC face IDs.  CGAL is GPL/commercial and was
  used as reference only.
- `MarcoAttene/CDT`, public reference implementation for Diazzi et al.  Its
  GPL/LGPL build choices are incompatible with a future MIT native core.  No
  code was copied.
- Osman, Vink, Jalba, and Chamberland, *Connectivity-Preserving Cortical
  Surface Tetrahedralization*, arXiv `2512.08450`, 2025.  Accessible preprint;
  supports explicit surface-connectivity evidence.

Inaccessible DOI: none.

## Provenance

Implementation is independent first-party C++23 plus an independent Python
oracle.  It uses only existing exact coordinate provenance and boundary-face
incidence.  No external source, generated output, dependency, or
`vendor/dependencies/` file was copied or modified.

## Results

- Warped diagonal: local boundary valid and component bijective, but source
  facet certificate changes `true -> false`; missing exact facets `2`.
- Planar diagonal: six candidate boundary faces owned, unowned `0`, uncovered
  patches `0`, area mismatches `0`, feature mismatches `0`, overlap pairs `0`;
  certificate valid.
- Non-convex shortcut, hole cover, gap, and overlap adverse fixtures all fail
  closed.  Point/face/tet permutation and native/Python parity pass.
- Cylinder exposes a pre-existing source-shape defect rather than relaxing it:
  candidate boundary faces `216`, owned `119`, unowned `97`, area-mismatch
  patches `2`, feature-boundary mismatches `2`, new boundary vertices `44`.
  Normalized no-source-plane distances span `4.40e-4..1.94e-1`; prior metrics
  also report Hausdorff relative `0.05631` and plane coverage `0.824`.  Three
  runs produce identical arrays/reports, return failure, and write zero
  `polyMesh` artifacts.  Stable point SHA-256 is
  `96f0ebd968dd7bdc19e3d222a215a36005643891d6432612230f648efedec95d`;
  tet SHA-256 is
  `0289f12f38728c81c1722326295450f40d5b4b07c289c947fd173ba79394505c`.
  A separate generator surface-conformance repair card is required.
- Fresh GCC 13.3 C++23 `-Werror` build passes.  Focused native extension,
  component, metric transaction, and provenance suites: `73 passed`, including
  four mixed-scale/translation cases.  Cube L0 strict-topology regression and
  three-run cylinder fail-closed regression also pass (`75` combined).
- 32-copy benchmark: `20,544` source points, `21,408` candidate points,
  `52,192` tets, 31-run median `0.036456 s`, peak RSS `115,072 KiB`.  Against
  Cycle-37 evidence `0.039763 s` and Cycle-36 RSS `113,808 KiB`, changes are
  `-8.32%` runtime and `+1.11%` RSS, inside fixed budgets.
