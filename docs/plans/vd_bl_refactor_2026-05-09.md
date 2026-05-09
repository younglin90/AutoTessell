# Vertex Duplication BL Refactor (continuation of 2026-05-08 wildmesh BL work)

Date: 2026-05-09

## Goal

Continue the vertex-duplication boundary-layer refactor started in
`.autoresearch/tet_bl_full/vd_refactor_plan.md` so that the 21-STL bench
(test_cube + tests/stl/thingi10k_bench20/*.stl) passes tet + BL (3 layers)
per `agents/specs/evaluator.md`.

Current state (commits `79771118`, `cb867530`, `97dcd299`):
- VD-1 plan (vd_refactor_plan.md)
- VD-2 junction detector (compute_face_normals, detect_junction_verts)
- VD-3 per-face inner vert generator (generate_per_face_inner_verts)
- VD-4a prism cell topology builder (build_prism_cells)

13/13 unit tests in `tests/test_native_bl_vd.py` PASS.
Bench score: 2700 (17/21 PASS, 20/21 BL=3 exact, Plan goal achieved).

Remaining 4 STL fails attributed to per-vertex extrusion limit:
- hard_100029 (multi-patch junction skew=260)
- extreme_1017013/14 (flat sheet 5-patch)
- extreme_102308 (pytetwild SIGSEGV — separate path)

The mathematical derivation `boundary_skew = tan(theta)` (theta = angle
between avg_vnorm and face_normal) requires per-face inner verts to push
theta to 0 at junction verts. The remaining tasks build the polyMesh
plumbing for that.

## Constraints

- One file change per task. Atomic commits.
- Each task ends with `python3 -m pytest tests/test_native_bl_vd.py -q`
  passing (existing tests must stay green).
- No regression on the 21-STL bench (bench script:
  `timeout 1800 python3 .autoresearch/tet_bl_full/verify.py 2>&1 | tail -3`).
  Expected score baseline 2700; goal 2800+ once VD wired in.
- VD code stays env-gated (`AUTO_TESSELL_BL_VD_ENABLE=0` default).

## Verification

After every task:
1. `python3 -m pytest tests/test_native_bl_vd.py -q` (unit tests)
2. `git status` (no unintended files)
3. Optional: bench (`timeout 1800 python3 .autoresearch/tet_bl_full/verify.py 2>&1 | tail -3`)

The bench is expensive (~15-30 min); only run after a wiring task that
could affect the pipeline output. Document any score change in the commit
message.

---

### Task 1: VD-4b — convert prism cells to OpenFOAM polyMesh format

Add `cells_to_polymesh(cell_face_verts)` to
`core/layers/native_bl_vd.py` that converts the prism cell list into
OpenFOAM-compatible `faces`, `owner`, `neighbour` lists plus a list of
boundary face indices grouped by patch hint (currently just
"wall"=bottom face of prism, "bl_internal"=top face, "bl_internal_side"=
side quad without a sharing neighbour).

Algorithm:
1. For each cell, for each face in `cell_face_verts[cell]`, build a
   canonical key `tuple(sorted(verts))` (face equality is unordered).
2. Collect occurrences `face_key -> list[(cell_id, face_idx_in_cell, raw_verts)]`.
3. Faces appearing exactly twice -> internal: `owner=min(cells)`,
   `neighbour=max(cells)`. Use the `raw_verts` from the lower-cell
   occurrence to preserve outward winding from the owner cell.
4. Faces appearing exactly once -> boundary. Owner is the only cell.
5. Patch classification (single layer of prisms only for now):
   - face is bottom face of prism (face_idx_in_cell == 0) -> `wall`
   - face is top face (face_idx_in_cell == 1) -> `bl_internal`
   - face is side quad (face_idx_in_cell in [2,3,4]) -> `bl_internal_side`
6. A face shared by 3+ cells -> raise `ValueError` (topology error).

Return a dataclass `PolyMeshResult` with fields:
- `points: ndarray` (passed-through)
- `faces: list[list[int]]`
- `owner: list[int]`
- `neighbour: list[int]`
- `patches: list[dict]` with `name`, `startFace`, `nFaces`

Order in `faces`: internal first (sorted by `(owner, neighbour)`), then
boundary grouped by patch (`wall` -> `bl_internal` -> `bl_internal_side`).
This matches the OpenFOAM convention (internal faces have neighbours;
boundary faces only own).

Write 4-5 unit tests in `tests/test_native_bl_vd.py`:
- flat strip (2 prisms): expect 1 internal side quad shared between
  prisms (when verts non-junction), and N boundary faces in each patch
- cube (12 prisms): all junction so no shared internal faces; all 60
  faces (12*5) are boundary
- single prism: 5 boundary faces, 0 internal
- topology error: 3+ occurrences raise ValueError
- patches list ordering: wall before bl_internal before bl_internal_side

Files changed: `core/layers/native_bl_vd.py`, `tests/test_native_bl_vd.py`.

Verify: `timeout 60 python3 -m pytest tests/test_native_bl_vd.py -q`.

---

### Task 2: VD-5 — gap-filling cells at junction edges

Add `build_gap_fill_cells(wall_face_indices, faces, points, inner_result)`
that closes the topology hole at junction edges where adjacent prisms
have different inner verts.

For each wall edge `(v, w)` shared by two faces `f1, f2`:
- Look up `vi1 = inner[(f1, v)]`, `wi1 = inner[(f1, w)]`,
  `vi2 = inner[(f2, v)]`, `wi2 = inner[(f2, w)]`.
- If all four are distinct (i.e. the edge is a junction edge):
  Insert TWO tetrahedra to close the gap:
  - tet A: `(v, w, wi1, vi1)`
  - tet B: `(v, w, vi2, wi2)`

(For three-way junctions where 3+ faces meet at the same edge, use a
fan triangulation. Add an explicit branch for that case if any test STL
exhibits it; otherwise raise NotImplementedError in this iteration.)

Return `cell_face_verts` for the gap-fill cells in the same format as
`build_prism_cells` returns.

Tests:
- flat strip (2 prisms, no junction edges): 0 gap-fill cells
- cube (12 prisms, 18 unique edges shared by 2 perpendicular faces each):
  expected 18*2 = 36 gap-fill tets
- vertex 3-way junction error or fan: explicit assertion

Files changed: `core/layers/native_bl_vd.py`,
`tests/test_native_bl_vd.py`.

Verify: `timeout 60 python3 -m pytest tests/test_native_bl_vd.py -q`.

---

### Task 3: VD-6 — combined polyMesh for prisms + gap fill

Wire `build_prism_cells` + `build_gap_fill_cells` into a single
`build_full_bl_polymesh()` that returns the merged polyMesh result.

Merge cells (prisms first, then gap-fills), re-run cells_to_polymesh on
the combined cell list. Side quads of adjacent prisms that previously
were boundary (because of vertex duplication) should now share faces
with neighbouring gap-fill tets and become internal.

Test: after merge, the cube example should have a connected polyMesh
where the only boundary faces are the bottom (wall), top
(bl_internal), and the OUTER side quads on the cube edges. No interior
holes.

File: `core/layers/native_bl_vd.py`, `tests/test_native_bl_vd.py`.

Verify: pytest unit tests pass.

---

### Task 4: VD-7 — multi-layer BL stack with per-face dup

Extend the single-layer prism builder so a stack of N layers can be
emitted. Each layer's outer = previous layer's inner; thickness grows
geometrically per `growth_ratio`.

For multi-layer: layer 1 cap = layer 2 base = shared between adjacent
layers (no extra dup). Layer 1 wall = original wall. Layer N inner =
bl_internal_domain boundary patch.

Add a `build_multi_layer_bl(...)` function with signature similar to
`build_prism_cells` but accepting `num_layers` and `growth_ratio`.

Test: cube with 3 layers => 12*3 = 36 prism cells, each layer's caps
are correctly shared.

File: `core/layers/native_bl_vd.py`, `tests/test_native_bl_vd.py`.

Verify: pytest passes.

---

### Task 5: VD-8a — wire VD into native_bl path (env-gated)

In `core/layers/native_bl.py`, after the existing per-vertex extrusion
path, add an env-gated alternative path:

```
if os.environ.get("AUTO_TESSELL_BL_VD_ENABLE", "0") == "1":
    from core.layers.native_bl_vd import build_multi_layer_bl, ...
    # build VD polyMesh, write it instead of the per-vertex result
```

Default OFF so existing 21-STL bench is unaffected.

Verify: bench with VD off (default) still 2700.
Verify with VD on, `hard_100029` boundary skew should drop drastically
(target < 20 to PASS evaluator soft threshold).

Files: `core/layers/native_bl.py`,
optional helper in `core/layers/native_bl_vd.py`.

Verify:
1. pytest passes.
2. `AUTO_TESSELL_BL_VD_ENABLE=0 timeout 1800 python3 .autoresearch/tet_bl_full/verify.py 2>&1 | tail -3` reports 2700.
3. `AUTO_TESSELL_BL_VD_ENABLE=1 timeout 1800 python3 .autoresearch/tet_bl_full/verify.py 2>&1 | tail -3` runs to completion (regardless of score).

---

### Task 6: VD-8b — per-STL VD enable list + bench validate

Add `AUTO_TESSELL_BL_VD_FOR=hard_100029,extreme_1017013,extreme_1017014`
support so VD only activates on STLs known to need it. Default empty
string means "off everywhere".

Run the bench with that list and confirm score >= 2700 (no regression)
and ideally improves.

File: `core/layers/native_bl.py`,
documentation in `.autoresearch/tet_bl_full/vd_refactor_plan.md`.

Verify:
1. pytest passes.
2. Bench with the targeted env list runs >= 2700.

---

## Out of scope (for later)

- pytetwild SIGSEGV on `extreme_102308` (upstream fTetWild bug).
- Anisotropic mesher for ultra-flat sheets (separate work).
- GUI / docs / CLI changes.

The acceptance criterion for THIS plan: every unit-test task green,
final VD-enabled bench >= 2700, and the codebase has the building
blocks (junction detection, per-face inner verts, gap fill,
multi-layer wiring) ready for further iteration in a future plan.
