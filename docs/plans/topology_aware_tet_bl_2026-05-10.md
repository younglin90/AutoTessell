# Topology-Aware Tet + BL Recovery Plan

Date: 2026-05-10

## Goal

Make the strict tet + BL(3) bench pass for:

- `test_cube.stl`
- `tests/stl/thingi10k_bench20/*.stl`

The verifier is:

```bash
AUTO_TESSELL_VERIFY_MAX_CELLS=10000 \
AUTO_TESSELL_VERIFY_BL_LAYERS=3 \
AUTO_TESSELL_VERIFY_ENGINES=tet \
timeout 1800 python3 tests/stl/verify_autoresearch_mesh_matrix.py
```

Acceptance: `tet_failed_case_count == 0`, exact `bl_used_layers == 3`, no
wrong-tier fallback success counting, and the evaluator gates in
`agents/specs/evaluator.md` stay authoritative.

## Current State

Latest retained full verifier result:

- `tet_failed_case_count = 16`
- `pass_count = 5/21`
- `fail_count = 28`
- Failure reasons: `hausdorff=15`, `surface_area=9`, `determinant=2`,
  `non_ortho=1`, `face_weight=1`

Two fundamentally different paths are failing:

1. `axis_extrusion` cap fastpath:
   - FVM quality is usually good.
   - Geometry fidelity fails because constant cap sweep cannot represent
     holes, changing section count, or side-surface variation.
2. exact WildMesh + native BL:
   - Geometry fidelity/topology are often good.
   - FVM fails at BL/bulk transition because bad internal faces remain near
     90 degree non-orthogonality and low face weight.

Recent retained building blocks:

- `62b0ff59` adds `native_bl_quality.fastpath.section_topology` metadata.
- `8411c043` adds unit coverage for stable interior-hole section detection.

## What Has Been Ruled Out

The following were tried and discarded or recorded as no-pass:

- Scalar BL thickness/growth sweeps.
- WildMesh epsilon/coarsen/simplify flags.
- Interior Laplacian smoothing.
- Full nearest-surface boundary snapping.
- Cap-to-midsection replacement.
- Boundary-only section projection.
- Affine least-squares section projection.
- Harmonic/Laplacian section-stack mapping.
- Simple bad-face agglomeration.
- Targeted VD rescue for `extreme_1017013`.
- Existing external tet tiers (`meshpy`, `netgen`, `tetwild`) as oracle
  replacements under `max_cells=10000`.

These failures mean the next work must be topology-changing, not another knob.

## Design Direction A: Topology-Aware Sweep Fastpath

Use this for cap-fastpath Hausdorff/surface-area failures.

### A1. Section Topology Classifier

Files:

- `core/generator/tier_wildmesh.py`
- `tests/test_generator.py`

Input: `fastpath.section_topology`, cap loop/hole counts, section area range.

Output classification:

- `constant_prism`: cap topology and interior section topology match, area range
  small.
- `stable_hole_sweep`: interior sections are stable but differ from cap topology
  by holes.
- `changing_section_sweep`: polygon or hole counts change along the axis.
- `unsafe_sweep`: missing or fragmented sections.

Gate:

- Current `axis_extrusion` stays active for `constant_prism`.
- Other classes must not use the current cap-only fastpath by default once a
  replacement exists.

Verify:

```bash
timeout 60 python3 -m pytest tests/test_generator.py -q -k "tier_wildmesh"
```

### A2. Stable-Hole Sweep Candidate

Scope: start with `easy_100423`-style stable one-polygon/one-hole sections.

Algorithm:

1. Sample sections at `z = linspace(0.02, 0.98, n_z+1)`.
2. Require every section to have the same polygon count and hole count.
3. Build boundary correspondence per loop by normalized arclength.
4. Generate each layer boundary from the actual section.
5. Build side faces only if every quad/triangle side candidate passes:
   - no zero area
   - face warpage below threshold
   - no triangle-triangle self-intersection against already accepted side faces
   - adjacent layer edge length ratio below a guard threshold
6. If any side candidate fails, reject the sweep candidate before writing
   `polyMesh`.

Important lesson from prior prototypes:

- Moving interior nodes to match sections without side-surface validity creates
  non-ortho, skewness, warpage, and self-intersections.
