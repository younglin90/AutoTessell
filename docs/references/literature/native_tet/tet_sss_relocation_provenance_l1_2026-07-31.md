# Native Tet SSS Relocation Provenance L1 — 2026-07-31

Three deterministic sphere runs pass source provenance immediately before SSS
pass-0 `_envelope_bounded_relocate`.  They fail immediately after relocation
and before acceptance assignment: missing source vertices `636`, faces `1280`.

Thus relocation output, not `final_pts = new_pts`, is first observed failure.
Report-only checkpoints only; no repair or policy change.
