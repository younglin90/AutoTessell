# Surface source-certificate binding schema — Cycle 56

State: `L0_PASS / CORRECTNESS_KEEP`; report-only, default disconnected.

## Hypothesis

Tri, strict-quad, and tri-quad products need one deterministic vocabulary for
source-certificate evidence gaps before any evaluator or route can claim a
product result.  The schema reports these five independent evidence IDs:

1. `source_shape`
2. `feature`
3. `patch`
4. `physical_group`
5. `provenance`

Each supplied ID must be a canonical lowercase SHA-256 string.  `None` means
the evidence was not supplied and is listed in `missing_evidence`; an invalid
non-`None` value is listed in `malformed_evidence`, never silently coerced or
misreported as proof.

## Deliberate limit

This schema validates only the presence and syntax of opaque evidence IDs.  It
does not read source/candidate geometry, bind a digest to a mesh, verify shape
envelopes, feature paths, patch membership, physical groups, or face
provenance.  Therefore even all five syntactically valid IDs return
`product_accepted=false` and
`source_product_certificate_required`.

No source geometry can mutate because none enters this API.  No C++ evaluator,
candidate, routing, writer, artifact, default, target-cell, or boundary-layer
path is imported or called.

## L0 evidence

Each tri, strict-quad, and tri-quad class reports all five missing fields in a
fixed order.  Each individual omission is reported exactly.  Complete IDs are
deterministic across three calls but stay explicitly unverified.  Malformed
IDs and invalid product classes fail closed.

Rollback this card if it grants a product acceptance, infers any missing
evidence, changes a mesh, calls a native evaluator, or enters routing/default
behavior.  `third_party/` is unchanged.

## Provenance

This is a new first-party reporting schema.  It does not copy any external
implementation.  Existing tri exact-clone certificates and strict-quad
preflight remain separate authoritative contracts; this module only aligns
their future evidence-gap reporting vocabulary.
