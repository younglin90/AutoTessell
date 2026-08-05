# Literature review — native-all-production-gate-043

## Question

043_atomic_stage_reread_commit_and_three_repeat_non_cube_corpus

## Planner transport

- Planner id `019fcbfc-0931-7810-afec-1706e86fb7ad` (`Lovelace`) completed normally. Requested `gpt-5.6-terra`, high reasoning, priority service tier, forked context. The API did not expose a `fast` field; the round fast-off default is recorded separately and is not claimed as an explicit argument. One wait request used `timeout_ms=900000`; no second planner or descendant was created.

## Sources read

- Local production path: `core/generator/tier_native_tet.py`, `core/generator/native_tet/harness.py`, `core/generator/native_tet/receipt_route.py`, and `auto_tessell_core/native_tet_surface_boundary_receipt_consumer_bind.cpp`. Finding: receipt ingress/read-back is now evidence-only; harness still writes directly to final `case_dir`, and C++ does not reread the disk artifact.
- Local transaction candidates: `auto_tessell_core/native_atomic_publish_bind.cpp` (same-filesystem `fsync`, `renameat2(RENAME_EXCHANGE)`), and `core/generator/native_tet/staged_runner.py`. These are existing building blocks, not yet connected to this receipt route.
- Fidkowski 2024, DOI `10.2514/1.j064644`, author PDF `https://websites.umich.edu/~kfid/MYPUBS/Fidkowski_2024_AIAAJ.pdf`. Planner read the metric-length mechanism and normal-vector smoothing/displacement limitation; it is mainly 2-D and cannot certify 3-D positive-BL release.
- WildMeshing Toolkit, GitHub default branch, MIT except Morton utility BSD-3. Planner read README-level per-operation invariants, attribute updates, and rollback design. No dependency or code copy is permitted.
- fTetWild `master`, MPL-2.0; `src/MeshImprovement.cpp` header and quality-improvement structure reviewed. Its envelope approximation is rejected for exact authoritative source binding.
- CGAL Mesh_3 documentation, official site; weighted-Delaunay/sliver exudation ordering is useful as a quality-stage ordering rule, but no external dependency is introduced.
- TIGER BCC-background method, DOI `10.1137/120866075`, abstract/public material reviewed. Dihedral guarantees are interesting, but approximate boundary treatment is rejected for exact CAD/STL authority.

## Equations or mechanisms adopted

- Metric edge length for a local metric tensor: `L_e^M = integral_e sqrt(dell^T M dell)`. Use only as a design reference for normal-layer displacement clipping; no positive-BL claim follows from the 2-D paper.
- Private sibling stage on the same filesystem; actual writer output is reread from the stage, not trusted from in-memory arrays. Audit includes canonical points/faces, Tet orientation/volume, face incidence, semantic binding, and artifact digest.
- Publish only after strict audit. Same-filesystem atomic exchange may preserve a backup; if post-publish reread fails, exchange back and retain `atomic_rollback` evidence.
- Boundary semantics: BL=0 receipt faces are external incidence 1; BL>=1 wall exterior is incidence 1 and layer/core interface is incidence 2 with explicit layer/core zone lineage. Incidence alone cannot create an interface label.
- Initial quality candidates remain non-orthogonality p95/max 35/50 degrees, skewness p95/max 0.25/0.50, aspect p99/max 10/20. Quality/topology/authority gates precede count.

## Rejected assumptions

- Current receipt ingress/read-back evidence is not atomic production commit.
- A writer success or in-memory candidate is not disk artifact authority.
- Approximate envelope recovery, incidence-2 relabeling, or target-count matching cannot substitute for source/feature/physical-group/provenance evidence.
- Positive BL remains an explicit refusal until a closed wall/interface/core volume partition exists.
