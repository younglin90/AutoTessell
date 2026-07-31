# Tet SSS source-admission transaction — 2026-07-31

## Mechanism

The SSS relocation candidate now commits only when all predeclared contracts
hold independently:

- source component bijection;
- source-face provenance and zero unowned candidate faces;
- candidate full boundary validity and non-increasing inverted-tet debt;
- non-increasing same-side and ambiguous internal-face debt.

Failure returns the exact pre-relocation point/tet arrays.  No geometry repair,
threshold change, target-cell change, or writer override occurs.

## Sphere baseline and candidate

Fixture: `tests/benchmarks/sphere.stl`, target 2000, phase-B/phase-C/BSP/edge
recovery disabled.

| Metric | Pre-relocation | SSS candidate | Admission result |
| --- | ---: | ---: | --- |
| Source component bijective | true | false | reject |
| Source faces preserved | true | false | reject |
| Unowned candidate faces | 0 | 1280 | reject |
| Inverted tets | 350 | 352 | reject |
| Same-side internal faces | 116 | 108 | reject: source/inversion debt remains hard |

The exact rollback keeps final source faces preserved with zero missing or
unowned faces.  Final strict topology still has 108 same-side internal faces,
so it returns `success=false` and writes no polyMesh.  This is fail-closed,
not a validity claim.
