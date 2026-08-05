# Literature and public-code review - native-all-production-gate-064

## Planner question and answer

What one common production mechanism advances every native product and surface mesher while BL=0/BL>=1, authoritative source, all user inputs, quality, topology and provenance must hold?

**Answer:** a complete user-request to writer-consumption binding, sealed with authority, quality and corridor receipts before writer execution. A new optimizer cannot compensate for a silently ignored setting or non-authoritative input.

## Sources read

- `docs/plans/native_quality_first_boundary_layer_plan_2026-08-01.md`: quality/topology/source first, BL=0 identity, atomic positive BL, corpus and product-family quality.
- 062 planning artifacts and `auto_tessell_core/native_quality_witness/native_quality_witness_v3.cpp`: signed owner-neighbour orientation, writer UID/lineage, sealed policy and candidate/reread parity. Its intentionally narrow policy vocabulary is not yet a complete UI/request contract.
- 063 artifacts and `auto_tessell_core/native_wall_edge_metric_corridor.{hpp,cpp}`: directed wall-edge frame, SPD metric and collision/visibility receipt, but no writer-consumption proof.
- `core/evaluator/native_quality_witness_admission.py`: legacy Python is orchestration only; it must not become a core default/geometry implementation.

## Local peer-reviewed papers read

1. R. Aubry et al., *Anisotropic sources for surface and volume boundary layer mesh generation*, JCP 424 (2021) 109855, DOI `10.1016/j.jcp.2020.109855`; `docs/research/papers/aubry2021.pdf`, pp. 1-6.
   - Coupled surface/volume anisotropy, close BL interaction and size jumps invalidate decoupled pipelines.
   - The sizing proxy uses metric ellipsoid `x^T M x=1`, preserving small-size directions before resolving the orthogonal plane. First height/growth are therefore contracts, not informal local hints.
   - Transfer: seal identical metric/BL inputs for every surface/volume consumer. No source code is copied.

2. K. Fidkowski, *A Prismatic-Layer Advancing-Front Approach to Anisotropic Metric-Based Curved Mesh Generation*, AIAA Journal (2024), DOI `10.2514/1.J064644`; `docs/research/papers/fidkowski-2024-a-prismatic-layer-advancing-front-approach-to-anisotropic-metric-based-curved-mesh-generation.pdf`, journal pp. 185-187.
   - Eq. (7): `L_M(e)=integral_e sqrt(dl^T M dl)`; metric-normal growth and distinct corner treatment avoid indiscriminate normal averaging.
   - Curvature attenuation is bounded by local layer height to avoid negative Jacobians; only valid fronts advance.
   - Transfer: intent seals exact metric/corner/attenuation controls; missing sector refuses. Variable 2-D local layer count is not permission to violate user's requested complete-layer contract.

3. H. Ye et al., *Robust full-layer prismatic mesh generation based on bijective mapping*, JCP 524 (2025) 113744, DOI `10.1016/j.jcp.2025.113744`; `docs/references/papers/source/pdf/61_ye_2025_bijective_prismatic_bl.pdf`, pp. 1-3.
   - Full layers need global positive-volume/bijective safeguards; local ALM termination leaves distorted pyramids and narrow residuals.
   - Transfer: writer token binds layer count/schedule/walls and positive-volume gates atomically. It does not justify arbitrary 3-D success claims for existing writers.

4. J. R. Shewchuk, *Adaptive Precision Floating-Point Arithmetic and Fast Robust Predicates for Computational Geometry* (1997); `docs/references/papers/source/pdf/38_shewchuk_1997_robust_predicates.pdf` was located but not re-read.
   - Follow-on writer mutation cards need robust orientation predicates; 064 cannot substitute for them.

## Equations or mechanisms adopted

```text
t=(p1-p0)/||p1-p0||; c=(n x t)/||n x t||;
M=R diag(h_t^-2,h_c^-2,h_n^-2) R^T, R=[t c n], M SPD;
h_k=h_0 r^k; H_N=sum(k=0..N-1)h_k;
L_M(e)=integral_e sqrt(dl^T M dl).
theta_f=acos(clamp(((C_n-C_o) dot S_f)/(||C_n-C_o|| ||S_f||),-1,1))*180/pi.
```

Use this quality-first order: topology -> positive measure -> authority/provenance -> BL corridor -> nonorthogonality -> skewness -> family aspect -> count.

## Public source-code review

1. [wildmeshing/wildmeshing-toolkit](https://github.com/wildmeshing/wildmeshing-toolkit), branch `main` observed 2026-08-05; README and `LICENSE` read. License is MIT, with BSD-3-Clause exception for `src/wmtk/utils/Morton.*`. The published shortest-edge-collapse example was read: validate explicit invariants after mutation and rollback geometry/connectivity/attributes on failure.
   - Transfer: named invariant and rollback-token discipline. No dependency or source copy.

2. [OpenFOAM-7 cellQuality.C](https://github.com/OpenFOAM/OpenFOAM-7/blob/master/src/meshTools/cellQuality/cellQuality.C), branch `master` identified. The body was unavailable through cache; [official API reference](https://cpp.openfoam.org/v9/cellQuality_8C.html) was read.
   - Transfer: quality is an explicit measured field, never inferred from count. No GPL source is copied/linked and no threshold is adopted.

3. [Gmsh BoundaryLayers.cpp](https://gitlab.onelab.info/gmsh/gmsh/-/blob/master/src/mesh/BoundaryLayers.cpp), project GPL-2.0-or-later. The public 4.14.0 listing was read; direct retrieval returned HTTP 403.
   - Transfer: layer settings carry selected geometric entities and coherent schedule. No source/dependency is transferred and it is not native authority.

4. [CGAL/cgal](https://github.com/CGAL/cgal), branch `master` observed 2026-08-05; repository and `LICENSE.md` read. Per-package licensing varies, so no dependency/copy decision is made.

All references inform method and validation only; 064 adds no external code or dependency.

## Rejected assumptions

- Count cannot waive topology, authority, BL, nonorthogonality, skewness or aspect failure.
- BL=0 is zero-work identity, not low-height positive BL.
- A policy receipt is not consumption proof; each writer must issue a manifest.
- Surface/volume may not independently reinterpret the same UI metric.
- Coordinate sorting/nearest point, no-op Tri clone, or quad relabeling are not authority/mixed-topology evidence.
- Cube success is not complex CAD/STL release evidence.

## Actual planner transport correction

Planner agent `019fcd6c-88a8-7c23-a88c-1d08390f1fdc` completed after approximately 11 minutes with `gpt-5.6-terra`, high reasoning, priority service. Fast-off was honored as lifecycle policy because no explicit API field exists. The planner's generated “main session / wait=0 / no subagent” line is transport metadata drift; the agent ID and wait record above are authoritative.

No unreadable DOI was used to set a threshold for this bounded intent-binding card.
