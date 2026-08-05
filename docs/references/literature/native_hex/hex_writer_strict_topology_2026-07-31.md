# Native Hex Writer Strict-Topology Card

Date: 2026-07-31
Card: `HEX-WRITER-STRICT-TOPOLOGY-1`
Claim: native-hex output must fail before writing when topology construction
would drop a cell/face or truncate a face with more than two owners.
Measured state: `L2_TARGET_PASS / RUNTIME_READY`; project-wide L3 remains an
integration responsibility before `PERMANENT` promotion.

## Measured baseline

`_write_polymesh_hex` converted each fixed-topology hex to six outward quads,
then called `write_generic_polymesh` with its default `strict=False`. The
writer already measured two topology-loss modes:

- a collapsed quad causes the entire source cell to be dropped;
- a face referenced by three or more cells keeps only the first two owners.

Both paths could still write a polyMesh and return success. The second path
also leaves the extra declared cell without its intended face incidence. This
is a false certification risk for release Gates 4 and 5, independent of cell
target accuracy.

## Primary literature

- Brückler and Campen, *Volume Quantization with Flexible Singularities for
  Hexahedral Meshing*, 2026, DOI `10.1111/cgf.70349`. The method allows
  singularity simplification while preserving topology and features exactly.
  AutoTessell uses only that acceptance principle; the algorithm is not ported.
- Pietroni et al., *Hex-Mesh Generation and Processing: A Survey*, 2022, DOI
  `10.1145/3554920`. The survey separates topological defects (open boundaries,
  holes, non-manifold elements) from geometric element quality. This card
  therefore does not trade topology loss for target-cell or skew improvement.
- Lyon, Bommes, and Kobbelt, *HexEx: Robust Hexahedral Mesh Extraction*, 2016,
  DOI `10.1145/2897824.2925976`. Reliable extraction explicitly constructs and
  connects topology instead of treating a partial connectivity result as valid.

All three sources were accessible from their official publisher pages on
2026-07-31. No inaccessible DOI was encountered.

## Active reference implementations and provenance

- MFEM (`https://github.com/mfem/mfem`, BSD-3-Clause plus separately inventoried
  bundled licenses) exposes `face_to_elem` and `GenerateFaces` as explicit mesh
  topology structures.
- OpenVolumeMesh (`https://gitlab.vci.rwth-aachen.de:9000/OpenVolumeMesh/OpenVolumeMesh`,
  LGPL-3.0-or-later with its documented template/linking exception) provides
  boundary-face, cell-cell, and vertex-cell incidence iterators.
- robust_hex_dominant_meshing
  (`https://github.com/gaoxifeng/robust_hex_dominant_meshing`, MIT) is an active
  C++ reference for hex-dominant generation and extraction.

No source code, data structure, threshold, or generated artifact was copied.
The implementation uses AutoTessell's existing independently implemented
C++23 `native_polymesh.build_topology` kernel and its Python parity fallback.

## Single mechanism

Pass `strict=True` at the native-hex writer boundary. This converts the
existing topology audit into a fail-closed production contract without adding
a new native symbol or rebuilding connectivity twice.

Acceptance:

1. two face-adjacent valid hexes write exactly 2 cells, 11 faces, 1 internal
   face, 10 `defaultWall` faces, and deterministic bytes over three runs;
2. a collapsed face and a three-owner face both reject before any case
   directory is created, with deterministic messages over three runs;
3. input coordinates/connectivity remain byte-identical;
4. native and Python writer parity tests remain green;
5. canonical native-hex solid, snap, volume, and target tests do not regress.

Rollback: revert only the strict native-hex call if a valid canonical mesh is
rejected; do not weaken the generic writer's topology audit.

Expected performance effect: no extra topology traversal. The writer already
computes drop and non-manifold records. The change adds only two constant-time
post-audit branches on a valid mesh.

## Results

- Fresh native build: GCC 13.3.0, C++23, `native_polymesh` Release.
- Native/Python topology parity and strict-contract group: `18 passed`.
- Full native-hex file group: `182 passed, 9 skipped` in `185.43 s`.
- Exact native build-contract tests: `7 passed`.
- L0 invalid cases, each repeated three times: collapsed cell rejected before
  artifact creation; three-owner faces rejected before artifact creation;
  messages deterministic; input hashes unchanged.
- L1 two-cell canonical case, three repeats: 2 cells, 11 faces, 1 internal
  face, 10 `defaultWall` boundary faces; byte-identical output hash and
  byte-identical input arrays.
- Alternating-order 8,000-cell benchmark, five runs per condition:
  `strict=False` median `0.232136 s`; native-hex strict median `0.238589 s`
  (`1.0278x`). The 2.78% delta is within the declared no-extra-traversal
  expectation; output hashes were exactly equal and deterministic in both
  conditions.
- `git diff --check`: pass. `vendor/dependencies/` changes: zero.

The first full native-hex suite attempt hit the command wrapper's 120-second
limit and was rerun with an explicit 600-second limit; the rerun passed. This
was a harness timeout, not a test failure.
