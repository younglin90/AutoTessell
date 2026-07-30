# POLY-PRIMAL-ORPHAN-VERTEX-1 evidence

## Claim and baseline

The tetrahedral-primal preflight accepted finite points that had zero
tetrahedron incidence.  A valid two-tetrahedron classified bipyramid with one
extra point therefore returned `success=True`, reported five dual cells for six
input points, reported zero invalid star cells/subtets, and wrote all eight case
files.  The unused input point and its provenance disappeared silently.

This is a false-success defect, not a target-cell-count defect.  The primary
metric is false successes (`1 -> 0`); the artifact metric is written files
(`8 -> 0`).  No target, orientation, quality, writer, or routing threshold is
changed.

## Independent mechanism

The existing first-party C++23 primal-conformity audit now marks vertex
incidence while it scans the contiguous tetrahedron array.  A final ascending
scan emits exact orphan vertex ids.  The algorithm is `O(V + T)` time and
`O(V)` bytes in addition to the pre-existing canonical tet/face records.  It
does not move, delete, or repair a point.  Preflight rejects any orphan before
dual construction and before creating an output directory.

The Python implementation remains an independent NumPy oracle.  Native results
are accepted only as a four-field exact contract: orphan ids must be
non-boolean integers, unique, sorted, and within `[0, point_count)`.  A present
but malformed native result fails closed; it never falls back after claiming
the native symbol.

## Verification

- L0 reject: the orphan bipyramid rejects identically in three runs, writes no
  artifact, and leaves the point/connectivity inputs exact.
- L1 accept: the ordinary classified bipyramid retains the five frozen
  `polyMesh` hashes for three runs and preserves `source_high:wall` and
  `source_low:patch` provenance through the existing boundary contract.
- Native/Python parity: exact orphan ids `(5, 6)` and the full conformity audit
  agree.
- Malformed native results: unsorted, duplicate, negative, out-of-range,
  boolean, and floating orphan ids reject; production invocation writes zero
  artifacts.
- Orientation remains diagnostic: the negative-orientation fixture still
  succeeds under the existing contract.
- 50,000-tet alternating-order benchmark: Python median `0.452012 s`, native
  median `0.012353 s`, `36.59x` speedup.  The previous native baseline was
  `0.011680 s`; the observed `+5.77%` is within the declared `+10%` budget.
- The focused strict-C++23 build and contract set passes `31`.  The bounded
  related Poly regression passes `94`; four sphere tests fail in upstream
  native-tet source-topology generation before entering this dual preflight.
  These are the already-recorded Cycle-33 real-sphere limitation, not a new
  orphan-audit regression.

Promotion state: `L3_REGRESSION_PASS / PERMANENT`, with the four declared
pre-existing upstream failures retained as known limitations.  This strengthens
a pre-existing fail-closed input contract and does not alter valid mesh output.

## Literature and code review

- CGAL's official `Mesh_complex_3_in_triangulation_3` documentation explicitly
  distinguishes vertices in the triangulation that are not incident to any
  simplex in the mesh complex and exposes `remove_isolated_vertices()`.  That
  validates the census category; AutoTessell rejects instead of repairing so
  input provenance cannot be silently changed:
  <https://doc.cgal.org/latest/SMDS_3/classCGAL_1_1Mesh__complex__3__in__triangulation__3.html>
- Bloch et al., *Linear simple-cell complexes: The structure and properties of
  a generalization of 2D and 3D digital complexes*, Graphical Models 67 (2005),
  DOI `10.1016/j.gmod.2004.12.001`, defines a tetrahedral mesh through its
  tetrahedra and their simplicial-complex intersections.  An unrelated point in
  the point array is not part of that tetrahedral complex.
- Garimella, *Mesh Generation for the Numerical Solution of Partial
  Differential Equations*, DOI `10.4208/cicp.030612.010313a`, remains the local
  dual-mesh design reference.
- The public CGAL repository was reviewed only as a behavioral reference:
  <https://github.com/CGAL/cgal>.  Its package-dependent GPL/LGPL licensing is
  not compatible with treating code as MIT-core provenance.  No CGAL source,
  dependency, generated artifact, or implementation-derived code was copied.

The implementation is an independent contiguous-array scan under the current
AutoTessell GPL project license and preserves the future native-core boundary.
