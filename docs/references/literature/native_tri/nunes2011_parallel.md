# Nunes et al. - A Parallel Remeshing Method

## Bibliography and access

- Cassia R. S. Nunes, Pollyana C. G. Mayrink, Renato C. Mesquita, David A.
  Lowther. The PDF prints the first author's name as `Cassia` with an accent;
  the ASCII form is used here for repository portability.
- *IEEE Transactions on Magnetics* 47(5), May 2011, pp. 1202-1205.
- DOI: `10.1109/TMAG.2010.2090944`.
- Supplied file: `C:/Users/user/Downloads/nunes2011.pdf`.
- Review status: `FULL_READ` on 2026-07-23. All four pages were read and all
  four were rendered at 2x resolution and visually inspected. The least-
  squares equation, partition figures, Algorithm 1, numerical results, and
  references were legible and consistent with extraction.

This is the paper previously represented by the inaccessible DOI
`10.1109/TMAG.2010.2090944`. The supplied PDF establishes that its lead author
is **Nunes**, not Almeida.

## Problem and method

The paper accelerates an earlier surface-remeshing method for poor triangle
meshes produced by Boolean CAD operations or surface reconstruction. It is
explicitly motivated as preprocessing for tetrahedral volume mesh generation:
input vertices, edges, faces, slits, and holes become constraints that a volume
mesher cannot freely remove.

Each input face and its surrounding vertices are fitted by an overlapping
B-spline patch. For samples `p_tau`, control points `c_omega`, and precomputed
blending functions `M_omega`, the paper minimizes

```text
F = sum_tau ||s(u_tau,v_tau)-p_tau||^2
  = sum_tau [sum_omega M_omega(u_tau,v_tau)c_omega - p_tau]^2.
```

This is an ordinary least-squares fit. The resulting patch collection is used
as smooth geometric support for edge swap, collapse, split, and vertex
relocation. A candidate is intended to be applied only if geometric
approximation is preserved and mesh quality improves.

There is a notable presentation discrepancy. Section III summarizes the
serial schedule as split long edges, collapse short edges, swap improving
edges, then relocate. Algorithm 1 instead loops over section edges and tries
collapse first, else swap, else split, followed by relocation. The paper does
not resolve this difference or provide thresholds, so neither ordering should
be treated as a normative algorithm specification.

## Parallel decomposition

The work divides parallelism into two distinct phases.

1. **Immutable patch fitting.** Faces are divided evenly among at most as many
   groups as processors. Patch inputs do not change during fitting, so groups
   can read the mesh and solve their least-squares problems independently.
2. **Topology modification.** The surface is partitioned into independent
   sections and separating intersections. Sections are at least two edges
   apart so an edit in one cannot interfere with another. All sections are
   processed in parallel first; intersections are processed afterward using
   the same scheme.

The implementation stores the B-rep in doubly connected lists. Candidate
evaluation acquires reader permission, but a collapse/swap/split needs global
writer permission and blocks the other processors. Vertex relocation is the
exception. The authors identify this data structure and locking policy as the
main scaling bottleneck and propose a thread-safe array-based half-edge
representation.

The central transferable concept is therefore not the particular B-spline
fit. It is the **conflict-radius schedule**: edits whose affected neighborhoods
are separated can be evaluated concurrently, followed by a controlled pass
over separator regions.

## Evidence

- Greek head: 16,532 faces, 24,798 edges, 8,268 vertices. Overall speedup was
  1.24 on two processors and 1.31 on eight. Patch-generation speedup rose from
  1.73 on two processors to 2.06 on eight.
- Shark: 20,104 faces, 30,156 edges, 10,054 vertices. Overall speedup was 1.22
  on two processors; patch-generation speedup was 1.6.
- Results are visual only for mesh quality. No triangle-quality distribution,
  geometric-error values, topology audit, load balance, efficiency, or
  statistical variability is reported.

