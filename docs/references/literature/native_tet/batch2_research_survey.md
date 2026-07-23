# Native Tet literature survey — batch 2

Date: 2026-07-23

Scope: additional literature for the Native Tet engine, deliberately excluding the three papers already covered in batch 1 (Shewchuk 1998 Delaunay refinement, Si 2015 TetGen, and Hu et al. 2020 fTetWild). The survey separates an exact boundary-preserving PLC/CDT path from a tolerance-bounded triangle-soup/Wild path.

## Evidence and access matrix

| Paper | Primary target | Intended geometry / format contract | Access and reading status | DOI or stable identifier |
|---|---|---|---|---|
| Shewchuk (2002), *Constrained Delaunay Tetrahedralizations and Provably Good Boundary Recovery* | segment/facet recovery; boundary preservation | valid 3D PLC; constrained segments and polygonal facets; output CDT/CCDT | `FULL_TEXT_READ`; public author PDF, 12 pages; text and representative figures inspected | No DOI located; public paper ID/URL: `https://people.eecs.berkeley.edu/~jrs/papers/cdtbasic.pdf` |
| Diazzi et al. (2023), *Constrained Delaunay Tetrahedrization: A Robust and Practical Approach* | robust exact PLC recovery | valid PLC; output exact/rational Steiner CDT, optionally rounded to floating point | `FULL_TEXT_READ`; public arXiv author manuscript, 15 pages; text and figures inspected | `10.1145/3618352`; arXiv:`2309.09805` |
| Hu et al. (2018), *Tetrahedral Meshing in the Wild* | soup tolerance, validity, repair, quality | arbitrary triangle soup, tolerance epsilon, target edge length; output approximately constrained tet mesh | `FULL_TEXT_READ`; public author PDF, 14 pages; text and figures inspected | `10.1145/3197517.3201353` |
| Wang et al. (2020), *Exact and Efficient Polyhedral Envelope Containment Check* | exact surface-deviation invariant | arbitrary triangle soup plus epsilon; query triangles against union of convex envelope cells | `FULL_TEXT_READ`; public author PDF, 14 pages; text and figures inspected | `10.1145/3386569.3392426` |
| Klingner and Shewchuk (2007), *Aggressive Tetrahedral Mesh Improvement* | sliver/bad-tet removal and worst-element quality | valid tetrahedral mesh with fixed triangulated boundary; output same domain with changed interior connectivity and possibly vertex count | `FULL_TEXT_READ`; public author PDF, 18 pages; text and figures inspected | `10.1007/978-3-540-75103-8_1` |
| Tournois et al. (2009), *Interleaving Delaunay Refinement and Optimization for Practical Isotropic Tetrahedron Mesh Generation* | quality, grading, boundary approximation, sliver cleanup | watertight, 2-manifold, non-self-intersecting PSC approximation with tagged creases/features; user size/error/shape/topology criteria | `FULL_TEXT_READ`; public author PDF, 8 pages; text and figures inspected | `10.1145/1531326.1531381` |
| Si et al. (2010), *Boundary Conforming Delaunay Mesh Generation* | constrained boundary recovery and finite-volume quality control | constrained PLC input with face recovery and Delaunay refinement control; bounded geometry under angle-dependent assumptions | `FULL_TEXT_READ`; 16 pages; full algorithm and limits reviewed | `10.1134/S0965542510010069` |
| Cheng et al. (2000), *Sliver Exudation* | theoretical sliver removal | weighted regular triangulation plus ratio-property assumptions for guaranteed sliver suppression in idealized Delaunay sets | `FULL_TEXT_READ`; 22 pages; abstract, theorems, and algorithmic pathway reviewed | `10.1145/355483.355487` |

`FULL_TEXT_READ` means the complete supplied/public PDF was processed and its relevant algorithm, experiment, limitation, and conclusion sections were reviewed. It does not mean every result is directly implementable without consulting cited proofs or source code.

## 1. Shewchuk 2002 — CDT and provably good boundary recovery

### What the paper establishes

