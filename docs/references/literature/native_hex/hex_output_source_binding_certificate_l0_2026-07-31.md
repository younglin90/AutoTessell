# Native Hex output source-binding certificate L0 — 2026-07-31

## Gap

Current STEP/CAD ingestion can preserve input B-Rep ordinals, orientations,
seams, and sometimes declared physical groups.  Native Hex output does not
emit a boundary-face to source-B-Rep binding.  Input hashes alone therefore do
not prove generated boundary shape, feature, topology, provenance, or physical
group preservation.

## L0 contract

The new disconnected diagnostic requires, for every generated boundary face:

1. one unique, sorted output boundary-face ID;
2. one in-range authoritative source B-Rep face ordinal; and
3. one exact physical-group name equal to that source face's declared group.

It records deterministic hashes of output face IDs, output-to-source ordinals,
and output physical groups.  Missing, malformed, duplicate, out-of-range, or
mismatched bindings reject explicitly.

Even a complete fixture binding returns:

- `accepted=false`;
- `mesher_success_allowed=false`; and
- `product_claimed=false`.

This prevents the certificate from forging current native-Hex success.  A
future producer must bind the payload to actual written boundary faces and
combine it with output shape, feature, topology, and provenance validation.

## Scope

No mesher, writer, routing, UI, shared evaluator, source B-Rep reader,
quality threshold, target-cell, boundary-layer, or `vendor/dependencies/` behavior is
changed.  The source B-Rep and physical-group authority are hard prerequisites,
not inferred metadata.
