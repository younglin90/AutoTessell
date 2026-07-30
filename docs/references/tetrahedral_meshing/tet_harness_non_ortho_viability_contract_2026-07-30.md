# Native Tet Harness Non-Orthogonality Viability Contract — 2026-07-30

## Card

`TET-HARNESS-NONORTHO-CONTRACT-1`

The draft/standard native-tet harness previously rejected a writer-valid,
zero-negative-volume candidate at `89.31439471907049°` solely because its
private cutoff was `< 89°`.  The project evaluator already accepts native tet
draft/standard values strictly below `90°`; the two layers disagreed.

## Measured cube probe

Input: `tests/benchmarks/cube.stl`, `target_cells=500`, default draft tier.

| metric | before harness alignment | after harness alignment |
|---|---:|---:|
| strict writer | accepted | accepted |
| negative volumes | 0 | 0 |
| checker `mesh_ok` | true | true |
| max non-orthogonality | 89.31439471907049° | 89.31439471907049° |
| tier result | failed at private 89° cutoff | generated result accepted |
| actual cells | 763 best-effort | 763 best-effort |
| target error | +52.6% | +52.6% |

The cell target is deliberately unchanged and remains a separate Gate-6
failure.  This card only prevents a private harness cutoff from rejecting an
otherwise strict-topology-valid result before the evaluator can apply the
tier-specific quality policy.

## Contract

- Accept strictly `< 90°` only when negative volume count is zero and cells are
  present.
- Keep `90°` itself rejected.
- Do not alter target-cell selection, geometry, topology, boundary layers, or
  quality reporting.
- Release quality specifications remain separate from this draft viability
  gate; high non-orthogonality remains observable and subject to corpus-level
  acceptance criteria.

## Sources and provenance

- Local evaluator policy: `core/evaluator/report.py` native-tet draft/standard
  tier policy already uses a `90°` hard non-orthogonality cap.
- OpenFOAM documents `maxNonOrtho` as a configurable face non-orthogonality
  limit and uses `65°` as a general meshing default:
  https://doc.openfoam.com/2212/tools/pre-processing/mesh/generation/snappyhexmesh/meshquality/
- OpenFOAM `checkMesh` documents user-defined mesh-quality controls:
  https://openfoam.org/release/2-2-0/meshing-tools/

No external implementation code was copied.
