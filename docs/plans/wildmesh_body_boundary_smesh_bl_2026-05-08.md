# WildMesh Body Boundary + SMESH-Style BL Redesign

Date: 2026-05-08

## Goal

Use WildMesh as the tet volume base and apply native BL only on the physical
body wall. Do not rely on fallback engines. For external flow, farfield/domain
faces must not be treated as wall faces.

## Design

### 1. External Domain Topology

Current external WildMesh input concatenates the body surface and inverted
domain box. The output writer previously labelled all tet boundary faces as
`wall_*`, so BL could grow on the farfield and fidelity checks could compare
domain faces against the original body.

The new writer path accepts a boundary patch classifier:

- domain-box boundary faces -> `farfield` / `patch`
- exposed obstacle boundary faces -> `body_wall` / `wall`

This is the patch boundary needed by the later boolean clipping step. If the
tet output still does not expose the body surface as boundary, BL now fails
clearly instead of growing on the wrong patch.

Next algorithmic step:

1. classify tet cell centroids as fluid using domain-inside and body-outside
   predicates;
2. drop solid-body cells;
3. rebuild polyMesh so the removed solid interface becomes `body_wall`;
4. run native BL with `post_layers_wall_patch_names=body_wall` and
   `post_layers_ignore_patch_names=farfield`.

### 2. SMESH-Style BL Front

The native BL selector now mirrors SMESH ViscousLayers concepts:

- `post_layers_set_faces`: explicit boundary face ids to receive layers;
- `post_layers_ignore_faces`: explicit boundary face ids to exclude;
- `post_layers_wall_patch_names`: patch-level SetFaces;
- `post_layers_ignore_patch_names`: patch-level IgnoreFaces;
- `post_layers_ignore_patch_prefixes`: domain/symmetry prefix exclusion.

The new `core/layers/layer_front.py` module builds a layer-edge front before
extrusion:

- front edges;
- boundary edges;
- non-manifold edges;
- strict mode face invalidation via `AUTO_TESSELL_BL_FRONT_STRICT=1`.

Current native BL still performs geometric extrusion, but it now has the
selection and front topology needed for advancing-front growth, per-edge stop
criteria and patch-specific fronts.

## Verification Gate

Narrow gate:

```bash
python3 -m pytest tests/test_layer_front.py tests/test_native_bl_helpers.py tests/test_tier_layers_post_bl_phase2.py tests/test_write_generic_polymesh.py -q
```

External-flow gate after boolean clipping:

```bash
auto-tessell run test_cube.stl -o /tmp/cube_ext \
  --mesh-type tet --quality draft --volume-engine wildmesh \
  --tier-param post_layers_engine=tet_bl_subdivide \
  --tier-param post_layers_wall_patch_names=body_wall \
  --tier-param post_layers_ignore_patch_names=farfield \
  --tier-param post_layers_num_layers=3
```
