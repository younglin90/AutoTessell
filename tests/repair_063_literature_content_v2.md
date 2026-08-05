# Literature review - native-all-production-gate-063

## Planner transport

- Sole planner: current Codex main session (GPT-5), per user instruction; no subagent.
- Reasoning/service: main session, no exposed separate reasoning/priority setting. Wait=0 seconds.
- No `fast` API field was exposed; fast-off is lifecycle policy, not a fabricated invocation option.

## Question

What shared native core makes BL0 identity and BL>=1 wall-edge growth fail closed before a product writer can lose topology, authority, provenance, or quality?

## Sources read

- Repository plan `docs/plans/native_quality_first_boundary_layer_plan_2026-08-01.md`; prior native round artifacts were inventoried with direct review of 060-062 and native-input-contract series.
- `native_tri_wall_edge_bl_preflight.hpp`/binding: directed sector authority is strong but Tri-only. `surface_bl_front_sector_bind.cpp` computes a separate `co_normal=normalize(normal x tangent)` and visibility path. `native_quality_witness_v3.cpp` has signed quality evidence but not common wall-edge feasibility.
- Aubry et al., *Anisotropic sources for surface and volume boundary layer mesh generation*, JCP (2021), local `docs/research/papers/aubry2021.pdf`, 17 pages, text/equation extraction reviewed. It couples surface-edge and volume-face sources and uses geodesic, not Euclidean, surface distance. Adopt common source/sector metric data.
- Aubry et al., *An Entropy Satisfying Boundary Layer Surface Mesh*, IJNME (2015), local `docs/research/papers/aubry2015.pdf`, 18 pages, algorithm/equation extraction reviewed. It uses Eikonal-like propagation, most-normal/most-visible directions and concavity/geometric-edge handling. Adopt sector direction and conservative visibility.
- Fidkowski, *A Prismatic-Layer Advancing-Front Approach to Anisotropic Metric-Based Curved Mesh Generation*, AIAA J. (2024), DOI `10.2514/1.j064644`, local PDF and https://websites.umich.edu/~kfid/MYPUBS/Fidkowski_2024_AIAAJ.pdf. It separates prism growth and simplex front, uses metric selection and `J_Q=sum(1/(Q_k+epsilon))`, and warns that anisotropic quad splitting can cause negative Jacobian. Adopt corridor-first, not count-driven splitting.
- Gmsh `BoundaryLayers.cpp` master, https://raw.githubusercontent.com/live-clones/gmsh/master/src/mesh/BoundaryLayers.cpp: source edges/faces are separate; dependencies/orientation precede normal-field extrusion. Method only; no code/dependency.
- OpenFOAM `cellQuality.C` v8, https://cpp.openfoam.org/v8/cellQuality_8C_source.html, GPLv3: signed non-orthogonality and face-centre skewness. Independently implement equations only; no GPL copy/link.
- Mmg, https://github.com/MmgTools/mmg and https://www.mmgtools.org/: LGPL metric-driven adaptation/local operations. Metric length is a diagnostic, no dependency/code.
- CGAL Mesh_3, https://doc.cgal.org/latest/Mesh_3/group__PkgMesh3Ref.html and https://www.cgal.org/license.html: independent shape/size/feature criteria. No dependency; package licensing varies.

## Equations or mechanisms adopted

```text
t=(p1-p0)/||p1-p0||
c=(n x t)/||n x t||
M=[t c n] diag(h_t^-2,h_c^-2,h_n^-2) [t c n]^T
L_M(d)=sqrt(d^T M d)
h_k=h0*r^k; H=sum(k=0..N-1,h_k)
```

Require SPD `M`, authoritative directed-sector sign, exact schedule agreement, conservative clearance/visibility, then topology/source/quality before count. `J_Q` is diagnostic only in 063.

## Rejected assumptions

- Averaged normals are valid at ridge/corner; they are not.
- Conflicting first/final/total/growth/count values may silently choose precedence; they may not.
- Surface collision proves volume-shell safety; it does not.
- Count offsets topology/authority/quality loss; it cannot.
- Public source read may be copied/linked; it may not.
