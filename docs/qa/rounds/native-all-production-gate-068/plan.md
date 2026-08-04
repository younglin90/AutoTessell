# Improvement plan — native-all-production-gate-068

## Goal

native-all-production-gate-068

## Scope and invariants

-

## Planned card

- Mechanism:
- Default state:
- Expected benefit:
- Failure/rollback condition:

## Quality and authority gates

-

## Verification ladder

- L0:
- L1:
- L2:
- L3:

## Evidence to preserve

-

## Planner-completed design gate (068-A)

- Sole planner: agent 019fcdea-7f0a-7730-b562-a9e6a98666f3 (Tesla), explicitly requested `gpt-5.6-terra`, high reasoning, priority, fast OFF. The API has no separate fast field; the long wait was retained and the agent was closed only after completed output. No code was changed by the planner.
- Card: `NativeTetVolumeArtifactV1`, default OFF / `EXPERIMENTAL_KEEP`.
- Replace the BL=0 early return in `native_tet_bl_writer_bind.cpp` with a non-empty persisted `polyMesh` artifact. Emit `actual_layers=0`, `layer_work=0`, empty BL rows, exact source-wall identity, artifact/tree/source/semantic/BL/policy/UID/lineage digests, and a native independent reader that reconstructs from disk only.
- Parameter receipt: for BL=0/1/3/8, record requested layer count, `h0`, `g`, derived `h_k=h0*g^(k-1)`, total `H_N=h0*(g^N-1)/(g-1)` or `N*h0` when `g=1`, and disk residuals. No parameter is silently rewritten.
- Quality gates: source authority first; duplicate/non-manifold/inverted/degenerate/unaccounted boundary all zero; positive volume, scaled Jacobian, minimum dihedral, mean ratio, radius-edge, non-orthogonality, skewness, aspect distributions; collision/clearance before narrow-gap/T-junction promotion.
- Corpus ladder: L0 one tetra/one-wall-prism persisted artifacts; L1 cube/sphere/regular-tetra CAD/STL at BL=0/1/3/8; L2 eight source families × 19 configurations × three fresh-process replays; L3 permanent release matrix with isolated reread, byte identity, and tamper tests.
- Blockers: no native BL=0 persisted volume writer/independent reader yet; reviewed CAD physical/wall mapping and OCCT ABI are unavailable. Do not use XDE display metadata as semantic authority or Python parsing as independent reread.
