# Tet immutable input-source ledger (Cycle 40)

## Card

`TET-IMMUTABLE-INPUT-SOURCE-LEDGER-1`

This card changes only the source used by final native-tet shape, topology,
validity, and provenance certification.  Target-cell tuning remains deferred
behind strict source topology.  No geometry-repair threshold, routing policy,
or boundary-layer policy changes.

## Baseline defect

`generate_native_tet` converted the caller arrays and then allowed input repair
to replace `V` and `F`.  Every later source-prefix restore, source-topology
audit, shape measurement, and P4C acceptance used those repaired working
arrays.  The generator could therefore certify a convenient surrogate rather
than the caller input.

The adverse fixture is a tetrahedron with five source points, where point four
duplicates point zero and the source faces deliberately use both IDs.  Baseline
input repair deduplicated the source to four points, returned success, and
wrote all five `polyMesh` files.  Final evidence incorrectly described the
repaired tetrahedron as the source.

## Hypothesis and fixed acceptance

Hypothesis: one immutable, owning, C-contiguous snapshot of the caller source,
created immediately after dtype/shape coercion, makes every final certificate
refer to the same source while leaving mutable working arrays available to the
mesher.

Acceptance was frozen before implementation:

- duplicate-coordinate false success changes `1 -> 0`;
- written `polyMesh` artifacts change `5 -> 0` for that failure;
- failure identifies ambiguous source coordinates;
- valid tetrahedron output arrays and all five writer files remain byte exact;
- vertex and face reorder controls remain valid and bijective;
- caller point and face bytes remain unchanged on success and failure;
- representative cube, cylinder, and sphere results remain exact;
- focused topology, provenance, and shape suites pass;
- runtime and peak RSS regress by at most `5%`;
- no `third_party/` change and no target-cell policy change.

## Mechanism and complexity

The entry point now takes one owning `float64` vertex copy and one owning
`int64` face copy, then marks both read-only.  Input self-intersection checking
and optional repair continue on separate working arrays.  The explicit
fTetWild audit, final edge/face/plane/Hausdorff evidence, P4C acceptance,
metric-topology and metric-surface transactions, source-prefix restoration,
strict source-topology audit, and final shape evidence all consume the
immutable source ledger.

Construction costs `O(|V| + |F|)` time and space once per call.  It adds no
copy inside refinement or optimization loops.  Read-only NumPy ownership also
prevents an accidental later alias from silently changing the certificate
source.

## Literature and public implementations

- Hu et al., *Tetrahedral Meshing in the Wild*, ACM TOG 39(4), 2020, DOI
  `10.1145/3386569.3392385`.  Full local text read.  The input surface remains
  the geometric reference for envelope and topology decisions.
- Diazzi, Panozzo, Vaxman, and Attene, *Constrained Delaunay
  Tetrahedrization: A Robust and Practical Approach*, ACM TOG 42(6), 2023,
  DOI `10.1145/3618352`.  Full author/arXiv text read.  PLC constraints remain
  explicit throughout tetrahedralization.
- Osman, Vink, Jalba, and Chamberland, *Connectivity-Preserving Cortical
  Surface Tetrahedralization*, arXiv `2512.08450`, 2025.  Public preprint read;
  motivates explicit source-connectivity evidence.
- CGAL 6.2 constrained tetrahedral meshing/remeshing documentation.  Current
  official documentation reviewed.  GPL/commercial implementation was used as
  reference only.
- `wjakob/wildmeshing-toolkit` (WMTK), MIT.  Current public source reviewed for
  invariant, rollback, and protected-attribute design.  No code copied.
- `MarcoAttene/CDT`, GPL/LGPL options.  Reference only; no code copied.

Publisher DOI endpoints for the two ACM papers returned HTTP 403, but complete
local or author-copy texts were available.  Inaccessible DOI requiring user
material: none.

## Provenance

The implementation is first-party Python orchestration over the existing
first-party C++23 strict topology/provenance audit.  It is a direct correction
to source ownership and call-site arguments, not a port or derivative of an
external implementation.  No dependency, generated code, GPL/AGPL source, or
`third_party/` file was copied or modified.

## Results

- Duplicate-coordinate adverse input: success `true -> false`; written writer
  artifacts `5 -> 0`; caller input bytes unchanged.
- Diagnostic: `source_points contains ambiguous duplicate coordinates`.
- Valid tetrahedron: point/tet SHA-256 and five `polyMesh` file SHA-256 values
  unchanged; caller input bytes unchanged.
- Reordered source: strict topology valid, component bijection valid, source
  faces preserved, caller input bytes unchanged.
- New L0 suite: `4 passed`; the auto-fix/rebind metric-transaction
  instrumentation alone passes in `2.63s`.
- Both metric transaction call sites receive the same owning, C-contiguous,
  read-only source arrays.  They equal the pre-repair caller source and share
  memory with neither the writable non-contiguous caller views nor the arrays
  returned by auto-fix.
- Shape/topology/provenance focused suite: `60 passed in 16.50s`.
- Representative result consistency: `3 passed in 51.63s`; cube, cylinder,
  and sphere counts, hashes, and shape evidence unchanged.
- Isolated cylinder process: `40.23s`, peak RSS `333,972 KiB`.  Against frozen
  evidence `38.65s` and `336,448 KiB`, changes are `+4.09%` runtime and
  `-0.74%` RSS, inside the fixed `5%` budgets.

Target-cell count remains explicitly deferred.  This card strengthens the
higher-priority strict topology contract without claiming target conformance.
