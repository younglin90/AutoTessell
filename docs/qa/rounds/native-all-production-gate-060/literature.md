# Literature review — native-all-production-gate-060

## Question

native-all-production-gate-060

## Sources read

-

## Equations or mechanisms adopted

-

## Rejected assumptions

-

## 060 detailed literature memo

- [Fidkowski 2024, prismatic-layer advancing-front approach](https://websites.umich.edu/~kfid/MYPUBS/Fidkowski_2024_AIAAJ.pdf): layer-front validity, inversion avoidance and metric quality precede cell-count tuning.
- [OpenFOAM `cellQuality.C`](https://cpp.openfoam.org/v8/cellQuality_8C_source.html): signed owner-to-neighbour/boundary vectors, oriented face-area vectors, non-orthogonality and skewness definitions. Equations are used independently; code is not copied.
- [OpenFOAM `snappyLayerDriver.C`](https://raw.githubusercontent.com/OpenFOAM/OpenFOAM-dev/master/src/mesh/snappyHexMesh/snappyHexMeshDriver/snappyLayerDriver.C): feature/non-manifold layer handling; AutoTessell keeps source preservation and refuses incomplete closed-source candidates.
- [Gmsh `BoundaryLayers.cpp`](https://fossies.org/linux/gmsh/src/mesh/BoundaryLayers.cpp) and [Gmsh project](https://gmsh.info/): source edge/face separation and layer-scale concepts only; no GPL code is copied.
- Repository `auto_tessell_core/native_tet_predicates_bind.cpp`: existing adaptive exact predicates are the preferred reusable C++ collision basis.

### Mechanisms adopted

- Internal non-orthogonality: `theta = acos((C_n-C_o) dot S_f / (|C_n-C_o| |S_f|))`; boundary follows the oriented face-centre vector form. Never use `abs(dot)`.
- Candidate and disk reread use the same quality kernel and retain max/p95 plus worst writer-face identity.
- The complete user input policy/configuration is canonicalized and hashed, then evaluated unchanged at each stage.

### Rejected assumptions

- Cell/face count cannot substitute for configured quality limits.
- Vertex-set reconstruction and temporary disk IDs are not authoritative identity.
- Partial extrusion is not acceptable for closed-source lineage; deterministic refusal is required.