- A 3D CDT is not guaranteed to exist for an arbitrary PLC. Existence is guaranteed when all required (or, more tightly, all *grazeable*) PLC segments are strongly Delaunay.
- Any PLC can be made edge-protected by adding Steiner vertices on its segments. The construction first places protecting-sphere intersections near input vertices where segments meet at angles below 90 degrees, then recursively bisects remaining segments that are not strongly Delaunay.
- The recovery procedure is not merely a midpoint heuristic. Sphere radii depend on local feature size and adjacent segment lengths. The resulting subsegments are bounded below by one quarter of local feature size, except for the explicit small-angle bound.
- Once edge protection holds, facets can be triangulated and the CDT constructed by cavity/gift-wrapping or sweep-style algorithms. Exact orientation and in-sphere predicates plus symbolic perturbation are recommended because CDT construction is especially sensitive to cospherical degeneracies.
- Delaunay refinement must protect recovered subsegments: insertion inside a segment's diametral sphere triggers segment splitting instead of the requested insertion.

### Native Tet consequence

The PLC path needs explicit `PLC -> edge protection -> facet recovery -> region extraction -> quality refinement` phases with phase-specific invariants. The current notion of “recover an edge by midpoint splitting” is insufficient unless it implements the protecting-sphere/local-feature-size policy and rechecks all affected constraints. Required predicates are `orient3d`, `insphere`, strong-Delaunay classification, visibility, segment/facet intersection, and a deterministic symbolic-perturbation rule.

## 2. Diazzi et al. 2023 — robust and practical CDT

### What the paper adds beyond TetGen's design

- It targets a **valid PLC** and preserves its geometry exactly; this is a different contract from a Wild mesher that is allowed to move the surface inside an envelope.
- Segment recovery follows Si's encroachment classification, but a Steiner point is represented implicitly as a rational linear combination on a PLC segment. Indirect `orient3d` and `inSphere` predicates operate on that implicit representation without first rounding it.
- It identifies a correctness gap in TetGen's face-recovery theory: expanding two half-cavities can cross the recovered face and make their local tetrahedralizations overlap. When safe cavity expansion fails, modified gift wrapping is used as the fallback.
- The complete loop recomputes missing segments until none remain and then repeatedly recovers missing faces, because inserting a Steiner point or expanding a cavity can invalidate a previously recovered constraint.
- Exact output may be stored rationally. Floating-point rounding is a separate post-process and can still flatten or invert nearly degenerate tetrahedra. The paper applies guarded face/edge swaps that strictly reduce maximum AMIPS energy before rounding, but explicitly states that flip-free floating-point representability remains unsolved.

### Evidence and limits

The authors report success on all 4,408 valid PLC models selected from Thingi10k; 76% finish under one second and average time is 4.3 seconds on one CPU core. Segment recovery accounts for 74.5% of total time. The worst case inserts about 10.2 million Steiner points, so a robust algorithm still needs hard resource budgets and diagnostic reporting. The method does not accept self-intersecting soup, does not preserve the original face connectivity in every coplanar case, contains no complete quality optimizer, and is single-threaded.

### Native Tet consequence

For the PLC engine, this is the most direct modern implementation model. Adopt implicit Steiner points and indirect predicates at the kernel boundary; implement a face-recovery fallback that does not assume both half-cavities can expand safely; retain exact provenance for every edge Steiner point; and treat floating conversion as an audited export operation, not an innocent cast.

## 3. Hu et al. 2018 — TetWild

### Contract and pipeline

Input is an arbitrary triangle soup, tolerance epsilon, and target edge length. The output must contain an approximation of the soup within epsilon, contain no inverted tetrahedra, and respect the requested edge-length bound; quality is optimized subject to those validity constraints.

The method deliberately decouples validity from quality:

1. Compute an exact-rational unconstrained Delaunay tet mesh covering a bounding box.
2. Cut intersected tetrahedra with all relevant input-triangle planes, producing convex BSP cells conforming exactly to the soup.
3. Tetrahedralize each convex cell by triangulating its faces and connecting them to an exact barycenter.
4. Improve with split/collapse/swap/smoothing operations, accepting only operations that preserve positive orientation and keep the tracked embedded surface inside an epsilon-envelope.
5. Extract volume by winding-number classification after optimization.

The exact BSP construction handles degeneracy, self-intersection, holes, and non-manifold connectivity, but may have quadratic intersection growth. Voxel stuffing and envelope-guarded input simplification reduce practical cost. A hybrid kernel keeps exact rationals only around regions that would invert after rounding.

### Limits and Native Tet consequence

The method is approximately, not exactly, boundary preserving. Sharp features can zigzag inside the envelope; winding-number hole filling can create output boundary outside the envelope where the input has no surface; and the original implementation is comparatively slow and single-threaded. Therefore this belongs in a distinct `WildTet` engine/API. Its reusable contributions are the validity-first pipeline, embedded-surface provenance, transactionally guarded local operations, and exact-to-float promotion/demotion rules.

