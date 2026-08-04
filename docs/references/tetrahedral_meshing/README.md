# Tetrahedral Meshing Research Archive

User-supplied research PDFs for internal engineering reference. Keep these files
in this directory. Do not redistribute copyrighted copies.

## Papers

| File | Citation | Proven result | Native-tet consequence |
| --- | --- | --- | --- |
| `cheng2000_sliver_exudation.pdf` | Cheng, Dey, Edelsbrunner, Facello, Teng. *Sliver Exudation*. JACM 47(5), 2000. DOI: 10.1145/355483.355487 | A point set with bounded Delaunay radius-edge ratio has a small vertex-weight assignment whose **weighted Delaunay** triangulation has no slivers. The proof is for periodic point sets, not bounded PLCs. | Weight sampling alone cannot change quality. It must be followed by a regular-triangulation rebuild. Do not enable the current proxy implementation. |
| `cheng2003_weighted_delaunay_refinement.pdf` | Cheng, Dey. *Quality Meshing with Weighted Delaunay Refinement*. SIAM J. Comput. 33(1), 2003. DOI: 10.1137/S0097539703418808 | Deterministic bounded-PLC refinement combines boundary recovery, weighted encroachment checks, and final weight pumping. It guarantees bounded radius-edge ratio and removes slivers when input angles are non-acute. | Implement bounded-domain regular refinement, not an isolated post-process. Acute features require a separate protection/chamfer path. |
| `1-s2.0-S0307904X17304493-main.pdf` | Chen et al. *Improved Boundary Constrained Tetrahedral Mesh Generation by Shell Transformation*. Applied Mathematical Modelling 51, 2017. DOI: 10.1016/j.apm.2017.07.011 | Recursive shell transformations reduce constraint intersections before Steiner insertion and can remove existing Steiner points. | Replace the current isolated 2-to-3 rescue with bounded cavity reconnection, first for boundary recovery and then for quality repair. |
| `leng2013.pdf` | Leng, Zhang, Xu. *A Novel Geometric Flow Approach for Quality Improvement of Multi-Component Tetrahedral Meshes*. CAD 45, 2013. DOI: 10.1016/j.cad.2013.05.004 | Boundary vertices need separate fixed, curve, surface, and interior motion rules; quality optimization must be followed by topology repair. | Add feature-classified, fidelity-bounded smoothing only after protected topology operations exist. |
| `ni2017.pdf` | Ni et al. *Sliver-Suppressing Tetrahedral Mesh Optimization with Gradient-Based Shape Matching Energy*. CAGD 2017. DOI: 10.1016/j.cagd.2017.02.004 | Gradient-based shape energy penalizes near-coplanar tets that edge-length or interpolation energies miss. | Use a barriered gradient-shape score as the native quality acceptance objective; do not optimize edge ratios alone. |
| `1-s2.0-S0965997824001893-main.pdf` | Wang et al. *Multi-Threaded Parallel Tetrahedral Mesh Improvement by Combining Atomic Operation and Graph Coloring*. Adv. Eng. Softw. 198, 2024. DOI: 10.1016/j.advengsoft.2024.103782 | Vertex coloring is suitable for smoothing; topology-changing cavity operations need atomic claims and per-thread element storage. | Parallelize only after serial cavity operations are parity-tested. Use coloring for smoothing, ownership tokens for cavity transforms. |
| `../papers/source/pdf/01_klingner_2007_aggressive_tet.pdf` | Klingner, Shewchuk. *Aggressive Tetrahedral Mesh Improvement*. | Worst-element-first improvement using quality-vector comparison, smoothing, vertex insertion, boundary smoothing, boundary edge removal, and multi-face removal can push dihedral bounds far beyond ordinary cleanup. | Add local cavity quality-vector acceptance. Native tet must combine smoothing plus 2-to-3, 3-to-2, 4-to-4, edge-removal, boundary smoothing, and multi-face removal instead of relying on one rescue transform. |
| `../papers/source/pdf/04_cheng_2000_sliver_exudation.pdf` | Edelsbrunner, Guoy, Edelsbrunner, Sullivan, Üngör. *Sliver Exudation*. | Weighted Delaunay exudation removes slivers only when weights affect the triangulation; text extraction is partially garbled locally, so use the PDF directly for proof details. | Keep current exudation proxy disabled until regular-triangulation rebuild exists. Weight sampling without connectivity change is invalid. |

