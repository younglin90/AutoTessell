# AutoTessell Product Roadmap

Derived from the product spec set 2026-07-18. Three pillars — surface input,
volume meshing, export — plus cross-cutting invariants. Status is **measured**
against the current codebase, not aspirational; percentages cite the evidence.

## Governing invariant (spec: "최중요사항")

> The pre-meshing surface must not be altered by volume meshing and must be
> preserved exactly in the final mesh. **This outranks every other goal.**

Status: this is now enforced for native_tet and measured by permanent gates —
surface coverage exactly equals the input area (6.000/6.000 on the cube),
zero off-surface boundary area, side-wall deviation 0.000 on the curved
cylinder (`tests/test_native_tet_solid_volume.py`,
`scripts/smoke_native_cylinder.py`). Every future engine change must keep
these gates green; the same gates must be generalized to hex/poly (open).

---

## Pillar 1 — Surface input                                  **~45%**

| Item | Status | Evidence / gap |
|---|---|---|
| Load STL/OBJ/PLY/OFF/3MF/STEP/IGES/BREP | **Done** | native readers + CAD tessellation (`core/analyzer/`) |
| Integrity check (manifold, watertight, self-intersection) | **Done (global)** | `geometry_analyzer` topology report |
| Problem *localization* + user notification | **Partial** | analyzer reports counts, not regions; GUI shows summary only |
| Auto-repair (L1 repair / L2 remesh / L3 reconstruct) | **Done (pipeline)** | `core/preprocessor/`; runs as a pipeline stage |
| Per-problem *selective* repair (user chooses per finding) | **Missing** | repair is all-or-nothing today |
| Multiple surface inputs | **Missing** | `desktop/server.py` upload is single-file |
| Boolean merge of multiple surfaces (user-chosen operator) | **Missing** | no mesh-arrangement/CSG anywhere in `core/` |

Next steps (order):
1. **S1 Multi-file upload + assembly list** (server + GUI; each part gets a
   patch name — also the foundation for per-face BL toggles in Pillar 2).
2. **S2 Boolean merge** — reference: fTetWild's volumetric mesh-arrangement
   (papers/02, §filtering: per-input winding numbers evaluate arbitrary
   Boolean expressions). This is the native-first route: insert all surfaces,
   keep tets by Boolean of winding numbers — no fragile surface-surface CSG.
3. **S3 Problem localization UI** — per-defect list (open edges, non-manifold
   edges, self-intersections) with viewer highlighting and per-item
   "auto-fix?" choice driving the existing L1/L2 machinery.

## Pillar 2 — Volume meshing                                 **~55%**

Engines: native_tet (baseline: WildMesh/fTetWild), native_hex (baseline:
cfMesh/snappyHexMesh), native_poly. Mesh type is an explicit user choice
(Auto removed 2026-07-18); default engine is Native Tet.

### 2a. native_tet                                           **~65%**
| Item | Status | Evidence |
|---|---|---|
| Solid correctness (surface/void/tiling/degenerate) | **Done (cube)** | 4 permanent gates, all green, P4C=0 |
| Quality: cube draft standalone | **Done** | skew 1.81 (threshold 8.0), verdict PASS, P4C=0 |
| Quality: curved (cylinder) standalone | **In progress** | fidelity done (dev 0.000); skew 4.16e3 → BETA2828 card in build |
| N-targeting | **Done** | 99x overshoot → ±3% for N≥2000 |
| Full 4-op improvement schedule (split/collapse/swap/smooth) | **Open** | flip inversion-safety landed (ed56fd31); schedule not wired |
| Hard-geometry bench (12 STL matrix) | **Open** | untested standalone |

### 2b. native_hex                                           **~15% (unmeasured)**
Exists (`core/generator/native_hex/mesher.py`) but has had no correctness
campaign. Next: port the tet methodology — canonical smoke script, solid
invariant gates (surface area identity, void=0, volume tiling), then quality.

### 2c. native_poly                                          **~15% (unmeasured)**
Same approach; known issue: poly BL hybrid pass produces 1280 negative-volume
prisms (pre-existing, documented in test_bl_numerical_quality).

### 2d. Common engine features
| Item | Status | Gap |
|---|---|---|
| Target cell count N | **tet done, netgen done** | hex/poly unwired |
| Boundary layers (count + growth ratio) | **Done (native_bl)** | growth ratio in GUI (2026-07-17) |
| BL only on user-enabled faces | **Partial** | `ignore_patch_names` exists in BLConfig; no GUI face/patch toggles (depends on S1 patch naming) |
| BL element type per engine (prism/hex/poly) | **Partial** | prism done; tet_bl_subdivide conformal (fixed); hex/poly BL via cfMesh dicts only |
| Quality (skew / non-ortho / aspect ratio) | **In progress** | KPI panel shows all three (2026-07-17); engine-side: tet cube at reference-class |
| MPI parallelism | **Missing** | no mpi4py anywhere |
| Multithreading | **Partial** | chunked-Delaunay helper exists (`native_tet/parallel.py`); smoothing/insertion single-threaded |

Next steps (order):
1. **V1 Finish tet curved quality** (BETA2828 in build) → cylinder PASS.
2. **V2 Tet hard-geometry campaign** — 12-STL bench standalone, fix walls
   found, then wire the full 4-op schedule (now unblocked).
3. **V3 Hex correctness campaign** (gates first, quality second) — this is
   where the cfMesh/snappy baseline porting begins in earnest.
4. **V4 Per-patch BL toggles** (after S1) + poly BL negative-prism fix.
5. **V5 Parallel**: multithread the improvement passes (graph-coloring vertex
   smoothing per fTetWild §3.5), then MPI domain decomposition — last, since
   correctness gates must be able to catch parallel-induced nondeterminism
   (lesson: the [0.15,0.18) dead-zone hunt).

## Pillar 3 — Export                                          **~90%**
polyMesh ZIP + VTU/VTK/Fluent/CGNS/SU2/Nastran/Tecplot/STL/OBJ/PLY are live in
the web GUI. Remaining: per-format regression fixtures and patch-name
round-trip fidelity once S1 lands multi-part naming.

---

## Sequencing (near-term)

```
now      V1 cylinder quality (in build)
next     S1 multi-file+patches ──┬── V2 tet hard-geometry bench
                                 └── V4 per-patch BL (needs S1)
then     S2 boolean merge (winding-number route)
         V3 hex campaign
later    S3 selective-repair UI, V5 MPI/threads, export fixtures
```

Method notes that got us here (keep): measure before planning (guessing was
refuted 4+ times), one canonical measurement script per geometry, primary-
source diffs against vendored fTetWild, relative (before/after) guards never
absolute ones, and the surface-preservation gates as the non-negotiable floor.
