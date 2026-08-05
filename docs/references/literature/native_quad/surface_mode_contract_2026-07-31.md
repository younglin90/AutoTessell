# SURFACE-MODE-CONTRACT-1 evidence

Date: 2026-07-31

Promotion state: `L1_PASS / CORRECTNESS_KEEP`.

## Scope

This card introduces a read-only Python orchestration certificate for three
canonical surface product names:

- `tri`: only triangle elements;
- `quad`: strict quad-only, with zero triangle elements and no triangular
  handoff; and
- `tri_quad`: separately represented triangle and quad arrays, retained as a
  mixed candidate rather than a pure-quad claim.

The certificate does not select a route, modify a mesh, triangulate faces,
change a default, alter a threshold, or expose a CLI/UI/API selector.  It is
therefore `CORRECTNESS_KEEP`; a later integration card must establish each
product's shape, feature, topology, provenance, target, boundary-layer, and
writer contracts before connecting it to output.

`native_quad_dominant` is forcibly classified as `candidate_mixed` for every
result, including fixtures with zero triangle remainder.  Its pair-merger
algorithm lacks a global strict quad-only certificate.  A request for `quad`
therefore fails closed; only an explicit `tri_quad` certificate with retained
separate arrays can be accepted.  A triangular handoff always fails strict
quad and mixed-representation certification.

The canonical public semantic spellings are `tri`, `quad`, and `tri_quad`.
The internal-only aliases `native_tri_only`, `native_quad_strict`, and
`native_tri_quad_mixed` map explicitly to those values and are recorded in the
same certificate.

## Research and provenance

Read local evidence before implementation:

- `docs/references/literature/native_tri/tri_source_certificate_preflight_2026-07-31.md`:
  runtime-disconnected certificates must fail closed and cannot upgrade a
  topology-changing path without source-envelope and provenance proof.
- `docs/references/literature/native_quad/evidence_matrix.md`:
  the existing pair merger is a conservative fallback, not a quad meshing
  engine; global field, singularity, extraction, and fidelity work remain.
- `docs/references/literature/native_quad/quad_preflight_prep_cpp23_2026-07-31.md`:
  its C++23 transaction preserves the existing mixed result semantics and
  does not supply a strict-quad product proof.

No external code, dependency, generated output, or threshold was used.  This
is an independent representation contract; future performance-sensitive
classification can move to a C++23 kernel only after parity tests.  No paper
was required by this narrowly scoped contract card, and `vendor/dependencies/` is
unchanged.

The strict-topology target for later surface products is component count,
boundary-loop structure, genus, feature graph, patch and physical-group
meaning, and coordinate/face/patch provenance preservation—not frozen triangle
IDs.  The independent native-tri candidate remains an immutable source BVH,
filtered-predicate, transactional C++23 design; this Python certificate does
not replace it.  A future strict quad route must emit degree-4 faces only and
explicitly reject rather than fall back to triangles.

Local literature records support that separation: Alliez et al. 2003, DOI
`10.1145/882262.882296`; Alliez et al. 2005, DOI
`10.1016/j.gmod.2004.06.007`; Jakob et al. 2015, DOI
`10.1145/2816795.2818078`; and Huang et al. 2018, DOI
`10.1111/cgf.13498`.  CGAL, WildMeshing, Instant Meshes, and QuadriFlow remain
reference-only/no-copy sources.  No newly inaccessible DOI arose; the existing
ledger entries `10.1002/nme.7644`, `10.1137/1.9781611978575.6`, and
`10.1137/1.9781611979138.18` remain unchanged.

## Acceptance

L0 exercises every product's accept/reject edge: triangle-only rejects a quad,
strict quad rejects both a triangle remainder and a triangular handoff, and
`native_quad_dominant` cannot be labelled strict quad even if supplied zero
triangles.  Invalid counts and unknown product spellings fail closed.

L1 runs the current public `native_quad_dominant_remesh` result three times on
a planar two-triangle quad pair.  Each read-only certificate is byte-equivalent as a frozen
dataclass and classifies the result `candidate_mixed`; it neither mutates the
result nor changes the existing route.
