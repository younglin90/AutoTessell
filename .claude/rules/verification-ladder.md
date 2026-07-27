---
description: Permanent staged verification policy for all AutoTessell native-engine cards
paths: ["core/**", "tests/**", "scripts/**", "docs/references/literature/**", "ROADMAP.md", "CHANGELOG.md"]
---

# Native-engine verification ladder

Every native_tet, native_hex, native_poly, and native_tri mechanism must be
verified in this order. A later level must never be used as the first
acceptance test for a new mechanism.

## L0 — minimal mechanism fixture

- Use a hand-checkable synthetic fixture that isolates one mechanism and one
  expected topology change.
- Include at least one expected-accept and one expected-reject case.
- Verify exact local invariants: connectivity, orientation/positive measure,
  ownership/provenance, conservation, rollback, and deterministic repetition.
- A mechanism that cannot pass L0 is fixed, deferred, or killed before it is
  run on a full engine fixture.

## L1 — canonical geometry

- Use ordinary canonical fixtures such as cube, cylinder, and sphere, choosing
  only those relevant to the mechanism.
- Existing permanent gates remain binding and may not be relaxed.
- Compare a fresh before/after baseline under identical route, quality,
  environment flags, and interpreter.
- A report-only diagnostic failure is evidence, not a production regression,
  unless the diagnostic is already a declared permanent gate.

## L2 — targeted hard geometry

- Use only hard fixtures named by the card, such as naca, thin disk, needle,
  gear, bracket, or dual torus.
- The card acceptance criterion is scoped to the target failure mode. Unrelated
  known limitations are recorded but do not veto the card unless they regress
  relative to the same baseline.
- A deterministic, explicit, non-mutating refusal is a valid result when the
  product does not yet claim support; silent approximation or false PASS is not.
- Hard-fixture measurements may falsify or defer a mechanism, but do not erase
  an L0/L1-safe implementation unless a permanent invariant regresses.

## L3 — full regression and campaign corpus

- Run the engine-wide permanent tests and the declared hard corpus only after
  L0, L1, and the card's L2 target have been evaluated.
- Preserve all permanent surface, topology, positive-volume/Jacobian, quality,
  provenance, and byte-determinism gates.
- Classify each corpus row as PASS, expected truthful rejection, known
  pre-existing limitation, timeout/performance issue, or new regression.
- Only a new regression blocks an otherwise accepted card. Known limitations
  remain open cards and must not be relabeled as regressions.

## Contract calibration

- Volume engines preserve the pre-meshing boundary exactly unless a plan's
  invariant table explicitly authorizes bounded movement under a hard gate.
- native_tri uses its declared geometric error envelope. Exact membership in a
  single source triangle is a conservative diagnostic, not the general
  acceptance contract; source-patch union or an explicit epsilon-envelope may
  be the correct gate.
- Topology/link/orientation checks do not imply geometric containment.
- Sampled proximity does not imply exact containment. Report the distinction.
- Report-only metrics never change routing, acceptance, rollback, or defaults.

## Card status and reporting

Record the highest completed level explicitly:

`MEASURED -> L0_PASS -> L1_PASS -> L2_TARGET_PASS -> L3_REGRESSION_PASS`

Use `DEFER` when prerequisites are missing and `KILL` when the measured
mechanism lacks leverage or violates a permanent invariant. Every report must
state fixture level, before/after values, gate result, and whether failure is a
new regression or a known/expected outcome.
