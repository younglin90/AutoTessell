# Tri / strict-quad physical-group provenance — Cycle 60

State: `DEFER / CORRECTNESS_KEEP`; report-only.

## Research result

Existing native-tri accepts `source_patch_ids` and records a payload hash that
mixes source faces, patch IDs, and feature declarations.  It has no dedicated
physical-group mapping or authority flag.  Fixed-pair strict-quad compares
generic source/quad patch payloads and exposes only a preservation boolean;
it likewise has no group mapping or dedicated group digest.  Neither object
can safely bind the common schema's physical-group evidence.

The retained schema binds a digest only from a new explicit authoritative
`source_face_groups` mapping with exactly one nonempty declared group per
source face.  Missing, undeclared, patch-like, or malformed payloads DEFER or
reject rather than being coerced.  Even a complete mapping remains
`report_authoritative_physical_group_mapping_unverified` and product
acceptance stays false.

No geometry, C++, candidate, route, writer, output, default, target-cell, or
boundary-layer path participates.  A future tri/strict-quad bridge may bind
this field only when its source object exposes the exact mapping plus an
authority declaration.  `third_party/` unchanged.
