# Hu et al. - Error-Bounded and Feature-Preserving Surface Remeshing

## Bibliography and access

- Kaimo Hu, Dong-Ming Yan, David Bommes, Pierre Alliez, Bedrich Benes.
- IEEE Transactions on Visualization and Computer Graphics, 2017.
- DOI: `10.1109/TVCG.2016.2632720`.
- Open manuscript: `https://arxiv.org/pdf/1611.02147`.
- Review status: `FULL_READ` on 2026-07-23.

## Problem and contract

The method optimizes three competing goals: geometric fidelity, minimum
triangle angle, and mesh complexity. Only the approximation-error threshold
`delta` is a hard constraint. Desired minimum angle `theta` and maximum vertex
count `N` are optimization targets because a mesh satisfying all three may not
exist.

The input contract is a 2-manifold triangle mesh. The method is not a repair
algorithm for arbitrary non-manifold triangle soups.

## Algorithm

The algorithm has three stages.

1. Initial simplification repeatedly collapses and relocates the edge with the
   lowest length-and-opposite-angle priority while respecting the error bound.
2. A dynamic priority queue stores angles below `theta`. For the current worst
   angle it attempts, in order, edge collapse plus relocation, vertex
   relocation, and longest-side propagation followed by split plus relocation.
3. Connectivity is frozen and queued vertex relocation continues until the
   local angle improvement falls below `0.1` degrees.

The implementation deliberately represents a flip as split followed by
collapse. The authors argue that direct flips complicate implicit feature
preservation and can destroy creases.

Every candidate operation is simulated before commit. Acceptance requires:

- the edge-collapse link condition;
- no triangle orientation reversal or fold-over;
- local minimum angle does not regress below the current feasible bound;
- the sampled two-sided surface error remains below `delta`;
- 2-manifold topology remains valid.

## Error metric

The paper uses a symmetric two-sided Hausdorff approximation. Both input and
result surfaces receive stratified vertex, edge, and face samples. Sample-to-
surface distance is evaluated against the full opposing surface rather than a
second point cloud. Static input queries use an AABB tree.

Only a local result patch changes after an operation. The result-to-input side
is recomputed on that patch. For the input-to-result side, stored closest links
whose targets lie in the affected outer patch are updated. The authors report
that a one-ring local patch with about ten samples per face captured more than
99.9 percent of global nearest links in their experiment.

Important limitation: sampled Hausdorff distance underestimates exact
Hausdorff distance. AutoTessell must therefore add a conservative sampling-gap
margin or an exact/envelope verification at finalization before claiming a hard
bound.

## Feature preservation

The paper avoids a brittle binary sharp-feature detector. It defines a soft
feature intensity from absolute discrete Gaussian curvature (angle defect) and
the maximum incident unsigned dihedral angle. This intensity influences the
initial position after collapse/split and weights the nonlinear local
relocation objective.

Relocation alternates between closest-pair updates and an analytic weighted
least-squares vertex position. The default step ratio is `lambda = 0.9`; the
paper found two iterations to be a useful effectiveness/runtime compromise.

For AutoTessell, this soft intensity is useful as an optimization weight, but it
cannot replace explicit semantic wall, patch-interface, boundary, and
user-selected feature constraints. Those classes must remain hard.

## Evidence and limitations

- The method achieved minimum angles above 35 degrees on its test set with
  bounded sampled error, but it has no convergence proof for a requested
  minimum angle.
- Very high angle targets can cause infinite refinement loops or degenerate
  edges.
- The method does not globally optimize connectivity, so valence regularity can
  trail global sampling/CVT methods.
- It only supports 2-manifold input.
- Noise is interpreted as feature intensity and can therefore be preserved.
- Initial simplification can reduce vertex count substantially but costs two to
  three times more runtime in the reported examples.

## AutoTessell decision

Adopt the feasibility/optimization separation and the worst-angle queue. Do not
copy the sampled Hausdorff claim as an exact guarantee, do not replace semantic
features with the soft feature intensity, and do not enable unbounded split
propagation.

First two falsifiable cards:

1. `TRI-ERROR-GATE1`: candidate operations use link, fold-over, semantic
   feature, and conservative two-sided local error guards with rollback.
2. `TRI-WORST-ANGLE1`: operate only on the current worst-angle queue, bounded by
   the cap-aware vertex budget and a deterministic operation limit.

