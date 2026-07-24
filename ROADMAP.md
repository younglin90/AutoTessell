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

## Track A — Meshing                                          **~65%**

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

### A-2 Volume engines                                        ~65%
- **native_tet ~75%**: solid gates green (cube P4C=0, PASS, skew 1.81);
  cylinder fidelity 0.000, skew 4160→44.9→**40.8** (2026-07-18, see below).
  **Coverage-collapse cluster closed (3/3)**: `high_genus_dual_torus.stl`
  (BETA2832 — `_final_validate`'s unconditional keep-largest-component was
  discarding a whole disjoint torus body; replaced with a relative guard,
  area/vol-ratio 0.56/0.47→1.01/1.01), `many_small_features_perforated_plate.stl`
  (BETA2833 — the same destructive clamp lived one layer upstream in L1
  pymeshfix's `remove_smallest_components`; fixed with per-component repair +
  an aggregate guard so many-small-bodies inputs can't be filtered away
  piecemeal even when no single body trips the 5%-of-max threshold),
  `sharp_features_micro_ridge.stl` (SHARPRIDGE1 — L2's cotan Laplacian
  smoothing has no free-boundary pin and was collapsing a thin open ridge
  to a point; added the same monotone area/Hausdorff revert-guard pattern).
  All three verified via the same canonical bench script, all three fixes
  are pure relative guards that no-op on healthy single-body input.
  **Sphere-class TIMEOUT cluster closed**: `core/utils/aabb.py`'s BVH leaf
  routine was called once per query point (660k scalar calls, 71% of
  profiled wall) instead of batched; vectorizing it dropped cumtime
  62.4s→2.8s and took `sphere.stl`/`sphere_watertight.stl` from 143s
  TIMEOUT to 29s PASS. The same investigation caught a **pre-existing
  correctness bug** in `TriangleBVH.build()` (a local argsort rank written
  as if it were a global triangle id, corrupting `tri_order` below the
  root — backs every envelope/hausdorff/cdt_recovery/signed_distance query
  project-wide) — fixed, ~80 BVH-adjacent tests unchanged.
  **Flat-all-surface-sliver sequence closed (FSL1→FSL4)** on dual_torus's
  residual quality FAIL: detector (read-only) → guarded 2-3 flip
  (infrastructure proven safe, but 0/9 eligible slivers were actually the
  FAIL driver — correctly a no-op) → known-limit gates (61 unflippable
  wedges are structurally coplanar-flat, cure needs the same
  near-wall-insertion class of fix as cylinder skew, out of scope; volume
  tiling locked at 0.99 so it can never silently regress, cure target
  pinned as xfail(strict) so a future fix trips a loud alarm instead of
  going unnoticed). **CYLSKEW1** landed the first card of that
  near-wall-insertion sequence (Garimella offset-ring seeding, default OFF,
  seeding-stage-only hook, proven not to leak onto the boundary) — as an
  unplanned bonus, even this unrefined seeding measured skew 44.9→40.8
  before any of the filtering/guarding follow-up cards.
  Sequence continued (CYLSKEW2-4): the originally-planned wall-adjacent
  filter was measured and falsified twice (cylinder has no pure side-wall
  vertex to filter for since it only has 2 z-rings; sphere's regression at
  N=500 is a holistic seed-density effect, not a per-vertex class problem),
  redirecting the sequence to a monotone best-of-two selector instead:
  scale-invariant guards (CYLSKEW2), a pure decision function verified
  against 3 measured cases including sphere's default-ON-breaking regression
  (CYLSKEW3), and wiring via a cheap pre-optimization Delaunay proxy since
  full best-of-two doubles bench time past budget (CYLSKEW4, default path
  unchanged, proxy/final correlation still open — the one case checked
  disagreed with the known-good full-pipeline result, flagged for CYLSKEW5).
  **Coverage-collapse-adjacent quality cluster** (naca0012, was FAIL from
  degen 17 + skew 58.83): THINSLIVER1 closed most of the degenerate axis
  (22->11 in a controlled config, correctness win, permanent regression
  lock + xfail(strict) for the remaining higher-valence victims). THINSLIVER2
  set out to fix the skew axis but, on independent reconfirmation, measured
  zero effect on the *current* baseline (which had already dropped from
  82.44 to ~60.3 via the cards above stacking) — the 123-line mechanism was
  discarded rather than kept as unexercised complexity; what's real (the
  ~60.3 state) is now a regression-locked permanent gate. A real skew fix
  needs fresh diagnosis against that baseline, not the stale one.
  Remaining: 12-STL hard-geometry bench sweep beyond the shapes closed so
  far, full 4-op schedule, CYLSKEW5 (proxy/final correlation, default-ON).
