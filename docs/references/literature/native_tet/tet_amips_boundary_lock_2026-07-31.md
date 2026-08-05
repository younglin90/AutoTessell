# Native tet Cycle 39: exact current-boundary lock for AMIPS

Date: 2026-07-31

Card: `TET-AMIPS-BOUNDARY-LOCK1`

Primary metric: cylinder strict source-facet ownership.

Priority: shape/topology/provenance; target-cell tracking is report-only.

## Evidence reviewed

- Hu et al., *Fast Tetrahedral Meshing in the Wild* (2020), DOI
  [10.1145/3386569.3392385](https://doi.org/10.1145/3386569.3392385).
  The envelope/invariant design was used only as an algorithmic reference.
  The fTetWild repository is MPL-2.0; no source was copied.
- CGAL 6.2, [Tetrahedral Remeshing reference manual](https://doc.cgal.org/latest/Tetrahedral_remeshing/group__PkgTetrahedralRemeshingRef.html).
  Its contract states that constrained vertices cannot be moved by smoothing.
  CGAL code is GPL/commercial and was not copied.
- Zhou et al., [Wildmeshing Toolkit](https://github.com/wildmeshing/wildmeshing-toolkit),
  MIT. Explicit invariants, rollback, and frozen-boundary concepts were reviewed;
  implementation is independent and no source was copied.
- Yu et al., *Weighted Squared Volume Minimization (WSVM) for Generating
  Uniform Tetrahedral Meshes* (2025), DOI
  [10.1109/TVCG.2025.3587642](https://doi.org/10.1109/TVCG.2025.3587642).
  The method optimizes internal vertices while maintaining positive volumes.
  The project page reported code as forthcoming; no code was available or used.

No inaccessible DOI remained for this card.

## Baseline localization

Configuration: `cylinder.stl`, target 2000, native route, PyTetWild and convex
extrusion rescue off, BSP/edge recovery/phase B/phase C off.

- Through post-EEE: 216/216 boundary faces owned, 0 unowned, relative
  Hausdorff `1.2760523383915705e-15`.
- First defect: NNN4 post-Steiner analytic AMIPS.
- NNN4 result: 119 owned, 97 unowned, two area mismatch patches, two feature
  mismatches, relative Hausdorff `0.057719130833732084`.
- Cause: AMIPS received only the 66 source-prefix vertices as locked, while the
  current tetrahedral boundary contained 110 vertices. All 44 surface-recovery
  vertices were eligible for relocation. RRR2 repeated the stale-prefix rule.
- Final rejected baseline: 353 points, 1495 tets, relative Hausdorff
  `0.056314359506959906`; writer absent.

## Change and complexity

Every AMIPS relocation path now computes the exact current boundary from
one-owner tetrahedral face incidence and ORs it with caller-provided locks.
The shared C++23 kernel validates the int64 contiguous tetrahedron contract and
indices before releasing the GIL. It reserves four face entries per tet and
performs no Python access while unlocked.

The analytic, finite-difference, and Torch paths share the same Python mask
adapter. Torch computes the native/fallback mask once, transfers the exact bool
mask to the selected CPU or CUDA device, then ORs explicit caller locks. The
native symbol is listed in `native_build_contract.json`, so missing/stale
binaries fail the exact ABI evidence check.

- Time: expected `O(T)` face census plus `O(V)` mask initialization.
- Space: expected `O(T + V)`.
- Determinism: the returned bool mask is indexed in ascending vertex-ID order;
  unordered-map iteration cannot change the mask.
- Python fallback retains the same exact one-owner-face semantics.

## Results

Cylinder, three exact repeats:

- strict ownership: 119/216 -> 216/216; unowned 97 -> 0.
- area/feature mismatch: 2/2 -> 0/0.
- relative Hausdorff: `0.056314359506959906` ->
  `1.2760523383915705e-15` (hard limit `1e-12`).
- inverted/degenerate: 0/0; writer present.
- points/cells: 353/1489.
- requested/actual cells: 2000/1489; error -511 (-25.55%), report-only.
- quality: min `0.0027987922`, mean `0.2699397928`, p10
  `0.0212134784`, min dihedral `0.6917432059` degrees, max aspect `209.8088`.
- point SHA-256:
  `85ad5dd102c51a66b668f4b6251e934665ec5b9fcb54fdec570b2309f83f7824`.
- tet SHA-256:
  `6093f8e12ae9a1584d75b63af05a28bd979bb44f0a7ad914705663e6828ca210`.

Representative controls:

- Sphere: exact baseline retained: 735 points, 2164 tets, 1280/1280 owned,
  mean quality `0.2583250929`; point/tet hashes unchanged.
- Cube: previous strict failure (35 owned, 283 unowned) became strict PASS
  (318/318 owned), with 0 invalid tets. Mean quality changed
  `0.3599213291` -> `0.357810`; the fixed control floor is `0.3563` because
  strict conformance has higher priority than this 0.59% quality movement.

Torch reachable regression (`cube_star`, one iteration, step 0.05):

- Before this card, all 9 vertices were reported moved and boundary displacement
  reached `8.660254037844386e-4`.
- After this card, both Torch CPU and CUDA move only the one interior vertex.
- Boundary maximum displacement is exactly `0.0` on both devices.
- Interior displacement is `8.660254037844386e-4` on both devices.
- An explicit lock on the interior vertex unions with the boundary mask and
  produces 0 moved vertices.

## Verification

- Fresh GCC 13.3 Release C++23 build with first-party warnings-as-errors: PASS.
- Native AMIPS/boundary/provenance/predicate/runtime suites: 63 PASS.
- Torch 2.11.0+cu130 reachable suite: 22 PASS, including CPU/CUDA parity.
- Exact native build contract and predicate suite: 30 PASS, no native-mask skip.
- Cylinder/cube/sphere hard integration: 3 PASS; cylinder includes exact
  three-run point/tet hashes.
- Cylinder three-run wall time: 38.65 s, peak RSS 336448 KiB. The pre-change
  focused run was 46.75 s, so the fixed 15% regression limit is satisfied.
- Targeted strict mypy still reports 15 pre-existing annotations/`Any` errors
  in `amips.py`; this card introduced no new reported item.
- `vendor/dependencies/`: untouched.
