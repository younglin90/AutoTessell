# Source-Component Face-Incidence Hash Census

Date: 2026-07-31

Card: `TET-SOURCE-COMPONENT-FACE-HASH-1`

## Hypothesis and fixed acceptance

The C++23 source-component certificate materialized all four faces per tet and
globally sorted that `4T` array before extracting the boundary.  Replacing only
that census with a reserved hash-incidence table changes expected complexity
from `O(T log T)` to `O(T)` while preserving the exact source-coordinate,
component, and malformed-input contracts.

Pre-edit frozen 32-copy sphere baseline:

- source vertices: 20,544
- candidate tets: 52,192
- source and candidate boundary components: 32
- median of nine audits: 0.681927 seconds

Primary acceptance is at least `5x` speedup and at most 0.08 seconds on the
same fixture.  One-copy performance may not regress by more than 10%.  Peak
process memory may not increase by more than 15%.  Reports must match the
Python oracle exactly for valid, lost, merged, split, unanchored, interiorized,
permuted, duplicate, degenerate, open, and non-manifold fixtures.  Inputs and
generated mesh bytes must remain unchanged.  Any verdict, count, topology,
provenance, threshold, or output change kills the card.

## Research and provenance

- Wang et al., *Multi-threaded parallel tetrahedral mesh improvement by
  combining atomic operation and graph coloring*, Advances in Engineering
  Software 198 (2024), DOI `10.1016/j.advengsoft.2024.103782`, emphasizes
  topology-correct atomic operations and memory organization.  The publisher
  abstract was accessible; the full text was not.
- WildMeshing Toolkit documents explicit invariants, rollback, and attribute
  protection for topology and geometry consistency.  Its repository is MIT:
  <https://github.com/wildmeshing/wildmeshing-toolkit>.
- CGAL's tetrahedral-remeshing documentation treats topology preservation as
  an invariant around local operations.  CGAL package licensing varies and is
  reference-only here: <https://doc.cgal.org/latest/Tetrahedral_remeshing/>.

No source, generated output, algorithm implementation, or dependency was
copied from these references.  The change is an independently authored
standard-library incidence census inside the existing first-party C++23
kernel.  `third_party/` remains unchanged.

## Observed result

- The fresh GCC 13.3 C++23 `-Werror` build passed without warnings.
- The 32-copy nine-audit median fell from 0.681927 seconds to 0.034191
  seconds: `19.95x`, below the fixed 0.08-second ceiling.
- The one-copy audit fell from 0.018660 seconds to 0.000852 seconds; it did
  not regress.
- Peak process RSS fell from 133,972 KiB to 113,808 KiB (`-15.05%`), below
  the fixed `+15%` cap.
- All 32 source components and all 32 candidate boundary components were
  reported bijectively, with all 20,544 source vertices on the candidate
  boundary.
- Component-contract, metric-transaction, and final strict-topology suites:
  37 passed.
- The generated sphere remained 669 points and 1,631 tets.  The accepted
  final path retained zero open edges, zero non-manifold edges, zero
  negative-volume tets, and zero zero-volume tets; the invalid metric
  candidate remained fail-closed.

The implementation changes only the exact face-incidence census data
structure.  No threshold, fallback, mesh mutation, topology result, report
field, Python routing contract, or target-cell behavior changed.
