# BOOLMERGE4: Per-input union inclusion

## Baseline

- HEAD: `b4a9cb05` (`BOOLMERGE3` code at `30f75c41`).
- Two overlapping unit cubes: analytic union `1.875`.
- BOOLMERGE3 measured `1.7574`, matching symmetric difference `1.750`.
- Cause: ray parity on the combined closed STL soup sees two crossings in the overlap.

## Change

- Keep combined soup for analysis, bbox, seeding, and surface vertices.
- Preserve original input paths in copied `tier_specific_params` as JSON-safe strings.
- Coerce two-surface `tier=auto` to `native_tet`; reject incompatible explicit tiers.
- At final centroid inclusion, load each original STL and OR its GWN mask.
- On original-STL load or classification failure, warn and use the prior combined-soup path.
- Keep single-input behavior and public API unchanged.

## Acceptance

- Overlap point must remain inside.
- Caller-owned `tier_specific_params` must remain unchanged.
- E2E volume must be in `[1.82, 1.95]`, excluding symmetric difference.
- Existing geometry, native filter, and desktop multi-surface tests must pass.

## Result

- E2E volume: `1.891203768` across `2859` positive-volume cells.
- Native checker: `negative_volumes=0`, verdict `PASS`.
- Required suites after server-tier gate coverage: `34 passed`.