- The first implementation should prefer rejecting unsafe cases over producing
  a low-quality mesh.

Verify targeted:

```bash
AUTO_TESSELL_VERIFY_RUN_ROOT=/tmp/autotessell_stable_hole_sweep \
AUTO_TESSELL_VERIFY_CASE_LIMIT=4 \
AUTO_TESSELL_VERIFY_MAX_CELLS=10000 \
AUTO_TESSELL_VERIFY_BL_LAYERS=3 \
AUTO_TESSELL_VERIFY_ENGINES=tet \
timeout 900 python3 tests/stl/verify_autoresearch_mesh_matrix.py
```

### A3. Changing-Section Decomposition

Scope: `easy_100643`, hard/extreme cases with changing polygon counts.

Algorithm:

1. Split the sweep axis at section topology change points.
2. Mesh each sub-interval only if topology is stable inside it.
3. Insert transition slabs between different section topologies.
4. Validate transition slabs with the same side-surface guards.

This is larger than A2 and should not start until A2 can reject safely and pass
or improve at least one stable-hole case.

## Design Direction B: Closed Advancing-Layer BL

Use this for exact WildMesh cases where fidelity is good but FVM fails.

### B1. Bad BL Interface Classifier

Files:

- `core/layers/native_bl.py`
- `core/layers/layer_front.py`
- `tests/test_native_bl.py` or `tests/test_native_bl_vd.py`

Classify every failing internal face by owner/neighbour type:

- bulk-bulk
- bulk-prism
- prism-prism
- VD bridge/gap-fill

Record histogram metadata in `native_bl_quality.json`.

Gate:

- No output topology change yet.
- Metadata must identify whether bad faces come from BL interface or bulk.

### B2. Closed Layer Cavity Replacement

SMESH-like closed advancing-layer approach:

1. Identify bulk cells touching selected wall faces.
2. Remove those bulk cells from the original volume.
3. Insert prism layers.
4. Fill the cavity between prism top and remaining bulk with checked transition
   tets/poly cells.
5. Accept each transition cell only if determinant, face weight, non-ortho, and
   local topology checks improve or stay within gates.

This replaces the current "append BL while preserving bulk" topology that
creates near-tangent interface faces.

## Immediate Next Tasks

### TAW-1: implement section topology classifier

- [x] Add `_classify_axis_section_topology(...)`.
- [x] Add unit tests for `constant_prism`, `stable_hole_sweep`, and
  `changing_section_sweep`.
- [x] No mesh output behavior change.

### TAW-2: add guarded candidate validation wrapper

- [x] Build fastpath candidates in a temporary case directory.
- [x] Run native checker + fidelity before replacing the real `polyMesh`.
- [x] Reject unsafe candidates without writing partial output.
- [x] Default behavior unchanged until a replacement candidate is enabled.

### TAW-3: implement stable-hole sweep candidate behind env flag

- [x] `AUTO_TESSELL_WILDMESH_STABLE_HOLE_SWEEP=1`
- [x] Target `easy_100423`.
- [x] Must reject rather than regress if side-surface guards fail.

### BLR-1: record bad-face interface histogram

- [x] Add native BL metadata for failing internal face classes.
- [x] Target `extreme_1017013` and exact `easy_100423`.
- [x] No output behavior change.

### BLR-2: local cavity component metadata

- [x] Group bad internal faces into connected cell components.
- [x] Record sample faces/cells per component for later cavity replacement.
- [x] No output behavior change.

### Discarded: direct bad-face union

- [x] Tried env-gated prism-prism bad-face deletion/union.
- [x] Discarded because `extreme_1017013` regressed max skewness from 3.69 to
  50.22 and max aspect ratio from 93.8 to 120.0.

## Stop/Keep Rules

Keep a task only if:

- It adds guarded metadata or a rejected-by-default candidate needed for the
  topology rewrite, with tests; or
- It reduces `tet_failed_case_count`; or
- It reduces a targeted case failure count without introducing new topology
  failures.

Discard a task if:

- It improves Hausdorff but introduces non-ortho, face-weight, warpage,
  self-intersection, open edge, flipped face, or cell-count failures.
- It relies on tier fallback success instead of making the selected method
  succeed.
