# Literature review - native-all-production-gate-063

## Planner transport

- Planner: current Codex main session (GPT-5), sole planner by operator instruction; no subagent was spawned.
- Reasoning/service: main session, with no exposed separate priority/reasoning option.
- Wait duration: 0 seconds. The API exposed no `fast` field; fast-off remains lifecycle policy rather than an asserted API argument.

## Design question

What shared native core can make BL=0 identity and BL>=1 wall-edge growth fail closed before any engine-specific writer can lose topology, source authority, provenance, or mesh quality?

## Repository material reviewed

- `docs/plans/native_quality_first_boundary_layer_plan_2026-08-01.md`: topology/shape/source authority and quality precede count; BL=0 identity and all-or-rollback are mandatory.
- Prior native-engine round artifacts were inventoried, emphasizing 060-062 and native-input-contract rounds: `NativeQualityWitness/v3` is default-OFF and signed, but has no all-engine wall-edge metric feasibility path.
- `auto_tessell_core/native_tri_wall_edge_bl_preflight.hpp`/binding: strong Tri-specific directed edge/sector authority validation, but no general metric corridor.
- `auto_tessell_core/surface_bl_front_sector/surface_bl_front_sector_bind.cpp`: separate surface `co_normal=normalize(normal x tangent)` and visibility logic; it is not shared with volume engines.
- `auto_tessell_core/native_quality_witness/native_quality_witness_v3.cpp`: signed quality evidence exists but does not certify an authoritative edge frame or complete BL schedule.

## Peer-reviewed literature read

- R. Aubry et al., *Anisotropic sources for surface and volume boundary layer mesh generation*, JCP (2021), local `docs/research/papers/aubry2021.pdf`, 17 pages. Reviewed with PyPDF extraction including equations/algorithm text. It couples surface-edge and volume-face boundary-layer sources; it distinguishes geodesic surface distance from Euclidean distance and preserves user first-size/growth/transition information. Adopt: a common source/sector-aware metric field before surface and volume generation.
- R. Aubry et al., *An Entropy Satisfying Boundary Layer Surface Mesh*, IJNME (2015), local `docs/research/papers/aubry2015.pdf`, 18 pages. Reviewed with PyPDF extraction including algorithm/equation text. It uses weak Eikonal-like surface propagation, most-normal/most-visible directions and explicit concavity/geometric-edge handling. Adopt: sector direction and conservative visibility, not normal averaging.
- K. J. Fidkowski, *A Prismatic-Layer Advancing-Front Approach to Anisotropic Metric-Based Curved Mesh Generation*, AIAA Journal (2024), DOI `10.2514/1.j064644`, local PDF and https://websites.umich.edu/~kfid/MYPUBS/Fidkowski_2024_AIAAJ.pdf. It separates prism growth and simplex front, uses metric-space selection, and penalizes degeneracy using `J_Q=sum(1/(Q_k+epsilon))`; it warns that high-order anisotropic quad splitting can create negative Jacobians without robust recovery. Adopt: certify the corridor before count-driven adaptation.

## Public code reviewed - method only, no code/dependency adopted

- Gmsh `BoundaryLayers.cpp`, master: https://raw.githubusercontent.com/live-clones/gmsh/master/src/mesh/BoundaryLayers.cpp. Source edges/faces are tracked separately, dependencies are resolved, source surfaces are oriented before normal construction, then extrusion proceeds. Transfer: explicit source sets/orientation. Do not copy/link source; license must be separately verified before any dependency decision.
- OpenFOAM `cellQuality.C`, v8: https://cpp.openfoam.org/v8/cellQuality_8C_source.html, GPLv3. Signed owner-neighbour non-orthogonality and face-centre skewness are evaluated. Transfer: independently implement equations, preserve sign. Do not copy/link GPL source.
- Mmg: https://github.com/MmgTools/mmg and https://www.mmgtools.org/. Project documentation describes LGPL metric-driven surface/volume adaptation and local operations. Transfer: metric-length diagnostic and deterministic local acceptance. No dependency/code proposed.
- CGAL Mesh_3: https://doc.cgal.org/latest/Mesh_3/group__PkgMesh3Ref.html and https://www.cgal.org/license.html. Transfer: separate shape/size/feature criteria. No dependency; Mesh_3 documentation reports GPL and CGAL licenses are package-specific.

## Adopted equations

```text
t=(p1-p0)/||p1-p0||
c=(n x t)/||n x t||
M=[t c n] diag(h_t^-2,h_c^-2,h_n^-2) [t c n]^T
L_M(d)=sqrt(d^T M d)
h_k=h0*r^k
H=sum(k=0..N-1,h_k)
```

Accept only SPD `M`; choose signs from authoritative directed sectors. Check schedule consistency, visibility/collision and the topology/source/quality tuple before count error. `J_Q=sum(1/(Q_k+epsilon))` stays diagnostic in 063.

## Rejected assumptions

- Averaged normal is valid at ridges/corners; it is not.
- Conflicting count/first/final/total/growth settings may be resolved silently; they may not.
- Surface collision alone proves volume-shell safety; it does not.
- Count can offset topology, authority or quality failure; it cannot.
- Read public code may be copied, linked or depended on; it may not.
