# Measurements — native-all-production-gate-068

## Build and focused validation

- CMake targets built: `native_transaction_executor`, `native_surface_bl_strip_writer`, `native_tet_bl_writer`, `native_tet_bl_authoritative_graph`, and `native_tet_persisted_volume_artifact`.
- Focused regression: **31 passed** in 3.57 s.
- New persisted-reader tests: **3 passed**; schedule-input test: **1 passed**.
- The existing Tet writer still reports two pre-existing signed/unsigned warnings in `generate_authoritative`; the new reader target builds without warnings after removing its unused helper and fixing the size comparison.

## BL and persisted artifact matrix

| Route | BL | Source of candidate | Independent reread | AQTE publish | Result |
| --- | ---: | --- | --- | --- | --- |
| Surface identity | 0 | C++ surface writer | deterministic writer rerun + canonical disk candidate | PASS | PASS |
| Surface strip | 1 | C++ surface wall-edge writer | deterministic writer rerun + canonical disk candidate | PASS | PASS |
| Tet prism bridge | 1 | C++ Tet writer + graph artifact | deterministic writer rerun + canonical disk candidate | PASS | PASS |
| Tet persisted volume | 0 | native C++ persisted `polyMesh` reader exposed by Tet writer API | fresh native disk reread | PASS | PASS (tetra fixture) |

## Quality/topology/authority evidence

- Persisted BL=0 tetra: `duplicate=0`, `non_manifold=0`, `inverted=0`, positive cell measure, `tet_dihedral` family witness, source boundary coverage exact, one cell UID and one semantic lineage row.
- Persisted reader refuses missing source boundary coverage before creating a publication candidate.
- Surface and Tet actual routes retain the prior strict topology and feature/patch/physical-group/component/provenance gates.
- Schedule inputs are explicit for BL=0/1/3/8; `h0=0.07`, `g=1.2` produced the formula `H_N=h0*(g^N-1)/(g-1)` and the returned `total_thickness` matched the disk-independent generated points.

## Known limits

- The persisted reader is now native and independent from producer arrays, but the current release corpus uses a tetra fixture. Full mesher-produced cube/sphere/NACA/CAD/STL persisted artifacts and three fresh-process replays remain open.
- No positive-BL narrow-gap/T-junction promotion is claimed without collision/clearance evidence.
