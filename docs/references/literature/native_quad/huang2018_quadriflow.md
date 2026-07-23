# Huang et al. 2018 — QuadriFlow

Status: `FULL_READ` (14/14 pages; equations, flow construction, SAT cleanup,
extraction, experiments, limitations, and references). Page 8 was rendered and
visually checked.

- Authors: Jingwei Huang, Yichao Zhou, Matthias Niessner, Jonathan Richard
  Shewchuk, Leonidas J. Guibas
- Venue: Computer Graphics Forum 37(5), 2018
- DOI: `10.1111/cgf.13498`
- Open PDF: https://stanford.edu/~jingweih/papers/quadriflow/quadriflow.pdf

## Method reconstructed

QuadriFlow starts from Instant Meshes orientation and position fields. It keeps
orientation-field singularities but seeks to remove all position-field
singularities. Rotated integer offsets on every input triangle must satisfy:

- regularity: the three consistently rotated offsets sum to zero;
- orientation consistency: their determinant is nonnegative.

The method first minimizes an `L1` change from the unconstrained offsets. It
approximates the resulting integer problem as a min-cost network flow by
balancing variables along breadth-first-search paths, solving at multiple
resolutions. Long offsets are subdivided until their infinity norm is at most
one. A flow theorem supplies feasibility only under the stated connectivity and
capacity assumptions.

Inverted triangles are removed first by greedy local contractions. Remaining
orientation constraints are encoded as SAT over the nine possible integer
offsets. Continuous representatives are then reoptimized by the linear least
squares objective in Equation (9). Vertices on sharp curves are constrained to
slide along the curve's affine hull. Finally, zero offsets collapse vertices;
the two integer right triangles of a cell pair across their hypotenuse to form a
quad.

## Evidence and limitations

- The paper evaluates 17,791 ShapeNet surfaces and shows substantially fewer
  singularities than Instant Meshes, with modestly higher angle/area distortion.
- Position singularity removal is the central robust contribution; it is not a
  complete proof of watertight output.
- The text reports that about 20% of attempted outputs were not watertight when
  the SAT stage could not eliminate every inversion. SAT feasibility is
  NP-complete and the practical solver can time out. Therefore neither
  inversion-free nor watertight output is guaranteed.
- The MIP-to-flow approximation ignores geometric fidelity during its discrete
  phase. Coarse meshes visibly lose thin details such as hands and fingers.
- No hard Hausdorff or feature-reconstruction bound is established.

## AutoTessell mapping

- `QUAD-OFFSET-LEDGER1`: store integer offsets, symmetry rotations, triangle
  residuals, and position singularities as auditable state.
- `QUAD-MCF1`: optional multiresolution min-cost-flow regularizer after the
  basic field engine works; preserve rollback to the unconstrained field.
- `QUAD-INVERSION1`: make every contraction transactional, then use bounded
  local exact/filtered orientation search; solver timeout rejects the candidate.
- `QUAD-FEATURE-SLIDE1`: pin corners and constrain degree-two sharp-feature
  vertices to one-dimensional motion.
- `QUAD-FIDELITY1`: reject a regular topology if bidirectional surface distance,
  patch provenance, or protected-feature coverage exceeds budget.

The paper supports topology regularization as a second-stage optimizer. It does
not justify trading away AutoTessell's hard geometry contract for a lower
singularity count.
