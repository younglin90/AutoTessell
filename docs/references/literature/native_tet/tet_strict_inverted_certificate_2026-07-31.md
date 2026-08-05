# Exact Inverted-Tetrahedron Strict Certificate

Date: 2026-07-31

Card: `TET-STRICT-INVERTED-CERT-1`

Status: `L2_TARGET_PASS`; campaign-level L3 and promotion remain pending.
Target-cell tracking is explicitly deferred behind topology and validity.

## Defect and fixed acceptance

The final source-aware certificate checked closed-manifold boundary topology,
duplicate/degenerate tetrahedra, and exact source-component provenance, but it
did not report tetrahedron orientation.  Reversing two vertices of an otherwise
valid tetrahedron therefore left every existing topology and provenance field
unchanged and produced a false `valid=True` certificate.

The pre-edit baselines were:

- one-tet L0: exact public orientation sign `-1`, yet source topology valid;
- generated sphere with one of 1,631 tetrahedra inverted: boundary valid,
  component bijective, and source topology valid;
- 48,000-tet structured audit median: 0.037465 seconds over 31 timed runs on
  the frozen local environment.

Acceptance was declared before implementation:

- false certifications on the positive/inverted L0 pair change from one to
  zero;
- a generated sphere with one inverted tetrahedron rejects without repair;
- the unmodified sphere remains byte-identical and valid;
- all existing boundary, component, provenance, duplicate, degenerate, open,
  and non-manifold reports remain unchanged;
- the native and fallback reports agree, including a near-degenerate pair;
- the 48,000-tet native audit runtime may increase by at most 10%;
- no mesh mutation, threshold change, target-cell change, or silent fallback.

## Research and provenance

- Bruno Levy, *Exact Predicates, Exact Constructions and Combinatorics for Mesh
  CSG*, ACM Transactions on Graphics (2025), DOI `10.1145/3744642`.  The DOI
  publisher endpoint returned HTTP 403, but the full author preprint was
  accessible as arXiv `2405.12949`.  It motivates exact sign decisions near
  zero so combinatorial classification cannot contradict itself.
- CGAL 6.3 `Triangulation_3` defines positive cell orientation as part of local
  triangulation validity.  CGAL is GPL/reference-only here.
- WildMeshing Toolkit documents explicit invariants, rollback, and attribute
  protection.  Its public repository is MIT-licensed and was reviewed only for
  architecture and test strategy.

No source or generated output was copied.  The implementation composes the
project's existing first-party C++23 binding and existing exact orientation
predicate.  No dependency was added and `vendor/dependencies/` is unchanged.

## Mechanism

`audit_tet_boundary` now returns `n_inverted_tets`.  Its existing extended-
precision signed-volume computation supplies the ordinary sign at no extra
mesh traversal.  Tetrahedra already inside the existing scale-relative
degeneracy band are classified with the existing exact predicate.  Thus the
new count uses the same frozen degeneracy threshold and adds no threshold.

`TetBoundaryAudit.valid` requires the count to be zero.  The final
`audit_source_topology` certificate consequently fails closed if the normal
orientation pass is disabled or throws.  Intermediate duplicate cleanup and
metric topology transactions retain their pre-orientation connectivity-only
contracts; the new gate does not change their mesh candidates.

## Evidence

- L0 positive tetrahedron: valid, `n_inverted_tets=0`.
- L0 reversed tetrahedron: invalid, `n_inverted_tets=1`, input unchanged.
- Near-degenerate `1e-18` positive/reversed pair: native and Python reports
  match exactly; reversed count is one.
- Generated sphere: 669 points, 1,631 tetrahedra, zero inverted cells, valid
  source topology, exact point/connectivity SHA-256
  `a87a55050628cf6987b0479cd35ed6b541dbbb52ce3cd94c5d92ee545f42082a`.
- Same sphere with only the first tetrahedron order reversed: one inverted
  cell, boundary/component counts unchanged, component bijective, final
  certificate rejected.
- 48,000-tet structured audit median: 0.039763 seconds versus 0.037465 seconds,
  a 6.14% increase, within the frozen 10% cap.
- Fresh GCC 13.3 C++23 Release build passed at `-j1`; the first-party target
  emitted no warning under the project's warnings-as-errors contract.
- Focused boundary/predicate/component/transaction/final-checkpoint/P4C-shape
  suites: 75 passed, 3 explicit unavailable-fTetWild/P4 skips.

The card changes certification and reporting only.  It does not rewrite an
inverted tetrahedron, weaken source shape/topology/provenance, or claim
target-cell closure.
