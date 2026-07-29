# TET-THIN-SECTION-1 — report-only census result

Status: `L0_PASS / CORRECTNESS_KEEP`. The implementation is disconnected from
generation, routing, acceptance, and mesh mutation.

The diagnostic casts deterministic inward rays from each non-degenerate
boundary triangle. For every confirmed opposing-boundary hit it reports both
the distance and the count of tetrahedra with non-zero ray overlap before that
hit. Missing or ambiguous hits remain `unknown`; no thickness is guessed.

## L0 synthetic fixtures

- A 5-tetrahedron box at height `0.05` reports a minimum thickness in
  `[0.049999, 0.050001]`, with at least one traversed tetrahedron per hit.
- The same box produces byte-identical report dictionaries on repeated calls.
- A single-tetrahedron/open calibration mesh reports four unknown rays and no
  thickness or through-thickness-cell estimate.

## L1 calibration measurement

Command:

```bash
python3 scripts/diag_native_tet_thin_section.py tests/benchmarks/cube.stl
```

The Delaunay calibration primal of `cube.stl` has 6 tetrahedra and 12 boundary
faces. All 12 rays hit; min/median/max thickness is `0.9999999986`, and
min/median/max through-thickness count is `3/3.0/3`. This calibration is not a
native-tet production result and does not authorize a generation change.

## L2 native-primal measurements

Command (the environment switch prevents the optional P4C external rescue so
the diagnostic observes the native route itself):

```bash
AUTO_TESSELL_P4C_PYTETWILD=0 \
  python3 scripts/diag_native_tet_thin_section.py --native-primal --target-cells 2000 \
  tests/benchmarks/very_thin_disk_0_01mm.stl \
  tests/benchmarks/extreme_aspect_ratio_needle.stl
```

| fixture | primal tets | ray hit fraction | p10 thickness | p10 cells | minimum cells |
| --- | ---: | ---: | ---: | ---: | ---: |
| very thin disk | 2,960 | 0.4320 | 0.0100000 | 4.0 | 2 |
| extreme needle | 89 | 1.0000 | 0.0184776 | 5.0 | 5 |

The disk's large unknown-ray fraction is reported conservatively rather than
filled with a nearest-surface estimate. The needle has zero interior seeds and
only 89 cells despite a target of 2,000, so these counts are diagnostic
coverage only, not evidence that the cell-budget contract was met.

For `naca0012.stl`, the pure native route fails closed before measurement:
the written polyMesh has three cells with a vertex count other than four. The
diagnostic intentionally refuses to drop those cells and measure a partial
primal. The optional P4C-rescued route did produce an all-tet 1,790-cell mesh,
but it is not evidence for the native-only card.

## TET-WRITER-TOPOLOGY-1 — NACA written-topology audit

Status: `L0_PASS / L2_MEASURED / CORRECTNESS_KEEP`. This is a reusable,
report-only parser for any written OpenFOAM `polyMesh`; it does not judge
geometric validity, alter writer input/output, or change generator routing.

Reproduction command:

```bash
AUTO_TESSELL_P4C_PYTETWILD=0 \
  python3 scripts/diag_native_tet_thin_section.py --native-primal --target-cells 2000 \
  tests/benchmarks/naca0012.stl
```

The diagnostic reports the same three unrecoverable written cell labels:
`622`, `872`, and `873`. Each has zero owner/neighbour face references, zero
face arities, and zero unique vertex ids; their structural classification is
`non_tetrahedron:face_count+unique_vertex_count`. These are orphan cell labels
in the written incidence, not a claim about the geometric validity of a cell.
Two consecutive runs with the same command produced the same three labels and
the same 16-cell incomplete-face count.

The more precise face census also found 16 additional cells that retain four
recoverable vertex ids but only two or three written triangular faces. They
are `incomplete_tetrahedron_face_encodings`: the legacy vertex-only primal can
form a four-index tuple, but the writer's face incidence is not a complete
four-triangle tetrahedron encoding. Thus the prior three-cell fail-closed
result remains correct for the primal reconstruction, while the writer audit
reveals a wider 19-cell face-incidence defect to investigate separately.

L0 test coverage uses a hand-built face list to verify owner/neighbour role,
face index, face arity, tetrahedron vertex incidence, incomplete face
incidence, and malformed owner-list refusal. Repeated reports are sorted by
cell and face index.

## Next step

Do not open anisotropic sizing or point insertion yet: no target
through-thickness count has been declared, and pure-native NACA has a
writer/primal topology inconsistency. The next safe card is to trace the
generic polyMesh writer's non-manifold-face handling that produces the three
orphan labels and 16 incomplete face encodings, without relaxing the existing
boundary/type/positive-volume gates.