## Verified File Hashes

| File | SHA-256 |
| --- | --- |
| `cheng2000_sliver_exudation.pdf` | `9af50a18d6ab91b71b3538414e18c3877fd108c6c5d4f42b180a02e9ed179387` |
| `cheng2003_weighted_delaunay_refinement.pdf` | `fcf1a69eeeaec2321166de28dcc0b4f11f146017659f03ced5c6c1dc8418b4a7` |
| `1-s2.0-S0307904X17304493-main.pdf` | `ee080a46aeb1dbfab3b3e7bd48a586de5d271da0601316ad1e32690dab93d643` |
| `leng2013.pdf` | `4fd57b97fde724d32e1f9640274a09f28a98e3535c76f363998d9894f0bb6378` |
| `ni2017.pdf` | `18706c58281aed5742b68e03a71a5261a8c8725f4659e6a74d9e6be4c7a3b5b4` |
| `1-s2.0-S0965997824001893-main.pdf` | `41e9f4379c7df6c94149cdda0cb98a9358488e72417456245dfe3568c3dfd809` |
| `../papers/source/pdf/01_klingner_2007_aggressive_tet.pdf` | `8ce37ebd848204da8c4adac9ee56912eb3c950d70d7c1243ee59e8d9afb0b0c8` |
| `../papers/source/pdf/04_cheng_2000_sliver_exudation.pdf` | `66ee9167b412ff10292b11f05801bae176262f3c78845e291ca2c4c212f70b13` |

## Required Native Architecture

1. Build a C++ regular triangulation from positions plus squared vertex weights.
   Every orientation and weighted in-sphere decision needs a filtered-exact
   predicate path. `native_tet_predicates.power_insphere_signs_exact` now
   supplies the exact IEEE-double power determinant. The first conservative
   internal 2-to-3 regularization flip is available; full regular rebuild,
   3-to-2/4-to-4 flips, and boundary recovery remain.
2. Enforce the radius-edge target before exudation. Add orthocentres of skinny
   tetrahedra only after checking weighted segment/facet encroachment.
3. Track local feature size `f(x)` and preserve the vertex-gap invariant:
   `nearest_vertex_distance >= 2 * omega0 * f(x)`.
4. Before pumping a vertex, test its maximum permitted weight against every
   boundary subsegment and subfacet. Refine any challenged boundary element.
5. Only after no weighted element is encroached, assign deterministic weights
   in `[0, omega0^2 * f(v)^2]`, rebuild the regular triangulation, recover the
   surface, then run existing quality and fidelity gates.
6. For acute input angles, use feature protecting balls or chamfer/recovery
   before this path. Cheng-Dey's bounded-domain guarantee assumes non-acute
   input angles.
7. Before inserting a recovery Steiner point, run a bounded recursive shell
   reconnection to reduce the constraint-intersection cavity. It must reject
   any candidate that worsens the protected boundary or its minimum quality.
8. Score each cavity with a gradient-based shape barrier plus signed-volume
   barrier. Apply geometry moves only in the permitted feature class: interior,
   surface tangent plane, curve tangent, or fixed corner.
9. Compare local replacement candidates by sorted quality vectors, not just the
   single worst tetrahedron. Accept only if the changed cavity's lexicographic
   quality vector improves and all protected boundary/fidelity barriers pass.
10. Add the full aggressive-improvement operation set in deterministic order:
   interior smoothing, feature-constrained boundary smoothing, vertex insertion,
   edge removal, 2-to-3, 3-to-2, 4-to-4, and multi-face removal.
11. Keep this optimizer serial until its parity and deterministic-repeat gates
   are green. Then color independent smoothing vertices; claim topology
   cavities atomically and use per-worker output storage.

## Current Gap

`core/generator/native_tet/stellar.py` has sampling helpers named for
exudation, but `_evaluate_weighted_quality_proxy` deliberately ignores the
weights. It is diagnostic-only and must remain disabled until step 1 exists.

## Acceptance Gates

- Regular triangulation changes connectivity for a nonzero weight assignment.
- All accepted tetrahedra have positive signed volume.
- Boundary faces remain conformal after weighted rebuild.
- Sliver count and worst quality improve without worsening Hausdorff fidelity.
- Cube, NACA, torus, thin wall, needle, and boolean-merge regressions pass
  native-only and deterministic-repeat checks.
