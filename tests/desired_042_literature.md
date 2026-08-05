# Literature review — native-all-production-gate-042

## Question

042_production_Tet_receipt_wiring_and_three_repeat_non_cube_corpus

## Sources read

- Planner: `gpt-5.6-terra`, high reasoning, priority service tier, forked context, fast argument not exposed by the agent API. The round default is fast-off and is recorded separately rather than claimed as an explicit API argument. Planner id `019fcbd9-fc8c-7671-9653-a47a95700768` (`Jason`) completed normally. One wait request used `timeout_ms=900000`; progress was observed during three 60-second client polls before the final memo. No second planner was spawned.
- Local production path inspected by the planner: `core/generator/tier_native_tet.py`, `core/generator/native_tet/mesher.py`; current route is `TierNativeTetGenerator._runner -> run_native_tet_research/quality-harness/generate_native_tet -> SciPy Delaunay -> PolyMeshWriter`. The planner found no production consumption of the current standalone receipt consumer.
- Local native evidence inspected: `auto_tessell_core/native_tet_surface_boundary_receipt_consumer_bind.cpp` (C++23 receipt validator), `auto_tessell_core/native_tet_bl_transaction_bind.cpp` (validator/transaction evidence, not the production generator route), `auto_tessell_core/surface_bl_front_shared/surface_bl_front_shared_bind.cpp` (surface front and cavity evidence), and `tests/test_native_tet_surface_boundary_receipt_consumer.py` (two focused tests). These establish sidecar validation only until the generator invokes them.
- Fidkowski, “A Prismatic Layer Advancing-Front Approach to Anisotropic Metric-Based Curved Mesh Generation,” 2024, DOI `10.2514/1.j064644`, author PDF `https://websites.umich.edu/~kfid/MYPUBS/Fidkowski_2024_AIAAJ.pdf`. Read at planner level. Transferable mechanism: grow a boundary/prismatic layer from a verified wall/interface and hand the remaining volume to an unstructured core; the paper is mainly 2-D and is not, by itself, a 3-D positive-BL release certificate.
- Chen et al., 3-D conforming Delaunay boundary recovery, DOI `10.1016/j.cma.2003.12.058`. The abstract and planner summary were available, but the full equations were not; it supports local swap/split/recovery principles only and is recorded as unreadable below.
- fTetWild, GitHub `https://github.com/wildmeshing/fTetWild`, branch `master` as inspected, MPL-2.0. Relevant files: `README.md`, `src/MeshImprovement.cpp`, and tests. Transferable ideas: orientation/quality checks and iterative local improvement. Rejected as a source-authority solution because envelope approximation cannot replace an exact CAD/STL receipt binding.
- WMTK, GitHub `https://github.com/wmtk/wmtk`, branch `main` as inspected, MIT license. Relevant files: `README.md`, `LICENSE`, and operation/attribute-transfer tests. Transferable ideas: operation invariants and attribute/provenance transfer. No code copied and no dependency added.
- Gmsh reference/manual material was used only for boundary-layer and mesh-quality terminology. It does not provide the project’s required authoritative source/output transaction evidence.

## Equations or mechanisms adopted

- Receipt-locked ingress: materialize canonical points, source triangles, semantic rows, source hash, and receipt digest from one sealed surface receipt. Caller-provided arrays must not silently replace receipt materialization.
- Actual Tet boundary incidence is reconstructed from generated `(points,tets)`: an external boundary face has incidence 1; a layer/core interface has incidence 2. The latter is an internal interface, so treating every BL face as an external boundary is invalid.
- Commit only after exact mapping, orientation/topology, positive Tet, and quality checks pass; reread the staged PolyMesh and compare binding/digest before atomic publish. On any mismatch, refuse and leave no published output.
- BL=0 must preserve the receipt and output binding exactly. BL>=1 must provide an actual wall/interface/core partition; if the current open surface cannot form a closed volume partition, refuse with `positive_bl_volume_partition_unavailable` rather than relabeling or count-tuning.
- Quality remains before count: proposed release gates are p95/max non-orthogonality 35/50 degrees, skewness 0.25/0.50, and aspect ratio p99/max 10/20, subject to the existing project gate definitions.

## Rejected assumptions

- The current standalone C++ consumer is not evidence of production wiring.
- An open hemisphere/front surface is not a valid positive-BL Tet volume corpus.
- A Delaunay result, writer output, or cell-count match alone is not source-authority/provenance evidence.
- A GitHub branch without an immutable release/commit is not treated as a reproducible dependency; no external source was copied.
