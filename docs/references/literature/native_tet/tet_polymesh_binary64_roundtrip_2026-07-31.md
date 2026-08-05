# Tet polyMesh binary64 round-trip certificate (Cycle 41)

## Card

`TET-POLYMESH-BINARY64-ROUNDTRIP-1`

Promotion target: `RUNTIME_READY` for native-tet ASCII point serialization.
The card does not change mesh generation, connectivity, target-cell policy,
boundary layers, quality thresholds, or geometry repair.

## Baseline defect and earliest failing stage

The canonical self-native cylinder (`target_cells=2000`, P4C and convex rescue
off) is valid in memory: 353 points, 1,489 tets, 216/216 owned boundary faces,
zero unowned faces, and relative Hausdorff `1.28e-15`.  The three-run permanent
test passed on master.

The first loss occurred after that certificate.  The shared OpenFOAM points
writer formatted every binary64 coordinate with `%.9g`.  A text round-trip of
the unchanged canonical cylinder produced:

- maximum coordinate delta `4.995044933231441e-10`;
- owned candidate boundary faces `216 -> 95`;
- unowned candidate boundary faces `0 -> 121`;
- area-mismatch patches `0 -> 2`;
- feature-boundary mismatches `0 -> 2`;
- source-facet preservation `true -> false`.

The GUI/Pipeline P4C fixture exposed the same disk-only defect: 244 candidate
boundary faces, 134 owned, 110 unowned, 32 uncovered source patches, and a
false source-facet certificate.  The in-memory generator gate did not see the
serialized coordinates.

The old wall-fidelity test then masked this defect with a second diagnostic
error.  It selected side-wall *vertices* using `abs(z) < 0.49`.  A conforming
two-ring cylinder has zero such vertices even though it has 64 side faces and
64 side-owned vertices.  Side faces have interior-z centroids; selecting faces
first and then collecting their vertices is topology-correct.  The obsolete
vertex assertion reported `n_side=0`; the corrected classifier reports 64.

## Hypothesis and frozen acceptance

Hypothesis: 17 significant decimal digits, the binary64 `max_digits10`
contract, preserve every finite native-tet point exactly across ASCII
serialization and parsing.  Generic and non-tet callers retain the historical
9-digit default.

Acceptance was declared before implementation:

- canonical cylinder disk ownership `95/216 -> 216/216`;
- canonical cylinder disk unowned faces `121 -> 0`;
- maximum point round-trip delta `4.995e-10 -> 0`;
- signed zero, smallest subnormal, adjacent-to-one, pi, and largest finite
  binary64 values round-trip bit exactly;
- non-finite native-tet coordinates fail before artifacts;
- default generic writer's five file SHA-256 values remain exact;
- 9-vs-17 native-tet files differ only in `points`;
- cube, sphere, cylinder, and four transformed/mixed-scale cylinders retain
  source facets and have zero inverted/degenerate tets;
- point-file size remains at most 2x;
- canonical cylinder wall time regresses by at most 10%;
- quality thresholds remain unchanged and `vendor/dependencies/` remains untouched.

Rollback conditions: any generic byte change, parser failure, connectivity or
patch-file change, source/topology regression, point-file ratio above 2x, or
canonical wall-time regression above 10%.

## Mechanism and compatibility

`_write_points` now accepts an explicit `precision` keyword with historical
default 9 and a closed valid range `[1, 17]`.  `write_generic_polymesh` and
`PolyMeshWriter.write` expose the same policy through `point_precision=9`.
Only the two native-tet writer call sites request 17.  Other engines and direct
generic calls remain byte exact.

Formatting remains one streaming `numpy.savetxt` traversal: `O(P)` time and
the existing `O(P)` text buffer.  No mesh array is copied by the precision
selection.  The native-tet wrapper rejects NaN or Inf before it creates writer
artifacts.

## Literature and public implementation evidence

- Adams, *Ryū: Fast Float-to-String Conversion*, PLDI 2018, DOI
  `10.1145/3192366.3192369`.  Public full text was accessible.  It formalizes
  correctly rounded, round-trippable binary-to-decimal conversion.
- NumPy 2.4 `savetxt` official documentation.  The official default is
  `%.18e`; for `g`, precision is the maximum number of significant digits.
  The project already uses NumPy, so no dependency was added.
- `nschloe/meshio`, MIT.  Current public mesh-I/O project reviewed for format
  round-trip practice; no code copied.
- `fmtlib/fmt`, MIT.  Current public formatting project reviewed as a
  permissive modern formatting reference; no code copied.
- OpenFOAM Foundation repositories, GPLv3+.  Its ASCII mesh ecosystem was used
  as a format reference only.  No OpenFOAM source was copied into native core.

Inaccessible DOI requiring user material: none.

## Provenance

Implementation is a first-party extension of the existing writer's format
parameter and call sites.  It uses the standard binary64 decimal round-trip
bound; it is not derived from Ryū, meshio, fmt, OpenFOAM, or another external
implementation.  No generated source, dependency code, GPL/AGPL code, or
`vendor/dependencies/` file was copied or modified.

## Results

- Binary64 extreme-value and policy L0: PASS, including negative zero,
  subnormal, largest finite, and invalid precision rejection.
- Generic 9-digit byte lock: all five files match frozen SHA-256 values.
- Native 17-digit isolation: parsed points bit-exact; faces, owner, neighbour,
  and boundary hashes unchanged from native 9-digit output.
- Four transformed cylinders (`1e-6`, `0.125`, `1`, `1e6` scales with
  translations): every source face owned, zero unowned, zero inverted, zero
  degenerate.
- New focused round-trip suite: `7 passed in 1.97s`; each transformed-cylinder
  case is evaluated inside the single disk-audit test to keep static typing
  strict while preserving all four cases.
- Immutable input/source-ledger suite: `4 passed in 3.01s`.
- Native polymesh extension suite: `15 passed in 2.07s`.
- Generic writer suite excluding one unrelated pre-existing parser expectation:
  `12 passed, 1 deselected in 2.22s`.  The excluded baseline test expects a
  boundary dictionary without `type`, while the current parser returns the
  existing `type="wall"`; this card does not modify that parser or boundary
  output.
- Real generator disk audit final combined run: cylinder three-run plus cube
  and sphere `3 passed in 67.39s`.
- Cylinder process wall/RSS: `41.31s`, `334,748 KiB`, versus master `41.10s`,
  `353,564 KiB`: wall `+0.51%`, RSS `-5.32%`.
- Representative star-cylinder point-file size: `2,654 -> 3,640` bytes,
  ratio `1.372x`, inside 2x.
- GUI/Pipeline disk source certificate after the change: 244/244 owned, zero
  unowned, zero uncovered/area/feature mismatches.  Corrected side-wall metric:
  64 vertices, maximum radial deviation `1.4421e-8`, mean `9.1777e-9`.

The GUI/Pipeline fidelity test now reaches, and still truthfully fails, its
unchanged evaluator-quality assertion because that output has one oriented
degenerate cell.  Before this card it stopped earlier at the false `n_side=0`
diagnostic.  No quality threshold was weakened; the remaining validity issue
is a separate card and does not negate the disk source-shape repair.
