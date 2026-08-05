# TRI-SOURCE-TOPOLOGY-AUDIT-CPP23-1 evidence

Date: 2026-07-31

Promotion state: `L1_PASS / CORRECTNESS_KEEP`.

## Scope

`native_metrics.triangle_surface_topology_audit()` is a read-only C++23
preflight for the native-tri source-certificate diagnostic.  It reports only
`valid`, `closed_oriented_manifold`, undirected edge count, face-component
count, and Euler characteristic.  It neither changes vertices, faces,
feature edges, patch/physical-group payloads, provenance, routing, defaults,
target-face behavior, boundary layers, nor mesh output.

The Python audit remains the independent oracle and normal default path.
The extension is selected only by
`AUTO_TESSELL_TRI_TOPOLOGY_AUDIT_CPP23=1`; absent extension/symbol falls back
to Python.  The source certificate remains fail closed and is not an edit or
an acceptance authorization.  This is therefore `CORRECTNESS_KEEP`, not an
experimental runtime feature or a promotion claim.

## Mechanism

The strict C++ ABI accepts only C-contiguous `float64 (V,3)` and `int64 (F,3)`
arrays.  It rejects non-finite coordinates, zero-area triangles, and invalid
indices with the same invalid audit tuple used by the Python oracle.  For a
valid input it stores three fixed records per triangle
`(min_vertex, max_vertex, face, direction)`, reserves once, sorts
lexicographically, reduces equal-edge runs, and joins exactly two-owner runs
with deterministic disjoint sets.  Edge direction detects orientation;
one-owner and more-than-two-owner edges are not closed-oriented; components
match the Python face-adjacency rule; `V-E+F` gives Euler characteristic.

Time is `O(F log F)` because of deterministic sort and space is `O(F)`.
The kernel never returns an edge-to-face map or changes any source array, so
it cannot substitute triangle IDs for the project’s actual strict topology
contract: components, boundary loops, genus, feature graph, patch/physical
groups, and coordinate/face/patch provenance remain later certificate gates.

## Research and provenance

Local sources read before implementation:

- `native_tri/evidence_matrix.md`: topology, feature, and envelope feasibility
  must precede quality and target optimization; the transaction stays Python
  orchestration around bounded native kernels.
- `tri_source_certificate_preflight_2026-07-31.md`: diagnostics must never
  upgrade a topology-changing candidate without source-envelope and
  provenance proof.
- `tri_flip_filter_cpp23_2026-07-31.md`: frozen-state, serial C++ filters
  preserve Python transaction ownership and strict optional-ABI validation.

Official pybind11 NumPy documentation was consulted for strict typed
`py::array`/contiguity boundaries; C++ standard-library `std::vector::reserve`
and `std::sort` support one allocation plan and deterministic reduction.  The
algorithm is an independent first-party implementation.  CGAL, WildMeshing,
and MMG remain reference-only/no-copy.  No new DOI was required or became
inaccessible; `vendor/dependencies/` is unchanged.

## Acceptance and measured result

L0 requires Python/native tuple parity on closed, open, inconsistent, and
non-manifold triangle surfaces; non-finite, zero-area, and invalid-index
inputs return the invalid tuple; strict ABI rejects wrong dtype/stride; input
hashes are unchanged; malformed extension output fails closed; OFF and missing
symbol use the Python oracle.

L1 requires cube/cylinder/sphere source-certificate reasons and hashes to be
identical with OFF and with the opt-in native audit across three repeats.
The primary acceptance metric is zero tuple and report mismatch.  A separate
20,480-face icosphere median-time/allocation measurement is recorded for
observability only and is not a release or promotion gate.

On GCC 13.3 Release C++23, Python 3.12, one BLAS/OpenMP thread, seven repeats
after one warmup, the Python oracle median was `0.676991239 s` with Python
traced peak `20,421,712` bytes.  The direct native audit median was
`0.003275630 s` with traced peak `411` bytes: `206.67x` faster with the Python
edge-incidence allocation removed.  This is a diagnostic-kernel measurement,
not an authorization to change routing or certification policy.
