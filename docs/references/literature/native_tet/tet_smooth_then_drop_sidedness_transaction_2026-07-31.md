# JJ3 Sidedness Transaction

Date: 2026-07-31

Card: `TET-SMOOTH-THEN-DROP-SIDEDNESS-TXN-1`

## Defect and hypothesis

Line-level tracing on the frozen cube pipeline found two distinct transitions.
The initial Phase-A `smooth_interior` candidate changed same-side internal
faces from 0 to 244, but its existing surface-area guard restored the exact
pre-candidate mesh.  The first persistent transition was the JJ3
`smooth_then_drop_slivers` candidate in `mesher.py`: cube changed from zero
same-side faces to 232, and cylinder changed from zero to 166.  Both candidates
passed the old cell-loss and exterior surface-area checks.

The hypothesis is deliberately narrow: treat JJ3 point smoothing as one atomic
transaction.  Commit only when same-side and ambiguous internal-face counts
each do not increase.  A decrease in ambiguity cannot pay for a new definite
overlap.  Otherwise return the exact pre-candidate array objects.  This card
does not repair a cavity, delete a tetrahedron, alter a threshold, move a source
vertex, or address target-cell count.

## Isolated cavity

The first lexicographic cube cavity after JJ3 has internal face
`[13, 17, 45]`, owner cells `[231, 233]`, and opposite apexes `[52, 288]`.
None is an original source vertex.  Before smoothing its robust orientation
signs are `[0, +1]`; afterwards they are `[+1, +1]`, a definite same-side
overlap.  Signed six-volumes change from `[0, 0.004629629629629628]` to
`[0.00011902174932853562, 0.004122636800391083]`.  Interior vertices 45 and 52
move by 0.027178773677272196 and 0.019533317007334326.  Connectivity is
unchanged and `n_drop=0`.

## Predeclared acceptance and rollback

- A safe opposite-apex candidate commits the exact candidate objects.
- A candidate increasing same-side faces returns the exact input objects and
  preserves their SHA-256 hashes.
- Same-side and ambiguous counts are compared independently; improvement in
  one cannot offset regression in the other.
- Frozen cylinder rejects JJ3 `0 -> 166`, reaches final same-side zero, and
  preserves source boundary, component, provenance, and validity.
- Frozen cube rejects JJ3 `0 -> 232`, reduces final same-side count from 142 to
  4, and honestly remains fail-closed with no output artifact.
- Frozen sphere commits the non-worsening JJ3 candidate `120 -> 120` and keeps
  its prior final count of 108 and fail-closed result.
- Three cylinder runs have identical point/connectivity hashes.
- Transaction overhead remains below 10% of generation wall time.

## Research basis and provenance

- WildMeshing Toolkit documents explicit per-operation invariants and exact
  rollback when an after-operation check fails.  Its repository is MIT:
  <https://github.com/wildmeshing/wildmeshing-toolkit>.
- CGAL 6.2 tetrahedral remeshing requires valid connectivity and positive cell
  orientation and describes topology-preserving atomic remeshing operations:
  <https://doc.cgal.org/latest/Tetrahedral_remeshing/index.html>.  This GPL
  implementation is reference-only and remains outside the native core.
- Hu et al., *Fast Tetrahedral Meshing in the Wild*, ACM TOG 2020, DOI
  `10.1145/3386569.3392385`, motivates maintaining a valid tetrahedral mesh
  throughout local optimization.
- The project-local `validate.py` already makes JJ3 void-free: it copies point
  coordinates, keeps connectivity, and performs no tet deletion by default.
  The missing contract was candidate-side embedding validation.

No external code was copied, no dependency was added, and `vendor/dependencies/` is
unchanged.

## Measured evidence

### Frozen cylinder, target 2,000

- JJ3 before: same-side 0, ambiguous 412.
- JJ3 candidate: same-side 166, ambiguous 4, moved count 254, dropped 0.
- Final: 353 points, 1,140 tets, same-side 0, ambiguous 0, duplicate 0,
  non-manifold face 0, inverted 0, degenerate 0, strict topology valid.
- Point SHA-256:
  `453039a0fb6341d8d05d6985bf88f5188a0e86d9214ee0d7979a632167348f04`.
- Tet SHA-256:
  `6f50e4cab807dc21c4d4433550bb410fc97af72084f048e8e6023eb1453a3426`.
- The requested-cell error is 860 cells, or 43%; target count remains deferred
  behind strict topology.

### Frozen cube, target 2,000

- JJ3 before: same-side 0, ambiguous 686.
- JJ3 candidate: same-side 232, ambiguous 110, moved count 226, dropped 0.
- Final: 300 points, 1,284 tets, same-side 4, ambiguous 0, duplicate 0,
  non-manifold face 0, inverted 0, degenerate 0.
- Final strict topology remains invalid; no `polyMesh` is published.

### Frozen cube checkpoint, target 10,000

- JJ3 before: same-side 0, ambiguous 4,620.
- JJ3 candidate: same-side 1,108, ambiguous 228.
- Pre/rollback point SHA-256:
  `b7856955a75e1d95aced2302b96eb9b4da641683b8b955d0ede9153ff1124978`.
- Pre/rollback tet SHA-256:
  `086f3e52462ebeb80206dd4724d70faf4a0e24604e74ef913cdaceafd1f00dab`.
- Candidate point SHA-256:
  `785e9199081ceecd2c3a9f4aa902cdd076fdf186567d3bd1c1f3c00787067925`.
- Candidate tet hash equals the pre hash, proving geometry-only mutation.
- Final same-side count is 12 and duplicate groups are zero, improved from the
  Tet42 oracle's one duplicate group, but Gate 5 still fails.

### Runtime

One cylinder transaction took 13.465 ms in a 7.584 s generation, or 0.178% of
wall time.  This is below the fixed 10% ceiling.

## Remaining blocker

Cube retains four and sphere retains 108 same-side faces from later or earlier
operations.  They remain strict failures.  The orchestrator P4C route also
falls through to a Netgen result whose exact source-facet provenance fails;
that is a separate routing/provenance card and is not claimed by this change.
