# HEX-LOCAL-FRONT-ADMISSION-PROVENANCE-CPP23-1

State: `EXPERIMENTAL_KEEP`, default OFF and report/candidate-only.

## Hypothesis

The local-front backtracking kernel may be evaluated only after Python has
proved immutable source-file/ordered-face identity, supplied feature/patch
entities, and exact triangle-to-three-quad provenance.  C++23 checks only the
numeric facts: exactly three rows per source face and requested step not above
the supplied inward-clearance bound.  It cannot infer CAD meaning, move source
geometry, construct a shell, select a route, or write output.

## Fixed acceptance

- source quad rows: exactly three per source face; duplicate, missing, and
  out-of-range rows zero;
- authoritative sidecar and exact entity-boundary audit pass;
- requested step finite positive; a manifest-gated sampled inward-clearance
  audit independently measures every source-face ray and requires minimum
  clearance >= step;
- Python and opt-in C++ numeric verdicts/counters equal;
- source coordinate and face bytes unchanged; three runs deterministic.

Any missing authority, numeric invalidity, native-result malformed/divergent
payload, source mutation, or production connection rejects/rolls back before
candidate construction.  Native absence uses the independent Python oracle.

## Scope

Only `native_hex_quality_local_front.hpp`, its pybind binding, this disconnected
Python authority, and L0/L1 tests change.  No mesher, routing, layer engine,
writer, default, CMake, target-cell policy, or `vendor/dependencies/` changes.

## Local evidence

`hex_local_front_cpp23_2026-07-31.md` proves local-step parity but records
missing source quadization/provenance/clearance/contact contracts.
`hex_cad_front_contract_2026-07-31.md` proves exact B-Rep entity ingress but
leaves physical groups and core fill unverified.  `hex_bl_source_surface_guard_2026-07-31.md`
proves outward extrusion cannot satisfy source-shape preservation.  This card
therefore admits no production boundary layer and makes no Gate 7 claim.

## Result

The labelled cube passes with 12 source triangles and 36 exact quad rows; its
sampled minimum inward clearance is 1.0 for requested step 0.1.  The native
numeric predicate and Python oracle agree over three opt-in calls.  Duplicate
source rows, wrong dtype/stride, manifest mismatch, insufficient clearance,
and non-finite/non-positive requested steps reject without a shell or case
artifact.  Source point and triangle byte hashes remain unchanged.

Verification used a fresh GCC 13.3 Release C++23 `native_hex_quality` build
and exercised native ABI plus Python fallback: `17 passed` in 28.15 seconds
for admission, local-front, exact-quad provenance, and sampled-clearance test
groups.  Ruff and `git diff --check` pass.  No performance claim is made: this
card is an admission gate, not a local-front optimization.
