# POLY-PRIMAL-CONFORMAL-AUDIT1 Evidence

Date: 2026-07-31

Pre-card base: `3534c748208c4546c378c3a1561f0e14593bd603`

Scope: reject a non-conformal tetrahedral primal before Poly dual construction.
No point, face, patch, target-cell, boundary-layer, quality threshold, route, or
`third_party/` change.

## Hypothesis and acceptance

Garimella, Kim, and Berndt require a valid conformal tetrahedral primal: the
intersection of two elements is a complete vertex, edge, or face.  A repeated
canonical tetrahedron or a triangular face owned by more than two tetrahedra
violates that prerequisite and makes one-owner/two-owner dual adjacency
undefined.

Primary metric: false-success runs on a frozen three-owner-face primal.

- Baseline: `3/3` false successes, each reporting `6` cells, `30` faces, and
  zero star-invalid cells/subtetrahedra.
- Acceptance: `0/3` false successes and zero output artifacts.
- Rollback: any valid classified bipyramid byte or patch-provenance change.

Orientation is deliberately not a hard rejection in this card.  Negative
primal orientation is returned as a deterministic census only.  Existing zero
volume rejection remains a validity hard gate.

## Baseline false certification

All baseline runs wrote `points`, `faces`, `owner`, `neighbour`, and `boundary`.
Their hashes were deterministic:

- `points`: `f620066b59debe9aa8feef42eb57328761362452be8f042882bcdebbfde7b4f2`
- `faces`: `8fe957a00dc32a04ff3b96392fc0dab97cd5f366dc7bce6252265af6bff1a37c`
- `owner`: `624a5be9b51072c93a130990fdb4a2045c66113507a4a87a4746591b2d2cf3b7`
- `neighbour`: `e42f750949805e8fd875b7f7184f86e269d266f9176638881d3949209ea80e5a`
- `boundary`: `5afff3552212019431dd8ea0c37c5b26c26b236d2c234aaaff0ebdcb842dedda`

The deterministic bytes do not make the result valid: the primal face
`(0, 1, 2)` has owners `(0, 1, 2)`, so OpenFOAM owner/neighbour semantics cannot
represent the primal incidence faithfully.

## Independent C++23 mechanism

`native_polymesh.audit_tet_primal_conformity` accepts only exact contiguous
`float64` points and `int64` tetrahedra.  It creates one contiguous canonical
tetrahedron record array and one contiguous `4M` face-record array, sorts each
lexicographically, and scans equal-key runs.  Duplicate tetrahedra and
faces with more than two owners are returned with sorted exact provenance.
Negative-orientation row ids are returned separately and do not affect the
conformity decision.

Complexity is `O(M log M)` time and `O(M)` auxiliary memory.  There are no
per-face heap allocations or hash-table order dependencies in the hot scan.
The GIL is released only after strict ABI validation.  Python retains an
independent sort/run oracle.  A malformed present native result raises instead
of silently falling back.

The exact native build contract now includes the new public symbol.

## Result

- Three-owner-face primal: `3/3` explicit deterministic refusals; artifact
  count `0`.
- Duplicate canonical tetrahedron: `3/3` explicit deterministic refusals;
  artifact count `0`.
- Negative-orientation single tetrahedron: census `(0,)`, conformal `true`,
  generation still succeeds.
- Valid classified bipyramid: `3/3` success with exact existing patch order and
  the five pre-card hashes:
  `fdab8bddd008ad6fc003427a6a153c4ae4898ddb540dee684cc2be2134a25957`,
  `e34a8b7e92d198a658ef33227d71ecbba55dba2c9c8ebd66c9db16fa297c854c`,
  `2f3f3f3e97e28db3e2c4ad74ec0b55690bb399ab97098b15d97172ae488873ca`,
  `8d80df3c7b13898717eb271b3913d3e577179c3f85e9441418159002f9374873`,
  `d29e59ca7dede8b5d1b3ecd5e7858923ab3e5ca459dafcf1d8b2ebd0281d88c0`.
- Input point/connectivity arrays remain byte-identical.

On `50,000` independent tetrahedra, alternating-order five-run medians are:

- Python oracle: `0.435978 s`
- Native C++23: `0.011680 s`
- Speedup: `37.33x`
- Exact audit parity: pass

The measurement command is:

```bash
AUTOTESSELL_EXT_BUILD_DIR=/tmp/autotessell-poly33-conformal PYTHONPATH=. \
python scripts/benchmark_native_poly_primal_conformity.py --tets 50000 --repeat 5
```

## Sources and license boundary

- Garimella, Kim, and Berndt, *Polyhedral Mesh Generation and Optimization for
  Non-manifold Domains* (2013), DOI
  `10.1007/978-3-319-02335-9_18`: dual construction starts from a valid conformal
  mesh and preserves only the topology present in that primal.
- [CGAL 6.2 Tetrahedral Remeshing manual](https://doc.cgal.org/latest/Tetrahedral_remeshing/index.html):
  imported tetrahedral meshes must satisfy valid connectivity; positive
  orientation is documented but remains diagnostic here pending a separate
  product convention audit.
- [CGAL/cgal](https://github.com/CGAL/cgal) and
  [libigl/libigl](https://github.com/libigl/libigl) were inspected as active C++
  reference implementations.  Their code and dependencies were not copied or
  added.

The implementation is first-party and independently authored.  No external
code, generated artifact, or dependency was reused.

## Verification

Fresh isolated GCC 13.3 Release build completed without a compiler warning.
Focused shape/topology/provenance/native parity validation:

```text
26 passed in 2.66s
```

The wider bounded Poly/build-contract set produced `67 passed, 1 failed`.  The
single failure is
`tests/test_native_poly_harness_edge.py::test_best_candidate_tracking_keeps_better_iter`.
It reproduces unchanged on immutable pre-card `3534c748`: the Cycle-32 Tet
source-component bijection rejects both harness primals with
`n_missing_source_vertices=35`, so the old test's expected best-case polyMesh
never exists.  This card does not alter or hide that cross-lane integration
regression.  Full L3 remains unverified.

`black --check`, `ruff check`, focused-test/script strict `mypy`, native build
contract tests, and `git diff --check` pass.  The pre-existing full `dual.py`
strict-mypy baseline still reports 17 unrelated errors; this card adds none.

Verification state: `L2_TARGET_PASS`; promotion remains pending advisor review
of the known cross-lane regression.
