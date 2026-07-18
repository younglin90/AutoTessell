# AutoTessell Roadmap

Two products, one platform:

- **Track A — Meshing** (this repo's shipped core): surface input → native
  volume engines (tet/hex/poly) → export. Spec set 2026-07-18.
- **Track B — CFD Surrogate / Digital-Twin platform** (new, spec + architecture
  review 2026-07-18): CFD *results* in → data contract → strategy registry of
  operator-learning models → fair evaluation → (eventually) operational twin.
  Full contract: `docs/TWIN_PLATFORM_SPEC.md` — the authority for Track B;
  this file only sequences it.

Meshing is upstream of solving (OpenFOAM), which is upstream of the twin
platform. They share real subsystems (below), but their maturity is very
different: Track A is mid-flight with measured gates; Track B starts at its
own Stage 0 (data contract) by explicit design — *"데이터 계약과 평가 프로토콜을
먼저 고정하고 모델을 순차적으로 추가한다."*

## Governing invariants

1. **(Track A, spec "최중요사항")** The pre-meshing surface must not be altered
   by volume meshing and must be preserved exactly in the final mesh. Enforced
   today for native_tet by permanent gates (surface-area identity, zero
   off-surface boundary, cylinder wall dev 0.000). Outranks every other goal.
2. **(Track B, spec §16)** The platform's core asset is the **data contract,
   transformation lineage, compatibility judgement, and fair evaluation** —
   not any particular network. No model lands before Stage 0 is fixed.
3. **(Both)** GUI never runs heavy compute in-process. Track A already runs
   meshing in a server/worker; Track B formalizes this as job-spec'd worker
   processes (CPU/MPI/GPU) — one job model for both tracks.

---

## Track A — Meshing                                          **~60%**

### A-1 Surface input                                         ~45%
Done: STL/OBJ/PLY/OFF/3MF/STEP/IGES/BREP readers; global integrity checks;
L1/L2/L3 auto-repair pipeline.
Missing: multi-file upload, Boolean merge, per-defect localization +
selective repair UI.
- **S1 Multi-file upload + assembly/patch naming** — also feeds Track B's
  BoundaryPatch entities and per-patch BL.
- **S2 Boolean merge** via fTetWild-style per-input winding numbers (volume
  judgement, not surface CSG — preserves invariant 1; same mechanism the twin
  spec cites for mesh arrangement).
- **S3 Defect localization + per-item auto-fix choice** (spec §8 editor flow:
  patch import → seed → region growing → normal threshold → lasso → validate).
  The §8 validator list (duplicate faces, unassigned faces, periodic pairs,
  normals, units) applies verbatim.

### A-2 Volume engines                                        ~60%
- **native_tet ~70%**: solid gates green (cube P4C=0, PASS, skew 1.81);
  cylinder fidelity 0.000 and skew 4160→44.9 (2026-07-18). The residual 44.9 is
  **structural**, not a tuning gap: cylinder.stl has only two side-wall z-rings
  (z=±0.5), so any wall-conforming tet is a full-height flat cap with tiny
  normal_dist. Three fixes were measured and refuted (flip, boundary-edge split,
  re-smooth — R-c7 in attempts_catalog); the only route is **near-wall interior
  point insertion** (Garimella offset ring), a multi-card effort. Remaining:
  near-wall insertion, 12-STL hard-geometry bench, full 4-op schedule (flip
  inversion-safety landed). SI-detection memoization landed (2026-07-18,
  zero-regression dedup of the rebudget loop's repeated calls) but did NOT
  fix the bench's 3 TIMEOUT shapes (sphere, sphere_watertight,
  high_genus_dual_torus) — direct instrumentation showed SI detection was
  never the bottleneck (~1.2s/call, not the ~17.8s a log-gap estimate
  implied). Open: profile the tet generation/CDT/quality passes themselves
  to find what actually dominates sphere.stl's ~130s.
- **native_hex ~40%**: solid gates green on the cube (surface 6.000/void
  0.000/vol 1.000/degen 0, skew 3.6e-16). Curved-wall **staircase** fixed
  (2026-07-18): per-vertex wall-fit snap (envelope-projected, accepted only
  on strictly-decreasing surface distance + positive-volume/orientation
  guard on every incident cell) closed cylinder standard wall_dev_max
  0.0466→0.0032 (gate <0.02, now a permanent test, not xfail); negative
  volumes 0. Next: extend the same guard to fine quality, then hex quality
  (skew currently 4.64 post-snap — bounded but unoptimized).
- **native_poly ~15%** (unmeasured): port the tet methodology — canonical
  smoke, solid gates, then quality.
- Common: N-targeting (tet+netgen done; hex/poly open), BL growth-ratio GUI
  done, per-patch BL toggles blocked on S1, MPI absent, threading partial.
  Parallelism deliberately LAST (invariant: correctness gates must be able to
  catch parallel nondeterminism first — the dead-zone lesson).

### A-3 Export                                                ~90%
10 formats live. Remaining: per-format fixtures; patch-name round-trip after
S1. Note: Track B ingests VTK/CGNS — CGNS *export* from the mesher becomes a
bridge deliverable (mesh + patch/BC semantics feed the twin's canonical store).

## Track B — Surrogate/Twin platform                          **~0% (spec fixed)**

Stages and exit criteria are authoritative in `docs/TWIN_PLATFORM_SPEC.md` §15;
integration tiers in §10/§16. Summary sequencing:

- **B0 Data contract** — canonical schema, field/BC ontology, unit/coordinate
  rules, topology/geometry hashes, DatasetSignature, plugin capability
  contract, license inventory. *Shared with Track A*: patch/BC ontology (S1),
  geometry/topology hashing (the mesher already computes surface hashes for
  fidelity gates — reuse).
- **B1 Load + Viewer MVP** — VTK/CGNS readers, patch import, region-growing
  selection, BC editor, wall distance/masks, raw+canonical stores. *Shared*:
  the boundary editor is the same component A-1/S3 needs; build once.
- **B2 Preprocessing + baselines** — versioned DAG, group splits before
  normalization, remap-error floor, Zarr cache, POD/PCA + PyDMD + OpInf +
  FNO/TFNO, MLflow, truth/pred/error viewer.
- **B3 Unstructured + varying geometry** — Transolver, GINO, MGN transient,
  query outputs, ensemble/OOD display.
- **B4 Large 3D + HPC** — DDP/FSDP, MPI preprocessing, halo/patch, DoMINO,
  AB-UPT, scheduler backends, checkpoint/resume.
- **B5 Research track** — Transolver-3, PGD-NO behind reproduction gates.
- **B6 Operational twin** — sensor streams, assimilation, drift detection,
  two-way interface.

MVP data combos (spec §16): same-geometry structured (ROM+FNO) →
varying-geometry unstructured steady (Transolver+GINO) → fixed-topology
unstructured transient (MGN). Hardest last: varying geometry + transient +
changing topology.

## Shared subsystems (build once, serve both)

| Subsystem | Track A use | Track B use |
|---|---|---|
| Patch/BC ontology + boundary editor | per-patch BL, BC export | BoundaryPatch/BCInstance entities (B0/B1) |
| Geometry/topology/coordinate hashes | mesh identity, fidelity gates | DatasetSignature geometry_relation (B0) |
| Job manager + worker process split | long meshing jobs, cancel/resume | MPI/GPU training jobs (B4) — same job spec |
| Viewer (VTK/WebGL) sync'd compare | mesh QC (KPI, colormaps) | truth/pred/error modes (B2, spec §11) |
| CGNS I/O | mesh+BC export (A-3 bridge) | canonical store (B0-B1) |

## Sequencing (near-term)

```
now      A: cylinder ≤8.0 (cap-sliver card) · hex smoke+gates 캠페인 시작
next     S1 multi-file+patch naming  ←— unblocks A per-patch BL AND seeds B0
         A: 12-STL tet hard-geometry bench
then     B0 data contract (schema/ontology/hashes/DatasetSignature) — design
         doc first, validator second;  S2 boolean merge (winding-number)
later    B1 viewer+readers (shared boundary editor) · V3 hex quality ·
         B2 baselines (ROM before any neural operator — 누수 검출 기준선)
last     parallel/MPI (A V5, B B4) · B5/B6
```

## Method (keep)

Measure before planning (guessing refuted 4+ times) · one canonical
measurement script per geometry · primary-source diffs against vendored
references · relative before/after guards, never absolute · surface
preservation and (for B) train-only fitting + group splits as non-negotiable
floors · new models enter through the strategy registry with declared
capabilities, disabled (not warned) when incompatible.
