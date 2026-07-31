# Qt native surface-product route selector L0 — 2026-07-31

## Exposed values

The desktop preprocessing L2 selector now exposes distinct request values:

- `native_tri` — source contract fail-closed;
- `native_strict_quad` — certificate required, deferred;
- `native_tri_quad` — certificate required, deferred.

Display labels carry the deferred condition, while QComboBox user data carries
the exact route value.  The worker therefore receives the route identity, not
a human display label.

## Safety

`native_isotropic` remains the default.  Existing text-only legacy selections
still use the previous `currentText().lower()` fallback.  The selector does
not expose or map any strict/mixed request to `native_quad_dominant`; it makes
no output, quality, geometry, topology, or acceptance claim.

## Deferred work

The browser UI remains outside this scoped Qt card.  A browser card must add
the same exact values and deferred labels; it must not create a quad-dominant
alias.
