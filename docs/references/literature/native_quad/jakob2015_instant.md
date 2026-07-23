# Jakob et al. 2015 — Instant Field-Aligned Meshes

Status: `FULL_READ` (15/15 pages; equations, hierarchy, extraction, experiments,
limitations, and references). Page 6 was rendered and visually checked.

- Authors: Wenzel Jakob, Marco Tarini, Daniele Panozzo, Olga Sorkine-Hornung
- Venue: ACM Transactions on Graphics 34(6), 2015
- DOI: `10.1145/2816795.2818078`
- Project and PDF: https://rgl.epfl.ch/publications/Jakob2015Instant

## Method reconstructed

For quadrilateral output, the method optimizes a four-fold rotationally
symmetric orientation field (4-RoSy) followed by a four-fold positional
symmetry field (4-PoSy). Neighbor representatives are compared in local tangent
planes over their finite symmetry classes. Intrinsic energies measure agreement
after parallel transport; extrinsic energies compare embedded representatives
and naturally snap the fields to sharp geometric features.

The position representatives live on tangent lattices with target spacing
`rho`. Equation (5) minimizes pairwise disagreement after the best integer
lattice translation. Equation (6) is its extrinsic counterpart. Each nonlinear
Gauss--Seidel update performs a small exhaustive search over symmetry or integer
choices and then averages the aligned representatives.

A multiresolution graph hierarchy is produced through deterministic-compatible
vertex aggregation scored by normal agreement and relative area. Roughly six
Gauss--Seidel sweeps are run per level from coarse to fine. The implementation
uses graph coloring (typically five to eight colors) for parallel updates and a
lock-free disjoint-set structure during extraction.

Extraction collapses zero-jump vertex clusters; unit integer translations
become output edges. Integer jumps accumulated around cycles expose orientation
and position singularities. Position singularities create T-junctions,
non-quad polygons, or irregular valence. Optional Catmull--Clark conversion can
make a pure-quad mesh, but replaces these defects with valence-3/5 pairs.

## Evidence and limitations

- Runtime and memory scale close to linearly over inputs ranging to very large
  meshes; multiresolution avoids the cost of a global mixed-integer solve.
- Extrinsic energy gives useful feature alignment without a separate feature
  detector or tuning parameter.
- The hierarchy and local nonlinear iterations have no global-optimum proof;
  randomization and coarse-to-fine continuation only help empirically.
- The local method generally creates more singularities than global
  parameterization methods.
- Coarse, high-genus, detailed, or non-manifold inputs can yield non-manifold
  extraction. Offending elements are discarded, which may leave holes or
  visible artifacts. “Graceful degradation” is not a correctness guarantee.

## AutoTessell mapping

The existing triangle-pair merger is retained as a conservative fallback, not
described as a complete quadrangulator. A real native quad path needs:

- `QUAD-ROSY1`: intrinsic 4-RoSy field with deterministic symmetry selection,
  plus optional extrinsic feature alignment.
- `QUAD-POSY1`: lattice-valued 4-PoSy field tied to the sizing/metric field.
- `QUAD-MULTIRES1`: reproducible coarsening, colored relaxation, and convergence
  telemetry at every level.
- `QUAD-SINGULARITY1`: explicit orientation/position singularity ledger rather
  than implicit cleanup.
- `QUAD-EXTRACT1`: transactional extraction guarded by manifoldness,
  orientation, feature, and fidelity checks; never silently discard cells.

Falsification suite: cube, torus, sharp wedge, thin feature, noisy scan,
non-manifold input, and large mesh. Record singularity count, quad fraction,
scaled Jacobian, angle range, symmetric distance, determinism, memory, and time.
