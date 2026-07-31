# Tet strict same-side connectivity transaction — 2026-07-31

## Hypothesis

Sphere final candidate retained exact source boundary while 108 internal faces
had both opposite apexes on one side.  These are real overlap debts, not a
tolerance relaxation case.  Rebuilding only tetrahedral connectivity over the
unchanged coordinates can remove that overlap without moving input geometry.

This uses the project’s existing SciPy/Qhull Delaunay dependency as a
candidate generator.  It is an independent transaction, not copied external
mesher implementation.  Delaunay refinement context: Shewchuk 1998, DOI
`10.1007/PL00009359`; project note:
`shewchuk1998_delaunay_refinement.md`.

## Admission contract

Promotion: `L1_PASS / EXPERIMENTAL_KEEP`.  Runtime transaction is default OFF;
only `AUTO_TESSELL_TET_SAME_SIDE_RETRIANGULATION=1` enables it.  Unset or any
other value preserves prior strict rejection and emits no transaction artifact.

Candidate commits only when all hold:

- source component bijection;
- source faces preserved; zero unowned candidate boundary faces;
- open/non-manifold/duplicate/degenerate/inverted/ambiguous debts do not
  increase;
- same-side internal-face debt strictly decreases.

Any exception or failed predicate returns original point and tet arrays.  No
source coordinate moves, target-cell override, topology threshold relaxation,
or writer bypass exists.

## Representative evidence

Fixture: `tests/benchmarks/sphere.stl`; requested target 2000; phase-B,
phase-C, BSP insertion, and edge recovery disabled.

| Metric | Before | Candidate | Result |
| --- | ---: | ---: | --- |
| Cells | 2166 | 2227 | accepted; target secondary |
| Source component bijection | true | true | pass |
| Source faces preserved | true | true | pass |
| Unowned candidate faces | 0 | 0 | pass |
| Inverted tets | 0 | 0 | pass |
| Ambiguous internal faces | 0 | 0 | pass |
| Same-side internal faces | 108 | 0 | pass |

Final strict source topology is valid; writer emits polyMesh; `success=true`.
The earlier SSS surface-relocation candidate remains independently rejected:
it loses source ownership.  This repair changes only connectivity after that
exact rollback.
