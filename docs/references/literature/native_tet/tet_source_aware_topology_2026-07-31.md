# TET-SOURCE-AWARE-STRICT-TOPOLOGY-1

Date: 2026-07-31

Status: `L2_PASS`; promotion pending campaign-level L3 regression. This card
does not claim target-cell closure or complete native-tet release readiness.

## Question and frozen acceptance

The standalone `TetBoundaryAudit.valid` required exactly one boundary
component. That rejects a locally valid tetrahedral mesh containing two or more
disconnected bodies, even when the output has an exact one-to-one source
component mapping. The primary metric was therefore false rejection count on
valid disconnected inputs: `1 -> 0` for the frozen two-body case.

Acceptance was declared before implementation:

- one or more closed, locally manifold boundary components are locally valid;
- source-aware production acceptance additionally requires an exact bijection
  between source and candidate boundary components;
- lost, merged, split, unanchored, open, non-manifold, duplicate, and
  degenerate candidates remain rejected;
- source coordinates, faces, candidate topology, routing, and target-cell
  policy are not weakened or approximated;
- external reordered P4C candidates are never rewritten.

## Primary and open-code review

- CGAL 6.2 Mesh_3 reference manual states that a meshed region may be connected
  or composed of multiple components and subdomains. This directly falsifies a
  universal one-component validity rule:
  <https://doc.cgal.org/latest/Mesh_3/group__PkgMesh3Ref.html>.
- CGAL `Polyhedral_mesh_domain_3` requires at least one closed connected
  component but permits additional components inside it:
  <https://doc.cgal.org/latest/Mesh_3/classCGAL_1_1Polyhedral__mesh__domain__3.html>.
- The TetGen 1.5 manual defines a tetrahedral mesh of a PLC by equality of the
  represented domain and by representation of each PLC segment/facet as mesh
  edges/faces. It explicitly permits boundary refinement with Steiner points;
  it does not make global one-component cardinality a validity axiom:
  <https://wias-berlin.de/software/tetgen/1.5/doc/manual/manual.html>.
- The current CGAL Mesh_3 GitHub tree was inspected only for public architecture
  and test organization: <https://github.com/CGAL/cgal/tree/main/Mesh_3>.
  CGAL Mesh_3 is GPL-licensed. No implementation or test code was copied and no
  dependency was added.

No paper required for this card was inaccessible. Existing full-read TetGen/Si
notes in this repository remain the algorithmic evidence; this card changes a
local acceptance interpretation, not tetrahedralization.

## Mechanism

`SourceTopologyAudit` is a thin Python composite over the existing first-party
C++23 `audit_tet_boundary` and `audit_source_component_bijection` kernels. It is
valid only when:

1. every candidate boundary component is locally closed and manifold, with no
   duplicate or degenerate tetrahedron; and
2. source and candidate components form an exact coordinate-provenance
   bijection.

`TetBoundaryAudit.valid` now requires `n_boundary_components > 0`, not `== 1`.
P4C, explicit fTetWild-loop, and final native-tet acceptance use the composite
certificate, so the local relaxation cannot admit a lost, merged, split, or
invented source component.

The explicit fTetWild route returns a failed result before the writer when the
composite certificate fails. It does not emit a partial `polyMesh`.

## Roundoff diagnosis and bounded restoration

The Cycle-32 exact coordinate-provenance audit exposed a pre-existing sphere
path failure in the native-poly harness. The candidate retained all `42` source
prefix ids on its `80` boundary faces, and boundary keys and area were
unchanged, but `35` source coordinates differed by `4.63e-18 .. 1.57e-16`.
Exact coordinate matching therefore reported `35` missing source vertices.

The audit itself remains exact. The native-only path now restores original
source-surface prefix coordinate bits before final certification only when:

- P4C did not rewrite or reorder the candidate;
- every source surface id remains a candidate boundary id; and
- every coordinate delta is at most
  `32 * epsilon(float64) * max(bbox_diagonal, max_abs_coordinate, tiny)`.

Any missing boundary id, meaningful displacement, malformed input, or unknown
ordering leaves the candidate unchanged; the exact composite audit then fails
closed. The transaction records reason, restored vertex count, maximum delta,
and cap.

## Evidence

- source-aware focused suite plus existing P4C/rescue tests:
  `59 passed` with the isolated native C++23 predicate extension;
- wider component, predicate, P4C, rescue, final-checkpoint, result-consistency,
  fTetWild-worker, and native-poly harness suite: `70 passed, 3 skipped`;
  skips are the unavailable vendored fTetWild extension and two explicit slow
  P4C end-to-end gates;
- valid disconnected component counts `1`, `2`, and `5` pass three identical
  audits with input bytes unchanged;
- malformed open/non-manifold fixture reports exactly `open=1`,
  `nonmanifold_edges=2`, `nonmanifold_faces=1` and rejects;
- duplicate and lost-source fixtures reject;
- explicit invalid fTetWild candidate performs zero writer calls and leaves no
  `constant/polyMesh` artifact;
- native-poly sphere best-candidate regression again writes its expected mesh;
- meaningful `1e-8` source motion and an interiorized source vertex are not
  restored;
- signed-zero coordinate bits are detected and restored despite zero numeric
  delta; huge finite coordinates retain a finite cap, while a cap overflow is
  rejected before multiplication; tiny normal-scale coordinates remain
  warning-free under warnings-as-errors;
- isolated `native_tet_predicates` Release build succeeds with GCC 13.3,
  C++23, `-Wall -Wextra -Wpedantic -Werror`;
- strict isolated type check and focused Ruff/bytecode checks pass;
- target cell count and boundary-layer behavior are unchanged.

The composite adds no native ABI and no external code. `vendor/dependencies/` is
unchanged. Future MIT-core eligibility is preserved.
