# Improvement plan — native-all-production-gate-071

## Goal

native-all-production-gate-071

## Scope and invariants

- Close the round-070 synthetic-receipt gap by connecting a real STL byte
  source to the independent Native Tet receipt/child route.
- Keep the Tet product distinct from Native Tri; only canonicalization may be
  reused.
- Accept BL=0 only in this card. BL>=1 remains an explicit refusal until
  writer-owned positive-layer geometry and a complete ledger exist.

## Planned card — 071-A actual STL authority ingress to Native Tet

- Mechanism: validate a regular non-symlink ASCII/binary STL through the
  existing C++ authority ingress, convert canonical points/faces and explicit
  semantic rows into a Tet-specific receipt, then reuse the actual stage,
  fresh-child, atomic-publish, and destination-child route.
- Default state: opt-in only; ordinary Tet and fallback routes are unchanged.
- Expected benefit: source bytes, canonical geometry, topology, semantic
  groups, and persisted Tet output become independently attributable.
- Failure/rollback condition: any source, certificate, ledger, quality, or
  topology mismatch refuses before publish and preserves the destination.

### Implementation files

- `auto_tessell_core/native_tri_cad_stl_authority_ingress_bind.cpp`
- `core/generator/native_tet/stl_authority_ingress.py`
- `core/generator/tier_native_tet.py`
- `core/generator/native_tet/receipt_stage.py`
- `auto_tessell_core/native_tet_surface_boundary_receipt_consumer_bind.cpp`

## Quality and authority gates

- Source raw SHA/byte count, canonical geometry SHA, and explicit
  feature/patch/physical-group/component/provenance rows are mandatory.
- Source and persisted duplicate/non-manifold/open/inverted counts are zero;
  every Tet volume is positive.
- Sealed quality policy remains max non-orthogonality <=50 degrees,
  skewness <=0.50, aspect ratio <=20. Quality failure is honest refusal.
- BL=0 records requested=actual=0 and pre/post identity. Positive BL is
  refused without exact writer geometry and ledger.
- Cell count is diagnostic only and cannot override quality or authority.

## Verification ladder and acceptance/refusal matrix

- L0: ASCII/binary tetra STL; source digest, semantic ledger, symlink,
  canonical-face-order, and source-byte tamper refusal.
- L1: registered cube STL through C++ authority, actual Tet harness, stage
  child, atomic publish, and destination child.
- L2: sphere and NACA STL measurement-only replays; topology/source failures
  are regressions and quality failures remain explicit known limitations.
- L3: no release promotion; keep experimental/default-off until three-source
  quality and authority evidence is complete.

## Evidence to preserve

- planner review and source URLs/commits;
- source/canonical/semantic/certificate digests;
- three independent replay manifests and quality metrics;
- all refusals, rollback state, BL=0 identity, and positive-BL refusal.
# Improvement plan — native-all-production-gate-071

## Goal

native-all-production-gate-071

## Scope and invariants

- Close the round-070 synthetic-receipt gap by connecting a real STL byte
  source to the independent Native Tet receipt/child route.
- Keep the Tet product distinct from Native Tri; only canonicalization may be
  reused.
- Accept BL=0 only in this card. BL>=1 remains an explicit refusal until
  writer-owned positive-layer geometry and a complete ledger exist.

## Planned card — 071-A actual STL authority ingress to Native Tet

- Mechanism: validate a regular non-symlink ASCII/binary STL through the
  existing C++ authority ingress, convert canonical points/faces and explicit
  semantic rows into a Tet-specific receipt, then reuse the actual stage,
  fresh-child, atomic-publish, and destination-child route.
- Default state: opt-in only; ordinary Tet and fallback routes are unchanged.
- Expected benefit: source bytes, canonical geometry, topology, semantic
  groups, and persisted Tet output become independently attributable.
- Failure/rollback condition: any source, certificate, ledger, quality, or
  topology mismatch refuses before publish and preserves the destination.

### Implementation files

- `auto_tessell_core/native_tri_cad_stl_authority_ingress_bind.cpp`
- `core/generator/native_tet/stl_authority_ingress.py`
- `core/generator/tier_native_tet.py`
- `core/generator/native_tet/receipt_stage.py`
- `auto_tessell_core/native_tet_surface_boundary_receipt_consumer_bind.cpp`

## Quality and authority gates

- Source raw SHA/byte count, canonical geometry SHA, and explicit
  feature/patch/physical-group/component/provenance rows are mandatory.
- Source and persisted duplicate/non-manifold/open/inverted counts are zero;
  every Tet volume is positive.
- Sealed quality policy remains max non-orthogonality <=50 degrees,
  skewness <=0.50, aspect ratio <=20. Quality failure is honest refusal.
- BL=0 records requested=actual=0 and pre/post identity. Positive BL is
  refused without exact writer geometry and ledger.
- Cell count is diagnostic only and cannot override quality or authority.

## Verification ladder and acceptance/refusal matrix

- L0: ASCII/binary tetra STL; source digest, semantic ledger, symlink,
  canonical-face-order, and source-byte tamper refusal.
- L1: registered cube STL through C++ authority, actual Tet harness, stage
  child, atomic publish, and destination child.
- L2: sphere and NACA STL measurement-only replays; topology/source failures
  are regressions and quality failures remain explicit known limitations.
- L3: no release promotion; keep experimental/default-off until three-source
  quality and authority evidence is complete.

## Evidence to preserve

- planner review and source URLs/commits;
- source/canonical/semantic/certificate digests;
- three independent replay manifests and quality metrics;
- all refusals, rollback state, BL=0 identity, and positive-BL refusal.
