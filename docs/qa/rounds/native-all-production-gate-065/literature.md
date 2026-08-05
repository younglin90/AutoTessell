# Literature and public-code review - native-all-production-gate-065

## Planner question and conclusion

What single bounded core method moves all native products and the surface mesher toward actual production while BL=0/BL>=1, all inputs, strict topology, authority/provenance and quality-first behavior hold?

**Conclusion: an authoritative quality transaction executor, rather than another preflight or a count optimizer.** 062 provides signed quality evidence, 063 a wall-edge metric corridor and 064 a complete input intent/consumer map. Their remaining common gap is that a writer can generate or publish without the receipts being enforced at its mutation/publish boundary. A staged rollback executor closes that production boundary.

## Sources read

- `docs/plans/native_quality_first_boundary_layer_plan_2026-08-01.md`: topology/shape/source -> quality -> count, BL=0 identity and atomic positive BL.
- 062 plan and `auto_tessell_core/native_quality_witness/native_quality_witness_v3.cpp`: signed owner-neighbour quality, UID/lineage and candidate/reread comparison; default-off until writer binding.
- 063 plan and `auto_tessell_core/native_wall_edge_metric_corridor.cpp`: directed `t,c,n`, SPD metric and schedule/collision/visibility certificate but no writer transaction.
- 064 plan, `native_transaction_intent_v1.cpp`, `core/native_input_runtime.py`, `core/input_contract.py`: the C++ intent supports seven product labels, while runtime truthfully leaves many user leaves as `accepted_pending`; no claim is made that every adjustable field is consumed today.

## Local peer-reviewed papers read

1. R. Aubry et al., *Anisotropic sources for surface and volume boundary layer mesh generation*, JCP 424 (2021) 109855, DOI `10.1016/j.jcp.2020.109855`; `docs/research/papers/aubry2021.pdf`.
   - Coupled surface/volume anisotropic sizing means both callbacks must consume one sealed metric/BL request, not independent defaults.
   - Transfer: common metric digest and refusal for an applicable-but-unconsumed metric input. No code/dependency/threshold copied.

2. K. J. Fidkowski, *A Prismatic-Layer Advancing-Front Approach to Anisotropic Metric-Based Curved Mesh Generation*, AIAA Journal (2024), DOI `10.2514/1.J064644`; local supplied PDF and readable author PDF.
   - Metric-conforming surface growth and exterior advancing front center validity in anisotropic curved layers. Its reported method is two-dimensional, not a general 3-D proof.
   - Transfer: metric-consistent staged validation and atomic rollback; no 3-D threshold extrapolation.

3. H. Ye et al., *Robust full-layer prismatic mesh generation based on bijective mapping*, JCP 524 (2025) 113744, DOI `10.1016/j.jcp.2025.113744`; `docs/references/papers/source/pdf/61_ye_2025_bijective_prismatic_bl.pdf`.
   - Full layers need global positive-volume/bijectivity safeguards; local termination makes poor residual transitions.
   - Transfer: full-layer commit-or-rollback, not an assertion existing writers implement Ye's mapping.

4. J. R. Shewchuk, *Adaptive Precision Floating-Point Arithmetic and Fast Robust Predicates for Computational Geometry* (1997); local PDF located, not reread in 065.
   - Later topology mutators need robust predicates; AQTE supplies the invariant/rollback boundary, not a replacement predicate.

## Public source-code review

1. `wildmeshing/wildmeshing-toolkit`, GitHub `main`, observed 2026-08-05, MIT with documented BSD-3-Clause exception. README explicit-invariant/rollback sections and test layout read.
   - Validates invariants after edits and restores topology, geometry and attributes on failure.
   - Transfer: propose/validate/rollback journal and attribute/provenance restoration. No code copy, dependency or scheduler transfer.

2. OpenFOAM Foundation `cellQuality` documentation v6 and current mesh-quality documentation, observed 2026-08-05.
   - Cell/face non-orthogonality and skewness are measured from cell centres, face centres and area vectors.
   - Transfer: signed face quality is a contract, not a count proxy; AutoTessell uses its own witness and does not link/copy GPL code.

3. Gmsh `src/mesh/BoundaryLayers.cpp`, `master`, GPL-2.0-or-later; raw source read through `live-clones/gmsh` mirror on 2026-08-05.
   - BL selection carries source geometric entities and coherent schedule into actual operation.
   - Transfer: source selection and schedule continuity only; no GPL source/dependency/output semantics copied.

4. `CGAL/cgal`, `master`, observed 2026-08-05. Repository and per-package licensing reviewed only; no dependency selected.

## Equations or mechanisms adopted

```text
theta_f=acos(clamp(((C_n-C_o) dot S_f)/(||C_n-C_o|| ||S_f||),-1,1))*180/pi
sigma_f=||C_f-(C_o+a/(a+b)*(C_n-C_o))||/(||C_n-C_o||+epsilon)
a=|(C_f-C_o) dot S_f|/||S_f||; b=|(C_n-C_f) dot S_f|/||S_f||
t=(p1-p0)/||p1-p0||; c=(n x t)/||n x t||
M=R diag(h_t^-2,h_c^-2,h_n^-2) R^T; L_M(e)=integral sqrt(dx^T M dx)
h_k=h0*r^k; H_N=sum h_k.
```

Adopt atomic `propose -> validate -> reread -> publish`, with rollback and lexicographic key:

```text
(strict-topology, inversion/measure, authority/lineage, BL contract,
 quality violation, -minimum measure, count error).
```

Count is evaluated only after every preceding term is zero and unchanged under the sealed envelope.

## Rejected assumptions

- Default-off receipts and cube sidecars are not actual writer transactions or release proof.
- `accepted_pending` is not input-consumption evidence.
- Absolute dot products cannot hide reversal; quality cannot be traded for count.
- BL=0 is not near-zero BL; BL>=1 cannot partially publish.
- Coordinate matching cannot recreate CAD/STL authority or metadata.
- Public ideas do not authorize GPL copying or a dependency.

## Planner transport record

The user required a sole planner. No agent was created; therefore no `gpt-5.6-terra` request/wait occurred. Fast-off is recorded accurately only as active lifecycle policy (`agent_fast=false`). No implementation, build or test result is claimed.

## Actual planner transport correction

Planner agent `019fcd81-900a-77a2-a5a9-ecd3f047fb10` completed after approximately 11 minutes with `gpt-5.6-terra`, high reasoning, priority service. Fast-off was honored as lifecycle policy because no explicit API field exists. The generated “main session / wait=0 / no agent” text is transport metadata drift; the actual agent ID and wait record above are authoritative.

No unreadable DOI was used to set a threshold for this bounded executor architecture.
