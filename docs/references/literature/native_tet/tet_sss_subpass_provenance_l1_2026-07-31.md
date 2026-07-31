# Native Tet SSS Subpass Provenance L1 — 2026-07-31

Three deterministic sphere runs preserve source provenance before P3 SSS
revival.  First observed failure is immediately after accepted SSS pass `0`:
missing source vertices `636`, source faces `1280`.  Later passes remain failed.

Conclusion: first failure interval is pass-0 candidate acceptance in P3 SSS
revival.  This card adds immutable report-only checkpoints only; no repair,
threshold, algorithm, writer, routing, fallback, or third-party behavior changes.

Status: `L1_PASS / CORRECTNESS_KEEP`.  Causality inside pass-0 requires a later
candidate-before/after card; this card makes no repair claim.