- **native_hex ~45%**: solid gates green on the cube (surface 6.000/void
  0.000/vol 1.000/degen 0, skew 3.6e-16). Curved-wall **staircase** fixed on
  both quality levels (3-card sequence, all permanent gates now):
  (1) per-vertex wall-fit snap (envelope-projected, accepted only on
  strictly-decreasing surface distance + positive-volume/orientation guard
  on every incident cell) closed cylinder standard wall_dev_max
  0.0466→0.0032; (2) envelope generalized to per-vertex local sizing
  (fTetWild-style) — measured harmless but not the fine blocker
  (n_reject_envelope=0 before/after); (3) root cause was the guard's
  all-or-nothing structure: full projection got reverted entirely on any
  face flip even though 39/39 rejected vertices had a safe partial move
  (binary-search fraction t*, min 0.706). Backtracking to the largest t*
  that still passes the *same* unmodified guard (no relaxation) took fine
  wall_dev_max 0.0353→0.008 (gate <0.02); negative_volumes=0 throughout.
  Follow-up: post-snap boundary skew (4.64) was decomposed to its root
  (wall-fit snap collapses the boundary cell's wall-normal thickness |nd|);
  freezing surface vertices and relaxing only the free interior vertices of
  flagged sliver cells restored it to 2.84 (new permanent gate ≤3.0) with a
  bonus fix — fine's pre-existing (undetected) negative_volumes=8 dropped to
  0 too, now permanently gated on both quality levels. Next: further skew
  reduction, then extend the solid-preservation methodology to poly.
- **native_poly ~40%** (measured and closed 2026-07-18, S1→S4): canonical
  smoke (`scripts/smoke_native_poly.py`) + all **4 solid invariants now
  permanent gates** on cube.stl, matching tet and hex's status. S1 measured
  a blind verdict=PASS hiding void 7.588 and volume 1.177x. S2's working
  hypothesis (boundary open-wall) was disproved by measurement — the real
  cause was tet->dual's per-cell ConvexHull triangulating each non-planar
  interior dual interface differently, so adjacent cells' shared face never
  vertex-matched and leaked as void on both sides; fixed with a topological
  path (each interior tet edge's ordered centroid ring emitted directly as
  the shared face) — void 7.588→2.435. S3 found two more boundary-only bugs
  in the same file (cap faces over-classified as boundary; boundary-edge
  seams between adjacent boundary cells had no separating face) — void
  →**0.000 exactly**. S4 root-caused the residual volume overfill (1.077x)
  with a controlled experiment: feeding dual.py's *unmodified* code a
  well-formed Kuhn tetrahedralization gives Sigma|vol|=1.0000 exactly, so
  the dual construction itself was never the bug — native_tet's interior
  Steiner points make sliver tets whose non-convex dual cells the
  pyramid-volume measure overestimates. Laplacian-smoothing only the
  interior tet vertices (boundary fixed, so surface/void stay
  structurally unchanged) pulled volume to 1.026 and even improved skew
  (0.457→0.422). Next (POLY-S5): generalize past the cube (sphere/cylinder),
  then quality.
- **native_poly Phase 0 FV census (2026-07-24):** report-only face planarity,
  normal spread, Juretić ψ, h, Circle Ratio, sphericity, and Uniformity Factor
  metrics are now emitted by `NativeMeshChecker`; no quality gate was changed.
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
now      A: CYLSKEW2-4 (near-wall insertion, wall-filter + monotone guard)
         · POLY-S4 (boundary-cell overfill) · hex skew reduction
next     S1 multi-file+patch naming  ←— unblocks A per-patch BL AND seeds B0
         A: 12-STL hard-geometry bench sweep beyond the closed cluster
then     B0 data contract (schema/ontology/hashes/DatasetSignature) — design
         doc first, validator second;  S2 boolean merge (winding-number)
later    B1 viewer+readers (shared boundary editor) ·
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
