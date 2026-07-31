# Tri / strict-quad source-certificate bridge — Cycle 58

State: `DEFER / CORRECTNESS_KEEP`; report-only and disconnected.

## Research question

Can existing native-tri and fixed-pair strict-quad diagnostics provide the
five authoritative source-certificate IDs required by the common surface
schema: source shape, feature, patch, physical group, and provenance?

## Evidence inventory

| Existing object | Direct authoritative digest | Not safe to relabel |
|---|---|---|
| `NativeTriSourceCertificateDiagnostic` | `declared_feature_edges_sha256` only when `feature_ownership_explicit=true` | separate vertex/face hashes are not a declared one-field shape certificate; `source_payload_hash` mixes faces, patches, and features; no physical-group or candidate-face-provenance digest |
| `StrictQuadPairPreflight` | none of the five | vertex/triangle/quad hashes and structural booleans are fixed-pair topology evidence, not dedicated shape/feature/patch/physical/provenance certificate IDs |

The smallest safe relation is therefore partial: the tri bridge carries only
its explicit feature declaration hash.  It reports source shape, patch,
physical group, and provenance as deferred.  Strict-quad carries none.  Both
bridges retain `product_accepted=false`; they never construct a candidate or
enter routing/output.

## Why this is deferred

The source schema needs one independently named, canonical digest for each
claim.  Combining unrelated diagnostics into new hashes would manufacture an
authority relation the source objects did not declare.  In particular,
physical-group evidence is absent from both objects.  No full product bridge
is implementable until source objects expose dedicated authoritative hashes
and their geometry/semantic verification contracts.

## L0 evidence

The tri closed-cube clone has an explicit feature declaration hash; three
bridge reports deterministically bind only that field and defer the other
four.  The accepted strict-quad square still defers all five.  Invalid objects
fail closed.  No source arrays mutate and no native C++ evaluator is loaded.

Rollback if a bridge synthesizes a hash, marks any deferred evidence present,
grants acceptance, constructs a candidate, changes production state, or adds
routing/default/output behavior.  `third_party/` remains unchanged.
