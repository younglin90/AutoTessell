---
description: Permanent staged verification policy for all AutoTessell native-engine cards
paths: ["core/**", "tests/**", "scripts/**", "docs/references/literature/**", "ROADMAP.md", "CHANGELOG.md"]
---

# Native-engine verification ladder

Every native_tet, native_hex, native_poly, and native_tri mechanism must be
verified in this order. A later level must never be used as the first
acceptance test for a new mechanism.

The verification level and the product-promotion state are deliberately
separate. Finishing a useful correctness primitive must not require production
runtime, target-hard coverage, and the full campaign in the same card. Moving
a mechanism into the default engine path still requires every later gate.

Older engine plans often say that "every card" must pass the full permanent
suite or a hard wall-clock target. Under this policy those clauses are
**promotion requirements** for `RUNTIME_READY`/`PERMANENT`, not prerequisites
for retaining runtime-disconnected `CORRECTNESS_KEEP` infrastructure. They
remain fully binding whenever the card changes mesh output or seeks promotion.

## Promotion states

Use exactly one of these states for a retained mechanism:

### `CORRECTNESS_KEEP`

- Intended for test-only, report-only, oracle, predicate, schema, or other
  runtime-disconnected infrastructure.
- Requires L0 and the relevant L1 canonical fixture, deterministic repetition,
  and zero false certification or permanent-invariant violation.
- May be committed without L2/L3. It must not affect routing, acceptance,
  rollback, defaults, or mesh output.
- If a supposedly disconnected card changes any existing permanent-test output,
  it is not disconnected and cannot use this state to bypass that regression.

### `EXPERIMENTAL_KEEP`

- Intended for a useful mechanism behind an explicit default-OFF flag or an
  offline/fine-tier diagnostic lane.
- Requires `CORRECTNESS_KEEP`, byte-identical OFF behavior, and no regression
  of any permanent gate in every exercised L0/L1 fixture.
- L2 must be measured, but a truthful timeout, conservative refusal, or known
  target limitation does not erase the safe implementation. Record the exact
  limitation and keep the feature OFF.

### `RUNTIME_READY`

- Requires the card's targeted L2 failure mode to pass, all relevant permanent
  gates to remain green, and the declared absolute end-to-end runtime/memory
  budget to pass on the canonical environment.
- A relative speedup alone is insufficient. This state authorizes integration
  testing in the normal route, not yet a new permanent/default contract.

### `PERMANENT`

- Requires `RUNTIME_READY` plus L3 full regression, byte-identical repeats,
  truthful hard-corpus classification, and documentation of the new default or
  permanent gate.
- Only this state may make a mechanism default ON or replace an existing
  permanent acceptance rule.

### `KILL` and `DEFER`

- `KILL`: false certification; surface/topology/orientation/provenance or other
  permanent-invariant regression; no measurable leverage; or maintenance cost
  clearly larger than measured benefit. Remove ineffective mechanism code and
  retain the negative evidence.
- `DEFER`: a named prerequisite, fixture, representation, exact predicate, or
  legal dependency is missing. Record the unblock condition; do not implement
  a substitute mechanism by guesswork.
- Missing a production-performance target does **not** by itself imply `KILL`
  when correctness is established and the mechanism has material leverage. It
  remains `EXPERIMENTAL_KEEP` or an offline oracle unless its maintenance cost
  is unjustified.

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

## Gate calibration by claim

- Correctness and promotion are evaluated separately. A card may establish a
  correct primitive without claiming that it solves its target hard geometry.
- One-sided certificates fail only on a false positive (`IN`/PASS issued for
  an invalid result). A conservative `UNCERTAIN`, explicit refusal, or false
  negative is coverage evidence, not a correctness failure, unless improving
  coverage is the card's declared mechanism.
- A target-hard timeout is a performance result until the mechanism seeks
  `RUNTIME_READY`; it is not automatically a correctness regression.
- Performance cards declare both a leverage threshold and an absolute product
  budget before measurement. As a default calibration, a reproducible >=3x
  end-to-end improvement is material evidence for `EXPERIMENTAL_KEEP`; only
  the absolute budget can grant `RUNTIME_READY`. A different multiplier must
  be justified by literature, a product SLO, or a frozen baseline—not chosen
  merely to force acceptance or rejection.
- Quality-improvement cards distinguish non-regression from the final target:
  L0/L1 must not worsen owned permanent metrics; L2 target closure is required
  only for `RUNTIME_READY`.
- Benchmark timing uses the same interpreter, environment flags, route, input,
  warmup policy, and a robust statistic (normally alternating-order median).
  Hardware/load outliers are remeasured rather than promoted or killed.

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

Record both the highest completed verification level and promotion state:

`MEASURED -> L0_PASS -> L1_PASS -> L2_TARGET_PASS -> L3_REGRESSION_PASS`

`CORRECTNESS_KEEP -> EXPERIMENTAL_KEEP -> RUNTIME_READY -> PERMANENT`

These are not aliases: for example, a runtime-disconnected oracle can be
`L1_PASS / CORRECTNESS_KEEP`, while a default-OFF mechanism can be
`L2 measured / EXPERIMENTAL_KEEP` even when the target remains unsolved.

Every report must state fixture level, promotion state, before/after values,
hard-gate result, default/OFF behavior, and whether each failure is a new
regression, conservative refusal, known limitation, timeout, or missing
prerequisite. Prior evidence is never deleted when a state changes.
