# POLY-VORONOI-VALIDITY-PREWRITE-1 Evidence

Date: 2026-07-31

Status: `DEFER / prerequisite`; mandatory fail-closed admission works, but
native Voronoi face orientation still produces invalid cells. Master
integration is prohibited until the orientation defect is repaired and the
legacy success regressions pass unchanged.

## Failure isolation

The direct Voronoi path called `validate_poly_cell_volumes`, logged its result,
then wrote and returned `success=True` regardless of thousands of
negative-volume cells. The dense cylinder wrote five canonical polyMesh files
with 4497 negative-volume cells. Automatic best-of-N then evaluated more
candidates until the 180-second module timeout.

The validator's environment disable switch also allowed validity admission to
be bypassed. Existing sphere success tests consequently accepted outputs with
one to 55 negative-volume cells.

## Mechanism

Signed-volume and degenerate-cell counts are now mandatory immediately before
the writer. `AUTO_TESSELL_VAL2_OFF` remains a diagnostic switch but cannot
disable admission. Any nonzero count or validation exception returns a typed
`failure_kind="validity_refused"` result. The writer is not called.

The public generator treats the first direct-candidate validity refusal as
terminal. It does not start further escalation, p=4, clipped, repair, or hex
fallback candidates. General non-validity failures retain their existing
semantics.

Primary metric: invalid canonical polyMesh files `5 -> 0`.

## Verification

- Focused pre-write tests: `4 passed in 1.96s`.
- Invalid writer calls: zero.
- Existing five polyMesh files and an unrelated sentinel remained byte-exact.
- Empty-case refusal created zero files.
- Valid synthetic tetra output matched the existing writer byte-for-byte,
  including all five polyMesh files.
- Terminal automatic escalation called the inner generator once and hex zero
  times.
- Dense direct cylinder (`target_edge_length=0.02`): explicit refusal in
  55.312 seconds, negative=4497, degenerate=0, output files=0.
- Dense cylinder mask mismatch, BL prism path, reconstructed surface, and child
  process leak: zero.
- Production and test modules: `py_compile` passed.
- `git diff --check`: passed.

Related regression sweep: 27 passed, five failed. The failures are unchanged
legacy sphere assertions that require invalid Voronoi output to succeed. Their
observed negative-volume counts were 1, 2, 7, and 55 depending on seed density
and Lloyd count. Those tests were not deleted, skipped, weakened, or edited.
They define the next repair's acceptance boundary.

Full PipelineOrchestrator reconstruction suppression is outside this Poly-only
card. `COMMON-TERMINAL-REFUSAL-RECONSTRUCTION-1` must propagate typed terminal
refusal through shared tier metadata before the full pipeline can guarantee no
last-resort reconstructed surface.

## Next prerequisite

`POLY-VORONOI-ORIENTATION-VALIDITY-REPAIR-1` must isolate one face-orientation
cause and correct only cell-local face loops while preserving coordinates,
topology, boundary identity, and provenance. All five legacy failures must
return to PASS without changing their assertions.

Rollback conditions: writer invocation for an invalid candidate, artifact or
existing-case drift, validity bypass, nonterminal invalid escalation, valid
writer-byte drift, shape/topology/provenance change, timeout, nondeterminism,
or any `vendor/dependencies/` change.