## 4. Wang et al. 2020 — exact polyhedral envelope containment

### Why vertex-only or sampled tests are invalid

Testing only a triangle's vertices, or a finite sample of its interior, does not prove triangle containment. A triangle classified inside can later be subdivided into a subtriangle classified outside, breaking the monotone invariant assumed by local remeshing. The observed consequence is locking, over-refinement, or failure.

### Method

- Around each input triangle, construct a small convex polyhedron as an intersection of half-spaces. With plane offset `delta = epsilon / sqrt(3)`, every point in the proposed prism-like cell is within Euclidean distance epsilon of that triangle.
- Do not explicitly Boolean-union the cells. Prove a query triangle lies in their open union using three classes of events: query vertices in cells (C1), edge/facet intersection points in cells (C2), and triple-plane/facet intersection points in cells (C3).
- Represent intersection points implicitly: LPI for line-plane intersections and TPI for three-plane intersections. Evaluate their orientation with semi-static floating filters, interval arithmetic, then exact floating expansions.
- Use AABB pruning, conservative floating filters, and decision-oriented ordering before exact fallback. The paper reports roughly two orders of magnitude acceleration from these strategies.

The envelope is conservative relative to an exact Euclidean L2 offset, but it supports adaptive thickness and its cost remains useful for very thin envelopes. Integration into fTetWild removes the sampled multi-stage heuristic and avoids severe over-refinement.

### Native Tet consequence

The shared surface-preservation layer must expose **whole-triangle containment**, not `all_vertices_inside`. Implement an immutable envelope index plus exact `point`, `LPI`, and `TPI` predicate tiers. Every surface-changing local edit must submit all replacement surface triangles to this checker before commit. Adaptive epsilon should be part of the field interface, not a global constant baked into the optimizer.

## 5. Klingner and Shewchuk 2007 — aggressive mesh improvement

### Operations and schedule

The paper combines optimization-based smoothing, edge removal, multi-face removal, boundary-compatible flips, and a general vertex-insertion operation. Insertions are composite transactions: insert a candidate, smooth its neighborhood, try topological changes, compare the resulting local quality vector with the deleted elements, and roll back the entire sequence if quality did not improve.

Scheduling is adaptive. It starts with smoothing and topological passes, then repeats while the worst element or thresholded means over the low-quality tail improve. Expensive vertex insertion is delayed until simpler passes stall. The quality objective is lexicographic over the worst tetrahedra rather than an average that can hide a sliver.

Across twelve reported meshes, final dihedral ranges were approximately 31–149 degrees for minimum sine, 25–142 degrees for biased minimum sine, and 23–136 degrees for volume-length. No tested mesh grew by more than 41%, but pathological inputs were expensive; composite insertion often consumed about 90% of runtime. The method assumes the input vertex spacing is already appropriate and holds the triangulated boundary fixed.

### Native Tet consequence

Build a shared transactional quality-improvement scheduler after either initial mesher. First implement inversion-safe smoothing and common bistellar/edge operations, then worst-first thresholded scheduling, then composite insertion with rollback. Boundary constraints differ by engine: PLC edits must preserve constrained facets exactly; Wild edits may change the embedded surface only after exact envelope approval.

## 6. Tournois et al. 2009 — interleaved refinement and optimization

The input is much stricter than Wild: a watertight, two-manifold, self-intersection-free piecewise-smooth-complex approximation, with sharp creases and feature vertices tagged. User criteria include size, surface/crease approximation error, radius-edge shape bounds, topology preservation, and manifoldness.

Instead of running refinement to completion and optimizing afterward, the algorithm alternates sparse batches of Delaunay refinement with ODT/Lloyd-style optimization. Bad restricted edges, facets, and tetrahedra propose Steiner points; encroachment redirects candidates to lower-dimensional boundary primitives. A conflict-region independent set selects mutually non-interfering insertions for each batch. Optimization relocates both interior and boundary vertices with boundary terms consistent with the same variational objective. Remaining slivers are perturbed at the end.

The key engineering lesson is that interleaving reduces short-lived over-refinement and gives smoother grading than a monolithic refine-then-optimize pipeline. The paper's boundary is an approximation obtained through restricted Delaunay structures, so it is not a replacement for exact PLC recovery. Its original small-angle termination assumptions and manual feature tags must remain visible in the API/preflight checks.

