# Du--Wang 2004 — constrained boundary recovery for 3D Delaunay

- Citation: Qiang Du and Desheng Wang, *Constrained Boundary Recovery for
  Three Dimensional Delaunay Triangulations*, International Journal for
  Numerical Methods in Engineering 61(9), 1471-1500 (2004).
- DOI: `10.1002/nme.1120`.
- Status: FULL_READ (implementation-relevant algorithm, proofs, full-mesh
  application, experiments, and references) from an openly reachable PDF on
  2026-07-28. The project has no user-provided archival PDF; do not treat the
  mirror as a redistributable project asset.
- Readable source: https://scispace.com/pdf/constrained-boundary-recovery-for-three-dimensional-delaunay-4hyoa6b2zs.pdf
- DOI verification: https://doi.org/10.1002/nme.1120

## Implementation-relevant evidence

The method separates a cheap first lane (recognise/apply local `Swap23`,
`Swap32`, or `Swap44`) from a guaranteed fallback.  The fallback first makes a
missing face conforming by inserting intersection points, then processes added
edge points one at a time, and finally processes interior face points one at a
time.  Its key invariant is not a particular Chen clusterel template: every
insertion chooses a valid cavity whose boundary protects all existing or
already recovered constraints.  Thus each step monotonically reduces the
remaining added-point configuration without deleting a recovered edge or face.

For a face interior point, the paper constructs a pair of small
face-symmetric Steiner points on opposite sides of the source plane, chooses
the one-sided part of the point ball bounded by the source sub-triangles as a
valid cavity, inserts it, then performs a ball transformation.  The source
face remains a union of triangles until the final one-point case, where the
operation reduces to `Swap32`.  The method explicitly retains the Steiner
point if later vertex suppression cannot safely re-tetrahedralize its ball.

## Consequence for AutoTessell

The failed FOU fixture seeds are not a reason to weaken the immutable
source-triangle proof or guess a Chen Table-12 dispatch.  The immediate missing
production prerequisite is a read-only **constraint-protection ledger**:
before a candidate `cdt_recovery` insertion/retriangulation, enumerate the
source-edge/source-subface keys already recovered, the proposed cavity shell,
and whether the candidate can remove or alter one of those keys.  The first
card is measurement-only (`TET-DUWANG-CONSTRAINT-PROTECTION-AUDIT1`). It must
report the current behaviour and fail closed; no face-point splitting, Steiner
placement, or production mutation is authorized until that ledger passes
minimal → basic → difficult → regression validation.

