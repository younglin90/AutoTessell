# Native Hex PRE3 Source-Surface Invariant

Date: 2026-07-31

Card: `HEX-PRE3-SOURCE-INVARIANT-1`

State: `L2_TARGET_PASS / RUNTIME_READY`; project-wide L3 remains an integration
responsibility before `PERMANENT` promotion.

## Decision

Delete the hidden isotropic-remesh substitution from `generate_native_hex`.
The standalone preprocessing implementation remains available, but the volume
generator no longer replaces its authoritative input coordinates or triangles.
This is one mechanism: make the caller's `V/F` arrays the sole source for bbox,
inside classification, feature extraction, snapping, and provenance.

Target-cell control is deliberately outside this card. Source shape, topology,
validity, and provenance outrank cell-count accuracy.

## Literature and public implementations

- Tong and Zhang, *MCHex: Marching Cubes Based Adaptive Hexahedral Mesh
  Generation with Guaranteed Positive Jacobian*, arXiv:2511.02064v5 (revised
  2026-07-02). The full public manuscript treats manifold boundary generation,
  boundary approximation, and positive Jacobian as coupled contracts and states
  that conventional remove/project post-processing is heuristic.
- Tong, Halilaj, and Zhang, *HybridOctree_Hex*, arXiv:2401.05984. The full public
  manuscript reports holes when narrow regions are not detected/refined and uses
  thickness-aware refinement to preserve input topology.
- Brückler and Campen, *Volume Quantization with Flexible Singularities for
  Hexahedral Meshing*, DOI `10.1111/cgf.70349` (2026). The publisher full-text
  page requires structure preservation of geometric and topological features.
- `gaoxifeng/robust_hex_dominant_meshing` is an MIT-licensed C++ reference for a
  distinct field-guided pipeline. `CMU-CBML/HybridOctree_Hex` is a research-code
  reference. `cgg-bern/AlgoHex` is AGPL-3.0 and excluded.

No source code, generated artifact, constants, or data structures were copied.
No new dependency was added. `vendor/dependencies/` is unchanged. No inaccessible DOI
was encountered.

## Reproduced failure

The deleted PRE3 block ran inside the volume generator when a surface had at
least 100 triangles and edge-length ratio above 100 (or more than 200,000
triangles). It called the generic isotropic remesher with surface projection and
feature locking both disabled, then accepted the result using only
`faces_after <= 2 * faces_before`.

Adverse fixture: closed dense icosphere, 10,242 vertices and 20,480 triangles,
with one edge shortened by `1e-6`. Edge-length ratio: `1,999,699.75`.

| Metric | Authoritative input | Accepted PRE3 replacement |
| --- | ---: | ---: |
| vertices / faces | 10,242 / 20,480 | 10,238 / 20,465 |
| watertight | true | false |
| Euler number | 2 | 0 |
| bbox max drift | 0 | 1.78177e-3 |
| surface-area ratio | 1 | 0.9958066 |
| enclosed-volume ratio | 1 | 0.9941053 |

Despite that substitution, the generator returned success with 136 cells,
zero reported flipped/degenerate cells, and grade A. Output points changed from
the existing PRE3-OFF oracle hash
`48828f117d68aa4d59691a0dabb9d5b4534df22991947153d2ac5c270b97f69a`
to
`dc7437f86548599f2dfe985a00e75429b20d3ff89be403b194e1277215cb70da`.

The hard bracket showed the guard's other failure mode: PRE3 changed 204/416
input entities to 4,047/4,078, reduced area to 15.54%, volume to 1.964%, and
lost watertightness. The face-count guard discarded that replacement, but only
after spending about 0.22 s.

## Frozen acceptance and result

Predeclared acceptance:

1. an L0 spy must prove the remesher is never called from native Hex;
2. the adverse route must match the previous PRE3-OFF bytes and result fields
   over three repeats, have zero negative/inverted/degenerate cells, run at
   least 3x faster, and have median runtime at most 1.0 s;
3. cube, cylinder, gear, and bracket output bytes and statistics must remain
   exact; bracket must not slow down;
4. full native-Hex tests, formatting, typing, and diff checks must pass;
5. no ABI, threshold, dependency, or `vendor/dependencies/` change.

Results:

- adverse whole route: `2.958305 s -> 0.453269 s`, `6.526x`; exact PRE3-OFF
  points hash, exact polyMesh bytes, exact result signature, and unchanged input
  hashes over three repeats;
- adverse result: 251 points, 136 cells, 504 faces, 136 hex cells, grade A,
  untangle beta pass, total volume `5.037037037925925`;
- cube/cylinder/gear/bracket combined artifact hashes exactly matched their
  frozen baselines over three repeats;
- bracket median `0.708518 s -> 0.525786 s`; output remains 144 points, 55
  cells, 236 faces, grade A, untangle beta pass;
- new source-invariant regression: `15 passed` with the whole input-preflight
  file;
- full native-Hex group: `193 passed, 11 skipped` in `210.87 s`;
- Black and Ruff pass for the new/changed test and benchmark files; strict mypy
  passes for both;
- caller arrays, native ABI/build contract, quality thresholds, routing,
  boundary-layer logic, and `vendor/dependencies/` are unchanged.

The 11 skips are pre-existing environment/optional-path skips and were not
introduced or modified by this card.
