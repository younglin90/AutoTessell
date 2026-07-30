# POLY-BL0-ORACLE-CORRECTION-1 Evidence

Date: 2026-07-31

Status: test-only correction after the explicit BL=0 production invariant.

## Stale oracle

`test_direct_scipy_no_drop_real_smoke` requested `bl_layers=0` but expected 36
sphere cells. Before `POLY-BL0-FALLBACK-INVARIANT-1`, the direct Voronoi path
silently entered boundary-layer extrusion and added nine cells. The corrected
base mesh contains 27 cells. This is an exact behavioral oracle correction,
not a target-cell tolerance change.

The test now expects 27 and carries an inline reason. No quality threshold,
fixture, success condition, or tolerance changed.

## Verification

- No-drop-holes regressions: `9 passed in 3.70s`.
- Three independent sphere runs: cell counts `[27, 27, 27]`.
- Requested layers: 0; actual layers: 0; extrusion calls: 0.
- Mandatory admission: negative=0 and degenerate=0 in all three runs.
- Each run emitted exactly the five canonical polyMesh files.
- Combined polyMesh digest, all three runs:
  `cb8cba21d464fb8c74a19156d64908216b66c9d1f0be913643613eb468ce46fd`.
- Source coordinate array remained byte-exact:
  `19879ce58c1f36cd58858fdf25c4d4dd7ff7eda21a5f7a58bd6dbb12c11ad8c1`.
- Source face topology remained byte-exact:
  `797116367c42eab2561e5c6482863b88ff8ef78aebcaa0aab69ff2548028edd1`.
- Output boundary/provenance file bytes are covered by the identical combined
  polyMesh digest.

Rollback conditions: any layer extrusion for BL=0, cell count other than 27
for this frozen fixture, invalid cell, nondeterministic output, source array
mutation, tolerance substitution, fixture change, or `third_party/` change.
