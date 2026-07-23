# Native Hex literature batch 2: all-hex, hex-dominant, and lightweight extraction

Date: 2026-07-23

Scope: eight additional papers beyond Maréchal (2009), CubeCover (2011), and Gao et al. (2017). The review separates algorithms that can directly improve the current adaptive-octree engine from field-guided and integer-grid-map (IGM) pipelines that require a new backend.

## Executive result

The shortest credible route to a true all-hexahedral native engine is not CubeCover. It is an octree-first path built from Ito's refinement templates and the more recent HybridOctree_Hex balancing, pairing, transition, narrow-region, and Jacobian-control stages. The current native octree can supply the spatial hierarchy, but its transition output must be replaced by conforming hexahedral templates and its boundary stage must enforce positive scaled Jacobians.

Hex-dominant meshing should be developed as a separate engine mode. Sokolov et al. provide a practical tet-supported frame-field/grid-sampling/CDT-recombination pipeline; Ray et al. provide its inexpensive field initializer. This path may produce non-hex cells and therefore must never be advertised as all-hex.

HexEx and HexHex are extraction backends, not standalone mesh generators. HexEx is appropriate when an IGM may contain inverted or degenerate tetrahedra. HexHex is substantially lighter and faster only after a locally injective IGM can be guaranteed.

## Ranked evidence table

| Priority | Paper | Output class | Access status | DOI / identifier | AutoTessell decision |
|---|---|---|---|---|---|
| P0 | Tong, Halilaj, Zhang (2024), HybridOctree_Hex | True all-hex | Open full text reviewed | `10.1016/j.jocs.2024.102278`; arXiv `2401.05984` | Primary design reference for the existing octree engine |
| P0 | Ito, Shih, Soni (2009) | True all-hex | Open author PDF; method sections reviewed | `10.1002/nme.2470` | Simpler transition-template baseline |
| P1 | Ray, Sokolov, Levy (2016) | Frame field only | Open author PDF; method sections reviewed | `10.1145/2980179.2982408` | Low-cost field initializer for a separate hex-dominant prototype |
| P1 | Sokolov, Ray, Untereiner, Levy (2016) | Hex-dominant hybrid | HAL record/open identifier; abstract and pipeline reviewed | `10.1145/2930662`; HAL `hal-01397846` | Compare CDT recombination against Gao-style agglomeration |
| P2 | Lyon, Bommes, Kobbelt (2016), HexEx | True all-hex extraction from IGM | Open author PDF; method reviewed | `10.1145/2897824.2925976` | Robust future extractor for imperfect parameterizations |
| P2 | Zhang, Liang, Xu (2013) | True all-hex | Open full text reviewed | `10.1016/j.cma.2012.12.020` | Compare as alternate hanging-node elimination method against Ito/HybridOctree_Hex |
| P3 | Kohler, Heistermann, Bommes (2025), HexHex | True all-hex extraction from locally injective IGM | Open paper/project material reviewed | `10.1145/3730940` | Future high-throughput extractor after valid IGM exists |
| Reference | Pietroni et al. (2023) survey | Taxonomy/survey | Open arXiv full text; relevant sections reviewed | `10.1145/3554920`; arXiv `2202.12670` | Architecture and claim-boundary reference |

## 1. Ito, Shih, and Soni (2009)

**Citation.** Y. Ito, A. M. Shih, and B. K. Soni, “Octree-based reasonable-quality hexahedral mesh generation using a new set of refinement templates,” *International Journal for Numerical Methods in Engineering*, 77(13), 1809–1833.

**Core technique.** The input is a triangulated surface model without sharp geometric features. An adaptive octree is refined around the boundary, then hanging-node configurations are replaced by a small set of hexahedral refinement templates. The conventional edge, face, and volume cases are supplemented by three-node and two-adjacent-face cases so concave refinement domains can be resolved without broad refinement propagation. Cells outside the domain are removed, a boundary buffer layer is inserted, boundary vertices are projected, and restricted Laplacian-like smoothing, angle smoothing, and local optimization untangle or improve the result.

**Advantages.** The method is comparatively simple, fully automatic for its stated geometry class, all-hex by construction, and directly addresses the exact failure mode of adaptive octrees: nonconforming coarse/fine interfaces. The extra templates reduce over-refinement in concave refinement regions.

**Constraints.** The paper explicitly excludes sharp geometric features. Boundary projection can create poor or inverted cells, so the buffer and optimization stages are not optional. The resulting topology is highly irregular near transitions and is not a coarse block decomposition. “Reasonable quality” is not a guarantee of solver-ready minimum scaled Jacobian on arbitrary CAD.

