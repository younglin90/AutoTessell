# Native hex fixed-outer inward shell L0

Date: 2026-07-31

Card: `HEX-BL-FIXED-OUTER-INWARD-SHELL-L0-1`

Promotion state: `EXPERIMENTAL_KEEP`, default OFF. This is restricted to one
axis-aligned rectangular base hex, not a general all-quad/CAD boundary-layer
claim and not a Gate 7 pass.

## Critic rejection and remediation

Commit `5dedfe79` is rejected and must not be merged alone. It admitted a broad
closed all-quad class without evidence, used a generic self-intersection
detector that can be incomplete on large meshes, and promoted five files with
sequential renames rather than a crash-recoverable directory transaction. The
remediated card supersedes that commit by mechanically restricting the input
class, replacing the collision claim with an analytic AABB thickness bound,
and transacting the entire `polyMesh` directory.

A second critic rejected commit `4011b195` because crash recovery had no
inter-process ownership lock: a second invocation could mistake a live stage
for a crashed transaction and delete it. That commit also must not be merged
alone. The second remediation holds a Linux non-blocking exclusive `flock` on
the existing `constant` directory inode from pre-read recovery through every
validation, commit, rejection cleanup, and return. No lock-file artifact is
created. Kernel process exit releases ownership; only the next lock owner may
recover marker-owned state.

## Research and provenance

- Reberol et al., *Robust Topological Construction of All-hexahedral Boundary
  Layer Meshes*, ACM TOMS 49(1), 2023, DOI `10.1145/3577196`. The method fixes
  the input boundary and treats interior layer geometry, ridges, and corners as
  coupled topology/untangling problems. This supports the fixed-outer contract
  and limits this local-normal card to a conservative L0 fixture.
- Ye et al., *Bijective and high-order meshing of boundary layers*, Journal of
  Computational Physics, 2025, DOI `10.1016/j.jcp.2025.113744`. The project
  copy `docs/references/papers/source/pdf/61_ye_2025_bijective_prismatic_bl.pdf` was read. It uses an
  initially thin positive layer and orientation-preserving optimization. Its
  global nonlinear solve is outside this card. The paper's experimental code
  URL, `github.com/yhfISnaive/2D-viscous-mesh-generation`, returned 404, so its
  license cannot be verified and no code was reused.
- Wang et al., 2025, DOI `10.3724/SP.J.1089.2023-00704`. The official paper's
  separated support/top-surface and collision handling motivates a staged
  transaction only; no implementation detail was copied.

Gmsh `hexbl` is GPL and AlgoHex is AGPL. They remain reference-only. The new
NumPy primitive, signed gates, lineage arrays, and transaction are independent
AutoTessell implementations. `third_party/` is unchanged. No DOI was
inaccessible.

## Frozen hypothesis and acceptance

With explicit `post_layers_hex_inward_shell=true`, first require exactly one
base cell, eight finite points, six selected boundary quads, twelve edges with
incidence two, six AABB planes, and all eight Cartesian box corners. Only then
duplicate the source wall at the exact outer position, move the original point
ids to the innermost interface, and connect inner-to-outer canonical hexes.
The Cycle38 outward guard and default route remain unchanged.

Acceptance fixed before implementation:

1. Flag OFF retains the deterministic Cycle38 `BL=1/3` refusal; `BL=0` stays a
   byte-exact no-op.
2. Unit and non-unit axis-aligned rectangular boxes are the only positive L0
   fixtures. Unit-cube `BL=1/3` produces 7/19 cells with exact source
   coordinates/faces/patches, zero negative volumes, and positive direct
   corner-Jacobian proxies.
3. Each duplicated outer point and face has a bijective source id/row mapping;
   coordinate and patch equality alone do not establish provenance.
4. Three fresh runs produce identical five-file SHA-256 hashes and messages.
5. The fixed analytic limit is strictly
   `total_thickness < 0.90 * 0.5 * minimum_side`. Equality, near-collapse,
   rotated boxes, multiple cells, and partial selection fail before candidate
   construction.
6. Promotion preserves the complete original `polyMesh`, including extra
   regular files such as `cellZones`, and every simulated crash window is
   recovered on the next invocation even when the inward flag is OFF.