The low end-to-end speedups directly support the authors' bottleneck claim:
independent read-only geometry work parallelizes, while coarse-grained writes
serialize topology changes.

## Guarantees, assumptions, and limitations

- No convergence, minimum-angle, approximation-error, topology, or complexity
  guarantee is proved.
- The smooth support is a local B-spline approximation, not the original CAD
  surface and not a certified Hausdorff envelope.
- The paper says geometry is preserved and quality increased but does not give
  the error metric, quality metric, tolerance, or complete acceptance tests.
- It does not specify how sections/intersections are constructed, balanced, or
  refreshed after topology changes beyond the two-edge separation statement.
- Reader-writer locking protects data-race safety but effectively serializes
  topological commits. Determinism and schedule-independent output are not
  studied.
- Experiments are small by current standards and include at most eight
  processors; there is no many-core or million-triangle evidence.
- The method assumes a usable input B-rep and smooth surface samples. It is not
  a repair method for arbitrary non-manifold triangle soup.

## Difference from the current AutoTessell engine

AutoTessell's native triangle path is deterministic and serial at the logical
operator level. `isotropic.py` vectorizes several NumPy calculations but still
commits split/collapse/flip/relocate passes sequentially. It does not build
distance-two independent edit sections, a conflict graph, or a separator pass.

The current code projects the final candidate vertices to original triangles
and applies post-hoc topology, orientation, drift, protected-edge, and quality
gates. It does not construct overlapping B-spline patches. That omission is
not itself a defect: projection to the actual input triangles is preferable to
introducing an uncertified smoothed surrogate when geometric fidelity is the
contract.

The current list/set/dictionary-based topology representation is also not a
transactional thread-safe half-edge store. Directly adding Python threads to
the existing mutation loops would add lock contention and nondeterministic
commit order without addressing algorithmic conflicts. Parallel work should
start with immutable candidate evaluation and deterministic conflict-free
batches, not concurrent in-place mutation.

## Falsifiable implementation cards

### `TRI-PAR-CONFLICT-BATCH-1` - deterministic independent edits

- Build candidate operation footprints, create a conflict relation for
  overlapping vertices/faces and distance-two neighborhoods, and produce
  deterministic color batches using stable edge identifiers.
- Evaluate one color in parallel from an immutable mesh snapshot. Commit
  accepted edits in stable identifier order after revalidating each footprint;
  then rebuild affected candidates.
- Pass criterion: 1-, 2-, 4-, and 8-worker runs produce identical vertex/face
  hashes and diagnostics; ThreadSanitizer-equivalent native tests or stress
  tests show no races; no two edits in one evaluation batch overlap.
- Reject criterion: result depends on scheduling, a commit sees stale
  topology, or parallel output differs in quality/error from serial output.

### `TRI-PAR-GEOMETRY-1` - parallel read-only queries

- Parallelize immutable work first: feature/curvature estimation, candidate
  scoring, nearest-surface queries, and conservative error sampling. Keep
  topology commits serial until conflict-batch correctness is established.
- Pass criterion: on at least one million triangles, four workers give at
  least 2x speedup in the targeted phase with identical numerical outputs and
  bounded peak memory; end-to-end runtime must also improve measurably.
- Reject criterion: phase speedup is hidden by serialization, memory exceeds
  the benchmark budget, or shared acceleration structures are not read-safe.

### `TRI-PAR-SCALE-BENCH-1` - honest scaling gate

- Record wall time, speedup `S_p=T_1/T_p`, parallel efficiency `S_p/p`, peak
  memory, accepted/rejected operation counts, mesh hash, certified error, and
  triangle-quality percentiles for 1/2/4/8 workers.
- Pass criterion: quality and correctness metrics are invariant, median of at
  least five warmed runs improves end-to-end at four workers, and confidence
  intervals are reported.
- Reject criterion: reporting only the easily parallel patch/query phase or
  claiming scalability from sub-1.5x end-to-end speedup.

