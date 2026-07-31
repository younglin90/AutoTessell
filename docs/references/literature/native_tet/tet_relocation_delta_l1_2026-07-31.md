# Tet SSS Relocation Delta L1 — 2026-07-31

Cycle70 isolates first failure to pass-0 `_envelope_bounded_relocate` output.
The immutable source audit changes from valid to: missing source vertices `636`,
missing source faces `1280`, unowned candidate faces `1280`.  Connectivity is
unchanged across this relocation; only point coordinates are replaced.

Minimal deterministic reject predicate for a future transaction is therefore
the existing immutable-source conjunction evaluated on `(new_pts, final_tets)`:
`component_bijective && source_faces_preserved && n_unowned_candidate_faces == 0`.
Any false value must retain exact pre-relocation points.  This card changes no
runtime policy; predicate is evidence only.
