# Gao et al. 2017 - Field-Guided Polyhedral Agglomeration

## Bibliographic record

- Xifeng Gao, Wenzel Jakob, Marco Tarini, Daniele Panozzo, *Robust Hex-Dominant Mesh Generation using Field-Guided Polyhedral Agglomeration*, ACM Transactions on Graphics 36(4), Article 114, 2017.
- DOI: `10.1145/3072959.3073676`
- Author manuscript: <https://gaoxifeng.github.io/papers/2017/Robust-Meshes-2017.pdf>
- Project record/code: <https://rgl.epfl.ch/publications/Gao2017Robust/>
- Status: `FULL_READ` (13/13 pages, 2026-07-23).
- Visual verification: pages 3, 7, and 11 rendered and inspected. Full pipeline, edge classes, extraction operators, and statistics table agree with extracted text.

## Pipeline

Input is a clean, sliver-free tetrahedral mesh. The paper's experiments remesh the surface densely with TetGen at about `0.3 lambda`, where `lambda` is desired output edge length.

1. Optimize a volumetric orientation field.
2. Optimize a position field with grid spacing `lambda`.
3. Morph input tet vertices toward position-field grid points.
4. Agglomerate/split the resulting polyhedral complex using local operations while preserving topology.

### Orientation field

Each vertex carries a right-handed frame. Cube symmetry gives 24 equivalent rotations. Smoothness is

```text
E_Q(Q,kappa) = sum_(i,j) d_Q(R_kappa_ij Q_i, Q_j)^2.
```

The implementation uses unit quaternions and explicit discrete matchings. A greedy edge-collapse hierarchy supplies coarse-to-fine initialization. At each hierarchy level, 200 randomized-neighbor nonlinear Gauss-Seidel iterations average matched quaternions. Boundary constraints align one frame axis to the normal while retaining rotation around that normal.

### Position field

Each vertex carries a local integer-grid point. Smoothness is

```text
E_p(p,tau) = sum_(i,j) ||p_i + lambda Q(q_ij) tau_ij - p_j||^2,
tau_ij in Z^3.
```

Best translation is componentwise rounding in the local frame. The same hierarchy and nonlinear Gauss-Seidel scheme optimize the field.

### Field-guided agglomeration

Position integers classify each tet edge:

- transient: `tau=0`, candidate for edge collapse;
- persistent: one `+/-1` component, desired output edge;
- face diagonal: two nonzero `+/-1` components, dissolve edge;
- interior diagonal: three nonzero components, dissolve surrounding faces;
- longer edges: component magnitude greater than one; input tet mesh must be refined or target length increased.

Extraction alternates coarsening and splitting, normally about three iterations, capped at ten:

- coarsening: edge collapse, edge dissolve, face dissolve;
- splitting: edge split, face split, polyhedral split.

Every operation is tested on a BFS-extracted topological sphere. Accepted output maintains two invariants: every polyhedral face is a topological circle; every polyhedron is a topological sphere. Failed operations are postponed/retried.

## Claims, measurements, and limits

- Manifoldness, genus, and number of holes are maintained by the topology tests.
- Field quality is guidance only; degeneracies in the optimized fields are allowed.
- Output is conforming but may contain arbitrary polyhedra.
- 106/106 benchmark inputs completed with no parameter tuning. Hex count ratio ranges 48-91%; average scaled Jacobian 0.93-0.99.
- This is **not a geometric-validity guarantee**. Table 1 contains inverted hexes, inverted/collapsed polyhedra, and self-intersections. Example minimum scaled Jacobians reach `-0.78`.
- Hex/volume ratios and element defects are reported separately. A high hex ratio does not imply valid CFD cells.
- Single-thread runtime ranges from one minute to ten hours on 0.06-3.6 million input tets. The authors say the method can be parallelized but do not demonstrate distributed scaling.
- More output density creates more position singularities. Removing them trades regularity against isotropy.

## AutoTessell code comparison

Current engine shares only high-level goals:

- It creates generic polyhedral adaptive transition cells and writes them with `write_generic_polymesh`.
- It checks written topology/quality through `NativeMeshChecker`.
- It has no quaternionic orientation field, position field, multiresolution field solve, edge classification, or transactional agglomeration/splitting sequence.

Current adaptive output can therefore be called hex-dominant only after a measured cell-type ratio is added. It is not Gao's method.

## Falsifiable implementation cards

### HEX-HD-1 - output truth metrics

- Report cell-count and volume fractions for hex, prism, pyramid, tet, and generic polyhedron; report invalid/self-intersecting counts by type.
- Pass: classifier matches synthetic one-cell fixtures and totals equal written mesh.
- Gate: `hex_dominant` grade cannot be A if reported hex volume fraction is below configured threshold or any invalid cell exists.

### HEX-HD-2 - manifold transaction kernel

- Prototype edge collapse/dissolve and face dissolve on generic polyMesh connectivity.
- Before commit, extract local ball and require every face loop to be a circle and every affected cell shell to be a sphere; also require positive signed volume and no new local self-intersection.
- Pass: adversarial locked configurations postpone operations; topology and genus remain unchanged after every accepted operation.

### HEX-HD-3 - field prototype

- On `native_tet` output, implement 24-symmetry quaternion matching, boundary-aligned orientation smoothing, then integer position smoothing.
- Pass: per-level energy is non-increasing after a sweep; cube/bent-tube fields align boundary normals; seeded random initialization yields equivalent final matching graph.
- Stop: if initialization sensitivity or memory exceeds benchmark limits, keep octree as production engine and field path experimental.

### HEX-HD-4 - geometric validity beyond topology

- Every local topology operation must also use a signed-volume/scaled-Jacobian and surface-envelope transaction.
- Pass: 106-case-equivalent local benchmark produces zero inverted, collapsed, and self-intersecting cells; rejected operation counts remain bounded; timeout returns partial diagnostics.
- This requirement intentionally exceeds the paper because CFD cannot accept its reported invalid examples.

## Decision

Best medium-term architecture for genuinely field-aligned hex-dominant output. Implement in stages after truthful cell metrics. Do not replace near-term octree path with the full method until native-tet input, transaction kernel, and geometric-validity gate exist.