Rollback conditions were shape or patch drift, non-bijective lineage, any
non-positive signed volume or corner determinant, analytic thickness-limit
failure, stage-check failure, rejection-side directory mutation,
nondeterminism, default-path change, or silent fallback.

## Implementation and direct gates

`extrude_hex_bl_inward_shell` does not mutate input arrays. It returns explicit
`source_point_ids -> outer_point_ids`, `source_quad_rows ->
outer_face_point_ids`, and every layer's point-id table. The router rejects
anything outside the exact one-box contract before constructing a candidate.

Before writer staging, the candidate must pass:

- signed volume of every original and new cell, using oriented polygon faces;
- eight signed canonical corner determinants for every new hex;
- the fixed `0.90 * half-minimum-side` analytic thickness bound;
- exact source-to-outer point and face lineage.

The transaction marker stores only schema version, strict 32-lowercase-hex UUID
token, and state. Stage/candidate/backup paths are reconstructed from the token
as direct children of the same `constant` directory; JSON cannot supply paths.
The complete original `polyMesh` is copied before the generic writer overwrites
its five authoritative files. File and directory `fsync`, durable marker
updates, and two atomic directory renames implement commit. Recovery infers the
safe action from target/backup/candidate topology. Ambiguous topology, symlink
`polyMesh`, invalid token/state, pre-existing owned paths, or durability
failure is fail-closed and is not deleted speculatively.

Every mutating transaction and recovery entry point requires an opaque live
lock proof tied to the same directory device/inode. Lock contention returns
`native_hex_bl_transaction_active` before reading or changing authoritative,
marker, candidate, backup, or stage data. A real child-process contention test
keeps its live stage intact. A separate child exits via `os._exit`; the kernel
releases the lock and the next flag-OFF invocation recovers before authoritative
reads. Unsupported platforms refuse only the experimental inward route; the
default flag-OFF route retains its prior behavior.

## Measured result

| Fixture | Cells | Source drift | Negative | Direct min signed volume | Direct min corner determinant | Verdict |
|---|---:|---:|---:|---:|---:|---|
| cube, `BL=1`, first `0.05` | 7 | 0 | 0 | `0.0272329214` | positive | PASS |
| cube, `BL=3`, first `0.05`, growth `1.2` | 19 | 0 | 0 | `0.0272329214` | positive | PASS |
| box `2x3x4`, `BL=3` | 19 | 0 | 0 | positive | positive | PASS |
| cube, total `0.45`, limit equality | unchanged | 0 | not built | not evaluated | not evaluated | PASS refusal |
| cube, total `0.49`, near collapse | unchanged | 0 | not built | not evaluated | not evaluated | PASS refusal |
| partial wall/inlet selection | unchanged | 0 | not staged | not evaluated | not evaluated | PASS rollback |
| rotated box / two base cells | unchanged | 0 | not built | not evaluated | not evaluated | PASS refusal |

For both accepted fixtures, patch names/types match the source, point lineage
is 8/8 bijective, face lineage is 6/6 bijective, and three five-file hashes are
identical. The staged native checker reports `mesh_ok=true`, negative volume
`0`, and positive normalized determinant.

Time and storage include `O(polyMesh bytes)` full-directory copy and durability
work in addition to candidate construction/validation. No performance or
target-cell improvement is claimed.

## Limits

The local averaged-normal map is not enabled for rotated boxes, sharp features,
narrow gaps, concave CAD, partial connected patches, multiple cells, or mixed
boundary topology. Those classes are mechanically refused, not merely
unverified. General promotion requires a separate feature-aware/global
collision card and representative corpus.

## Verification

- inward-shell, transaction, process-lock, and routing files: `46 passed`;
- legacy outward extrusion selection: `3 passed`;
- native-hex regression file: `16 passed`;
- `git diff --check`: PASS;
- `third_party/` diff: empty;
- temporary stage directories after success/refusal: zero.

The full `tests/test_cvt3d_aniso_cvt.py` file has one unrelated base failure:
`test_p4c_fallback_monotone_guard_wired` expects the native-tet symbol
`_accept_fb`, which is absent at the stacked base commit `0f51e7c0`. The three
hex-BL tests in that file pass. Whole-file Ruff/Black conformance of the legacy
`tier_layers_post.py` is not claimed; its pre-existing findings lie outside the
changed Cycle39 region.
