# Improvement plan — native-all-production-gate-042

## Goal

042_production_Tet_receipt_wiring_and_three_repeat_non_cube_corpus

## Scope and invariants

- Wire the authoritative surface receipt into the actual Native Tet ingress/commit path; the current standalone receipt consumer is not sufficient.
- Preserve source exactness, semantic feature/boundary/component/physical-group rows, provenance digest, orientation, manifoldness, and positive Tet volume.
- BL=0 must work on a closed authoritative non-cube corpus. BL>=1 must either produce an actual wall/interface/core partition or refuse explicitly when the current input is an open surface or no volume partition is available.
- Quality is the primary gate: strict topology first, then skewness, non-orthogonality, and aspect ratio; requested cell count is secondary and cannot waive a failed quality or authority gate.
- Core validation, incidence reconstruction, quality evaluation, and transaction/rollback logic should be C++23/native. Python remains orchestration and test glue.

## Planned cards

### 042-A — C++23 receipt-locked production ingress

- Mechanism: materialize canonical points/triangles/semantic rows from the sealed receipt, reject caller-array substitution, and expose one explicit production adapter used by the Tet generator.
- Default state: strict route is available only when the receipt is supplied; no legacy output is silently upgraded. Existing unsupported positive-BL inputs remain refusal paths.
- Expected benefit: actual source/output authority and provenance evidence rather than sidecar-only validation.
- Failure/rollback: source hash/digest mismatch, missing/duplicate/extra semantic row, non-manifold/orientation error, or unavailable closed positive-BL partition yields a typed refusal and no publish.

### 042-B — post-generation incidence and atomic commit

- Mechanism: reconstruct face incidence from actual generated Tets, distinguish external incidence 1 from BL/core interface incidence 2, validate exact receipt binding, reread PolyMesh, and atomically publish only after all checks pass.
- Default state: strict transaction route; any mismatch rolls back staged output.
- Expected benefit: proof that the real generator output, not a test fixture, preserves authoritative boundaries and BL interfaces.
- Failure/rollback: extra/missing/mis-bound face, duplicate/non-positive/inverted Tet, writer digest mismatch, or quality threshold failure.

### 042-C — non-cube repeat corpus and BL contract

- Mechanism: run a closed sphere/curved shell or enclosure corpus three times with BL=0, then positive-BL cases only where a real partition exists; record deterministic output and quality distributions.
- Default state: no count tuning until quality/authority gates pass.
- Expected benefit: release evidence across non-cube geometry and repeatability.
- Failure/rollback: open-surface positive-BL input must record `positive_bl_volume_partition_unavailable`; no relabel/count adjustment is allowed.

## Quality and authority gates

- Strict topology: non-manifold, duplicate, and inverted counts are zero; all Tets have positive volume.
- Exact source/shape: canonical source hash, receipt digest, boundary feature/component/physical-group/provenance rows, and output face binding match.
- BL semantics: BL=0 external faces have incidence 1; BL>=1 wall/interface/core rows have the expected incidence and lineage. A positive layer without a valid volume partition is a refusal, not a pass.
- Quality target before count: non-orthogonality p95/max <= 35/50 degrees, skewness p95/max <= 0.25/0.50, aspect ratio p99/max <= 10/20, using the project’s strict definitions and recording measured values.
- Repeatability: three independent runs have identical authoritative receipt/output digests for deterministic routes and no unexplained topology/quality drift.

## Verification ladder

- L0: receipt materialization, tamper refusal, canonical mapping, incidence fixtures, and C++ rollback tests.
- L1: closed authoritative sphere/curved shell BL=0 through the real Native Tet route, staged PolyMesh reread, and three-repeat digest/quality evidence.
- L2: closed non-cube curved enclosure with an actual positive-BL wall/interface/core partition; open hemisphere remains an explicit refusal case.
- L3: release corpus across non-cube Tet inputs with source/feature/physical-group/provenance certificates, strict topology, quality metrics, and packaging/audit records.

## Evidence to preserve

- `literature.md`, `unreadable-dois.md`, this plan, planner id/options/wait diagnostics, exact commands, build/test logs, measured quality/topology/authority values, refusal reasons, and staged/published artifact digests.
- Public-code references are advisory only: fTetWild (MPL-2.0, `src/MeshImprovement.cpp`/tests) and WMTK (MIT, operation/attribute-transfer tests); no code copied or dependency added.
- Do not delete, merge, or remove worktrees/branches; record the audit at finish.
