# Native hex oriented-box inward-shell certificate

Date: 2026-07-31

Card: `HEX-BL-ORIENTED-BOX-CONTRACT-1`

Promotion state: `EXPERIMENTAL_KEEP`, default OFF. This extends the existing
one-cell AABB fixture to one certified orthogonal box under rigid rotation. It
does not support general CAD boundary layers and does not pass Gate 7.

## Baseline and hypothesis

Cycle39 admitted exactly one axis-aligned rectangular base hex. A 30-degree
rotation was refused before candidate construction, so both positive requests
in this card had `actual_layers=0`.

Hypothesis: a native C++23 certificate can replace coordinate-axis recognition
with a rigid-frame invariant contract while preserving every existing inward
shell gate. The source face and edge incidence remain authoritative. The
certificate chooses point id zero as deterministic anchor, sorts its three
topological neighbors by id, makes their basis right-handed deterministically,
and requires a bijection from every source vertex, edge, and face to exactly one
orthogonal-box role.

Primary metric: safe rotated-box requests fulfilled. Baseline `0/2`; target
`2/2` for one layer on a rotated unit box and three layers on a rotated
`2x3x4` box. Target-cell control is outside this card.

## Frozen floating contract

OpenFOAM points are serialized by the project writer with `%.9g`. An arbitrary
SO(3) round-trip of the `2x3x4` fixture measured a maximum normalized basis dot
residual of `1.1032821337527498e-9`. A pure `4096*epsilon` test would therefore
reject a valid serialized box.

The predeclared certificate uses:

- normalized orthogonality tolerance `8*sqrt(double epsilon) =
  1.1920928955078125e-7`;
- coordinate reconstruction tolerance `8*sqrt(double epsilon) *
  max(1, bbox diagonal)`.

Tests freeze one synthetic basis immediately below and above this threshold.
A `1e-3` shear is refused. The tolerance represents writer serialization
equivalence only; it does not move or repair source geometry. Outer coordinates,
face connectivity, patch identity, and provenance remain exact source values.

## Research and provenance

- Reberol et al., *Robust Topological Construction of All-hexahedral Boundary
  Layer Meshes*, ACM TOMS 49(1), 2023, DOI `10.1145/3577196`. The official full
  paper keeps the input boundary fixed and shows that general ridge/corner
  topology requires a globally coupled solution. This limits the current card
  to an orthogonal one-cell fixture.
- The authors' supplemental
  `mxncr/AllHexBoundaryLayerTopologySolver` repository is MIT licensed. It
  contains only the Gecode integer topology solver, not a standalone mesher.
  No source, constants, data structures, or generated artifacts were copied.
- The complete research implementation is referenced in Gmsh's `hexbl` branch.
  Gmsh is GPL and remains reference-only. No code was copied.
- Ye et al., *Bijective and high-order meshing of boundary layers*, JCP 2025,
  DOI `10.1016/j.jcp.2025.113744`, remains a positive-layer validity reference.
  Its global nonlinear solve is outside this card.

No new dependency was added. `third_party/` is unchanged. No DOI was
inaccessible.

## Implementation

`native_hex_quality.certify_oriented_box` performs one bounded `O(V+E+F)`
certificate over eight points, twelve edges, and six faces:

1. finite `8x3` points and six unique quads;
2. twelve source edges, each with incidence two, and vertex degree three;
3. deterministic nonzero right-handed orthogonal basis;
4. unique reconstruction of all eight corner roles;
5. bijective cube-edge role assignment for all twelve source edges;
6. bijective `(axis, side)` role assignment for all six source faces.

The Python router validates the returned ABI and uses only its three certified
side lengths for the unchanged strict thickness bound:

`total_thickness < 0.90 * 0.5 * min(side_lengths)`.

The inward constructor, signed-volume gate, eight-corner Jacobian gate,
source-point/source-face provenance, whole-directory lock, recovery, and atomic
transaction are unchanged.

## Measured result

| Fixture | Request | Actual | Cells | Source drift | Invalid/inverted | Provenance | Repeat |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| unit box, 30-degree rotation | 1 | 1 | 7 | 0 | 0 | points `8/8`, faces `6/6` | three hashes equal |
| `2x3x4`, arbitrary SO(3) | 3 | 3 | 19 | 0 | 0 | points `8/8`, faces `6/6` | three hashes equal |
| shear `1e-3` | 1 | 0 | unchanged | 0 | not built | unchanged | deterministic refusal |
| side length `1e-9` | 1 | 0 | unchanged | 0 | not built | unchanged | deterministic refusal |

AABB output stayed byte-identical to the Cycle39 baseline:

- one layer: `468d49b2c27caeede8ef21248a43bb6ec253bc7720a0f8d234dcdf914a50d959`;
- three layers: `9e8d079c973291cac6627c697e47bee1dd0128fe51a549ad0e5fe0517705fdcc`.

`boundary layer = 0`, flag-OFF outward refusal, partial selection, two-cell
input, analytic near-collapse refusal, transaction recovery, and process-lock
behavior remain unchanged.

## Verification

- GCC 13.3, C++23, Release, `-Wall -Wextra -Wpedantic -Werror`, `j1`: PASS;
- native certificate direct tests: `2 passed`;
- inward-shell focused file: `14 passed`;
- process lock, crash transaction, and routing: `35 passed`;
- native hex quality extension file: `15 passed`;
- full `tests/test_native_hex*.py` group: `241 passed` in `167.48 s`;
- Ruff on both changed test files: PASS;
- source coordinates and all five authoritative files are deterministic;
- `third_party/` diff: empty.

The repository-wide exact native ABI contract test has one unrelated base
failure: `native_polymesh` exports `assemble_dual_hull_faces`, while its current
manifest entry does not list that symbol. This card updates and exercises the
`native_hex_quality` ABI only; it does not modify the unrelated Poly manifest.
Project-wide strict mypy also remains red at the base (`1006 errors in 118
files`); the first reported errors are existing `_shewchuk` annotations, and
the changed quality test already had an unannotated `incident` local at its
pre-card line. No type threshold or unrelated annotation was changed here.

General CAD, multi-cell cores, non-orthogonal hexahedra, partial connected
patches, ridges/corners, narrow gaps, and collision-coupled layer fronts remain
mechanically unsupported. The next general-CAD card must begin with the
report-only topology/feature/collision prerequisites from the Reberol full read.
