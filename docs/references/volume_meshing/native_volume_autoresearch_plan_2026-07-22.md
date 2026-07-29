# Native Volume Autoresearch Plan

Date: 2026-07-22

Scope: native tet, native hex dom, native polyhed, wall-face boundary layers, and
volume autoresearch metrics.

## Decision

Improve volume engines through separate clean worktrees. Do not initialize new
autoresearch in the dirty root worktree. Keep the existing tet/BL foreground run
`/home/younglin90/work/claude_code/AutoTessell-autoresearch-bl-v2` separate until
its controller reaches target.

The common BL failure pattern is a topology problem, not only a thickness problem:

- one averaged wall normal per vertex fails at ridges and mixed patch junctions,
- face normals can become nearly orthogonal to the layer front,
- boundary skew can grow roughly with the normal-angle tangent,
- bulk-first generation followed by global shrink should be replaced by a
  layer-first closed advancing-front shell where possible.

## Common Metric Hardening

Primary metric for future volume lanes:

- `fail_count`, lower is better, target `0`.
- Run each baseline twice. If results differ, fix determinism before init.
- Metric source: `tests/stl/verify_autoresearch_mesh_matrix.py` plus added family and
  BL-coverage checks.

Required invariants:

- crash, timeout, negative/zero volume: `0`,
- open, non-manifold, duplicate, self-intersection: `0`,
- native-only path; cross-family fallback: `0`,
- target cells initially within `[0.5N, 2N]`, final target `[0.9N, 1.1N]`,
- native tet share at least `90%`,
- hex share at least `70%`,
- true poly share at least `95%`,
- requested wall-face BL coverage `100%`,
- non-wall inlet/outlet/symmetry BL count `0`,
- every prism corner signed Jacobian positive,
- first-height error, growth ratio, and layer orthogonality reported,
- `maxNonOrtho <= 65` for ranking and `<= 70` for compatibility,
- boundary/internal skew separately reported,
- internal skew `<= 4`,
- `minDeterminant >= 0.001`,
- `minFaceWeight >= 0.05`,
- `minVolRatio >= 0.01`,
- Hausdorff and area deviation `<= 2%`.

Before loop start, unify BL aspect definitions:

- `core/evaluator/bl_quality.py` currently uses `height/base_edge`.
- `core/layers/native_bl.py::_evaluator_prism_aspect` uses `base_edge/min_height`.
- Report physical BL aspect separately from harmful bulk aspect.

## Native Tet

Adopt:

- TetGen-style constrained Delaunay facet recovery and off-centre refinement,
- fTetWild-style envelope, local split/collapse/flip/AMIPS loop, and positive-volume
  plus envelope barriers,
- wall-prism shell before cavity tetrahedralization,
- multi-normal feature fan at sharp ridges and corners,
- existing Dompierre-compatible prism-to-tet split only after shell validity.

First experiment after current tet/BL foreground run reaches terminal state:

`TET-FEATURE-FAN1`: prototype feature-fan cap for the current hard case, default-off
behind an environment flag. Success requires wall coverage `100%`, cap open/non-manifold
edge `0`, inverted cells `0`, boundary skew `<20`, and cube/sphere non-regression.

Expected files:

- `core/generator/native_tet/mesher.py`
- `core/generator/native_tet/cdt_recovery.py`
- `core/generator/native_tet/envelope.py`
- `core/generator/native_tet/amips.py`
- `core/layers/layer_front.py`
- `core/layers/native_bl.py`
- `core/layers/tet_bl_subdivide.py`

## Native Hex Dom

Adopt:

- current balanced octree as baseline,
- feature edges mapped to discrete hex-edge paths,
- scaffold-style local/global inversion prevention,
- boundary and first interior ring moved together,
- scaled-Jacobian barrier line search,
- quad wall extrusion as all-hex BL columns,
- fixed outer cap and first-ring bulk matching,
- Reberol-style disk configuration concepts for ridge/corner topology.

Defer full AlgoHex frame-field import. AlgoHex code is AGPL; use paper concepts only.

First experiment:

`HEX-RING-LINESEARCH1`: combine wall-fit snap and first-interior-ring relaxation into
one quality line search. Accept only if negative volume stays `0`, min scaled Jacobian
does not regress, max non-orthogonality/skewness do not regress, and wall Hausdorff
improves. Corpus: cube, cylinder, `medium_100322`, all BL3. Target for the hard case:
non-ortho `<65`, hex share at least `70%`, wall BL coverage `100%`.

Expected files:

- `core/generator/native_hex/octree.py`
- `core/generator/native_hex/snap.py`
- `core/generator/native_hex/quality.py`
- `core/generator/native_hex/mesher.py`
- `core/layers/native_hex_bl.py`
- `core/layers/native_bl.py`

## Native Polyhed

Adopt:

