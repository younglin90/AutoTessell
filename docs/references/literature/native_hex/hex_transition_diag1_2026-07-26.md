# HEX-TRANSITION-DIAG1 — report-only transition-chain cross-tab

Date: 2026-07-26
Status: **BLOCKED — exact transition cross-tab not measurable from the current fixtures**
Scope: `native_hex` diagnostic code, explicit script, test, and result only

## Literature-to-measurement contract

Elsheikh 2014 (DOI `10.1016/j.advengsoft.2014.05.005`) is a generation-time
octree conditioning/template method. Its hanging-node elimination uses
refinement and decoupling templates, so its evidence requires the refinement
field and the topology of the transition, not merely the final point/cell
coordinates. It is not a post-snap repair to be enabled in native_hex.

The Chen transition-chain abstract describes an adaptive octree core, a search
template that locates hanging nodes in a transition chain, template-based
elimination, and a positive scaled-Jacobian quality result. For this card, that
supports a report-only join over:

`transition_chain_id × hanging_node_valence × template_class × face_warpage × local_scaled_Jacobian × patch/provenance`.

No production mesh-generation, quality-gate, or route change is authorized by
this card.

## What was reused and measured

`scripts/diag_hex_transition1.py` calls the existing
`analyze_patch_layer_subsets` implementation from PATCH-LAYER-DIAG1. It keeps
the existing writer-equivalent feature patch grouping and explicit
`defaultWall` reconstruction mode. It also measures geometry-only baselines:

- Chen-style quad-face warpage `1 - min(n0·n2, n1·n3)`, for unique faces and
  physical boundary faces;
- minimum absolute local corner scaled-Jacobian magnitude per clean hex cell.

Those values are reported as baselines only. The implementation does not infer
transition chains, valence, template names, or source provenance from geometry.

## Fixture audit

The existing PATCH-LAYER-DIAG1 cache blobs were inspected:

| shape | cache | fields | points | cells |
| --- | --- | --- | ---: | ---: |
| cylinder | `/tmp/hexmatch/cylinder_8000.npz` | `points`, `cells` | 9261 | 6320 |
| sphere | `/tmp/hexmatch/sphere_8000.npz` | `points`, `cells` | 9261 | 4224 |
| gear | `/tmp/hexmatch/gear_8000.npz` | `points`, `cells` | 11767 | 4914 |

The blobs contain none of the following:

1. per-cell octree level plus stable leaf lineage/origin;
2. per-face `transition_chain_id` and `hanging_node_valence`;
3. the emitted `template_class`;
4. authoritative per-boundary-face patch and source provenance.

The existing patch-layer reconstruction supplies only a writer-equivalent
feature patch and the known single-source label `defaultWall`; it is not an
authoritative provenance record. Consequently, an exact cross-tab for
cylinder/sphere/gear cannot be truthfully computed from these fixtures.

## Result

Running:

```text
python scripts/diag_hex_transition1.py --cache-dir /tmp/hexmatch --max-cells 8000
```

returned `status=BLOCKED` for all three shapes. PATCH-LAYER-DIAG1 was rerun
twice per cache by its existing runner and remained deterministic:

| shape | PATCH-LAYER decision | components | eligible S/Q | approved operations |
| --- | --- | ---: | ---: | ---: |
| cylinder | `KILL` | 6 | 544 / 544 | 0 |
| sphere | `KILL` | 6 | 24 / 24 | 0 |
| gear | `KILL` | 22 | 888 / 888 | 0 |

No transition-chain/valence/template/provenance cross-tab or before/after
quality claim is made. The new script reports the available geometry baseline
and the blocker, but never mutates or regenerates a mesh.

The geometry-only output was:

| shape | all-face warpage (p50 / p95 / max) | boundary warpage (p50 / p95 / max) | finite local SJ magnitude (n / min / p50 / max) |
| --- | --- | --- | --- |
| cylinder | 0 / 0.000656 / 1.000000 | 0 / 0.016690 / 0.523079 | 6320 / 1.66e-8 / 1.000000 / 1.000000 |
| sphere | 0 / 0.415846 / 0.818809 | 0.000002 / 0.136864 / 0.388541 | 4224 / 0.000767 / 1.000000 / 1.000000 |
| gear | 0 / 0.326013 / 1.000000 | 0 / 0.382081 / 1.000000 | 4790 / 0 / 0.856497 / 1.000000 |

The local SJ column is an absolute corner-Jacobian magnitude baseline, not a
signed validity gate. Gear has 4790 finite values out of 4914 cells; the
remaining cells do not have a canonical 3-edge-per-vertex hex neighborhood in
the cached shell and are intentionally excluded rather than assigned a value.

## Required next fixture

Export one sidecar bundle per pre-BL mesh, joined by stable cell/face IDs, with
the four metadata groups above. A minimal NPZ/JSON contract is:

```text
cell_level[N], cell_origin[N,3] or stable_leaf_id[N]
transition_chain_id[F], hanging_node_valence[F]
template_class[N]
face_patch[F], face_source_provenance[F]
```

The face table must identify the exact cyclic face vertices/owner cell used by
the `points`/`cells` cache. Without that join key, even a separately exported
transition table cannot be cross-tabulated safely. Once supplied, the same
report-only runner can be extended to emit the requested cross-tab before any
template or repair implementation is considered.

## Verification

The new unit tests cover: blocked status when only `points`/`cells` exist,
reuse of PATCH-LAYER-DIAG1, no input mutation, zero warpage and unit local
scaled-Jacobian magnitude on a unit cube. Existing
`tests/test_native_hex_patch_layer_diagnostic.py` remains unchanged and was run
with the new test.
