# Metric-Sweep Source-Topology Transaction

Date: 2026-07-31

Card: `TET-METRIC-SOURCE-TOPOLOGY-TXN-1`

## Defect and hypothesis

The native Tet metric sweep can improve its quality metric while producing a
candidate whose exposed boundary is not a 2-manifold.  The frozen sphere route
accepted such a candidate internally, then the final source-aware gate rejected
it with 2,924 non-manifold boundary edges.  The source component bijection still
passed, so relaxing the final topology gate would hide a real connectivity
defect.

The hypothesis is narrower: treat the metric sweep as a transaction and commit
its distinct candidate arrays only when the existing C++23-backed local
boundary audit and exact source-component certificate both pass.  A rejection
returns the exact pre-sweep arrays.  No repair, projection, target-cell change,
or quality-threshold change is allowed.

## Predeclared acceptance

- Primary: frozen sphere native-Tet false failure changes from one to zero.
- The rejected metric candidate reports at least one concrete topology defect.
- The final sphere boundary has zero open and non-manifold edges, preserves all
  642 source vertices and the single source component, and writes no invalid
  intermediate artifact.
- Valid, non-manifold-boundary, unanchored-component, and malformed candidates
  have deterministic commit or exact rollback behavior.
- Existing strict-topology and source-component tests do not regress.

## Research basis and provenance

- CGAL 6.3 Tetrahedral Remeshing documents topology-preserving atomic split,
  collapse, flip, relocation, and reprojection rules.  Official documentation:
  <https://doc.cgal.org/latest/Tetrahedral_remeshing/index.html>.
- WildMeshing Toolkit documents rollback and attribute protection as the means
  to preserve topology and geometry across discrete operations.  Official
  repository: <https://github.com/wildmeshing/wildmeshing-toolkit>.
- Hu et al., *Fast Tetrahedral Meshing in the Wild*, ACM TOG 2020, describes
  maintaining a valid floating-point tetrahedral mesh throughout optimization.
  DOI: `10.1145/3386569.3392385`.

CGAL and WildMeshing code are reference-only.  No external code or dependency
is copied.  The implementation composes existing first-party audits and keeps
`third_party/` unchanged.

## Baseline and observed transaction

- Source sphere: 642 vertices, 1,280 triangles, one component.
- Baseline final candidate: 2,193 points, 4,811 tets, 9,160 boundary faces,
  2,924 non-manifold boundary edges, component bijection true, result false.
- Transaction run: the metric candidate is rejected with
  `local_boundary_invalid`; the exact pre-sweep mesh continues with 669 points,
  1,631 tets, 1,280 boundary faces, and the downstream Poly dual fixture passes.

The target-cell objective remains deferred behind topology and validity.

## Validation evidence

- Focused transaction, final strict-topology, and source-component suites:
  36 passed, 1 skipped.
- Frozen sphere repeated three times: 669 points and 1,631 tets every run.
- Final topology every run: zero open edges, zero non-manifold edges, source
  component bijection true.
- Final validity every run: zero negative-volume and zero zero-volume tets.
- Combined point/connectivity SHA-256 every run:
  `a87a55050628cf6987b0479cd35ed6b541dbbb52ce3cd94c5d92ee545f42082a`.
- End-to-end generation times were 3.737791 s, 4.972994 s, and 2.318510 s;
  timing was observed, not used as this correctness card's acceptance metric.
