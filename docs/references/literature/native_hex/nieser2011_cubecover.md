# Nieser, Reitebuch, and Polthier 2011 - CubeCover

## Bibliographic record

- Matthias Nieser, Ulrich Reitebuch, Konrad Polthier, *CubeCover - Parameterization of 3D Volumes*, Computer Graphics Forum 30(5), 1397-1406, 2011.
- DOI: `10.1111/j.1467-8659.2011.02014.x`
- Publisher record: <https://onlinelibrary.wiley.com/doi/10.1111/j.1467-8659.2011.02014.x>
- Legal open PDF: <https://diglib.eg.org/server/api/core/bitstreams/584f2ef3-7a95-4183-a71e-537ac26e0e02/content>
- Status: `FULL_READ` (10/10 pages, 2026-07-23).
- Visual verification: pages 3, 7, and 9 rendered and inspected. Parameterization equations, singularity figures, meta-mesh examples, and result tables agree with extracted text.

## Core construction

Input is a bounded tetrahedral volume plus a frame field. Output is a boundary-aligned hexahedral parameterization `f=(u,v,w)` whose inverse integer iso-surfaces induce a hex tessellation.

Three stages:

1. Design a guiding frame field.
2. Compute a parameterization aligned to that field.
3. Intersect each mapped tet with the unit grid in texture space and extract the hex mesh.

Adjacent tet charts satisfy

```text
f|t = Pi_st f|s + g_st
```

where `Pi_st` is one of 24 orientation-preserving cube symmetries and `g_st` is an integer translation. Boundary alignment fixes one of `u,v,w` to an integer on every boundary triangle.

The continuous fit minimizes

```text
E(f) = integral_V ||grad(f) - X||^2 dvol
```

with chart compatibility constraints. The exact mixed-integer problem is a closest-vector problem and NP-hard. CubeCover first solves a relaxed constrained sparse linear system, then successively rounds singular/boundary coordinate variables and resolves it.

The paper derives topology of singularities:

- non-degenerate 3D singularities are curves, not isolated points;
- legal edge types are identity or rotations about one coordinate axis;
- for an interior hex vertex, `sum_i (6 - valence(e_i)) = 12`;
- badly placed singularities cause high distortion; boundary singularities on nearly planar regions can approach 180-degree angles.

## Frame-field source and guarantees

CubeCover does **not** automatically design a general 3D frame field. The paper uses a manually built coarse hex meta-mesh, allowed to contain T-junctions and not required to fit the boundary. It induces frames, matchings, and singularities. The final mesh is relaxed toward cubes and boundary vertices are reprojected.

- The least-squares fit is optimal for the relaxed problem, not the NP-hard integer problem.
- A non-degenerate parameterization induces a pure hex mesh, but non-degeneracy is not guaranteed.
- Incompatible fields can degenerate parts of the parameterization.
- Flipped tets can occur under high distortion.
- Automatic field generation and automatic singularity placement are explicitly left unsolved.

Experiments include genus 4/5 objects, torus, fandisk, rocker arm, hand, skull, and bush. Output ranges from 268 to 96,054 hexes. Minimum reported dihedral angles range from 5.2 to 18.6 degrees. The largest solve shown is 15:40 for a 125,131-tet hand model in an unoptimized Java implementation.

## AutoTessell code comparison

Current `native_hex` has no tetrahedral chart atlas, cube-symmetry matching, volumetric frame field, singularity graph, mixed-integer/rounding solve, or parametric-grid extraction. Axis-aligned octree cells and nearest-surface snapping are a different family.

Dependency contract:

- CubeCover requires a clean tetrahedral volume before hex extraction.
- AutoTessell already owns `native_tet`, but `tier_native_hex` currently receives only preprocessed surface vertices/faces through `run_native_tier`.
- A CubeCover-like route would therefore be a composed `surface -> tet -> frame/parameterization -> hex` engine, not a small patch inside `octree.py`.

## Falsifiable implementation cards

### HEX-FIELD-0 - research prototype only

- Build frame samples and 24-way matching on a small native-tet mesh.
- Pass: cube, torus, and bent tube boundary frames align one axis to the boundary normal; loop products expose expected singularity edges; repeated seeded runs are deterministic.
- Stop: no production extraction until inverted parameterization tets are detected and rejected.

### HEX-FIELD-1 - relaxed parameter solve

- Implement chart transitions and constrained least squares without integer rounding.
- Pass: unit cube recovers an affine map; transition residual and frame-fit energy fall below specified tolerance; all mapped tet determinants stay positive.
- Fail fast: incompatible prescribed matchings return a diagnostic singularity cycle, not distorted output.

### HEX-FIELD-2 - integer extraction gate

- Add successive rounding and unit-grid intersection only after HEX-FIELD-1.
- Pass: extracted mesh is watertight, all cells have six quad faces, boundary integer constraint holds, and mapped/tessellated volume agrees within tolerance.
- Required metrics: inverted mapped tets, minimum scaled Jacobian, singularity-edge valence histogram, boundary deviation.

## Decision

Retain as long-term all-hex research path and topology reference. Reject as next production milestone: manual meta-mesh, NP-hard rounding heuristic, and possible inversion conflict with fully automatic native-first requirements.
