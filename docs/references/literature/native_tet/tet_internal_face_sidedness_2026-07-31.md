# Strict Internal-Face Sidedness Detection

Date: 2026-07-31

Card: `TET-INTERNAL-FACE-SIDEDNESS-1`

## Defect and hypothesis

The Pipeline cylinder result reported one oriented-degenerate OpenFOAM cell
even though direct tetrahedron volume was nonzero.  Cell 311 has vertices
`[148, 149, 412, 413]`, direct absolute volume
`3.621556297342733e-05`, normalized volume
`6.96968834385404e-06`, and no source-owned vertex or boundary face.  Its four
signed face-pyramid contributions cancel because every adjacent tetrahedron
places its opposite apex on the same side of the shared triangular face.  This
is a real overlapping-volume topology defect, not roundoff or an evaluator
threshold problem.

The strict boundary audit previously checked incidence, duplicates, volume,
and boundary manifoldness but not this embedding invariant.  The hypothesis is
that every exactly-two-owner triangular face must have robust `orient3d` signs
of opposite polarity.  Equal signs are overlap; zero or scale-uncertain signs
are ambiguous.  Both must fail closed before `polyMesh` publication.

## Predeclared acceptance

- A valid two-tet opposite-apex fixture passes with false-positive count zero.
- A same-side two-tet fixture reports one overlap and fails strict topology.
- A near-coplanar fixture reports one ambiguous internal face and fails closed.
- Final native-Tet output with either count nonzero returns failure and leaves
  no newly published `constant/polyMesh` artifact.
- Klingner candidates may not increase non-manifold, same-side, or ambiguous
  internal-face counts.  This is candidate rejection only; no repair or tet
  deletion is part of this card.
- Existing source-boundary, component, provenance, inversion, and quality
  thresholds remain unchanged.

## Research basis and provenance

- Shewchuk, *Adaptive Precision Floating-Point Arithmetic and Fast Robust
  Geometric Predicates*, Discrete & Computational Geometry 1997, DOI
  `10.1007/PL00009321`; conference version DOI `10.1145/237218.237337`.
  Robust orientation signs motivate exact side classification.
- Si, *TetGen, a Delaunay-Based Quality Tetrahedral Mesh Generator*, ACM TOMS
  2015, DOI `10.1145/2629697`.  Used as tetrahedral-complex validity context.
- WildMeshing Toolkit, MIT-licensed reference implementation and documentation:
  <https://github.com/wildmeshing/wildmeshing-toolkit>.  Its invariant and
  rollback model informed the transaction boundary.

No external code was copied.  The implementation uses the existing
first-party `orientation_signs` robust-predicate wrapper.  `vendor/dependencies/` is
unchanged.  No DOI needed for this card was inaccessible.

## Baseline diagnosis

Pipeline and self-only routes are distinct stages and must not share counts:

- Pipeline cylinder final mesh: 1,987 tets, 112 same-side internal faces, 138
  affected cells.  Cell 311 evaluator oriented volume is
  `-5.759824041329242e-20`, while its absolute pyramid sum equals the direct
  volume.  The evaluator floor is `3.6215562973427363e-17`.
- Pipeline quality's actual hard failure is maximum skewness
  `8.750607596932202 > 8.0`; `oriented_degenerate_cells=1` was report-only.
  This card does not change evaluator skewness thresholds.
- Self-only final cylinder: 353 points, 1,493 tets, 2,870 internal faces,
  72 same-side, zero ambiguous, two duplicate tets, four non-manifold faces.
- Self-only final cube: 300 points, 1,301 tets, 142 same-side, zero ambiguous,
  one duplicate tet, two non-manifold faces.
- Self-only final sphere: 735 points, 2,164 tets, 108 same-side, zero ambiguous,
  zero duplicate tets, zero non-manifold faces.

P4C was not active in the failing Pipeline route.  Runtime tracing observed 82
same-side faces before the first Klingner sweep and 112 at Pipeline final.  The
pre-existing strict-audit blind spot is therefore established; this card does
not claim to identify or repair the first overlap-producing operation.

## Implementation and behavior

- `audit_internal_face_sidedness` groups canonical triangular faces, selects
  exactly-two-owner faces, and classifies their two opposite apexes with the
  existing robust orientation predicate.
- `TetBoundaryAudit.valid`, `has_strict_writer_topology`, duplicate-group
  transaction acceptance, and final source-aware topology all require zero
  same-side and zero ambiguous internal faces.
- Klingner candidate acceptance prevents increases in all three strict
  internal topology defect counts.  It does not delete or repair cells.
- A rejected final mesh returns its in-memory arrays for diagnosis but does not
  publish an invalid `polyMesh` result.

## Validation evidence

- Crafted opposite-side, same-side, and near-coplanar tests pass.  The valid
  opposite-side case reports one valid internal face and zero false positives.
- Cylinder three-run refusal is deterministic:
  point SHA-256
  `85ad5dd102c51a66b668f4b6251e934665ec5b9fcb54fdec570b2309f83f7824`;
  tet SHA-256
  `77ffb3be34f1a66191a1a0fd197898521bf41931e06bb43cce208e8eeb18f894`.
- Cylinder, cube, and sphere preserve the exact source boundary/provenance
  certificate and have zero inverted or degenerate tets, but are refused due
  to the independent strict topology defects listed above.
- The sidedness audit median is 1.737 ms and p95 is 1.784 ms over 30 cylinder
  runs.  Relative to the 9.790 s generation wall time, median observed overhead
  is 0.018%, below the predeclared 10% ceiling.
- Whole-generation instrumentation observed six sidedness calls totaling
  11.816 ms in a 9.654 s cylinder run, or 0.122% aggregate wall time.

This detection-only card does not pass Tet functionality or Mesh Validity Gate
5.  A separate cavity-safe overlap repair card is required before these
fixtures can be published successfully.