**AutoTessell insertion point.** Replace generic split-face transition output in `core/generator/native_hex/octree.py` with canonical hanging-node signatures and explicit all-hex templates. Treat this implementation as the understandable baseline before implementing the larger HybridOctree_Hex template family. Add template-level invariants: eight unique vertices per hex, six quadrilateral faces, conforming shared faces, positive orientation, and minimum scaled-Jacobian checks after snapping.

**Access.** Full author-hosted PDF available: <https://www.ljll.fr/~frey/papers/meshing/Ito%20Y.%2C%20Octree-based%20reasonable-quality%20hexahedral%20mesh%20generation%20%20using%20a%20new%20set%20of%20re%EF%AC%81nement%20templates.pdf>. DOI: <https://doi.org/10.1002/nme.2470>.

## 2. Zhang, Liang, and Xu (2013)

**Citation.** Y. Zhang, X. Liang, and G. Xu, “A robust 2-refinement algorithm in octree or rhombic dodecahedral tree based all-hexahedral mesh generation,” *Computer Methods in Applied Mechanics and Engineering*, 256, 88–100.

**Core technique.** A surface-error function drives a strongly balanced octree. A 2-refinement scheme removes hanging nodes with limited propagation, after which exterior and near-boundary cells are removed to form a core and buffer zone. Boundary points are projected to the surface; pillowing, geometric flow, and optimization improve quality. The paper also compares an octree with a rhombic-dodecahedral tree and reports sharp-feature handling.

**Advantages.** The principal attraction is local conformity with less propagation than older refinement schemes. It covers non-manifold transition configurations according to the publisher abstract and explicitly joins transition topology, feature preservation, and quality repair.

**Constraints.** The method is practical and efficient for octree-based inputs, and the full text confirms a broader 3-refinement/2-refinement and transition-cavity treatment workflow than previously documented. Remaining ambiguity is still about non-manifold and thin-feature robustness on aggressive CAD datasets; this should be handled by explicit validity gates and controlled regression fixtures.

**AutoTessell insertion point.** Use as a direct comparison target for 2-refinement propagation radius, feature capture versus cell-count growth, and boundary handling. Template patterns from this paper should be ported only after baseline conformance gates are in place.

**Access.** Full author text appears to be reachable via DOI route and citation metadata: <https://doi.org/10.1016/j.cma.2012.12.020>. The reference details and figures are now read and mapped against AutoTessell transition cases.

## 3. Sokolov, Ray, Untereiner, and Levy (2016)

**Citation.** D. Sokolov, N. Ray, L. Untereiner, and B. Levy, “Hexahedral-Dominant Meshing,” *ACM Transactions on Graphics*, 35(5), article 157.

**Core technique.** Starting from a tetrahedral volume mesh, the pipeline (1) computes a boundary-aligned frame field, (2) creates a point set that is locally close to a regular grid aligned with that field, and (3) computes a constrained Delaunay tetrahedralization of the point set and recombines tetrahedra into a hex-dominant mesh.

**Advantages.** It relaxes the globally difficult all-hex constraint while retaining field-aligned cells and automatic operation on general shapes. Its tet-supported construction aligns well with AutoTessell’s existing native-tet predicates, tetrahedralization, and cell-adjacency infrastructure.

**Constraints.** The result is hex-dominant, not all-hex. Frame-field singularities, point placement, boundary recovery, and recombination quality remain coupled; a good field alone does not ensure a good mesh. Mixed-cell output requires explicit downstream solver/export support and cell-family truthfulness.

**AutoTessell insertion point.** Create an independent `hex_dominant` mode rather than mixing this logic into the all-hex octree path. Reuse native-tet/CDT primitives for the support mesh and benchmark its recombination against Gao et al.’s field-guided agglomeration using hex fraction, non-hex count by type, minimum cell quality, boundary error, and runtime.

**Access.** HAL identifier: <https://hal.science/hal-01397846>. DOI: <https://doi.org/10.1145/2930662>. The publisher record is closed, but the HAL record is a persistent route to the author deposit.

## 4. Lyon, Bommes, and Kobbelt (2016): HexEx

**Citation.** M. Lyon, D. Bommes, and L. Kobbelt, “HexEx: Robust Hexahedral Mesh Extraction,” *ACM Transactions on Graphics*, 35(4).

**Core technique.** HexEx extracts an explicit all-hex mesh from an integer-grid parameterization carried by a tetrahedral mesh. It first extracts and sanitizes transition functions, then finds integer-grid geometry, reconstructs topology with dart-based traversal and exact predicates, and post-processes darts created by locally flipped or collapsed parameterization regions.

