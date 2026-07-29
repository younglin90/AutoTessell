# Boundary-Layer Mesh Research Archive

User-supplied research PDFs for internal engineering reference. Keep these files
in this directory. Do not redistribute copyrighted copies.

## Papers

| File | Citation | Implementation use |
| --- | --- | --- |
| `boundary-layer-arbitrary-geometries-2017.pdf` | Aubry, Dey, Mestreau, Karamete. *Boundary layer mesh generation on arbitrary geometries*. IJNME (2017). DOI: 10.1002/nme.5514 | Generalized spherical Voronoi candidates and canonical multiple-normal topology at nonsmooth corners. |
| `multiple-normals-arbitrary-manifold-2022.pdf` | Ye, Chen, Liu, Xiao, Zheng, Zheng. *Multiple normals configuration on an arbitrary manifold for viscous mesh generation*. IJNME (2022). DOI: 10.1002/nme.7104 | Spherical feasible regions, visibility graph, connected face coverage, topology/normal optimization, and corner stitching. |
| `robust-boundary-layer-mesh-generation-2013.pdf` | Loseille, Lohner. *Robust Boundary Layer Mesh Generation* (2013). DOI: 10.1007/978-3-642-33573-0_29 | Exact-visibility cavity enlargement, constrained layer preservation, deterministic point insertion, and prism provenance. |
| `anisotropic-sources-surface-volume-bl-2021.pdf` | Aubry, Dey, Mestreau, Williamschen, Szymczak. *Anisotropic sources for surface and volume boundary layer mesh generation*. JCP (2021). DOI: 10.1016/j.jcp.2020.109855 | Shared SPD source metric for surface sizing, BL placement, curvature/nearby-source coupling, and core transition. |
| `entropy-solution-concave-corners-ridges-2019.pdf` | Aubry, Karamete, Mestreau, Jones, Dey. *Entropy solution at concave corners and ridges, and volume boundary layer tangential adaptivity*. JCP (2019). DOI: 10.1016/j.jcp.2018.09.030 | Concavity-seeded FMM, prism diagonal/collapse/cavity fallback, and tangential split/coarsening for adaptive mode. |
| `robust-full-layer-prismatic-mesh-generation-2025-publisher.pdf` | Ye, Liu, Ni, Chen. *Robust full-layer prismatic mesh generation based on bijective mapping*. JCP 524 (2025) 113744. DOI: 10.1016/j.jcp.2025.113744 | Publisher version supplied by the user; thin positive shell, air mesh, symmetric-Dirichlet deformation, prism remeshing, and Hermite refinement. |
| `robust-full-layer-prismatic-mesh-generation-2025.pdf` | Ye, Liu, Ni, Chen. *Robust full-layer prismatic mesh generation based on bijective mapping*. Journal of Computational Physics 524 (2025) 113744. DOI: 10.1016/j.jcp.2025.113744 | Existing manuscript copy; global symmetric-Dirichlet/ARAP deformation, auxiliary air mesh, positive-volume line search, and adaptive target mesh. |
| `variational-prismatic-boundary-layer-meshes-2009.pdf` | Dyedov et al. *Variational generation of prismatic boundary-layer meshes for biomedical computing*. IJNME 79 (2009) 907-945. DOI: 10.1002/nme.2583 | Gradient-limited local feature size, face-offset propagation, variational prism quality and orthogonality optimization. |
| `tetrahedral-boundary-layer-mesh-generation-2002.pdf` | Bottasso, Detomi. *A Procedure for Tetrahedral Boundary Layer Mesh Generation*. Engineering with Computers 18 (2002) 66-79. DOI: 10.1007/s003660200006 | Constrained spring/elasticity deflation, validity-preserving mesh motion, transition-zone tet retriangulation. |

## Verified file hashes

| File | SHA-256 |
| --- | --- |
| `boundary-layer-arbitrary-geometries-2017.pdf` | `737c3ccee3d3283539f7ec52189a0056b6380da549bb0f63b24701585d11da01` |
| `multiple-normals-arbitrary-manifold-2022.pdf` | `643c3c7a67dc9d52949cdd42da73cff10e34215964aaabd563602a4d6bbd68df` |
| `robust-boundary-layer-mesh-generation-2013.pdf` | `c481816a61e76ff81ed55edcd2b2336e950f3c8f9b290947d1ae12a517ac1552` |
| `anisotropic-sources-surface-volume-bl-2021.pdf` | `7c2b68ee75a6be0b1962d47e0945d642e2ee51ebb544f512eb6e69c864ef9c01` |
| `entropy-solution-concave-corners-ridges-2019.pdf` | `5dacd8d3a5741919785b16f9c89ff84c12339897cdd1bb317ffb1bfa706de87c` |
| `robust-full-layer-prismatic-mesh-generation-2025-publisher.pdf` | `c422e61e537690928e477420a8f6e0e29a3a5d69d5d376904898d470c141ad15` |
| `robust-full-layer-prismatic-mesh-generation-2025.pdf` | `0df0327b4dc8ed0265e219664ad6f66f297b968856ef50872f83225851c8e26e` |
| `variational-prismatic-boundary-layer-meshes-2009.pdf` | `1c4e4c50244164b2d4b459c06426ecdb64741b8d68e643745154c17342fecda8` |
| `tetrahedral-boundary-layer-mesh-generation-2002.pdf` | `aa999ecfebba63842033b988cdf1415d64d25bad9d319ffce989073d81637614` |

## Integrated development plan

The six user-supplied papers were read in full and integrated into
[`native_bl_literature_integrated_development_plan_2026-07-23.md`](../boundary_layers/native_bl_literature_integrated_development_plan_2026-07-23.md).
The plan separates strict and adaptive layer contracts, defines a C++ module
architecture, replaces sampled/generic quality gates with element-class-aware
validation, and gives phased falsifiable implementation cards.

## Design decisions derived from the papers

1. Retain prismatic boundary layers and tetrahedral core cells. Do not judge a
   boundary layer by raw isotropic aspect ratio alone.
2. Separate strict requests from explicit adaptive compression. Never report a
   capped or reduced layer as if it realized the requested first height and total
   thickness.
3. Compute multiple normals from spherical feasibility and visibility, with
   generalized spherical Voronoi candidates for canonical topology.
4. Drive surface remeshing, BL placement, and core transition from one smooth
   anisotropic source metric.
5. Reject candidate layer motion unless every prism and an auxiliary collision
   volume stay positively oriented throughout a line search.
6. Optimize layer shape with wall vertices fixed and with tangential/normal degrees
   of freedom separated. Optimize the tetrahedral core independently.
7. Replace append-only prism generation with constrained visibility-cavity insertion
   and core cut/refill under an explicit cell ledger.
8. Use direct finite-volume face penalties for non-orthogonality and skewness; use
   determinant and metric-normalized element shape as hard barriers.

## Implemented Research Controls

- `BLConfig.feature_size_smoothing=True` enables the Dyedov local feature-size
  field. Collision-derived vertex caps are propagated over wall edges with
  `feature_size_gradient_limit` (default `0.85`). The propagation only lowers caps.
- The control remains opt-in. The default production path retains the validated
  global collision cap because unconstrained activation regressed the full STL
  matrix.
- Every opt-in result still passes the Ye et al. positive-volume extrusion line
  search before it is written. Diagnostics are persisted under `feature_size` and
  `extrusion_line_search` in `native_bl_quality.json`.