### Native Tet consequence

After correctness baselines exist, change the quality loop from independent “refine” and “optimize” commands into rounds. Generate candidates with reason codes (`SIZE`, `BOUNDARY_ERROR`, `RADIUS_EDGE`, `TOPOLOGY`), select a conflict-independent batch, apply it transactionally, optimize affected neighborhoods, and reevaluate all criteria. This also supplies a natural unit of parallel work.

## 7. Si et al. 2010 — boundary conforming Delaunay mesh generation

This paper is fully accessible and useful as a constrained-PLC reference for quality-constrained refinement. Starting from a Delaunay initial mesh, it combines boundary segment/face encroachment rules and point insertion priorities to retain a boundary-conforming structure while reducing poor tetrahedra.

### Native Tet consequence

The full text justifies `NativeTetPLC` preflight checks for boundary angle constraints and refined quality tradeoffs before the Wild path. It is still not a soup-repair algorithm; keep PLC validity and boundary integrity as preconditions.

## 8. Cheng et al. 2000 — sliver exudation (full-text review)

The method is a weighted-Delaunay sliver-removal approach for point sets satisfying a ratio-property condition. It proposes a pressure/weight-pumping mechanism so slivers are eliminated mostly without massive Steiner insertion; boundary peeling is part of its cleanup strategy.

This remains a long-horizon path for AutoTessell because it introduces strict geometric assumptions and complex precondition gating. It can be placed after first-release PLC/Wild correctness milestones.

## Engine architecture implied by batch 1 + batch 2

```text
                          Shared robust geometry kernel
                  orient3d / insphere / symbolic perturbation
                    implicit points / exact intersections
                                   |
                 +-----------------+-----------------+
                 |                                   |
          NativeTetPLC                         NativeTetWild
      valid PLC, exact boundary           arbitrary triangle soup
 edge protection + CDT recovery        exact valid initialization
 cavity expansion + gift-wrap         embedded surface + envelope
                 |                                   |
                 +-----------------+-----------------+
                                   |
                    Transactional quality engine
            smooth / split / collapse / flips / rollback
             worst-first metrics + interleaved refinement
                                   |
                         validation and export
          exact/rational or audited float; surface provenance;
          inversion, conformity/envelope, region and quality checks
```

The two public engine contracts must not be conflated:

- `NativeTetPLC`: rejects invalid PLC input; exact geometric boundary preservation is non-negotiable; output may contain segment Steiner points and may use exact coordinates internally.
- `NativeTetWild`: accepts defective soup; topology and geometry may change within an explicit tolerance; the output must record the chosen inside/outside policy and any hole-filling boundary not supported by input triangles.

## Recommended implementation order

1. **Shared predicates and validation.** Exact-filtered `orient3d`/`insphere`, deterministic degeneracy policy, tet orientation audit, adjacency/manifold checks, and provenance-bearing vertex representation.
2. **PLC correctness milestone.** Strong-Delaunay edge protection; missing-segment fixed point; missing-face detection; safe cavity recovery with gift-wrap fallback; exact constraint audit.
3. **Wild correctness milestone.** Exact valid initialization, embedded-surface tracking, whole-triangle exact polyhedral-envelope checker, and explicit winding/region policy.
4. **Shared local-operation transaction layer.** Candidate cavity creation, validate-before-commit, rollback, local provenance update, and engine-specific boundary guard.
5. **Quality baseline.** Worst-first AMIPS/minimum-sine/radius-ratio reporting; safe smoothing and swaps; sliver corpus; no regression in conformity/envelope.
6. **Interleaved improvement.** Sparse conflict-independent refinement batches alternating with local optimization; budgets on time, vertices, tetrahedra, and exact-fallback rate.
7. **Advanced research.** Weighted sliver exudation only after its full text and preconditions are acquired; parallel batches only after deterministic serial invariants pass.

## Stop gates for the next research/implementation round

- Do not call PLC recovery complete until every input segment and facet has an independently audited representation in the output and the fixed-point loops terminate without a resource-budget breach.
- Do not call Wild surface preservation complete until every output embedded-surface triangle passes whole-triangle containment; vertex-only and sampled acceptance are forbidden as proof.
- Do not claim quality improvement from averages alone. Record worst and lower-tail dihedral/AMIPS/radius metrics plus inversion count.
- Do not export rounded implicit/rational coordinates without rerunning orientation and boundary/envelope audits on the actual exported coordinates.