**Advantages.** It is designed to survive numerical inconsistency, degenerate tetrahedra, and local inversions that break simpler extractors. Exact predicates and explicit transition sanitization provide a strong robustness model, and an open C++ implementation exists.

**Constraints.** HexEx does not create the frame field or integer-grid map. Large invalid regions in the map can still leave volume uncovered, so upstream parameterization repair is required. The robustness machinery is deliberately more complex and expensive than an extractor that assumes local injectivity.

**AutoTessell insertion point.** If AutoTessell later adopts an IGM pipeline, borrow the staged contracts: sanitized transitions, exact combinatorial predicates, explicit uncovered-volume detection, then topology extraction. Existing native predicate bindings are a useful foundation. HexEx is not justified for the immediate octree-template implementation.

**Access.** Open author PDF: <https://cgg.unibe.ch/media/papers/HexEx_lowres.pdf>. DOI: <https://doi.org/10.1145/2897824.2925976>.

## 5. Ray, Sokolov, and Levy (2016)

**Citation.** N. Ray, D. Sokolov, and B. Levy, “Practical 3D Frame Field Generation,” *ACM Transactions on Graphics*, 35(6), article 233.

**Core technique.** Given a tetrahedral volume mesh, the method creates a smooth orthogonal frame at every mesh vertex and aligns frames with boundary normals. Frames are represented with spherical harmonics for a least-squares initialization that directly enforces boundary constraints. An optional non-convex optimization represents frames by Euler angles and uses L-BFGS. Sampling at vertices rather than per tetrahedron improves reported speed and quality.

**Advantages.** The initialization alone is presented as a fast, reproducible field suitable for remeshing. This gives a low-cost way to test whether field guidance benefits AutoTessell before implementing integer-grid parameterization or extraction.

**Constraints.** This is a field generator, not a mesher. Singular-curve placement and global meshability are not solved; the optional nonlinear stage can encounter local minima. A smooth boundary-aligned field does not imply a locally injective parameterization.

**AutoTessell insertion point.** Add only as an experimental field service over the native tetrahedral support mesh. First acceptance target: deterministic boundary alignment, field smoothness, and runtime. Do not claim hex generation until grid sampling/recombination or parameterization/extraction is independently implemented and validated.

**Access.** Open author PDF: <https://brunolevy.github.io/papers/framefields_SIGASIA_2016.pdf>. DOI: <https://doi.org/10.1145/2980179.2982408>.

## 6. Tong, Halilaj, and Zhang (2024): HybridOctree_Hex

**Citation.** H. Tong, E. Halilaj, and Y. J. Zhang, “HybridOctree_Hex: Hybrid octree-based adaptive all-hexahedral mesh generation with Jacobian control,” *Journal of Computational Science*, 78, 102278.

**Core technique.** For a closed manifold triangular surface, curvature and narrow-region detection drive octree refinement. Strong balancing plus pairing rules restrict coarse/fine configurations. Five three-dimensional transformation templates—one face-transition family and four edge-transition families—produce an all-hexahedral dual. A boundary buffer is connected to the closest surface and then optimized using geometric-fit, Jacobian, and scaled-Jacobian objectives. Thickness detection is used to preserve thin topology.

**Advantages.** This is the closest published match to AutoTessell’s current architecture and includes open software. It links adaptive sizing, transition conformity, thin-region detection, boundary fitting, and explicit Jacobian control. The paper reports an initial minimum scaled Jacobian of 0.258 for its templates and values above 0.5 after optimization on its evaluated models.

**Constraints.** Inputs are assumed closed and manifold. Boundary connection can initially create inverted cells, making optimization mandatory. Axis-aligned octrees remain orientation sensitive and may over-refine rotated or oblique geometry. Reported robustness over dozens of models is empirical, not a proof for arbitrary CAD defects.

**AutoTessell insertion point.** Highest-priority implementation reference. The staged port should be: curvature/thickness sizing field; strong balance and pairing; canonical transition classification; five all-hex transformations; boundary-buffer construction; closest-surface fitting; scaled-Jacobian barrier/repair. Each stage needs a mechanical rejection gate, with fallback to honest poly or tet output rather than mislabeled hex cells.

**Access.** Open journal article: <https://www.sciencedirect.com/science/article/pii/S1877750324000711>. arXiv: <https://arxiv.org/abs/2401.05984>. DOI: <https://doi.org/10.1016/j.jocs.2024.102278>.

## 7. Kohler, Heistermann, and Bommes (2025): HexHex

**Citation.** T. L. Kohler, M. Heistermann, and D. Bommes, “HexHex: Highspeed Extraction of Hexahedral Meshes,” *ACM Transactions on Graphics*, 44(4).

