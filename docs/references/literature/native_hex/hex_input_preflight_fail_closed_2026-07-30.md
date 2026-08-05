# HEX-INPUT-PREFLIGHT-FAIL-CLOSED-1

Date: 2026-07-30

## Hypothesis

Rejecting only malformed array ingress before diagnostics, octree, winding, or
writer work turns native-hex malformed-input crashes into explicit failures
without changing valid source geometry or imposing a new strict-topology gate.

## Research and provenance

- CGAL 6.2 Polygon Mesh Processing, Combinatorial Repair:
  <https://doc.cgal.org/latest/PMP_Mesh_repair/group__PMP__combinatorial__repair__grp.html>
  documents that a fully valid polygon soup requires stronger properties:
  bounded/oppositely directed edge incidence, no repeated polygon vertex, and
  manifoldness.
- CGAL 6.2 Mesh_3:
  <https://doc.cgal.org/latest/Mesh_3/group__PkgMesh3Functions.html>
  states that manifold output cannot be generated from non-manifold input and
  that feature-aware domains are required when exposed features must be
  represented accurately.
- CGAL repository license note:
  <https://github.com/CGAL/cgal/blob/main/LICENSE.md>.  It directs release
  source licensing to `Installation/LICENSE`; no CGAL source, API, dependency,
  generated output, or implementation was copied or added.

The first source makes a complete topology validator possible, but that would
be too strict for this ingress card and could reject supported valid-use cases.
This card therefore checks only finite `(N, 3)` vertices, finite integral
triangle indices, in-range indices, and distinct indices within a triangle.
It does not repair, merge, orient, close, relabel, or otherwise modify input.

## Baseline

Direct master baseline probe with `faces=[[0, 1, 8]]` for four vertices raised
`IndexError: index 8 is out of bounds for axis 0 with size 4`.  That is a Gate
10 failure: malformed input reaches internals instead of returning a validation
error.

Valid stock cube, `seed_density=6`, baseline focused regression passed before
the card.  Post-card representative result is unchanged:

- `success=True`, `64` hex cells, `125` points;
- negative volumes `0`, checker `mesh_ok=True`, max skewness `0.0`;
- concatenated `points`, `faces`, `owner`, `neighbour`, `boundary` SHA-256:
  `d30ab5470929ae6d7594d6b13a259f2c008889ad69c2e9008066ee0c450efaa9`.

## Change

`_prepare_native_hex_surface_input()` is a read-only ingress conversion.  It
returns stable `native_hex_invalid_input:<reason>` failures before any
self-intersection diagnostic, PRE3 remesh, winding/octetree path, or writer.
It rejects complex vertices and boolean or complex face indices before any
lossy float conversion; real numeric integral connectivity remains supported.
Empty input retains its existing `빈 입력 mesh` failure.

No target-cell, boundary-layer, quality threshold, acceptance, routing, or
output topology behavior changes.  No `vendor/dependencies/` file changed.

## Evidence

Focused L0:

```bash
python3 -m pytest -q tests/test_native_hex_input_preflight.py
```

Initial result: `8 passed` in `2.40s`.  Review follow-up added raw complex and
boolean rejection; final focused result: `14 passed` in `2.40s`.

Coverage: bad vertex shape, non-finite vertex, bad face shape, non-finite face
index, non-integral face index, out-of-range face index, repeated face vertex,
complex vertex, boolean face index, complex face index, and valid cube
caller-array/output-byte preservation.  Complex and boolean cases cover both
native NumPy dtypes and `object` scalar arrays.  The malformed tests replace
winding with a raising sentinel and verify no case directory exists.

Related representative regression:

```bash
python3 -m pytest -q tests/test_native_hex.py -k 'empty_input_fails or perfect_aspect_ratio'
```

Baseline result before card: `2 passed` in `2.45s`.  Post-card representative
rerun (`empty_input_fails`, `perfect_aspect_ratio`,
`sphere_produces_only_hexahedra`) passed `3` tests in `2.91s`; adaptive empty
input regression passed `1` test in `2.37s`.

Target and boundary-layer non-regression:

```bash
python3 -m pytest -q tests/test_native_hex.py -k \
  'target_cells_tracks_implicit_cube_budget or explicit_zero_bl_keeps_cell_budget_unreserved or cube_zero_post_layers_preserves_polymesh_bytes'
```

Result: `3 passed` in `17.61s`.

## Decision

Keep if post-card focused and representative regressions pass.  This is
`CORRECTNESS_KEEP`: it changes invalid-input behavior only, preserves valid
input geometry, and intentionally defers strict manifold/topology rejection to
a separately measured card.
