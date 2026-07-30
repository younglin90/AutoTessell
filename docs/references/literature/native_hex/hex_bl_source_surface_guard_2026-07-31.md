# Native hex BL source-surface guard

Date: 2026-07-31

Card: `HEX-BL-SOURCE-SURFACE-GUARD-1`

Promotion state: production safety fix; Gate 7 remains `FAIL/UNVERIFIED` for
positive layer requests.

## Measured gap

`post_layers_engine=auto` routes `hex_dominant` to `native_hex_bl`.  The
positive-layer primitive retained the old wall as an internal cap and appended
the new boundary along averaged outward normals.  A valid-looking mesh could
therefore replace the authoritative input surface without the native checker
detecting the contract violation.

The frozen full-wall unit cube used `first_thickness=0.05` and
`growth_ratio=1.2`:

| Request | Previous result | Cells | Negative volumes | Source-surface max deviation |
| ---: | --- | ---: | ---: | ---: |
| 0 | exact no-op | unchanged | 0 | 0 |
| 1 | success / checker PASS | 7 | 0 | `0.05000000007` |
| 3 | success / checker PASS | 19 | 0 | `0.18200000175` |

The direct extrusion measurement also reported requested/actual layers
`0/0`, `1/1`, and `3/3`.  Validity alone was therefore insufficient: the
one- and three-layer candidates were topologically closed and positive but
geometrically outside the source contract.

## Research and provenance

- Reberol, Verhetsel, Henrotte, Bommes, and Remacle, *Robust Topological
  Construction of All-hexahedral Boundary Layer Meshes*, ACM TOMS 49(1), 2023,
  DOI `10.1145/3577196`.  The public full paper fixes the input boundary while
  untangling/smoothing the interior, and treats ridge/corner configurations as
  a globally coupled topology problem.  This supports refusal of the current
  outward construction; it does not authorize a local normal-offset port.
- Wang et al., *Research on the Application of Unstructured Construction
  Method in Boundary Layer Mesh Generation*, 2025, DOI
  `10.3724/SP.J.1089.2023-00704`.  The official PDF describes a segmented
  support/top-surface construction followed by top-surface collision handling
  and reports no folded elements.  It is a collision/transaction reference,
  not code provenance for this card.
- Gmsh's `hexbl` branch is GPL and AlgoHex is AGPL.  Both are reference-only;
  no source, generated code, data structure, or implementation detail was
  copied.  The guard is an independent NumPy comparison over AutoTessell's own
  candidate arrays.

No DOI was inaccessible in this card.

## Hypothesis and fixed acceptance

Before any generic-writer call, compare every candidate outer-layer quad with
its authoritative source quad.  Exact coordinate inequality is a hard refusal;
the maximum Euclidean deviation is diagnostic only and is not a tolerance.

Acceptance declared before implementation:

1. `BL=0` remains a successful exact no-op.
2. Frozen cube `BL=1` and `BL=3` refuse deterministically before mutation,
   report requested layers, `actual_layers=0`, and maximum deviation.
3. `points`, `faces`, `owner`, `neighbour`, and `boundary` remain byte-identical
   after each refusal.
4. Three repeated calls produce the same message and bytes.
5. No fallback to another BL engine occurs.

Rollback conditions: any write on refusal, a zero-layer behavior change, false
acceptance, silent fallback, nondeterministic diagnostics, or threshold
weakening.

## Result

The guard runs after in-memory extrusion and before patch reconstruction or the
generic writer.  The fixed one- and three-layer candidates now return
`native_hex_bl_source_surface_not_preserved`, report `actual_layers=0`, and
leave all five authoritative files byte-identical across three repeats.
`BL=0` remains unchanged.  Focused native-hex routing checks pass.

This card does not implement a boundary layer and does not make Gate 7 pass.
The next independent card is a default-OFF fixed-boundary inward-shell
primitive: duplicate the source wall exactly, move only the interior interface,
and commit only after patch/topology, collision, and positive-Jacobian checks.

Verification on the Cycle38 worktree:

- focused `native_hex_bl` / zero-layer selection: `11 passed`;
- full routing, native-hex, and patch-layer diagnostic files: `33 passed`;
- `git diff --check`: PASS;
- `third_party/` diff: empty.

Repository-wide Ruff/Black conformance is not claimed by this card: both edited
legacy Python files already fail whole-file style checks outside the changed
hunks.  The card does not reformat or repair unrelated legacy code.
