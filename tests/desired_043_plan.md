# Improvement plan — native-all-production-gate-043

## Goal

043_atomic_stage_reread_commit_and_three_repeat_non_cube_corpus

## Scope and invariants

- Connect the receipt-bound Native Tet route to a private same-filesystem sibling stage; never let the strict route write directly to the final `case_dir` before audit.
- Reread the actual stage PolyMesh/artifact, reconstruct topology/incidence/quality/semantic binding, and compare source/receipt/output digests before publish.
- Preserve exact source geometry, feature/patch/physical-group/component/provenance rows, positive Tet orientation, and deterministic replay.
- BL=0 is the only positive route in this round’s closed tetra/ellipsoid corpus. BL>=1 remains refusal unless an actual closed layer/core partition is available.

## Planned cards

### 043-A — private stage route

- Mechanism: create a private sibling stage on the same filesystem and redirect receipt-bound harness output there; leave final output untouched until the stage audit passes.
- Default state: strict receipt route only; legacy no-receipt route unchanged.
- Expected benefit: failed candidates cannot contaminate final artifacts and can be discarded transactionally.
- Failure/rollback: missing stage, cross-filesystem path, writer failure, or stage contamination refuses without final publish.

### 043-B — C++23 disk reread/audit and atomic commit

- Mechanism: reread staged points/Tets and semantic output, compute exact artifact digest and face incidence, apply strict topology/quality/source gates, then use the existing same-filesystem atomic publish kernel. Preserve backup and exchange back on post-publish reread failure.
- Default state: read-back evidence and publication remain locked until all gates pass; no count tuning can waive a failure.
- Expected benefit: actual writer artifact becomes the authoritative output certificate.
- Failure/rollback: duplicate/non-manifold/inverted/non-positive Tet, wrong incidence, semantic mismatch, digest mismatch, quality failure, or reread failure leaves no accepted publication and records rollback.

### 043-C — three-repeat non-cube corpus

- Mechanism: run a watertight ellipsoid, enclosed/extruded NACA-like shape, and feature-rich closed STL/CAD fixture three times; compare source/receipt/output digests and strict quality matrix.
- Default state: BL=0 first; positive-BL is an explicit refusal where volume partition is unavailable.
- Expected benefit: reproducible non-cube authority and quality evidence.
- Failure/rollback: any topology/authority/quality drift or unexplained digest difference fails the corpus gate.

## Quality and authority gates

- Strict topology: duplicate, non-manifold, inverted, and non-positive Tet counts are zero; every face incidence is valid for its semantic role.
- BL=0 external receipt faces incidence 1 exact one-to-one. BL>=1 requires incidence-1 wall exterior plus incidence-2 layer/core interface and explicit zone lineage.
- Source/output/feature/patch/physical-group/component/provenance rows and canonical/source/output digests match exactly.
- Initial quality caps: non-orthogonality p95/max <= 35/50 degrees, skewness p95/max <= 0.25/0.50, aspect p99/max <= 10/20. Count remains secondary.
- Three independent replays produce identical authoritative artifact digests for deterministic routes.

## Verification ladder

- L0: C++ receipt/stage tamper, digest, topology, and rollback fixtures.
- L1: actual Native Tet closed non-cube BL=0 stage/reread/commit and post-publish reread.
- L2: three-repeat ellipsoid/NACA-like/feature-rich corpus with quality matrix; explicit positive-BL refusal evidence.
- L3: actual positive-BL closed enclosure when wall/interface/core partition is implemented, followed by release packaging audit.

## Evidence to preserve

- `literature.md`, `unreadable-dois.md`, this plan, `measurements.md`, planner transport/options, exact stage paths, artifact digests, incidence/quality/topology values, refusal/rollback reasons, and finish-hook worktree audit.
- Public code references and licenses are advisory only; no external code copied and no dependency added.
- Do not delete, merge, or remove worktrees/branches.