- promote VoroCrust-style unclipped Voronoi path over clipped Voronoi,
- local-feature-size surface sampling,
- paired inside/outside boundary sites around wall facets,
- pinned feature/corner sites,
- Poisson or saturated interior sampling followed by protected Lloyd/CVT,
- BL shell first, then paired sites on the cap for cap-conforming Voronoi bulk,
- convexity, planarity, and signed-pyramid validation for transition cells,
- remove `prefer_hex_for_budget=True` from poly autoresearch lanes.

First experiment:

`POLY-PAIRED-SITES1`: add paired surface sites for cube and cylinder, pin feature sites,
disable hex budget fallback, compare against clipped Voronoi. Target: wall Hausdorff
`<2%`, convex cells `100%`, face planarity pass, max non-ortho improves, true poly share
at least `95%`, BL3 wall coverage `100%`.

Expected files:

- `core/generator/tier_native_poly.py`
- `core/generator/native_poly/voronoi.py`
- `core/generator/native_poly/aniso_cvt.py`
- `core/generator/native_poly/quality.py`
- `core/layers/poly_bl_transition.py`
- `core/layers/layer_front.py`

## Baseline Commands

Tet:

```bash
AUTO_TESSELL_VERIFY_ENGINES=native_tet \
AUTO_TESSELL_VERIFY_MAX_CELLS=10000 \
AUTO_TESSELL_VERIFY_BL_LAYERS=3 \
AUTO_TESSELL_VERIFY_QUALITY=standard \
AUTO_TESSELL_VERIFY_STRICT_EXIT=1 \
AUTO_TESSELL_VERIFY_RUN_ROOT=/tmp/autotessell_ar_native_tet \
AUTO_TESSELL_P4C_PYTETWILD=0 \
timeout 10800 python3 tests/stl/verify_autoresearch_mesh_matrix.py
```

Hex:

```bash
AUTO_TESSELL_VERIFY_ENGINES=hex \
AUTO_TESSELL_VERIFY_MAX_CELLS=10000 \
AUTO_TESSELL_VERIFY_BL_LAYERS=3 \
AUTO_TESSELL_VERIFY_QUALITY=standard \
AUTO_TESSELL_VERIFY_STRICT_EXIT=1 \
AUTO_TESSELL_VERIFY_RUN_ROOT=/tmp/autotessell_ar_hex \
timeout 10800 python3 tests/stl/verify_autoresearch_mesh_matrix.py
```

Poly:

```bash
AUTO_TESSELL_VERIFY_ENGINES=poly \
AUTO_TESSELL_VERIFY_MAX_CELLS=10000 \
AUTO_TESSELL_VERIFY_BL_LAYERS=3 \
AUTO_TESSELL_VERIFY_QUALITY=standard \
AUTO_TESSELL_VERIFY_STRICT_EXIT=1 \
AUTO_TESSELL_VERIFY_RUN_ROOT=/tmp/autotessell_ar_poly \
timeout 10800 python3 tests/stl/verify_autoresearch_mesh_matrix.py
```

Use `AUTO_TESSELL_VERIFY_CASE_LIMIT=3` for smoke. Use full command before keep.

## License Constraints

- fTetWild: MPL-2.0. Direct copied files carry MPL obligations; prefer clean-room.
- TetGen: AGPL-3.0/commercial dual license. Do not copy or statically link.
- AlgoHex: AGPL-3.0. Do not copy code.
- VoroCrust: BSD-3-Clause style. Port possible with attribution, but keep provenance clear.
- Feature-Preserving-Octree-Hex-Meshing vendored code has no root license file. Do not copy.
- OpenFOAM/cfMesh GPL code is behavior and metric reference only.

## Key Literature

- TetGen: https://doi.org/10.1145/2629697
- TetWild: https://doi.org/10.1145/3197517.3201353
- fTetWild: https://doi.org/10.1145/3386569.3392385
- VoroCrust: https://doi.org/10.1145/3337680
- VoroCrust sampling: https://doi.org/10.4230/LIPIcs.SoCG.2018.1
- AlgoHex locally meshable fields: https://doi.org/10.1145/3592457
- Feature-preserving octree hex: https://doi.org/10.1111/cgf.13795
- Field-guided hex-dominant agglomeration: https://doi.org/10.1145/3072959.3073676
- Hex-dominant "Mind the gap": https://doi.org/10.1016/j.cad.2018.04.012
- Maréchal octree hex, source currently inaccessible: https://doi.org/10.1007/978-3-642-04319-2_5
- Garimella boundary layers: https://doi.org/10.1002/1097-0207(20000910/20)49:1/2<193::AID-NME929>3.0.CO;2-R
- Robust BL cavity/multi-normal: https://doi.org/10.1007/978-3-642-33573-0_29
- All-hex BL topology: https://doi.org/10.1145/3577196
- Fast BL collision detection: https://doi.org/10.31857/S0044466922080105