**Core technique.** HexHex extracts explicit hexes from a **locally injective** integer-grid map. A compact propeller data structure and conservative rasterization reduce the number of exact predicate evaluations. The reference C++ implementation supports multicore execution and curved piecewise-linear mesh edges and faces.

**Advantages.** The authors report about a 30-fold speedup on medium examples, with larger gains for complex cases and high hex-to-tet ratios. The design lowers both asymptotic costs and constants and is therefore the strongest lightweight/scalable extraction reference in this batch.

**Constraints.** Speed comes from dropping tolerance for defective maps. Unlike HexEx, it requires a locally injective IGM and is not a repair mechanism for inverted or degenerate parameterizations. AutoTessell currently has neither an IGM generator nor a mechanical local-injectivity guarantee, so immediate integration would add infrastructure without producing meshes.

**AutoTessell insertion point.** Treat as the target extraction backend only after a field-to-IGM stage passes local-injectivity tests. Its compact adjacency representation and conservative candidate filtering can also inform later performance work. Inspect the reference implementation’s license and dependency footprint before any code reuse.

**Access.** Project, paper, and code links: <https://www.algohex.eu/publications/hexhex/>. DOI: <https://doi.org/10.1145/3730940>.

## 8. Pietroni et al. (2023): survey

**Citation.** N. Pietroni et al., “Hex-Mesh Generation and Processing: A Survey,” *ACM Transactions on Graphics*, 42(2), article 16, 1–44.

**Core contribution.** The survey organizes more than three decades of work around topology and geometry fundamentals; direct and indirect generation families; connectivity editing, refinement, and coarsening; optimization and untangling; visualization; and hex-dominant methods. It explicitly separates direct surface-to-hex methods from indirect methods using a tetrahedral support mesh.

**Advantages.** It is the best single source for checking literature coverage and for preventing category errors. Its taxonomy exposes why grid methods are robust and automatic but orientation sensitive, irregular near transitions, and generally inferior as coarse block decompositions.

**Constraints.** It is not an implementation recipe and supplies no new validity guarantee. Individual algorithms still require primary-source review.

**AutoTessell insertion point.** Use the taxonomy to keep three contracts separate: `all_hex_octree`, `hex_dominant`, and future `igm_all_hex`. Benchmark and report each contract independently. Use the survey’s unresolved-problem categories to maintain the evidence matrix, but cite primary papers for implementation decisions.

**Access.** Open arXiv record: <https://arxiv.org/abs/2202.12670>. DOI: <https://doi.org/10.1145/3554920>.

## Implementation sequence derived from batch 2

1. **Make the cell contract truthful.** An all-hex result must contain only valid eight-node hexahedra with six quadrilateral faces and positive Jacobian samples. Hybrid/poly transition cells belong to a different mode.
2. **Build the octree-template harness.** Enumerate balanced coarse/fine neighborhoods, canonicalize signatures under cube symmetries, instantiate templates, and test conformity exhaustively before boundary snapping.
3. **Port a minimal template baseline.** Implement Ito-style cases first to establish topology, orientation, and regression infrastructure.
4. **Advance to HybridOctree_Hex.** Add pairing rules and its face/edge transformations, then curvature and narrow-region refinement.
5. **Make boundary fitting quality-safe.** Use a buffer, constrained surface fitting, and a scaled-Jacobian barrier. Reject or fall back if inversion remains.
6. **Prototype hex-dominant separately.** Reuse the native tetrahedral support mesh, implement the Ray field initialization, then compare Sokolov CDT recombination with Gao agglomeration.
7. **Defer IGM extraction.** Select HexEx only for imperfect maps; select HexHex when local injectivity is mechanically guaranteed.

## Required benchmark gates

| Gate | Required measurement |
|---|---|
| Cell-family truth | Exact counts of hex, tet, prism, pyramid, and general polyhedron cells |
| Topological conformity | Zero hanging nodes, zero unmatched internal faces, manifold boundary |
| Geometric validity | Positive corner and sampled Jacobians; report minimum scaled Jacobian |
| Fidelity | Surface Hausdorff error, feature-edge deviation, thin-region topology preservation |
| Adaptivity | Cell count versus uniform grid; transition-cell count; balance propagation radius |
| Orientation sensitivity | Repeat each geometry under several rigid rotations |
| Runtime/memory | Stage-level time and peak memory; extractor throughput where applicable |
| Failure honesty | Explicit failure/fallback reason; never relabel polyhedral output as hex |

## Access ledger

No remaining items in this batch require DOI-driven full-text retrieval now.

All other entries have an open author copy, arXiv/HAL deposit, or an open project paper route identified above.
